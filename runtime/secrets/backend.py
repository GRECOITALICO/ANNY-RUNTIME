import abc
import os
import hashlib
import hmac
from pathlib import Path
from typing import List, Optional
import re
import base64
from cryptography.fernet import Fernet, InvalidToken
from runtime.security.execution_context import ExecutionContext

class SecretBackend(abc.ABC):
    @abc.abstractmethod
    def store(self, reference: str, value: bytes) -> bool:
        pass

    @abc.abstractmethod
    def retrieve(self, reference: str) -> Optional[bytes]:
        pass

    @abc.abstractmethod
    def delete(self, reference: str) -> bool:
        pass

    @abc.abstractmethod
    def exists(self, reference: str) -> bool:
        pass

    @abc.abstractmethod
    def list_references(self) -> List[str]:
        pass

class FileSecretBackend(SecretBackend):
    """File-based encrypted secret backend."""
    def __init__(self, data_dir: str, master_key: bytes) -> None:
        self.secrets_dir = Path(data_dir) / "secrets"
        self.secrets_dir.mkdir(parents=True, exist_ok=True)
        
        if len(master_key) == 32:
            derived_key = master_key
        else:
            derived_key = hashlib.sha256(master_key).digest()
            
        self._fernet_key = base64.urlsafe_b64encode(derived_key)
        self._fernet = Fernet(self._fernet_key)

    def _safe_reference(self, reference: str) -> Path:
        if not re.match(r'^[\w\-\.]+$', reference):
            raise ValueError("UNSAFE_REFERENCE")
        path = (self.secrets_dir / reference).resolve()
        if not str(path).startswith(str(self.secrets_dir.resolve())):
            raise ValueError("UNSAFE_REFERENCE")
        return path

    def _encrypt(self, value: bytes) -> bytes:
        return self._fernet.encrypt(value)

    def _decrypt(self, encrypted: bytes) -> Optional[bytes]:
        try:
            return self._fernet.decrypt(encrypted)
        except InvalidToken:
            return None

    def store(self, reference: str, value: bytes) -> bool:
        path = self._safe_reference(reference)
        encrypted = self._encrypt(value)
        with open(path, "wb") as f:
            f.write(encrypted)
        os.chmod(path, 0o600)
        return True

    def retrieve(self, reference: str) -> Optional[bytes]:
        path = self._safe_reference(reference)
        if not path.exists():
            return None
        with open(path, "rb") as f:
            encrypted = f.read()
        return self._decrypt(encrypted)

    def delete(self, reference: str) -> bool:
        path = self._safe_reference(reference)
        if path.exists():
            path.unlink()
            return True
        return False

    def exists(self, reference: str) -> bool:
        return self._safe_reference(reference).exists()

    def list_references(self) -> List[str]:
        return [p.name for p in self.secrets_dir.iterdir() if p.is_file()]

class SecureBroker(SecretBackend):
    def __init__(self, backend: SecretBackend, context: ExecutionContext, tenant_id: str) -> None:
        self.backend = backend
        self.context = context
        self.tenant_id = tenant_id

    def _check_access(self):
        if not self.context.has_capability("SECRET_USE"):
            raise PermissionError("Missing SECRET_USE capability")
        if self.context.tenant_id != self.tenant_id:
            raise PermissionError("Tenant scope mismatch")

    def store(self, reference: str, value: bytes) -> bool:
        self._check_access()
        return self.backend.store(reference, value)

    def retrieve(self, reference: str) -> Optional[bytes]:
        self._check_access()
        return self.backend.retrieve(reference)

    def delete(self, reference: str) -> bool:
        self._check_access()
        return self.backend.delete(reference)

    def exists(self, reference: str) -> bool:
        self._check_access()
        return self.backend.exists(reference)

    def list_references(self) -> List[str]:
        self._check_access()
        return self.backend.list_references()
