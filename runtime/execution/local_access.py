"""Fail-closed local-root policy used by the GitHub inbox capabilities.

The policy is deliberately data-only: a request selects a registered capability
and a configured root identifier, but it never supplies permissions or a host
path.  It is not a replacement for the Codex sandbox or OS permissions.
"""
from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable


MAX_TEXT_BYTES = 16 * 1024
MAX_HASH_BYTES = 4 * 1024 * 1024
MAX_LIST_ENTRIES = 200
OPERATIONS = frozenset({"read", "list", "inspect", "hash", "write", "create", "move", "delete", "execute"})
_SENSITIVE_SEGMENTS = frozenset({
    ".ssh", ".gnupg", ".aws", ".config", ".tokens", ".netrc", "secrets",
    "secret", "credentials", "credential", "keyring", "keyrings",
})


class LocalAccessError(ValueError):
    """Normalized rejection which is safe to publish to the private inbox."""


@dataclass(frozen=True)
class LocalRoot:
    root_id: str
    path: Path
    operations: frozenset[str]


def _relative_path(value: Any, *, allow_root: bool = False) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise LocalAccessError("LOCAL_PATH_INVALID")
    if value == "." and allow_root:
        return ()
    if value.startswith("/"):
        raise LocalAccessError("LOCAL_PATH_ABSOLUTE_DENIED")
    pieces = tuple(value.split("/"))
    if any(not part or part in {".", ".."} for part in pieces):
        raise LocalAccessError("LOCAL_PATH_TRAVERSAL_DENIED")
    if any(part.lower() in _SENSITIVE_SEGMENTS or part.lower().endswith((".pem", ".key", ".p12", ".pfx")) for part in pieces):
        raise LocalAccessError("LOCAL_PATH_SENSITIVE_DENIED")
    return pieces


