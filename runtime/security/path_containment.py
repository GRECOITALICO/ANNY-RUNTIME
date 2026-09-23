"""Physical path and resource-scope containment primitives.

Authorization is deliberately split into two checks:

* a resource identity/scope check (which resource, project and tenant); and
* physical containment of a requested path below an authorized root.

Neither check is a substitute for the other.  In particular, this module
never uses a lexical string prefix as an authorization decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class ContainmentResult(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    DENIED = "DENIED"
    INVALID_SCOPE = "INVALID_SCOPE"
    MISSING_WORKSPACE = "MISSING_WORKSPACE"
    MISSING_RESOURCE = "MISSING_RESOURCE"
    OUTSIDE_AUTHORIZED_ROOT = "OUTSIDE_AUTHORIZED_ROOT"
    SYMLINK_ESCAPE = "SYMLINK_ESCAPE"
    CROSS_PROJECT = "CROSS_PROJECT"
    CROSS_TENANT = "CROSS_TENANT"
    UNAUTHORIZED_WRITE = "UNAUTHORIZED_WRITE"


class ContainmentError(ValueError):
    """A fail-closed containment decision with a machine-readable reason."""

    def __init__(self, result: ContainmentResult, detail: str):
        self.result = result
        super().__init__(f"{result.value}: {detail}")


@dataclass(frozen=True)
class PathContainmentDecision:
    authorized_root: str
    requested_path: str
    resolved_path: str
    result: ContainmentResult = ContainmentResult.AUTHORIZED


@dataclass(frozen=True)
class AuthorizedResourceScope:
    """Identity authorization kept distinct from its physical access root."""

    resource_id: str
    project_id: str
    tenant_id: Optional[str]
    authorized_root: str
    access_mode: str = "READ_ONLY"
    resource_kind: str = "EPHEMERAL_WORKSPACE"


def _contains_symlink(path: Path) -> bool:
    """Return whether an extant component of *path* is a symlink.

    ``resolve(strict=False)`` follows every extant component and therefore also
    handles a missing final target.  This scan only improves the rejected
    reason; it is never used to grant access.
    """
    current = Path(path.anchor) if path.is_absolute() else Path()
    for part in path.parts[1:] if path.is_absolute() else path.parts:
        current /= part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def require_contained_path(authorized_root: str, requested_path: str) -> PathContainmentDecision:
    """Resolve a path physically and require it to remain below *authorized_root*.

    Relative paths are evaluated relative to the authorized root, never the
    process CWD.  The root must exist physically.  For a missing target,
    ``Path.resolve(strict=False)`` resolves the longest existing ancestor and
    all symlinks before the structural containment comparison.
    """
    if not isinstance(authorized_root, str) or not authorized_root:
        raise ContainmentError(ContainmentResult.MISSING_WORKSPACE, "authorized root is required")
    if not isinstance(requested_path, str) or not requested_path:
        raise ContainmentError(ContainmentResult.INVALID_SCOPE, "requested path is required")

    try:
        root = Path(authorized_root).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ContainmentError(ContainmentResult.MISSING_WORKSPACE, "authorized root is not physically resolvable") from exc
    if not root.is_dir():
        raise ContainmentError(ContainmentResult.INVALID_SCOPE, "authorized root is not a directory")

    raw = Path(requested_path)
    candidate = raw if raw.is_absolute() else root / raw
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ContainmentError(ContainmentResult.INVALID_SCOPE, "requested path cannot be physically resolved") from exc

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        result = (
            ContainmentResult.SYMLINK_ESCAPE
            if _contains_symlink(candidate)
            else ContainmentResult.OUTSIDE_AUTHORIZED_ROOT
        )
        raise ContainmentError(result, "requested path resolves outside authorized root") from exc

    return PathContainmentDecision(
        authorized_root=str(root),
        requested_path=requested_path,
        resolved_path=str(resolved),
    )


def require_resource_scope(
    scope: Optional[AuthorizedResourceScope],
    *,
    resource_id: Optional[str],
    project_id: str,
    tenant_id: Optional[str],
    operation: str,
) -> AuthorizedResourceScope:
    """Require an identity-scoped resource authorization before path access."""
    if scope is None or not scope.resource_id or not scope.authorized_root:
        raise ContainmentError(ContainmentResult.MISSING_RESOURCE, "authorized resource scope is required")
    if resource_id is not None and resource_id != scope.resource_id:
        raise ContainmentError(ContainmentResult.DENIED, "resource identity is not authorized")
    if project_id != scope.project_id:
        raise ContainmentError(ContainmentResult.CROSS_PROJECT, "resource project does not match execution project")
    if tenant_id is not None and scope.tenant_id is not None and tenant_id != scope.tenant_id:
        raise ContainmentError(ContainmentResult.CROSS_TENANT, "resource tenant does not match execution tenant")
    if operation.upper() == "WRITE" and scope.access_mode.upper() != "READ_WRITE":
        raise ContainmentError(ContainmentResult.UNAUTHORIZED_WRITE, "resource scope is read-only")
    return scope
