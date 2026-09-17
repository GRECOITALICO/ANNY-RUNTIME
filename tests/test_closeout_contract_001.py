"""
tests/test_closeout_contract_001.py

Focused contract tests for DETERMINISTIC-OBSERVABILITY-001 closeout.
Serial: AG-012

Covers:
  test_implementation_commit_resolves
  test_evidence_closeout_commit_resolves
  test_implementation_is_ancestor_of_closeout
  test_closeout_is_reachable_from_main
  test_current_documentation_anchor_resolves
  test_verified_prior_milestone_not_regressed
  test_self_referential_commit_hash_is_not_required
"""

import subprocess
import os
import yaml
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER_PATH = os.path.join(REPO_ROOT, "docs", "MILESTONE-LEDGER-001.yaml")

IMPL_SHA = "c8f21e7888227cc64a02ec9c9bd008e3ed463307"
SYNC_F_SHA = "3f0903bbd82af6c5af051c23ac10a591786b08e6"


def git(*args):
    result = subprocess.run(
        ["git", "-C", REPO_ROOT] + list(args),
        capture_output=True, text=True
    )
    return result


def load_ledger():
    with open(LEDGER_PATH, "r") as f:
        return yaml.safe_load(f)


def find_milestone(ledger, milestone_id):
    for m in ledger.get("milestones", []):
        if m.get("id") == milestone_id:
            return m
    return None


class TestCloseoutContract001:

    def test_implementation_commit_resolves(self):
        """The implementation commit must resolve as a real commit object."""
        result = git("cat-file", "-t", IMPL_SHA)
        assert result.returncode == 0, f"cat-file failed: {result.stderr}"
        assert result.stdout.strip() == "commit", (
            f"Expected 'commit', got: {result.stdout.strip()}"
        )

    def test_evidence_closeout_commit_resolves(self):
        """Every evidence_closeout_commit must resolve as a real commit object."""
        ledger = load_ledger()
        milestone = find_milestone(ledger, "DETERMINISTIC-OBSERVABILITY-001")
        assert milestone is not None, "Milestone not found in ledger"

        evidence_commits = milestone.get("evidence_closeout_commits", [])
        assert len(evidence_commits) > 0, (
            "No evidence_closeout_commits registered in ledger"
        )

        for sha in evidence_commits:
            result = git("cat-file", "-t", sha)
            assert result.returncode == 0, (
                f"SHA {sha} does not resolve: {result.stderr}"
            )
            assert result.stdout.strip() == "commit", (
                f"SHA {sha}: expected 'commit', got: {result.stdout.strip()}"
            )

    def test_implementation_is_ancestor_of_closeout(self):
        """Implementation commit must be an ancestor of every evidence closeout commit."""
        ledger = load_ledger()
        milestone = find_milestone(ledger, "DETERMINISTIC-OBSERVABILITY-001")
        assert milestone is not None

        evidence_commits = milestone.get("evidence_closeout_commits", [])
        assert len(evidence_commits) > 0

        for evidence_sha in evidence_commits:
            result = git("merge-base", "--is-ancestor", IMPL_SHA, evidence_sha)
            assert result.returncode == 0, (
                f"Implementation {IMPL_SHA} is NOT ancestor of evidence {evidence_sha}"
            )

    def test_closeout_is_reachable_from_main(self):
        """Every evidence closeout commit must be reachable from refs/heads/main."""
        ledger = load_ledger()
        milestone = find_milestone(ledger, "DETERMINISTIC-OBSERVABILITY-001")
        assert milestone is not None

        evidence_commits = milestone.get("evidence_closeout_commits", [])
        assert len(evidence_commits) > 0

        for sha in evidence_commits:
            result = git(
                "merge-base", "--is-ancestor", sha, "refs/heads/main"
            )
            assert result.returncode == 0, (
                f"Evidence commit {sha} is NOT reachable from refs/heads/main"
            )

    def test_current_documentation_anchor_resolves(self):
        """The current_documentation_anchor commit must resolve and be on main."""
        ledger = load_ledger()
        anchor = ledger.get("current_documentation_anchor", {})
        sha = anchor.get("commit_sha")
        assert sha and sha.strip(), "current_documentation_anchor.commit_sha is empty"

        result = git("cat-file", "-t", sha)
        assert result.returncode == 0, (
            f"Documentation anchor {sha} does not resolve: {result.stderr}"
        )
        assert result.stdout.strip() == "commit", (
            f"Anchor {sha}: expected 'commit', got: {result.stdout.strip()}"
        )

        # Must be reachable from main
        reachable = git("merge-base", "--is-ancestor", sha, "refs/heads/main")
        assert reachable.returncode == 0, (
            f"Anchor {sha} is NOT reachable from refs/heads/main"
        )

    def test_verified_prior_milestone_not_regressed(self):
        """SYNC-IMPLEMENTATION-001-F must remain VERIFIED and its commit must resolve."""
        ledger = load_ledger()
        milestone = find_milestone(ledger, "SYNC-IMPLEMENTATION-001-F")
        assert milestone is not None, "SYNC-IMPLEMENTATION-001-F not found in ledger"
        assert milestone.get("status") == "VERIFIED", (
            f"SYNC-IMPLEMENTATION-001-F regressed: status={milestone.get('status')}"
        )

        sha = milestone.get("commit_sha")
        assert sha, "SYNC-IMPLEMENTATION-001-F has no commit_sha"
        result = git("cat-file", "-t", sha)
        assert result.returncode == 0, (
            f"SYNC-IMPLEMENTATION-001-F commit {sha} does not resolve"
        )
        assert result.stdout.strip() == "commit"

    def test_self_referential_commit_hash_is_not_required(self):
        """
        Verify that no ledger rule requires a commit to contain its own SHA.
        The rules section must not mandate commit_sha == HEAD or
        any variant of self-referential hash equality.
        """
        ledger = load_ledger()
        rules = ledger.get("rules", [])
        prohibited_phrases = [
            "commit_sha == current head",
            "ledger.commit_sha == final head",
            "commit must contain its own sha",
            "final head == commit_sha",
        ]
        for rule in rules:
            rule_lower = str(rule).lower()
            for phrase in prohibited_phrases:
                assert phrase.lower() not in rule_lower, (
                    f"Rule contains prohibited self-reference mandate: '{rule}'"
                )

        # Confirm the explicit exclusion rule exists
        exclusion_found = any(
            "self-reference" in str(r).lower() or "self-referential" in str(r).lower()
            or "not a valid verification primitive" in str(r).lower()
            for r in rules
        )
        assert exclusion_found, (
            "No explicit rule found that excludes commit self-reference. "
            "Expected a rule containing 'self-referential' or "
            "'not a valid verification primitive'."
        )
