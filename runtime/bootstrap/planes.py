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
from typing import Optional, Dict, Any

from runtime.identity.runtime_identity import RuntimeIdentity
from runtime.github.client import GitHubClient, GitHubAuthError
from runtime.fabric.client import FabricClient, FabricError, FabricAdmissionResult
from runtime.continuity.engine import ContinuityEngine

from .gates import ReadinessGate, GateResult, MANDATORY_GATES
from .report import BootstrapReport

logger = logging.getLogger(__name__)

# Localhost admin control plane — used for RUNTIME_* gate checks
ADMIN_HOST = "127.0.0.1"
ADMIN_PORT = 7891


class ThreePlaneBootstrap:
    """Orchestrates the full mandatory gate startup sequence."""

    def __init__(
        self,
        data_dir: str,
        github_client: Optional[GitHubClient],
        fabric_client: Optional[FabricClient],
        continuity_engine: ContinuityEngine,
        config=None,
    ):
        self.data_dir = data_dir
        self.github = github_client
        self.fabric = fabric_client
        self.continuity = continuity_engine
        self.config = config

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
        # PLANE 2: GitHub Connectivity & Auth
        # ---------------------------------------------------------
        gh_connected = self._gate_github_connected(report)
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
        # CROSS-PLANE: Reconciliation + Continuity
        # ---------------------------------------------------------
        self._gate_plane_reconciliation(report, can_proceed_fabric, identity, fab_reachable, rt_reachable)
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
            url = f"http://{ADMIN_HOST}:{ADMIN_PORT}/api/status"
            req = urllib.request.Request(url, method="GET")
            req.add_header("X-Bootstrap-Probe", "1")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    report.add_result(GateResult(
                        ReadinessGate.RUNTIME_REACHABLE, True,
                        f"Admin API responded 200 at {ADMIN_HOST}:{ADMIN_PORT}",
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
                f"Admin API not reachable at {ADMIN_HOST}:{ADMIN_PORT}: {e.reason}"
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
            url = f"http://{ADMIN_HOST}:{ADMIN_PORT}/api/status"
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
            url = f"http://{ADMIN_HOST}:{ADMIN_PORT}/api/status"
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

        # 4. Fabric state and runtime state should agree on runtime_id
        if ident and fab_reachable and rt_reachable:
            try:
                fabric_state = self.fabric.read_fabric_state()
                registered = fabric_state.get("registered_runtimes", [])
                if ident.runtime_id not in registered:
                    issues.append(
                        f"{ident.runtime_id} not in fabric state registered_runtimes"
                    )
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
