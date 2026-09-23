# Legacy physical validation archive

These scripts are preserved as historical/manual validation surfaces. They are not canonical Runtime entrypoints, are not imported by the current execution path, and must not be counted as current certification or production controls.

Reference-closure was checked against the current repository search and the canonical CI workflow set before archival.

Archived paths:
- `scripts/legacy-validation/run_001c_a_r2_smoke.py`
- `scripts/legacy-validation/run_001c_b_physical_audit.py`
- `scripts/legacy-validation/run_001d_interactive_colab_validation.py`
- `scripts/legacy-validation/run_001g_diagnostic.py`
- `scripts/legacy-validation/run_001g_physical_validation.py`

Original paths removed from the executable scripts surface:
- `scripts/run_001c_a_r2_smoke.py`
- `scripts/run_001c_b_physical_audit.py`
- `scripts/run_001d_interactive_colab_validation.py`
- `scripts/run_001g_diagnostic.py`
- `scripts/run_001g_physical_validation.py`

Governance:
- Historical content is preserved in Git history.
- No production deployment, activation, Azure mutation, authority expansion, G5 recovery, or KIRA_P2 modification is implied.
