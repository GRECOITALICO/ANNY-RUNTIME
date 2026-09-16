"""
Bootstrap Access Verifier — Phase H.

Runs safe, non-destructive smoke tests for each critical capability
promised to be available at runtime.

RULES:
  - Tests MUST be non-destructive (read-only, no mutation, no side effects).
  - A failing smoke test → BLOCKED (never DEGRADED).
  - Tests are capability-scoped, not tool-scoped.
  - Evidence string is recorded for each test so ChatGPT can audit.
"""
import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AccessTestResult:
    """Result of a single capability smoke test."""
    capability_id: str
    passed: bool
    evidence: str
    error: Optional[str] = None


@dataclass
class AccessVerificationResult:
    """Aggregate result of Phase H."""
    passed: bool
    results: List[AccessTestResult] = field(default_factory=list)
    critical_failures: List[str] = field(default_factory=list)


class CriticalAccessVerifier:
    """
    Executes Phase H: safe smoke tests for all authorized capabilities.

    Only tests capabilities that are both authorized AND in the critical set.
    Non-critical capabilities are skipped (they fail at invocation time, not boot).
    """

    CRITICAL_CAPABILITIES = frozenset({
        "repository.read",
        "repository.search",
        "filesystem.inspect",
        "filesystem.list",
        "fabric.read",
        "runtime.status",
        "runtime.execution",
        "tool.resolve",
        "model.resolve",
        "worker.resolve",
    })

    def __init__(
        self,
        authorized_capabilities: List[str],
        data_dir: str,
        fabric_adapter=None,
        github_client=None,
    ):
        self._authorized = set(authorized_capabilities)
        self._data_dir = data_dir
        self._fabric = fabric_adapter
        self._github = github_client

    def verify(self) -> AccessVerificationResult:
        """Run all critical access smoke tests; any failure blocks Phase H."""
        result = AccessVerificationResult(passed=True)

        for cap_id in self.CRITICAL_CAPABILITIES:
            if cap_id not in self._authorized:
                result.passed = False
                result.critical_failures.append(cap_id)
                logger.error("Phase H: Critical capability NOT AUTHORIZED: %s", cap_id)
                result.results.append(AccessTestResult(
                    capability_id=cap_id,
                    passed=False,
                    evidence="UNAUTHORIZED",
                    error="Required critical capability is not authorized by the fabric contract."
                ))
                continue

            test_result = self._run_test(cap_id)
            result.results.append(test_result)

            if not test_result.passed:
                result.passed = False
                result.critical_failures.append(cap_id)
                logger.error(
                    "Phase H: smoke test FAILED for %s: %s",
                    cap_id,
                    test_result.error,
                )
            else:
                logger.info("Phase H: smoke test PASSED for %s", cap_id)

        return result

    def _run_test(self, cap_id: str) -> AccessTestResult:
        dispatch = {
            "repository.read": self._test_repository_read,
            "repository.search": self._test_repository_search,
            "filesystem.inspect": self._test_filesystem_inspect,
            "filesystem.list": self._test_filesystem_list,
            "fabric.read": self._test_fabric_read,
            "runtime.status": self._test_runtime_status,
            "runtime.execution": self._test_runtime_execution,
            "tool.resolve": self._test_tool_resolve,
            "model.resolve": self._test_model_resolve,
            "worker.resolve": self._test_worker_resolve,
        }
        fn = dispatch.get(cap_id)
        if fn is None:
            return AccessTestResult(
                capability_id=cap_id,
                passed=False,
                evidence="NO_TEST_DEFINED",
                error="Critical capability has no smoke test implementation.",
            )
        try:
            return fn()
        except Exception as e:
            return AccessTestResult(
                capability_id=cap_id,
                passed=False,
                evidence="EXCEPTION",
                error=str(e),
            )

    def _test_repository_read(self) -> AccessTestResult:
        cap = "repository.read"
        if self._github is None:
            return AccessTestResult(cap, False, "NO_GITHUB_CLIENT", "GitHub client not initialized")
        try:
            repos = self._github.list_repos()
            count = len(repos) if repos else 0
            return AccessTestResult(cap, True, f"REPOS_ACCESSIBLE count={count}")
        except Exception as e:
            return AccessTestResult(cap, False, "REPOS_FETCH_FAILED", str(e))

    def _test_filesystem_inspect(self) -> AccessTestResult:
        cap = "filesystem.inspect"
        try:
            stat = os.stat(self._data_dir)
            return AccessTestResult(
                cap, True,
                f"STAT_OK path={self._data_dir} mode={oct(stat.st_mode)}"
            )
        except OSError as e:
            return AccessTestResult(cap, False, "STAT_FAILED", str(e))

    def _test_filesystem_list(self) -> AccessTestResult:
        cap = "filesystem.list"
        try:
            entries = os.listdir(self._data_dir)
            return AccessTestResult(
                cap, True,
                f"LS_OK path={self._data_dir} count={len(entries)}"
            )
        except OSError as e:
            return AccessTestResult(cap, False, "LS_FAILED", str(e))

    def _test_fabric_read(self) -> AccessTestResult:
        cap = "fabric.read"
        if self._fabric is None:
            return AccessTestResult(cap, False, "NO_FABRIC_CLIENT", "Fabric adapter not initialized")
        try:
            node = self._fabric.read_node_config()
            node_id = getattr(node, "node_id", "UNKNOWN")
            return AccessTestResult(cap, True, f"NODE_CONFIG_READ node_id={node_id}")
        except Exception as e:
            return AccessTestResult(cap, False, "NODE_CONFIG_FAILED", str(e))

    @staticmethod
    def _not_implemented(capability_id: str) -> AccessTestResult:
        return AccessTestResult(
            capability_id,
            False,
            "NOT_IMPLEMENTED",
            "No non-destructive smoke test implementation exists for this critical capability.",
        )

    def _test_repository_search(self) -> AccessTestResult:
        return self._not_implemented("repository.search")

    def _test_runtime_status(self) -> AccessTestResult:
        return self._not_implemented("runtime.status")

    def _test_runtime_execution(self) -> AccessTestResult:
        return self._not_implemented("runtime.execution")

    def _test_tool_resolve(self) -> AccessTestResult:
        return self._not_implemented("tool.resolve")

    def _test_model_resolve(self) -> AccessTestResult:
        return self._not_implemented("model.resolve")

    def _test_worker_resolve(self) -> AccessTestResult:
        return self._not_implemented("worker.resolve")
