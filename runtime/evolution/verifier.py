"""Release/evolution verification for ANNY Runtime.

Release trust is separate from Runtime identity and Repository Fabric trust.
The runtime only needs the public verification key; private signing material must
stay outside the installed runtime.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


@dataclass(frozen=True)
class ReleaseDescriptor:
    version: str
    artifact: str
    artifact_sha256: str
    runtime_version: str
    compatibility: str
    signing_key_id: str
    signature: str

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "ReleaseDescriptor":
        required = (
            "version", "artifact", "artifact_sha256", "runtime_version",
            "compatibility", "signing_key_id", "signature"
        )
        missing = [key for key in required if not value.get(key)]
        if missing:
            raise ValueError(f"release descriptor missing fields: {','.join(missing)}")
        return cls(*(value[key] for key in required))


class ReleaseVerifier:
    """Verify signed release descriptors and artifact integrity."""

    def __init__(self, public_key: Union[str, bytes], signing_key_id: str):
        self.signing_key_id = signing_key_id
        if isinstance(public_key, str):
            value = public_key.strip()
            try:
                raw = bytes.fromhex(value)
            except ValueError:
                raw = base64.b64decode(value)
        else:
            raw = public_key
        self._public_key = Ed25519PublicKey.from_public_bytes(raw)

    @staticmethod
    def canonical_payload(descriptor: Dict[str, Any]) -> bytes:
        unsigned = {key: value for key, value in descriptor.items() if key != "signature"}
        return json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def verify_descriptor(self, descriptor: Dict[str, Any]) -> ReleaseDescriptor:
        parsed = ReleaseDescriptor.from_dict(descriptor)
        if parsed.signing_key_id != self.signing_key_id:
            raise ValueError("unknown release signing key id")
        signature = base64.b64decode(parsed.signature)
        try:
            self._public_key.verify(signature, self.canonical_payload(descriptor))
        except InvalidSignature as exc:
            raise ValueError("invalid release signature") from exc
        return parsed

    @staticmethod
    def sha256_file(path: Union[str, Path]) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def verify_artifact(self, descriptor: ReleaseDescriptor, artifact_path: Union[str, Path]) -> bool:
        return self.sha256_file(artifact_path).lower() == descriptor.artifact_sha256.lower()
