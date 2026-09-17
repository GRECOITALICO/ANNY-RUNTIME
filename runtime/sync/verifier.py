"""Candidate verification for ANNY Runtime Sync."""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.request
import urllib.error
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

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
    """Verifies discovered candidates against a cryptographic proof/provenance."""

    def __init__(self, expected_digest: Optional[str] = None):
        """Initialize the verifier.
        
        Args:
            expected_digest: Optional expected SHA-256 digest (e.g. from a known secure side-channel
                             or test fixture). In a production environment, this might be loaded
                             from an attached signature file.
        """
        self.expected_digest = expected_digest

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

            # Look for an asset to verify
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
