# Legacy physical validation archive

These scripts are preserved as historical/manual validation surfaces. They are not canonical Runtime entrypoints, are not imported by the current execution path, and must not be counted as current certification or production controls.

Reference-closure was checked against the current repository search and the canonical CI workflow set before archival.

Archived paths:
- `scripts/legacy-validation/run_001c_a_r2_smoke.py`
- `scripts/legacy-validation/run_001c_b_physical_audit.py`
- `scripts/legacy-validation/run_001d_interactive_colab_validation.py`
- `scripts/legacy-validation/run_001g_diagnostic.py`
- `scripts/legacy-validation/run_001g_physical_validation.py`

Historical test surface retired from active pytest discovery in Batch 7
(`BATCH-7-FULL-SUITE-RECONCILIATION-20260923-001`):

- Former `tests/test_001f_harness_hardening.py` exercised the archived
  interactive Colab harness's host preflight and marker classifier. It is
  retained in Git history because it records what that harness used to test;
  it is not a current Runtime CI or certification contract and must not import
  `scripts/legacy-validation/` from active Runtime tests.
- Current replacements are the active broker resolver/IPC tests in
  `tests/test_001d_r4_governance.py`, `tests/test_001g_broker_security.py`,
  `tests/test_001g_managed_browser.py`, and the current Runtime admission
  tests in `tests/test_authorization_path_batch3.py`. They do not claim remote
  Colab execution or certification.

Original paths removed from the executable scripts surface:
- `scripts/run_001c_a_r2_smoke.py`
- `scripts/run_001c_b_physical_audit.py`
- `scripts/run_001d_interactive_colab_validation.py`
- `scripts/run_001g_diagnostic.py`
- `scripts/run_001g_physical_validation.py`

Governance:
- Historical content is preserved in Git history.
- The `scripts/legacy-validation/` directory is a historical/manual surface;
  no current Runtime module or active pytest test imports it.
- No production deployment, activation, Azure mutation, authority expansion, G5 recovery, or KIRA_P2 modification is implied.
