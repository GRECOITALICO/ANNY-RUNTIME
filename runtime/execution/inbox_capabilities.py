"""Bounded deterministic capabilities used by the GitHub inbox worker.

These helpers deliberately accept only a configured Downloads directory.  They
never infer a fallback directory and never follow a file symlink.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path
from typing import Any, Dict


MAX_TEXT_BYTES = 16 * 1024
_SIMPLE_TEXT_NAME = re.compile(r"^[^/\\.][^/\\]*\.txt$")


class InboxCapabilityError(ValueError):
    """A normalized, non-sensitive inbox-capability rejection."""


def _xdg_downloads_root() -> str:
    """Read only the standard XDG Downloads declaration; never guess a path."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    definition = config_home / "user-dirs.dirs"
    try:
        text = definition.read_text(encoding="utf-8")
    except OSError as exc:
        raise InboxCapabilityError("DOWNLOADS_ROOT_NOT_CONFIGURED") from exc
    match = re.search(r'^XDG_DOWNLOAD_DIR="([^"]+)"\s*$', text, re.MULTILINE)
    if not match:
        raise InboxCapabilityError("DOWNLOADS_ROOT_NOT_CONFIGURED")
    value = match.group(1).replace("${HOME}", str(Path.home())).replace("$HOME", str(Path.home()))
    if "$" in value:
        raise InboxCapabilityError("DOWNLOADS_ROOT_INVALID")
    return value


def resolve_downloads_root(configured_root: str | None) -> Path:
    """Resolve configured or XDG-declared Downloads root, otherwise fail closed."""
    configured = configured_root.strip() if isinstance(configured_root, str) else ""
    candidate = Path(configured or _xdg_downloads_root()).expanduser()
    try:
        root = candidate.resolve(strict=True)
    except OSError as exc:
        raise InboxCapabilityError("DOWNLOADS_ROOT_UNAVAILABLE") from exc
    if not root.is_dir() or root.is_symlink():
        raise InboxCapabilityError("DOWNLOADS_ROOT_INVALID")
    return root


def _relative_text_name(value: Any) -> str:
    if not isinstance(value, str) or not _SIMPLE_TEXT_NAME.fullmatch(value):
        raise InboxCapabilityError("INVALID_RELATIVE_TEXT_NAME")
    if value in {".", ".."} or ".." in value:
        raise InboxCapabilityError("INVALID_RELATIVE_TEXT_NAME")
    return value


def validate_relative_text_name(value: Any) -> str:
    """Public contract-level validation for the single-file read capability."""
    return _relative_text_name(value)


def list_text_files(configured_root: str | None) -> Dict[str, Any]:
    root = resolve_downloads_root(configured_root)
    entries = []
    try:
        with os.scandir(root) as directory:
            for entry in directory:
                if entry.is_symlink() or not entry.name.endswith(".txt"):
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if stat.S_ISREG(info.st_mode):
                    entries.append({"name": entry.name, "size_bytes": info.st_size})
    except OSError as exc:
        raise InboxCapabilityError("DOWNLOADS_LIST_FAILED") from exc
    return {"files": sorted(entries, key=lambda item: item["name"])}


def read_text_file(configured_root: str | None, relative_path: Any, max_bytes: Any) -> Dict[str, Any]:
    root = resolve_downloads_root(configured_root)
    name = _relative_text_name(relative_path)
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or not 1 <= max_bytes <= MAX_TEXT_BYTES:
        raise InboxCapabilityError("INVALID_MAX_BYTES")
    target = root / name
    # O_NOFOLLOW makes the final component fail closed when it is a symlink.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
    except FileNotFoundError as exc:
        raise InboxCapabilityError("TEXT_FILE_NOT_FOUND") from exc
    except OSError as exc:
        raise InboxCapabilityError("TEXT_FILE_OPEN_DENIED") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise InboxCapabilityError("TEXT_FILE_NOT_REGULAR")
        if info.st_size > max_bytes:
            raise InboxCapabilityError("TEXT_FILE_TOO_LARGE")
        chunks = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(4096, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > max_bytes:
            raise InboxCapabilityError("TEXT_FILE_TOO_LARGE")
    finally:
        os.close(descriptor)
    try:
        content = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise InboxCapabilityError("TEXT_FILE_NOT_UTF8") from exc
    return {
        "relative_path": name,
        "content": content,
        "encoding": "utf-8",
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
