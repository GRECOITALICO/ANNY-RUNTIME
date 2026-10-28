"""Registered, bounded local-access helpers for the GitHub inbox.

All host access is delegated to :mod:`local_access`; this module keeps the
deterministic executor independent from configuration parsing details.
"""
from __future__ import annotations

from typing import Any, Dict

from runtime.execution.local_access import (
    MAX_HASH_BYTES,
    MAX_LIST_ENTRIES,
    MAX_TEXT_BYTES,
    LocalAccessError,
    LocalAccessPolicy,
)


InboxCapabilityError = LocalAccessError


def build_local_access_policy(configured_roots: Any) -> LocalAccessPolicy:
    return LocalAccessPolicy.from_config(configured_roots)


def list_local_directory(policy: LocalAccessPolicy, root_id: Any, relative_path: Any, max_entries: Any) -> Dict[str, Any]:
    return policy.list_directory(root_id, relative_path, max_entries)


def read_local_text(policy: LocalAccessPolicy, root_id: Any, relative_path: Any, max_bytes: Any) -> Dict[str, Any]:
    return policy.read_text(root_id, relative_path, max_bytes)


def inspect_local_file(policy: LocalAccessPolicy, root_id: Any, relative_path: Any) -> Dict[str, Any]:
    return policy.inspect(root_id, relative_path)


def hash_local_file(policy: LocalAccessPolicy, root_id: Any, relative_path: Any, max_bytes: Any) -> Dict[str, Any]:
    return policy.hash_file(root_id, relative_path, max_bytes)
