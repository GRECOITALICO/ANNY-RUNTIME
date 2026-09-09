"""Continuity reconciler comparing canonical state, GitHub state, and local runtime state."""
import logging
from typing import Dict, Any, Optional, List

from runtime.continuity.state import ContinuityStatus, AnnyCanonicalState
from runtime.github.discovery import DiscoveredRepository, DiscoveredPrincipal

logger = logging.getLogger(__name__)


class ContinuityReconciler:
    """Reconciles canonical operational state against observable GitHub and local runtime state."""

    def reconcile(
        self,
        canonical_state: Optional[AnnyCanonicalState],
        principal: Optional[DiscoveredPrincipal],
        discovered_repos: List[DiscoveredRepository],
        github_connected: bool = True,
        runtime_ready: bool = True
    ) -> ContinuityStatus:
        """Evaluate reconciliation status across canonical, GitHub, and local states."""

        # 1. Access / Auth check
        if not github_connected or not runtime_ready:
            logger.warning("Reconciliation: GitHub disconnected or runtime not ready -> DEGRADED")
            return ContinuityStatus.DEGRADED

        if not canonical_state:
            logger.warning("Reconciliation: Canonical state missing -> BLOCKED")
            return ContinuityStatus.BLOCKED

        if canonical_state.blockers and any(b.severity == "CRITICAL" for b in canonical_state.blockers):
            logger.warning("Reconciliation: Critical blockers present -> BLOCKED")
            return ContinuityStatus.BLOCKED

        # 2. Check if operational repository is among discovered repos (or local)
        if canonical_state.metadata.get("repo_type") == "github":
            repo_names = [r.full_name.lower() for r in discovered_repos]
            target_repo = canonical_state.repository_name.lower()
            if target_repo not in repo_names:
                # Target repo not found in discovered list
                logger.warning(f"Reconciliation: Canonical repo {target_repo} not in discovered repos -> CONFLICTED")
                return ContinuityStatus.CONFLICTED

        # 3. Check mission consistency
        if not canonical_state.current_mission:
            logger.warning("Reconciliation: No current mission in canonical state -> DEGRADED")
            return ContinuityStatus.DEGRADED

        # 4. Check for active blockers
        if canonical_state.blockers:
            logger.info(f"Reconciliation: State contains {len(canonical_state.blockers)} active blockers -> DEGRADED")
            return ContinuityStatus.DEGRADED

        return ContinuityStatus.CONSISTENT