class LocalAccessPolicy:
    """Configured roots with separate, non-inheriting operation permissions."""

    def __init__(self, roots: Dict[str, LocalRoot] | None = None):
        self._roots = dict(roots or {})

    @classmethod
    def from_config(cls, raw: Any) -> "LocalAccessPolicy":
        if raw in (None, ""):
            return cls()
        if not isinstance(raw, dict):
            raise LocalAccessError("LOCAL_ROOTS_CONFIG_INVALID")
        roots: Dict[str, LocalRoot] = {}
        for root_id, spec in raw.items():
            if not isinstance(root_id, str) or not root_id or len(root_id) > 64 or not root_id.replace("-", "").replace("_", "").isalnum():
                raise LocalAccessError("LOCAL_ROOT_ID_INVALID")
            if not isinstance(spec, dict) or set(spec) != {"path", "operations"}:
                raise LocalAccessError("LOCAL_ROOT_SPEC_INVALID")
            path, operations = spec.get("path"), spec.get("operations")
            if not isinstance(path, str) or not path or not isinstance(operations, list) or not operations:
                raise LocalAccessError("LOCAL_ROOT_SPEC_INVALID")
            if any(not isinstance(item, str) or item not in OPERATIONS for item in operations):
                raise LocalAccessError("LOCAL_ROOT_OPERATION_INVALID")
            candidate = Path(path).expanduser()
            if not candidate.is_absolute() or candidate.is_symlink() or candidate.name.lower() in _SENSITIVE_SEGMENTS:
                raise LocalAccessError("LOCAL_ROOT_PATH_INVALID")
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise LocalAccessError("LOCAL_ROOT_UNAVAILABLE") from exc
            if not resolved.is_dir() or resolved.is_symlink():
                raise LocalAccessError("LOCAL_ROOT_PATH_INVALID")
            if root_id in roots:
                raise LocalAccessError("LOCAL_ROOT_DUPLICATE")
            roots[root_id] = LocalRoot(root_id, resolved, frozenset(operations))
        return cls(roots)

    def status(self) -> Dict[str, Any]:
        """Return policy evidence without exposing host paths to GitHub."""
        return {
            "configured_roots": [
                {"root_id": root.root_id, "operations": sorted(root.operations)}
                for root in sorted(self._roots.values(), key=lambda item: item.root_id)
            ]
        }

    def _root(self, root_id: Any, operation: str) -> LocalRoot:
        if not isinstance(root_id, str) or root_id not in self._roots:
            raise LocalAccessError("LOCAL_ROOT_NOT_AUTHORIZED")
        root = self._roots[root_id]
        if operation not in root.operations:
            raise LocalAccessError("LOCAL_OPERATION_NOT_AUTHORIZED")
        return root

    @staticmethod
    def _open_root(root: LocalRoot) -> int:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            return os.open(root.path, flags)
        except OSError as exc:
            raise LocalAccessError("LOCAL_ROOT_OPEN_DENIED") from exc

    def _open_parent(self, root: LocalRoot, pieces: tuple[str, ...]) -> tuple[int, str]:
        if not pieces:
            raise LocalAccessError("LOCAL_PATH_INVALID")
        descriptor = self._open_root(root)
        try:
            for piece in pieces[:-1]:
                flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
                next_descriptor = os.open(piece, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor, pieces[-1]
        except OSError as exc:
            os.close(descriptor)
            raise LocalAccessError("LOCAL_PATH_OPEN_DENIED") from exc

    def list_directory(self, root_id: Any, relative_path: Any, max_entries: int) -> Dict[str, Any]:
        root = self._root(root_id, "list")
        pieces = _relative_path(relative_path, allow_root=True)
        if not isinstance(max_entries, int) or isinstance(max_entries, bool) or not 1 <= max_entries <= MAX_LIST_ENTRIES:
            raise LocalAccessError("LOCAL_LIST_LIMIT_INVALID")
        descriptor = self._open_root(root)
        try:
            for piece in pieces:
                next_descriptor = os.open(piece, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
            entries = []
            with os.scandir(descriptor) as directory:
                for entry in directory:
                    if len(entries) >= max_entries:
                        break
                    if entry.name.lower() in _SENSITIVE_SEGMENTS or entry.name.lower().endswith((".pem", ".key", ".p12", ".pfx")):
                        continue
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.S_ISLNK(info.st_mode):
                        continue
                    entries.append({"name": entry.name, "kind": "directory" if stat.S_ISDIR(info.st_mode) else "file" if stat.S_ISREG(info.st_mode) else "other", "size_bytes": info.st_size})
            return {"root_id": root.root_id, "relative_path": relative_path, "entries": sorted(entries, key=lambda item: item["name"])}
        except OSError as exc:
            raise LocalAccessError("LOCAL_LIST_DENIED") from exc
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass

    def _open_regular(self, root_id: Any, relative_path: Any, operation: str) -> tuple[LocalRoot, int, str]:
        root = self._root(root_id, operation)
        pieces = _relative_path(relative_path)
        parent, final_name = self._open_parent(root, pieces)
        try:
            descriptor = os.open(final_name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent)
        except OSError as exc:
            os.close(parent)
            raise LocalAccessError("LOCAL_FILE_OPEN_DENIED") from exc
        os.close(parent)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise LocalAccessError("LOCAL_FILE_NOT_REGULAR")
        except Exception:
            os.close(descriptor)
            raise
        return root, descriptor, "/".join(pieces)

    def read_text(self, root_id: Any, relative_path: Any, max_bytes: Any) -> Dict[str, Any]:
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or not 1 <= max_bytes <= MAX_TEXT_BYTES:
            raise LocalAccessError("LOCAL_READ_LIMIT_INVALID")
        root, descriptor, normalized = self._open_regular(root_id, relative_path, "read")
        try:
            if os.fstat(descriptor).st_size > max_bytes:
                raise LocalAccessError("LOCAL_FILE_TOO_LARGE")
            raw = os.read(descriptor, max_bytes + 1)
            if len(raw) > max_bytes:
                raise LocalAccessError("LOCAL_FILE_TOO_LARGE")
        finally:
            os.close(descriptor)
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise LocalAccessError("LOCAL_FILE_NOT_UTF8") from exc
        return {"root_id": root.root_id, "relative_path": normalized, "content": text, "encoding": "utf-8", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

    def inspect(self, root_id: Any, relative_path: Any) -> Dict[str, Any]:
        root, descriptor, normalized = self._open_regular(root_id, relative_path, "inspect")
        try:
            info = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        return {"root_id": root.root_id, "relative_path": normalized, "kind": "file", "size_bytes": info.st_size, "mode": oct(stat.S_IMODE(info.st_mode)), "mtime": info.st_mtime}

    def hash_file(self, root_id: Any, relative_path: Any, max_bytes: Any) -> Dict[str, Any]:
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or not 1 <= max_bytes <= MAX_HASH_BYTES:
            raise LocalAccessError("LOCAL_HASH_LIMIT_INVALID")
        root, descriptor, normalized = self._open_regular(root_id, relative_path, "hash")
        try:
            if os.fstat(descriptor).st_size > max_bytes:
                raise LocalAccessError("LOCAL_FILE_TOO_LARGE")
            digest, total = hashlib.sha256(), 0
            while True:
                chunk = os.read(descriptor, min(64 * 1024, max_bytes - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise LocalAccessError("LOCAL_FILE_TOO_LARGE")
                digest.update(chunk)
        finally:
            os.close(descriptor)
        return {"root_id": root.root_id, "relative_path": normalized, "algorithm": "sha256", "sha256": digest.hexdigest(), "bytes": total}

    @staticmethod
    def _text_bytes(value: Any) -> bytes:
        if not isinstance(value, str):
            raise LocalAccessError("LOCAL_TEXT_INVALID")
        raw = value.encode("utf-8")
        if len(raw) > MAX_TEXT_BYTES:
            raise LocalAccessError("LOCAL_TEXT_TOO_LARGE")
        return raw

    def create_text(self, root_id: Any, relative_path: Any, content: Any) -> Dict[str, Any]:
        """Create one new regular UTF-8 file; this is not an inbox capability."""
        root = self._root(root_id, "create")
        pieces, raw = _relative_path(relative_path), self._text_bytes(content)
        parent, final_name = self._open_parent(root, pieces)
        try:
            descriptor = os.open(final_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=parent)
            try:
                os.write(descriptor, raw)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except FileExistsError as exc:
            raise LocalAccessError("LOCAL_FILE_ALREADY_EXISTS") from exc
        except OSError as exc:
            raise LocalAccessError("LOCAL_CREATE_DENIED") from exc
        finally:
            os.close(parent)
        return {"root_id": root.root_id, "relative_path": "/".join(pieces), "bytes": len(raw)}

    def write_text(self, root_id: Any, relative_path: Any, content: Any) -> Dict[str, Any]:
        """Replace a pre-existing regular UTF-8 file; this is not an inbox capability."""
        root = self._root(root_id, "write")
        pieces, raw = _relative_path(relative_path), self._text_bytes(content)
        parent, final_name = self._open_parent(root, pieces)
        try:
            descriptor = os.open(final_name, os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent)
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise LocalAccessError("LOCAL_FILE_NOT_REGULAR")
                os.ftruncate(descriptor, 0)
                os.write(descriptor, raw)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError as exc:
            raise LocalAccessError("LOCAL_WRITE_DENIED") from exc
        finally:
            os.close(parent)
        return {"root_id": root.root_id, "relative_path": "/".join(pieces), "bytes": len(raw)}

    def delete_file(self, root_id: Any, relative_path: Any) -> Dict[str, Any]:
        """Delete one regular file after an explicit policy grant; not inbox-exposed."""
        root = self._root(root_id, "delete")
        pieces = _relative_path(relative_path)
        parent, final_name = self._open_parent(root, pieces)
        try:
            info = os.stat(final_name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise LocalAccessError("LOCAL_FILE_NOT_REGULAR")
            os.unlink(final_name, dir_fd=parent)
        except OSError as exc:
            raise LocalAccessError("LOCAL_DELETE_DENIED") from exc
        finally:
            os.close(parent)
        return {"root_id": root.root_id, "relative_path": "/".join(pieces), "deleted": True}

    def move_file(self, root_id: Any, source_path: Any, destination_path: Any) -> Dict[str, Any]:
        """Move a regular file inside one root; cross-root moves are never allowed."""
        root = self._root(root_id, "move")
        source_parts, destination_parts = _relative_path(source_path), _relative_path(destination_path)
        source_parent, source_name = self._open_parent(root, source_parts)
        destination_parent, destination_name = self._open_parent(root, destination_parts)
        try:
            info = os.stat(source_name, dir_fd=source_parent, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise LocalAccessError("LOCAL_FILE_NOT_REGULAR")
            try:
                existing = os.stat(destination_name, dir_fd=destination_parent, follow_symlinks=False)
            except FileNotFoundError:
                existing = None
            if existing is not None:
                raise LocalAccessError("LOCAL_DESTINATION_EXISTS")
            os.rename(source_name, destination_name, src_dir_fd=source_parent, dst_dir_fd=destination_parent)
        except OSError as exc:
            raise LocalAccessError("LOCAL_MOVE_DENIED") from exc
        finally:
            os.close(source_parent)
            os.close(destination_parent)
        return {"root_id": root.root_id, "source_path": "/".join(source_parts), "destination_path": "/".join(destination_parts), "moved": True}
