"""
Three-Plane Bootstrap Orchestrator.

Enforces ALL mandatory gates across:
  1. GitHub (Source)
  2. Repository Fabric (Control)
  3. Runtime (Execution)

RULE: ANNY_READY requires ALL MANDATORY_GATES to pass.
      Failure → BLOCKED (never DEGRADED).
      RuntimeIdentity.load() is NOT proof of runtime reachability.
"""
import logging
import urllib.request
import urllib.error
import json
from typing import Optional, Dict, Any, Callable, List

from runtime.identity.runtime_identity import RuntimeIdentity
from runtime.github.client import GitHubClient, GitHubAuthError
from runtime.fabric.github_adapter import GitHubFabricAdapter, FabricError, FabricAdmissionResult
from runtime.continuity.engine import ContinuityEngine
from runtime.core.inventory import InventoryDiscovery, BootstrapInventory
from runtime.core.config import get_admin_port
from runtime.core.access_verifier import CriticalAccessVerifier

from .gates import ReadinessGate, GateResult, MANDATORY_GATES
from .report import BootstrapReport, ComponentInventory
from .conrrad import (
    REQUIRED_CONRRAD_SERVICES,
    normalize_dependency_registry,
    not_configured_dependency_matrix,
    registry_is_complete,
)

logger = logging.getLogger(__name__)

# Localhost admin control plane — used for RUNTIME_* gate checks.
# The port must follow RuntimeConfig/admin_port so bootstrap cannot probe a
# different endpoint than the Runtime server actually starts on.
ADMIN_HOST = "127.0.0.1"


