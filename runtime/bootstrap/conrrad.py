"""CONRRAD dependency-truth projection contract.

This module is deliberately read-only. It describes the eight mandatory external
services ANNY requires before claiming a verified CONRRAD boundary. Missing external
observations are represented explicitly; no service endpoint, trust, identity, or
certification is synthesized.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


REQUIRED_CONRRAD_SERVICES = (
    "CONRRAD.BOOTSTRAP",
    "ANNY.AUTH",
    "CONRRAD.EXECUTION_CONTEXT",
    "CONRRAD.REPOSITORY_FABRIC",
    "CONRRAD.POLICY",
    "CONRRAD.EVIDENCE",
    "CONRRAD.IDENTITY",
    "CONRRAD.OBSERVABILITY",
)

DEPENDENCY_FIELDS = (
    "service_id",
    "service_name",
    "service_class",
    "owner_plane",
    "endpoint",
    "node_id",
    "deployment_id",
    "source_commit",
    "artifact_digest",
    "contract_version",
    "online_status",
    "trust_status",
    "certification_state",
    "last_live_check",
    "evidence_ref",
    "failure_reason",
)

AVAILABLE_ONLINE_STATUSES = frozenset({"ONLINE_VERIFIED"})
VERIFIED_TRUST_STATUSES = frozenset({"VERIFIED"})


def not_configured_dependency_matrix(reason: str) -> List[Dict[str, str]]:
    """Project mandatory requirements without claiming external observation."""
    return [
        {
            "service_id": "UNKNOWN",
            "service_name": service_name,
            "service_class": "UNKNOWN",
            "owner_plane": "CONRRAD_REMOTE",
            "endpoint": "NOT_CONFIGURED",
            "node_id": "UNKNOWN",
            "deployment_id": "UNKNOWN",
            "source_commit": "UNKNOWN",
            "artifact_digest": "UNKNOWN",
            "contract_version": "UNKNOWN",
            "online_status": "NOT_CONFIGURED",
            "trust_status": "UNKNOWN",
            "certification_state": "UNKNOWN",
            "last_live_check": "UNKNOWN",
            "evidence_ref": "UNKNOWN",
            "failure_reason": reason,
        }
        for service_name in REQUIRED_CONRRAD_SERVICES
    ]


def normalize_dependency_registry(records: Any) -> List[Dict[str, Any]]:
    """Normalize only externally supplied records; never fill missing fields."""
    if isinstance(records, dict):
        records = records.get("services", records.get("dependencies"))
    if not isinstance(records, Iterable) or isinstance(records, (str, bytes, dict)):
        return []

    normalized: List[Dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            return []
        item = {field: record.get(field, "UNKNOWN") for field in DEPENDENCY_FIELDS}
        if not item["service_name"] or item["service_name"] == "UNKNOWN":
            return []
        normalized.append(item)
    return normalized


def registry_is_complete(records: List[Dict[str, Any]]) -> bool:
    """Require every mandatory service to be online and trust-verified."""
    for service_name in REQUIRED_CONRRAD_SERVICES:
        matches = [record for record in records if record.get("service_name") == service_name]
        if not any(
            str(record.get("online_status", "UNKNOWN")).upper() in AVAILABLE_ONLINE_STATUSES
            and str(record.get("trust_status", "UNKNOWN")).upper() in VERIFIED_TRUST_STATUSES
            for record in matches
        ):
            return False
    return True


def project_dependency_matrix(report: Any) -> List[Dict[str, Any]]:
    """Return observed registry records or an explicit NOT_CONFIGURED matrix."""
    observed = getattr(report, "conrrad_dependencies", None) if report is not None else None
    normalized = normalize_dependency_registry(observed)
    if normalized:
        return normalized
    return not_configured_dependency_matrix(
        "No authoritative CONRRAD dependency registry has been observed"
    )
