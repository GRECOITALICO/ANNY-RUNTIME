"""Candidate verification for ANNY Runtime Sync."""

from __future__ import annotations

import hashlib
import ast
import io
import json
import logging
import re
import tarfile
import urllib.request
import urllib.error
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Optional

from .models import CandidateIdentity, VerificationState

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    status: VerificationState
    candidate_identity: Optional[CandidateIdentity] = None
    digest_algorithm: Optional[str] = None
    digest: Optional[str] = None
    proof_reference: Optional[str] = None
    verifier_identity: str = "CandidateVerifier/1.0"
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verified": self.status == VerificationState.VERIFIED,
            "status": self.status.value,
            "candidate_identity": self.candidate_identity.to_dict() if self.candidate_identity else None,
            "digest_algorithm": self.digest_algorithm,
            "digest": self.digest,
            "proof_reference": self.proof_reference,
            "verifier_identity": self.verifier_identity,
            "error": self.error,
        }


class CandidateVerifier:
    """Verifies discovered candidates against a cryptographic proof/provenance.

    Generic byte verification is intentionally distinct from strict Runtime
    release verification. A Runtime release requires a filename, embedded
    metadata, full source commit, expected digest, and an external commit
    resolver; a digest alone never turns it into an applicable update.
    """

    def __init__(
        self,
        expected_digest: Optional[str] = None,
        *,
        source_commit_resolver: Optional[Callable[[str], Optional[str]]] = None,
    ):
        """Initialize the verifier.
        
        Args:
            expected_digest: Optional expected SHA-256 digest (e.g. from a known secure side-channel
                             or test fixture). In a production environment, this might be loaded
                             from an attached signature file.
        """
        self.expected_digest = expected_digest
        self.source_commit_resolver = source_commit_resolver

    def _fetch_bytes(self, url: str) -> bytes:
        """Fetch bytes from a URL.
        
        A real implementation would support chunking, large files, and timeouts.
        This provides the minimum testable boundary for fetching an artifact.
        """
        req = urllib.request.Request(url, headers={'User-Agent': 'ANNY-Runtime-Verifier/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read()

    def verify(self, discovered: Dict[str, Any], trace_id: str, candidate_bytes: Optional[bytes] = None) -> VerificationResult:
        """Verify the candidate artifact.
        
        If candidate_bytes is not provided, this attempts to download the first available asset
        from the discovered payload. If no asset is found or no proof is available, it fails closed.
        """
        try:
            source = discovered.get("source", "UNKNOWN")
            candidate_version = discovered.get("candidate_version")
            release_id = str(discovered.get("release_id")) if discovered.get("release_id") else None

            if not candidate_version:
                return VerificationResult(
                    status=VerificationState.INVALID,
                    error="MISSING_CANDIDATE_VERSION"
                )

            identity = CandidateIdentity(
                source=source,
                candidate_version=candidate_version,
                trace_id=trace_id,
                release_id=release_id
            )

            if not self.expected_digest:
                return VerificationResult(
                    status=VerificationState.MISSING_PROOF,
                    candidate_identity=identity,
                    error="NO_PROVENANCE_AVAILABLE"
                )

            # Look for an asset to verify. A strict Runtime release may carry
            # the artifact identity directly in authoritative metadata.
            assets = discovered.get("assets", [])
            asset_to_verify = assets[0] if assets else None
            
            if asset_to_verify:
                identity.artifact_name = asset_to_verify.get("name")
                identity.artifact_size = asset_to_verify.get("size")
                download_url = asset_to_verify.get("browser_download_url")
                
                if not candidate_bytes and download_url:
                    try:
                        candidate_bytes = self._fetch_bytes(download_url)
                    except Exception as e:
                        return VerificationResult(
                            status=VerificationState.ERROR,
                            candidate_identity=identity,
                            error=f"ARTIFACT_DOWNLOAD_FAILED: {e}"
                        )

            if not identity.artifact_name:
                identity.artifact_name = discovered.get("artifact_name")
            
            if not candidate_bytes:
                return VerificationResult(
                    status=VerificationState.ERROR,
                    candidate_identity=identity,
                    error="NO_CANDIDATE_BYTES_AVAILABLE"
                )

            # Hash actual candidate bytes
            hasher = hashlib.sha256()
            hasher.update(candidate_bytes)
            computed_digest = hasher.hexdigest()
            
            identity.content_digest = computed_digest
            
            if computed_digest != self.expected_digest:
                return VerificationResult(
                    status=VerificationState.INVALID,
                    candidate_identity=identity,
                    digest_algorithm="sha256",
                    digest=computed_digest,
                    error="CHECKSUM_MISMATCH"
                )

            if discovered.get("candidate_kind") == "RUNTIME_RELEASE":
                identity_error = self._validate_runtime_release_identity(
                    discovered, candidate_bytes, identity
                )
                if identity_error:
                    return VerificationResult(
                        status=VerificationState.INVALID,
                        candidate_identity=identity,
                        digest_algorithm="sha256",
                        digest=computed_digest,
                        error=identity_error,
                    )
                
            return VerificationResult(
                status=VerificationState.VERIFIED,
                candidate_identity=identity,
                digest_algorithm="sha256",
                digest=computed_digest,
                proof_reference=f"expected_digest:{self.expected_digest}"
            )

        except Exception as exc:
            logger.exception("Verifier encountered an unhandled exception")
            return VerificationResult(
                status=VerificationState.ERROR,
                error=f"VERIFIER_EXCEPTION: {type(exc).__name__}"
            )

    def _validate_runtime_release_identity(
        self,
        discovered: Dict[str, Any],
        candidate_bytes: bytes,
        identity: CandidateIdentity,
    ) -> Optional[str]:
        """Return a fail-closed reason unless a Runtime archive identity agrees."""
        filename = identity.artifact_name
        source_commit = discovered.get("source_commit")
        if not isinstance(filename, str) or not isinstance(source_commit, str):
            return "RELEASE_IDENTITY_METADATA_MISSING"
        name_match = re.fullmatch(
            r"ANNY-RUNTIME-v([0-9]+(?:\.[0-9]+)*)-([0-9a-f]{7,40})\.tar\.gz",
            filename,
        )
        if not name_match:
            return "RELEASE_FILENAME_INVALID"
        if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
            return "SOURCE_COMMIT_INVALID"
        if not source_commit.startswith(name_match.group(2)):
            return "FILENAME_SOURCE_COMMIT_MISMATCH"
        if self.source_commit_resolver is None:
            return "SOURCE_COMMIT_RESOLVER_UNAVAILABLE"
        resolved = self.source_commit_resolver(source_commit)
        if resolved != source_commit:
            return "SOURCE_COMMIT_UNRESOLVABLE"
        try:
            with tarfile.open(fileobj=io.BytesIO(candidate_bytes), mode="r:gz") as archive:
                members = [
                    member for member in archive.getmembers()
                    if member.name.endswith("/runtime/core/version.py")
                ]
                if len(members) != 1:
                    return "EMBEDDED_VERSION_METADATA_MISSING"
                stream = archive.extractfile(members[0])
                if stream is None:
                    return "EMBEDDED_VERSION_METADATA_MISSING"
                metadata = self._literal_assignments(stream.read().decode("utf-8"))
        except (OSError, tarfile.TarError, UnicodeDecodeError, SyntaxError):
            return "RELEASE_ARTIFACT_INVALID"
        if metadata.get("__version__") != name_match.group(1):
            return "ARTIFACT_VERSION_MISMATCH"
        if metadata.get("__version__") != identity.candidate_version.removeprefix("v"):
            return "CANDIDATE_VERSION_MISMATCH"
        if metadata.get("__commit__") != source_commit:
            return "EMBEDDED_SOURCE_COMMIT_MISMATCH"
        if metadata.get("__commit__") in {"dev", "unknown", "HEAD"}:
            return "EMBEDDED_SOURCE_COMMIT_INVALID"
        if metadata.get("__build_time__") in {None, "", "unknown"}:
            return "BUILD_TIME_INVALID"
        return None

    @staticmethod
    def _literal_assignments(source: str) -> Dict[str, str]:
        values: Dict[str, str] = {}
        for node in ast.parse(source).body:
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                values[node.targets[0].id] = node.value.value
        return values