class ThreePlaneBootstrap:
    """Orchestrates the full mandatory gate startup sequence."""

    def __init__(
        self,
        data_dir: str,
        github_client: Optional[GitHubClient],
        fabric_client: Optional[GitHubFabricAdapter],
        continuity_engine: ContinuityEngine,
        config=None,
        capability_registry=None,
        tool_registry=None,
        model_registry=None,
        worker_manager=None,
        conrrad_client=None,
        event_sink: Optional[Callable[[str], None]] = None,
    ):
        self.data_dir = data_dir
        self.github = github_client
        self.fabric = fabric_client
        self.continuity = continuity_engine
        self.config = config
        configured_host = getattr(config, "admin_host", None) if config else None
        configured_port = getattr(config, "admin_port", None) if config else None
        self.admin_host = configured_host if isinstance(configured_host, str) and configured_host else ADMIN_HOST
        if isinstance(configured_port, (int, str)):
            try:
                self.admin_port = int(configured_port)
            except (TypeError, ValueError):
                self.admin_port = get_admin_port()
        else:
            self.admin_port = get_admin_port()
        self._cap_registry = capability_registry
        self._tool_registry = tool_registry
        self._model_registry = model_registry
        self._worker_manager = worker_manager
        # Injected external authority boundary; absent client fails closed before GitHub.
        self.conrrad = conrrad_client
        self.event_log: List[str] = []
        self._event_sink = event_sink

    def _admin_url(self, path: str) -> str:
        """Return the configured local admin URL used by Runtime probes."""
        clean_path = path if path.startswith("/") else "/" + path
        return f"http://{self.admin_host}:{self.admin_port}{clean_path}"
    def _record_event(self, event: str) -> None:
        """Expose causal order to bounded tests without treating it as live evidence."""
        self.event_log.append(event)
        if self._event_sink:
            self._event_sink(event)

    def resolve(self) -> BootstrapReport:
        """Executes the full bootstrap sequence. Returns a BootstrapReport.

        ANNY_READY is True ONLY if ALL mandatory gates pass.
        """
        report = BootstrapReport(anny_ready=False, runtime_id="UNKNOWN", fabric_node="UNKNOWN")

        # ---------------------------------------------------------
        # PLANE 1: Local Runtime Identity
        # ---------------------------------------------------------
        identity = self._gate_runtime_identity(report)
        if identity:
            report.runtime_id = identity.runtime_id

        # ---------------------------------------------------------
        # PLANE 2: CONRRAD external authority (must precede GitHub)
        # ---------------------------------------------------------
        conrrad_preflight = self._gate_conrrad_bootstrap_preflight(report, identity)
        conrrad_trust = self._gate_conrrad_manifest_and_trust(report, identity, conrrad_preflight)
        conrrad_registry = self._gate_conrrad_dependency_registry(report, conrrad_trust)

        # ---------------------------------------------------------
        # PLANE 3: GitHub Connectivity & Auth. It is unreachable from this
        # source path until every required CONRRAD precondition passes.
        # ---------------------------------------------------------
        can_connect_github = bool(identity and conrrad_preflight and conrrad_trust and conrrad_registry)
        gh_connected = self._gate_github_connected(report) if can_connect_github else False
        if not can_connect_github:
            report.add_result(GateResult(
                ReadinessGate.GITHUB_CONNECTED, False,
                "CONRRAD preflight, manifest/trust, or dependency registry is not ready",
            ))
        gh_bound = self._gate_github_org_bound(report, gh_connected)

        # ---------------------------------------------------------
        # PLANE 3: Repository Fabric (Requires Identity + GitHub)
        # ---------------------------------------------------------
        can_proceed_fabric = (identity is not None) and gh_connected and gh_bound

        fab_reachable = self._gate_fabric_reachable(report, can_proceed_fabric)
        fab_id_verified = self._gate_fabric_identity_verified(report, can_proceed_fabric, identity)
        fab_node_head = self._gate_fabric_node_at_remote_head(report, can_proceed_fabric)
        fab_trust = self._gate_fabric_trust_verified(report, can_proceed_fabric, identity)
        fab_tenant = self._gate_fabric_tenant_bound(report, can_proceed_fabric, identity)

        if fab_id_verified:
            # Derive fabric_node from the actual node config
            try:
                node = self.fabric.read_node_config()
                report.fabric_node = node.node_id
            except Exception:
                pass

        fab_state = self._gate_fabric_state_readable(report, can_proceed_fabric and fab_reachable)
        fab_prov = self._gate_fabric_provenance(report, can_proceed_fabric and fab_reachable, identity)

        # ---------------------------------------------------------
        # ANNY-RUNTIME Reachability Gates (PLANE 3)
        # These are MANDATORY and SEPARATE from identity.
        # RuntimeIdentity.load() does NOT prove these.
        # ---------------------------------------------------------
        rt_reachable = self._gate_runtime_reachable(report)
        rt_health = self._gate_runtime_health_verified(report, rt_reachable)
        rt_binding = self._gate_runtime_binding_verified(report, rt_reachable, identity)
        rt_admitted = self._gate_runtime_admitted(report, can_proceed_fabric and fab_reachable, identity)

        # ---------------------------------------------------------
        # PHASE E: Policy Snapshot
        # ---------------------------------------------------------
        fabric_contract = None
        if can_proceed_fabric and fab_reachable:
            fabric_contract = self._gate_policy_snapshot(report)
        else:
            report.add_result(GateResult(ReadinessGate.POLICY_SNAPSHOT_FRESH, False, "Prerequisites not met"))

        # ---------------------------------------------------------
        # PHASE F: Cross-Plane Reconciliation
        # ---------------------------------------------------------
        self._gate_plane_reconciliation(report, can_proceed_fabric, identity, fab_reachable, rt_reachable)

        # ---------------------------------------------------------
        # PHASE G: Inventory Discovery
        # ---------------------------------------------------------
        inventory = self._gate_inventory(report, fabric_contract)
        if inventory:
            report.capabilities = _to_component_inventory(inventory.capabilities)
            report.tools = _to_component_inventory(inventory.tools)
            report.models = _to_component_inventory(inventory.models)
            report.workers = _to_component_inventory(inventory.workers)
            report.connectors = _to_component_inventory(inventory.connectors)

        # ---------------------------------------------------------
        # PHASE H: Critical Access Verification
        # ---------------------------------------------------------
        self._gate_critical_access(
            report,
            authorized_capabilities=report.capabilities.authorized,
        )

        # ---------------------------------------------------------
        # PHASE I: Contracts Discovery
        # ---------------------------------------------------------
        self._gate_contracts(report, fabric_contract)

        # ---------------------------------------------------------
        # PHASE J: Delegation Context
        # ---------------------------------------------------------
        self._gate_delegation_context(report, identity, fabric_contract)

        # ---------------------------------------------------------
        # PHASE K: Continuity Coherence
        # ---------------------------------------------------------
        self._gate_continuity_coherent(report)

        # ---------------------------------------------------------
        # FINAL VERDICT — ALL mandatory gates must pass
        # ---------------------------------------------------------
        gate_map = {g.gate: g.passed for g in report.gates}
        all_mandatory_pass = all(
            gate_map.get(gate, False) for gate in MANDATORY_GATES
        )
        report.finish(ready=all_mandatory_pass)

        if not all_mandatory_pass:
            failed = [
                gate.name for gate in MANDATORY_GATES
                if not gate_map.get(gate, False)
            ]
            logger.warning(f"Bootstrap BLOCKED. Failed mandatory gates: {failed}")

        return report

    # --- Gate Implementations ---

    def _gate_conrrad_bootstrap_preflight(
        self, report: BootstrapReport, ident: Optional[RuntimeIdentity]
    ) -> bool:
        self._record_event("CONRRAD_BOOTSTRAP_PREFLIGHT")
        if not ident:
            report.conrrad_dependencies = not_configured_dependency_matrix("Runtime identity unavailable")
            report.add_result(GateResult(ReadinessGate.CONRRAD_BOOTSTRAP_PREFLIGHT, False, "Runtime identity unavailable"))
            return False
        if not self.conrrad:
            report.conrrad_dependencies = not_configured_dependency_matrix("External CONRRAD bootstrap is not configured")
            report.add_result(GateResult(
                ReadinessGate.CONRRAD_BOOTSTRAP_PREFLIGHT, False,
                "External CONRRAD bootstrap is not configured",
            ))
            return False
        try:
            response = self.conrrad.bootstrap_preflight(ident.runtime_id)
            status = str(response.get("status", response.get("online_status", "UNKNOWN"))).upper() if isinstance(response, dict) else "UNKNOWN"
            if status == "ONLINE_VERIFIED":
                report.add_result(GateResult(ReadinessGate.CONRRAD_BOOTSTRAP_PREFLIGHT, True, "External CONRRAD preflight passed"))
                return True
            report.conrrad_dependencies = not_configured_dependency_matrix(f"CONRRAD bootstrap preflight: {status}")
            report.add_result(GateResult(ReadinessGate.CONRRAD_BOOTSTRAP_PREFLIGHT, False, f"CONRRAD bootstrap preflight: {status}"))
            return False
        except Exception as exc:
            report.conrrad_dependencies = not_configured_dependency_matrix("CONRRAD bootstrap preflight unavailable")
            report.add_result(GateResult(ReadinessGate.CONRRAD_BOOTSTRAP_PREFLIGHT, False, f"CONRRAD bootstrap preflight unavailable: {type(exc).__name__}"))
            return False

    def _gate_conrrad_manifest_and_trust(
        self, report: BootstrapReport, ident: Optional[RuntimeIdentity], preflight_passed: bool
    ) -> bool:
        if not preflight_passed or not ident or not self.conrrad:
            report.add_result(GateResult(ReadinessGate.CONRRAD_MANIFEST_AND_TRUST_VERIFIED, False, "CONRRAD bootstrap preflight not passed"))
            return False
        self._record_event("VERIFY_CONRRAD_MANIFEST_AND_TRUST")
        try:
            response = self.conrrad.verify_manifest_and_trust(ident.runtime_id)
            trust_status = str(response.get("trust_status", "UNKNOWN")).upper() if isinstance(response, dict) else "UNKNOWN"
            manifest_status = str(response.get("manifest_status", "UNKNOWN")).upper() if isinstance(response, dict) else "UNKNOWN"
            if trust_status == "VERIFIED" and manifest_status == "VERIFIED":
                report.add_result(GateResult(ReadinessGate.CONRRAD_MANIFEST_AND_TRUST_VERIFIED, True, "External manifest and trust verified"))
                return True
            report.add_result(GateResult(
                ReadinessGate.CONRRAD_MANIFEST_AND_TRUST_VERIFIED, False,
                f"CONRRAD manifest/trust not verified: manifest={manifest_status}, trust={trust_status}",
            ))
            return False
        except Exception as exc:
            report.add_result(GateResult(ReadinessGate.CONRRAD_MANIFEST_AND_TRUST_VERIFIED, False, f"CONRRAD manifest/trust unavailable: {type(exc).__name__}"))
            return False

    def _gate_conrrad_dependency_registry(self, report: BootstrapReport, trust_passed: bool) -> bool:
        if not trust_passed or not self.conrrad:
            if not report.conrrad_dependencies:
                report.conrrad_dependencies = not_configured_dependency_matrix("CONRRAD manifest/trust is not verified")
            report.add_result(GateResult(ReadinessGate.CONRRAD_DEPENDENCY_REGISTRY_LOADED, False, "CONRRAD manifest/trust not verified"))
            return False
        self._record_event("LOAD_REQUIRED_CONRRAD_DEPENDENCY_REGISTRY")
        try:
            records = normalize_dependency_registry(self.conrrad.load_required_dependency_registry())
            if not registry_is_complete(records):
                report.conrrad_dependencies = records or not_configured_dependency_matrix(
                    "CONRRAD dependency registry is absent or incomplete"
                )
                report.add_result(GateResult(
                    ReadinessGate.CONRRAD_DEPENDENCY_REGISTRY_LOADED, False,
                    "CONRRAD dependency registry is absent or incomplete",
                ))
                return False
            report.conrrad_dependencies = records
            report.add_result(GateResult(
                ReadinessGate.CONRRAD_DEPENDENCY_REGISTRY_LOADED, True,
                f"Required CONRRAD dependency registry loaded ({len(REQUIRED_CONRRAD_SERVICES)} services)",
            ))
            return True
        except Exception as exc:
            report.conrrad_dependencies = not_configured_dependency_matrix(
                "CONRRAD dependency registry unavailable"
            )
            report.add_result(GateResult(ReadinessGate.CONRRAD_DEPENDENCY_REGISTRY_LOADED, False, f"CONRRAD dependency registry unavailable: {type(exc).__name__}"))
            return False

    def _gate_runtime_identity(self, report: BootstrapReport) -> Optional[RuntimeIdentity]:
        try:
            ident = RuntimeIdentity.load(self.data_dir)
            report.add_result(GateResult(
                ReadinessGate.RUNTIME_IDENTITY, True,
                "Identity loaded from disk", ident.runtime_id
            ))
            return ident
        except Exception as e:
            report.add_result(GateResult(ReadinessGate.RUNTIME_IDENTITY, False, str(e)))
            return None

    def _gate_github_connected(self, report: BootstrapReport) -> bool:
        self._record_event("CONNECT_GITHUB")
        if not self.github:
            report.add_result(GateResult(ReadinessGate.GITHUB_CONNECTED, False, "No GitHub client provided"))
            return False

        try:
            principal = self.github.get_authenticated_principal()
            login = principal.get("login", "UNKNOWN")
            report.add_result(GateResult(ReadinessGate.GITHUB_CONNECTED, True, "Authenticated", login))
            return True
        except GitHubAuthError as e:
            report.add_result(GateResult(ReadinessGate.GITHUB_CONNECTED, False, f"Auth error: {e}"))
            return False
        except Exception as e:
            report.add_result(GateResult(ReadinessGate.GITHUB_CONNECTED, False, str(e)))
            return False

    def _gate_github_org_bound(self, report: BootstrapReport, gh_connected: bool) -> bool:
        if not gh_connected:
            report.add_result(GateResult(ReadinessGate.GITHUB_ORG_BOUND, False, "GitHub not connected"))
            return False

        # Resolve the required org from config (dynamic, not hardcoded)
        required_org = None
        if self.config:
            required_org = getattr(self.config, 'fabric_org', None)
        if not required_org and self.fabric:
            required_org = self.fabric.org

        if not required_org:
            report.add_result(GateResult(
                ReadinessGate.GITHUB_ORG_BOUND, False,
                "fabric_org not configured — cannot verify org membership"
            ))
            return False

        try:
            self._record_event("GITHUB_ORGANIZATION_MEMBERSHIP")
            orgs = self.github.list_organizations()
            org_names = {org["login"] for org in orgs}
            if required_org in org_names:
                report.add_result(GateResult(
                    ReadinessGate.GITHUB_ORG_BOUND, True,
                    f"Member of {required_org}", required_org
                ))
                return True
            else:
                report.add_result(GateResult(
                    ReadinessGate.GITHUB_ORG_BOUND, False,
                    f"Not a member of {required_org}. Orgs: {sorted(org_names)}"
                ))
                return False
        except Exception as e:
            report.add_result(GateResult(ReadinessGate.GITHUB_ORG_BOUND, False, str(e)))
            return False

    def _gate_fabric_reachable(self, report: BootstrapReport, can_proceed: bool) -> bool:
        if not can_proceed or not self.fabric:
            report.add_result(GateResult(ReadinessGate.FABRIC_REACHABLE, False, "Prerequisites not met"))
            return False

        reachable, latency_ms, error = self.fabric.probe_reachability()
        if reachable:
            report.add_result(GateResult(
                ReadinessGate.FABRIC_REACHABLE, True,
                f"Fabric reachable ({latency_ms:.0f}ms)", f"{self.fabric.org}/{self.fabric.repo}"
            ))
            return True
        else:
            report.add_result(GateResult(ReadinessGate.FABRIC_REACHABLE, False, error))
            return False

    def _gate_fabric_identity_verified(
        self, report: BootstrapReport, can_proceed: bool, ident: Optional[RuntimeIdentity]
    ) -> bool:
        if not can_proceed or not self.fabric:
            report.add_result(GateResult(ReadinessGate.FABRIC_IDENTITY_VERIFIED, False, "Prerequisites not met"))
            return False

        try:
            node = self.fabric.read_node_config()
            report.add_result(GateResult(
                ReadinessGate.FABRIC_IDENTITY_VERIFIED, True,
                "Node config read from Fabric", node.node_id
            ))
            return True
        except FabricError as e:
            report.add_result(GateResult(ReadinessGate.FABRIC_IDENTITY_VERIFIED, False, str(e)))
            return False

    def _gate_fabric_node_at_remote_head(self, report: BootstrapReport, can_proceed: bool) -> bool:
        """Explicitly verify fabric/node.json exists at the remote HEAD (not cached)."""
        if not can_proceed or not self.fabric:
            report.add_result(GateResult(ReadinessGate.FABRIC_NODE_AT_REMOTE_HEAD, False, "Prerequisites not met"))
            return False

        exists, sha = self.fabric.node_json_exists_at_remote_head()
        if exists:
            report.add_result(GateResult(
                ReadinessGate.FABRIC_NODE_AT_REMOTE_HEAD, True,
                "fabric/node.json confirmed at remote HEAD", sha
            ))
            return True
        else:
            report.add_result(GateResult(
                ReadinessGate.FABRIC_NODE_AT_REMOTE_HEAD, False,
                f"fabric/node.json not found at remote HEAD of {self.fabric.org}/{self.fabric.repo}"
            ))
            return False

    def _gate_fabric_trust_verified(
        self, report: BootstrapReport, can_proceed: bool, ident: Optional[RuntimeIdentity]
    ) -> bool:
        if not can_proceed or not self.fabric or not ident:
            report.add_result(GateResult(ReadinessGate.FABRIC_TRUST_VERIFIED, False, "Prerequisites not met"))
            return False

        try:
            token = self.fabric.issue_trust_token(ident.runtime_id, ident._private_key)
            report.add_result(GateResult(
                ReadinessGate.FABRIC_TRUST_VERIFIED, True,
                "Trust token issued", token.signature[:8] + "..."
            ))
            return True
        except Exception as e:
            report.add_result(GateResult(ReadinessGate.FABRIC_TRUST_VERIFIED, False, str(e)))
            return False

    def _gate_fabric_tenant_bound(
        self, report: BootstrapReport, can_proceed: bool, ident: Optional[RuntimeIdentity]
    ) -> bool:
        if not can_proceed or not self.fabric or not ident:
            report.add_result(GateResult(ReadinessGate.FABRIC_TENANT_BOUND, False, "Prerequisites not met"))
            return False

        try:
            tenant = self.fabric.read_tenant_binding(ident.runtime_id)
            report.add_result(GateResult(
                ReadinessGate.FABRIC_TENANT_BOUND, True,
                "Tenant binding found", tenant.tenant_id
            ))
            return True
        except FabricError as e:
            report.add_result(GateResult(ReadinessGate.FABRIC_TENANT_BOUND, False, str(e)))
            return False

    def _gate_fabric_state_readable(self, report: BootstrapReport, can_proceed: bool) -> bool:
        if not can_proceed or not self.fabric:
            report.add_result(GateResult(ReadinessGate.FABRIC_STATE_READABLE, False, "Prerequisites not met"))
            return False

        try:
            state = self.fabric.read_fabric_state()
            # Verify it's a non-empty dict — not just a successful HTTP response
            if isinstance(state, dict) and len(state) > 0:
                report.add_result(GateResult(
                    ReadinessGate.FABRIC_STATE_READABLE, True,
                    "Fabric state read successfully",
                    f"keys={list(state.keys())[:5]}"
                ))
                return True
            else:
                report.add_result(GateResult(
                    ReadinessGate.FABRIC_STATE_READABLE, False,
                    "fabric/state.json is empty or malformed"
                ))
                return False
        except FabricError as e:
            report.add_result(GateResult(ReadinessGate.FABRIC_STATE_READABLE, False, str(e)))
            return False

    def _gate_fabric_provenance(
        self, report: BootstrapReport, can_proceed: bool, ident: Optional[RuntimeIdentity]
    ) -> bool:
        if not can_proceed or not self.fabric:
            report.add_result(GateResult(ReadinessGate.FABRIC_PROVENANCE_VALID, False, "Prerequisites not met"))
            return False

        # Read the version commit SHA from identity or config
        commit_sha = None
        if ident and hasattr(ident, 'origin_commit'):
            commit_sha = ident.origin_commit
        if not commit_sha and self.config and hasattr(self.config, 'version_commit'):
            commit_sha = self.config.version_commit

        if not commit_sha:
            report.add_result(GateResult(
                ReadinessGate.FABRIC_PROVENANCE_VALID, False,
                "No commit SHA available for provenance check"
            ))
            return False

        valid, error = self.fabric.validate_provenance(commit_sha)
        if valid:
            report.add_result(GateResult(
                ReadinessGate.FABRIC_PROVENANCE_VALID, True,
                f"Commit {commit_sha[:7]} confirmed at Fabric remote", commit_sha[:7]
            ))
            return True
        else:
            report.add_result(GateResult(
                ReadinessGate.FABRIC_PROVENANCE_VALID, False,
                error or f"Commit {commit_sha[:7]} not found in Fabric"
            ))
            return False

    def _gate_runtime_reachable(self, report: BootstrapReport) -> bool:
        """Verify the ANNY-RUNTIME localhost control plane responds.

        RuntimeIdentity.load() is NOT equivalent to this check.
        This gate proves the process is up and the HTTP server accepts connections.
        """
        try:
            url = self._admin_url("/api/status")
            req = urllib.request.Request(url, method="GET")
            req.add_header("X-Bootstrap-Probe", "1")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    report.add_result(GateResult(
                        ReadinessGate.RUNTIME_REACHABLE, True,
                        f"Admin API responded 200 at {self.admin_host}:{self.admin_port}",
                        url
                    ))
                    return True
                else:
                    report.add_result(GateResult(
                        ReadinessGate.RUNTIME_REACHABLE, False,
                        f"Admin API returned HTTP {resp.status}"
                    ))
                    return False
        except urllib.error.URLError as e:
            report.add_result(GateResult(
                ReadinessGate.RUNTIME_REACHABLE, False,
                f"Admin API not reachable at {self.admin_host}:{self.admin_port}: {e.reason}"
            ))
            return False
        except Exception as e:
            report.add_result(GateResult(ReadinessGate.RUNTIME_REACHABLE, False, str(e)))
            return False

    def _gate_runtime_health_verified(self, report: BootstrapReport, rt_reachable: bool) -> bool:
        """Parse the /api/status response to verify health."""
        if not rt_reachable:
            report.add_result(GateResult(ReadinessGate.RUNTIME_HEALTH_VERIFIED, False, "Runtime not reachable"))
            return False

        try:
            url = self._admin_url("/api/status")
            req = urllib.request.Request(url, method="GET")
            req.add_header("X-Bootstrap-Probe", "1")
            with urllib.request.urlopen(req, timeout=3) as resp:
                raw = resp.read().decode('utf-8')
                data = json.loads(raw)
                state = data.get("state", "UNKNOWN")
                if state not in ("STOPPED", "ERROR"):
                    report.add_result(GateResult(
                        ReadinessGate.RUNTIME_HEALTH_VERIFIED, True,
                        f"Runtime state: {state}", state
                    ))
                    return True
                else:
                    report.add_result(GateResult(
                        ReadinessGate.RUNTIME_HEALTH_VERIFIED, False,
                        f"Runtime in unhealthy state: {state}"
                    ))
                    return False
        except Exception as e:
            report.add_result(GateResult(ReadinessGate.RUNTIME_HEALTH_VERIFIED, False, str(e)))
            return False

    def _gate_runtime_binding_verified(
        self, report: BootstrapReport, rt_reachable: bool, ident: Optional[RuntimeIdentity]
    ) -> bool:
        """Verify runtime reports matching fabric_org/repo binding."""
        if not rt_reachable:
            report.add_result(GateResult(ReadinessGate.RUNTIME_BINDING_VERIFIED, False, "Runtime not reachable"))
            return False

        expected_org = None
        expected_repo = None
        if self.fabric:
            expected_org = self.fabric.org
            expected_repo = self.fabric.repo
        elif self.config:
            expected_org = getattr(self.config, 'fabric_org', None)
            expected_repo = getattr(self.config, 'fabric_repo', None)

        if not expected_org or not expected_repo:
            report.add_result(GateResult(
                ReadinessGate.RUNTIME_BINDING_VERIFIED, False,
                "Cannot verify binding: fabric_org/repo not configured"
            ))
            return False

        try:
            url = self._admin_url("/api/status")
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                reported_org = data.get("fabric_org")
                reported_repo = data.get("fabric_repo")

                if reported_org == expected_org and reported_repo == expected_repo:
                    report.add_result(GateResult(
                        ReadinessGate.RUNTIME_BINDING_VERIFIED, True,
                        f"Binding matches: {expected_org}/{expected_repo}",
                        f"{expected_org}/{expected_repo}"
                    ))
                    return True
                else:
                    report.add_result(GateResult(
                        ReadinessGate.RUNTIME_BINDING_VERIFIED, False,
                        f"Binding mismatch: expected {expected_org}/{expected_repo}, "
                        f"got {reported_org}/{reported_repo}"
                    ))
                    return False
        except Exception as e:
            report.add_result(GateResult(ReadinessGate.RUNTIME_BINDING_VERIFIED, False, str(e)))
            return False

    def _gate_runtime_admitted(
        self, report: BootstrapReport, can_proceed: bool, ident: Optional[RuntimeIdentity]
    ) -> bool:
        """Verify the Fabric has issued an explicit ALLOW for this runtime_id.

        Local HMAC trust token ≠ Fabric admission.
        """
        if not can_proceed or not self.fabric or not ident:
            report.add_result(GateResult(ReadinessGate.RUNTIME_ADMITTED, False, "Prerequisites not met"))
            return False

        admission = self.fabric.check_admission(ident.runtime_id)

        if admission.is_admitted():
            report.add_result(GateResult(
                ReadinessGate.RUNTIME_ADMITTED, True,
                f"Fabric ALLOW: {admission.reason}",
                admission.verdict
            ))
            return True
        else:
            report.add_result(GateResult(
                ReadinessGate.RUNTIME_ADMITTED, False,
                f"Fabric verdict={admission.verdict}: {admission.reason}"
            ))
            return False

    def _gate_plane_reconciliation(
        self,
        report: BootstrapReport,
        can_proceed: bool,
        ident: Optional[RuntimeIdentity],
        fab_reachable: bool,
        rt_reachable: bool,
    ) -> bool:
        """Cross-plane reconciliation: compare runtime identity vs Fabric state."""
        if not can_proceed:
            report.add_result(GateResult(ReadinessGate.PLANE_RECONCILIATION, False, "Prerequisites not met"))
            return False

        # Collect reconciliation evidence
        issues = []

        # 1. runtime_id must be set
        if not ident or not ident.runtime_id:
            issues.append("runtime_id missing from identity")

        # 2. Fabric must be reachable
        if not fab_reachable:
            issues.append("Fabric not reachable — cannot reconcile")

        # 3. Runtime must be reachable
        if not rt_reachable:
            issues.append("Runtime not reachable — cannot reconcile")

        # 4. Fabric state and runtime state should agree on runtime_id and fabric binding
        if ident and fab_reachable and rt_reachable:
            try:
                fabric_state = self.fabric.read_fabric_state()
                registered = fabric_state.get("registered_runtimes", [])
                if ident.runtime_id not in registered:
                    issues.append(
                        f"{ident.runtime_id} not in fabric state registered_runtimes"
                    )
                
                # Check fabric_org and fabric_repo matching the identity/config
                expected_org = self.fabric.org if self.fabric else (self.config.fabric_org if self.config else None)
                expected_repo = self.fabric.repo if self.fabric else (self.config.fabric_repo if self.config else None)
                
                state_org = fabric_state.get("fabric_org")
                state_repo = fabric_state.get("fabric_repo")
                
                if state_org and state_org != expected_org:
                    issues.append(f"Fabric org mismatch: expected {expected_org}, got {state_org}")
                if state_repo and state_repo != expected_repo:
                    issues.append(f"Fabric repo mismatch: expected {expected_repo}, got {state_repo}")

            except FabricError as e:
                issues.append(f"Could not read fabric state for reconciliation: {e}")

        if not issues:
            report.add_result(GateResult(
                ReadinessGate.PLANE_RECONCILIATION, True,
                "All planes agree", ident.runtime_id if ident else "UNKNOWN"
            ))
            return True
        else:
            report.add_result(GateResult(
                ReadinessGate.PLANE_RECONCILIATION, False,
                "; ".join(issues)
            ))
            return False

    def _gate_continuity_coherent(self, report: BootstrapReport) -> bool:
        if not self.continuity:
            report.add_result(GateResult(ReadinessGate.CONTINUITY_COHERENT, False, "No continuity engine"))
            return False

        try:
            status = self.continuity.status
            state = status.get("state", "UNKNOWN")
            if state == "COHERENT":
                report.add_result(GateResult(
                    ReadinessGate.CONTINUITY_COHERENT, True,
                    "Continuity coherent", state
                ))
                return True
            else:
                report.add_result(GateResult(
                    ReadinessGate.CONTINUITY_COHERENT, False,
                    f"Continuity state: {state}"
                ))
                return False
        except Exception as e:
            report.add_result(GateResult(ReadinessGate.CONTINUITY_COHERENT, False, str(e)))
            return False

    # ------------------------------------------------------------------
    # Phase E: Policy Snapshot
    # ------------------------------------------------------------------

    def _gate_policy_snapshot(self, report: BootstrapReport):
        """Phase E: Fetch and validate the authoritative Fabric policy snapshot."""
        try:
            from runtime.fabric.models import FabricPolicy
            raw = self.fabric.read_policy()
            policy = FabricPolicy.from_dict(raw)
            report.policy_revision = policy.revision
            report.add_result(GateResult(
                ReadinessGate.POLICY_SNAPSHOT_FRESH, True,
                f"Policy snapshot fetched, revision={policy.revision}",
                policy.revision
            ))
            # Return the contract from the same read if present
            return raw.get("_contract")

        except Exception as e:
            report.add_result(GateResult(ReadinessGate.POLICY_SNAPSHOT_FRESH, False, str(e)))
            return None

    # ------------------------------------------------------------------
    # Phase G: Inventory Discovery
    # ------------------------------------------------------------------

    def _gate_inventory(self, report: BootstrapReport, fabric_contract) -> Optional[BootstrapInventory]:
        """Phase G: Enumerate capabilities, tools, models, workers, connectors."""
        try:
            discovery = InventoryDiscovery(
                capability_registry=self._cap_registry,
                tool_registry=self._tool_registry,
                model_registry=self._model_registry,
                worker_manager=self._worker_manager,
                fabric_contract=fabric_contract,
            )
            inv = discovery.discover()

            all_pass = True
            for gate, name, component in [
                (ReadinessGate.CAPABILITIES_INVENTORIED, "capabilities", inv.capabilities),
                (ReadinessGate.TOOLS_INVENTORIED, "tools", inv.tools),
                (ReadinessGate.MODELS_INVENTORIED, "models", inv.models),
                (ReadinessGate.WORKERS_INVENTORIED, "workers", inv.workers),
                (ReadinessGate.CONNECTORS_INVENTORIED, "connectors", inv.connectors),
            ]:
                count = len(component.declared)
                enabled = len(component.authorized)
                passed = count > 0
                all_pass = all_pass and passed
                report.add_result(GateResult(
                    gate, passed,
                    f"{name}: {count} declared, {enabled} authorized",
                    f"{count}/{enabled}"
                ))

            return inv
        except Exception as e:
            for gate in [
                ReadinessGate.CAPABILITIES_INVENTORIED,
                ReadinessGate.TOOLS_INVENTORIED,
                ReadinessGate.MODELS_INVENTORIED,
                ReadinessGate.WORKERS_INVENTORIED,
                ReadinessGate.CONNECTORS_INVENTORIED,
            ]:
                report.add_result(GateResult(gate, False, f"Inventory error: {e}"))
            return None

    # ------------------------------------------------------------------
    # Phase H: Critical Access Verification
    # ------------------------------------------------------------------

    def _gate_critical_access(
        self, report: BootstrapReport, authorized_capabilities
    ) -> bool:
        """Phase H: Run safe smoke tests against critical capabilities."""
        try:
            verifier = CriticalAccessVerifier(
                authorized_capabilities=list(authorized_capabilities),
                data_dir=self.data_dir,
                fabric_adapter=self.fabric,
                github_client=self.github,
            )
            result = verifier.verify()

            detail = f"tested={len(result.results)}, failures={result.critical_failures}"
            evidence = ", ".join(r.evidence for r in result.results if r.passed)

            report.add_result(GateResult(
                ReadinessGate.CRITICAL_ACCESS_VERIFIED,
                result.passed,
                detail,
                evidence or None,
            ))
            return result.passed
        except Exception as e:
            report.add_result(GateResult(ReadinessGate.CRITICAL_ACCESS_VERIFIED, False, str(e)))
            return False

    # ------------------------------------------------------------------
    # Phase I: Contracts Discovery
    # ------------------------------------------------------------------

    def _gate_contracts(self, report: BootstrapReport, fabric_contract) -> bool:
        """Phase I: Verify operational limits and contracts are discoverable."""
        try:
            # If we resolved a contract during Phase E, use it
            if fabric_contract is not None:
                cid = getattr(fabric_contract, "contract_id", "INLINED")
                report.limits_verified = True
                report.add_result(GateResult(
                    ReadinessGate.CONTRACTS_DISCOVERED, True,
                    f"Contract: {cid}", cid
                ))
                return True

            # Otherwise try to read from fabric
            if self.fabric:
                raw = self.fabric.read_contract()
                from runtime.fabric.models import FabricContract
                contract = FabricContract.from_dict(raw)
                report.limits_verified = True
                report.add_result(GateResult(
                    ReadinessGate.CONTRACTS_DISCOVERED, True,
                    f"Contract: {contract.contract_id}",
                    contract.contract_id
                ))
                return True
            
            report.add_result(GateResult(
                ReadinessGate.CONTRACTS_DISCOVERED, False,
                "No fabric client — cannot discover contracts"
            ))
            return False
            return False
        except Exception as e:
            report.add_result(GateResult(ReadinessGate.CONTRACTS_DISCOVERED, False, str(e)))
            return False

    # ------------------------------------------------------------------
    # Phase J: Delegation Context
    # ------------------------------------------------------------------

    def _gate_delegation_context(
        self, report: BootstrapReport,
        ident: Optional[RuntimeIdentity],
        fabric_contract
    ) -> bool:
        """Phase J: Verify the delegation context can be constructed.

        The delegation context establishes who issued what authority to whom.
        Minimum requirements: runtime_id known, tenant_id known, fabric_node known.
        """
        issues = []

        if not ident or not ident.runtime_id:
            issues.append("runtime_id unknown")

        tenant_gate = report.get_gate(ReadinessGate.FABRIC_TENANT_BOUND)
        if not tenant_gate.passed or not tenant_gate.evidence:
            issues.append("tenant_id not bound")

        if report.fabric_node == "UNKNOWN":
            issues.append("fabric_node not resolved")

        if not issues:
            evidence_parts = [
                f"runtime_id={ident.runtime_id}",
                f"tenant_id={tenant_gate.evidence}",
                f"fabric_node={report.fabric_node}",
            ]
            report.add_result(GateResult(
                ReadinessGate.DELEGATION_CONTEXT_BUILT, True,
                "Delegation context complete",
                " | ".join(evidence_parts)
            ))
            return True
        else:
            report.add_result(GateResult(
                ReadinessGate.DELEGATION_CONTEXT_BUILT, False,
                "; ".join(issues)
            ))
            return False


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _to_component_inventory(inv) -> ComponentInventory:
    """Convert a core.inventory.ComponentInventory → report.ComponentInventory."""
    return ComponentInventory(
        declared=list(inv.declared),
        configured=list(inv.configured),
        enabled=list(inv.enabled),
        authorized=list(inv.authorized),
        available=list(inv.available),
        functional=list(inv.functional),
        tested=list(inv.tested),
        verified=list(inv.verified),
    )
