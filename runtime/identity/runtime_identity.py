import os
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from contracts.identifiers import generate_id
from contracts.protocol import PROTOCOL_VERSION

class RuntimeIdentity:
    """
    Represents the cryptographic identity and baseline configuration of the Runtime.
    Handles signing operations and persistence of the public/private key pairs.
    """
    
    def __init__(self, runtime_id: str, installation_id: str, private_key: bytes, public_key: str, 
                 platform: str, runtime_version: str, protocol_version: str, generation: int, created_at: str):
        self.runtime_id = runtime_id
        self.installation_id = installation_id
        self._private_key = private_key
        self.public_key = public_key
        self.platform = platform
        self.runtime_version = runtime_version
        self.protocol_version = protocol_version
        self.generation = generation
        self.created_at = created_at

    @classmethod
    def generate(cls, platform: str = "linux") -> "RuntimeIdentity":
        """
        Generate a new RuntimeIdentity with a fresh cryptographic key pair.
        Uses Ed25519 for secure digital signatures.
        """
        private_key_obj = Ed25519PrivateKey.generate()
        private_key = private_key_obj.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        public_key = private_key_obj.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        ).hex()
        
        return cls(
            runtime_id=generate_id("RT"),
            installation_id=generate_id("INST"),
            private_key=private_key,
            public_key=public_key,
            platform=platform,
            runtime_version="0.1.0",
            protocol_version=PROTOCOL_VERSION,
            generation=1,
            created_at=datetime.now(timezone.utc).isoformat()
        )

    def save(self, data_dir: str) -> None:
        """
        Persists the identity to disk. The public fields go to runtime_identity.json,
        and the private key to a securely permissioned private_key.pem.
        """
        path = Path(data_dir)
        identity_dir = path / "identity"
        identity_dir.mkdir(parents=True, exist_ok=True)
        
        public_data = self.public_manifest()
        
        with open(identity_dir / "runtime_identity.json", "w") as f:
            json.dump(public_data, f, indent=2)
            
        priv_path = identity_dir / "private_key.pem"
        with open(priv_path, "wb") as f:
            f.write(self._private_key)
        # Ensure 0600 permissions
        os.chmod(priv_path, 0o600)

    @classmethod
    def load(cls, data_dir: str) -> "RuntimeIdentity":
        """
        Load an existing RuntimeIdentity from disk.
        """
        path = Path(data_dir) / "identity"
        with open(path / "runtime_identity.json", "r") as f:
            data = json.load(f)
            
        with open(path / "private_key.pem", "rb") as f:
            private_key = f.read()
            
        return cls(
            runtime_id=data["runtime_id"],
            installation_id=data["installation_id"],
            private_key=private_key,
            public_key=data["public_key"],
            platform=data["platform"],
            runtime_version=data["runtime_version"],
            protocol_version=data["protocol_version"],
            generation=data["generation"],
            created_at=data["created_at"]
        )

    def public_manifest(self) -> Dict[str, Any]:
        """
        Return the public fields only, safe for exposure.
        """
        return {
            "runtime_id": self.runtime_id,
            "installation_id": self.installation_id,
            "public_key": self.public_key,
            "platform": self.platform,
            "runtime_version": self.runtime_version,
            "protocol_version": self.protocol_version,
            "generation": self.generation,
            "created_at": self.created_at
        }
        
    def sign(self, message: bytes) -> bytes:
        """
        Sign a message using the private key.
        Uses Ed25519.
        """
        private_key_obj = serialization.load_pem_private_key(self._private_key, password=None)
        return private_key_obj.sign(message)

    def verify(self, message: bytes, signature: bytes) -> bool:
        """
        Verify a signed message.
        """
        try:
            public_key_bytes = bytes.fromhex(self.public_key)
            public_key_obj = Ed25519PublicKey.from_public_bytes(public_key_bytes)
            public_key_obj.verify(signature, message)
            return True
        except (InvalidSignature, ValueError):
            return False
