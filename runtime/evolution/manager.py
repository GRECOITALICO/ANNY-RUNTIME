"""Durable, reversible runtime evolution primitives inspired by Citizen.

The manager intentionally stops before replacing the running executable. It stages and
verifies an artifact, records the pending transaction, then exposes an explicit commit
step for a supervisor/updater process. This keeps update authority separate from
release verification and Fabric admission.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from .verifier import ReleaseDescriptor, ReleaseVerifier


class EvolutionError(RuntimeError):
    pass


class RuntimeEvolutionManager:
    """Prepare, verify, commit, and roll back runtime artifacts."""

    def __init__(self, data_dir: str):
        self.root = Path(data_dir) / "evolution"
        self.staging = self.root / "staging"
        self.backups = self.root / "backups"
        self.history_path = self.root / "history.jsonl"
        self.staging.mkdir(parents=True, exist_ok=True)
        self.backups.mkdir(parents=True, exist_ok=True)

    def prepare(self, descriptor: Dict[str, Any], artifact_path: str, verifier: ReleaseVerifier) -> Dict[str, Any]:
        """Verify and atomically stage an artifact without changing the running runtime."""
        parsed: ReleaseDescriptor = verifier.verify_descriptor(descriptor)
        source = Path(artifact_path)
        if not source.is_file():
            raise EvolutionError("artifact does not exist")
        if not verifier.verify_artifact(parsed, source):
            raise EvolutionError("artifact sha256 mismatch")

        txn = uuid.uuid4().hex
        target = self.staging / f"{txn}-{source.name}"
        fd, temp_name = tempfile.mkstemp(prefix=f"{txn}-", dir=self.staging)
        os.close(fd)
        try:
            shutil.copy2(source, temp_name)
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

        record = {
            "transaction_id": txn,
            "status": "VERIFIED_STAGED",
            "version": parsed.version,
            "artifact_sha256": parsed.artifact_sha256,
            "staged_path": str(target),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._append_history(record)
        return record

    def commit(self, transaction_id: str, install_path: str) -> Dict[str, Any]:
        """Atomically replace a single runtime artifact, keeping a backup for rollback."""
        record = self._find(transaction_id)
        if record is None or record.get("status") != "VERIFIED_STAGED":
            raise EvolutionError("transaction is not ready to commit")
        staged = Path(record["staged_path"])
        if not staged.is_file():
            raise EvolutionError("staged artifact is missing")

        target = Path(install_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = self.backups / f"{transaction_id}.bak"
        if target.exists():
            shutil.copy2(target, backup)
        os.replace(staged, target)

        committed = {**record, "status": "COMMITTED", "install_path": str(target), "backup_path": str(backup)}
        self._append_history(committed)
        return committed

    def rollback(self, transaction_id: str) -> Dict[str, Any]:
        record = self._find_last(transaction_id, "COMMITTED")
        if record is None:
            raise EvolutionError("no committed transaction available for rollback")
        backup = Path(record.get("backup_path", ""))
        target = Path(record.get("install_path", ""))
        if not backup.is_file() or not target:
            raise EvolutionError("rollback backup is unavailable")
        os.replace(backup, target)
        rolled_back = {**record, "status": "ROLLED_BACK", "rolled_back_at": datetime.now(timezone.utc).isoformat()}
        self._append_history(rolled_back)
        return rolled_back

    def _append_history(self, record: Dict[str, Any]) -> None:
        with open(self.history_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _read_history(self):
        if not self.history_path.exists():
            return []
        rows = []
        with open(self.history_path, "r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    def _find_last(self, transaction_id: str, status: str):
        for item in reversed(self._read_history()):
            if item.get("transaction_id") == transaction_id and item.get("status") == status:
                return item
        return None

    def _find(self, transaction_id: str):
        for item in reversed(self._read_history()):
            if item.get("transaction_id") == transaction_id:
                return item
        return None
