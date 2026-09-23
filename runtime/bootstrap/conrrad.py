"""CONRRAD bootstrap contract projection.

This module deliberately contains no endpoint, transport, issuer, or trust-root
implementation.  Runtime receives an external client at its integration
boundary; absent live authority is represented explicitly rather than emulated.
"""
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


def not_configured_dependency_matrix(reason: str) -> List[Dict[str, str]]:
    """Project mandatory contract requirements without claiming service identity."""
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
    """Normalize only externally supplied registry records; never fill missing ones."""
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
    """A registry gate passes only when every contract-required service is present."""
    return {record["service_name"] for record in records} >= set(REQUIRED_CONRRAD_SERVICES)
