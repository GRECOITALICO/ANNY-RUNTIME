PATH | CLASSIFICATION | CALLERS | REPLACEMENT | ACTION | RETIREMENT_GATE
--- | --- | --- | --- | --- | ---
runtime/telemetry/aggregator.py | RETAIN_WITH_BLOCKER | runtime/admin/routes.py (handle_processing_matrix, handle_processing_events); runtime/admin/server.py (admin_context injection) | None – canonical implementation | RETAIN: active production code providing get_matrix() and get_events() used by /api/processing/* routes | None; blocked on DETERMINISTIC-EXECUTION-SUBSTRATE-001-VERIFY
runtime/telemetry/collector.py | RETAIN_WITH_BLOCKER | runtime/telemetry/stream.py (get_live); runtime/admin/routes.py (handle_telemetry_timeline); runtime/telemetry/aggregator.py (query) | None – canonical implementation | RETAIN: provides emit(), query(), get_live(), get_timeline() for all observability consumers | None; blocked on DETERMINISTIC-EXECUTION-SUBSTRATE-001-VERIFY
runtime/telemetry/telemetry.py | RETAIN_WITH_BLOCKER | All telemetry consumers via TelemetryEnvelope import | None – canonical model | RETAIN: TelemetryEnvelope dataclass is the sole event contract; no legacy duplication observed | None
runtime/telemetry/scrubber.py | RETAIN_WITH_BLOCKER | runtime/telemetry/collector.py (scrub_metadata call in emit()) | None – canonical implementation | RETAIN: scrub_metadata enforces credential redaction on all emitted events | None
runtime/telemetry/stream.py | RETAIN_WITH_BLOCKER | runtime/admin/routes.py (handle_telemetry_stream via /api/v1/telemetry/stream) | None | RETAIN: SSE streaming endpoint for live telemetry; active consumer of get_live() | None
runtime/telemetry/context.py | RETAIN_WITH_BLOCKER | Execution pipeline if trace_context is used | None | RETAIN: trace context propagation; no identified legacy duplicate | None
runtime/admin/routes.py (/telemetry/live) | RETAIN_WITH_BLOCKER | HTML page route registered at line 72; returns telemetry_live_page() template | runtime/admin/templates.py:telemetry_live_page | RETAIN: active Control Center page route; no replacement or removal; RUNTIME_VERIFICATION=NOT_ESTABLISHED | Blocked until browser runtime verification is performed
runtime/admin/routes.py (/telemetry/timeline) | RETAIN_WITH_BLOCKER | HTML page route registered at line 73; calls telemetry_collector.get_timeline(limit=100) | runtime/admin/templates.py:telemetry_timeline_page | RETAIN: active Control Center page route; no replacement or removal; RUNTIME_VERIFICATION=NOT_ESTABLISHED | Blocked until browser runtime verification is performed
runtime/admin/routes.py (/api/processing/matrix) | RETAIN_WITH_BLOCKER | HTTP route registered at line 74; calls aggregator.get_matrix(filters); exercised by test_t11_processing_matrix_http_boundary | runtime/telemetry/aggregator.py:get_matrix | RETAIN: verified HTTP API endpoint; tested via real socket in test suite | None for this route
runtime/admin/routes.py (/api/processing/events) | RETAIN_WITH_BLOCKER | HTTP route registered at line 75; calls aggregator.get_events(filters, limit); exercised by test_t11_processing_matrix_http_boundary | runtime/telemetry/aggregator.py:get_events | RETAIN: verified HTTP API endpoint; tested via real socket in test suite | None for this route
runtime/admin/server.py | RETAIN_WITH_BLOCKER | Entry point for AdminServer; injects telemetry_aggregator into admin_context for all route handlers | runtime/telemetry/aggregator.py | RETAIN: canonical admin server; telemetry aggregator injection is the live wiring path | None
tests/test_deterministic_observability_001.py | RETAIN_WITH_BLOCKER | DETERMINISTIC-OBSERVABILITY-001 verification suite (13 tests: T-01..T-11) | None – authoritative test suite | RETAIN: active, green test suite per current focused run | None; re-run required at each milestone close
docs/evidence/ (OBSERVABILITY-001-*.md) | HISTORICAL_ONLY | Referenced by MILESTONE-LEDGER-001.yaml evidence field | None | HISTORICAL_ONLY: AG-008 intermediate evidence artifacts; superseded by AG-009 test-run JSON and closeout | Retired by AG-009 closeout
docs/evidence/DETERMINISTIC-OBSERVABILITY-001-POST-CLOSEOUT-AUDIT-001..004.md | HISTORICAL_ONLY | Referenced in prior ledger entries | None | HISTORICAL_ONLY: audit trail documents; do not delete; not callable production code | None
docs/LEGACY-CLEANUP-REVIEW-001.md | RETAIN_WITH_BLOCKER | Referenced by MILESTONE-LEDGER-001.yaml | This document | RETAIN: replaces prior narrative version; now contains mandatory contractual table | Updated by AG-009
docs/PRE-EXISTING-FAILURES-TRIAGE-001.md | RETAIN_WITH_BLOCKER | Referenced by MILESTONE-LEDGER-001.yaml | This document | RETAIN: replaces prior narrative version; now contains per-failure triage schema or explicit zero-failure record | Updated by AG-009


## 2026-09-22 root scratch cleanup

The following root-level files were classified as obsolete development tooling and removed from the cleanup branch:

- `diag_browser.py` — one-off browser diagnostic; no production caller.
- `fix.py`, `patch.py`, `patch2.py`, `patch_all.py`, `patch_broker.py`, `patch_broker_submit.py`, `patch_dump.py`, `patch_error.py`, `patch_physical.py` — one-off source-rewrite/patch scripts that directly mutate implementation or historical test files; superseded by committed source and canonical tests.
- `generate_001b_s2_evidence.py`, `generate_evidence_002.py` — historical evidence-generation scripts tied to old scratch paths and providers; evidence is retained as artifacts, not regenerated through these scripts.
- `list_tools.py` — one-off local MCP bridge inspection script.
- `test.js`, `test_node.js`, `test_backend_node.py`, `test_cdp.py`, `test_cdp2.py`, `test_cdp_hide.py`, `test_describe_node.py` — root-level manual browser/CDP diagnostics; canonical Runtime tests remain under `tests/`.

The repository workflows reviewed on the cleanup base execute canonical `runtime/**` modules and tests under `tests/`; none reference the removed root paths.

Deletion is therefore safe for this milestone. Git history remains the historical record of the removed files.


Additional root-test cleanup on 2026-09-22:

Removed obsolete manual root tests:
- `test_dev_broker.py`
- `test_dynamic_tools.py`
- `test_fetch.py`
- `test_find_cdp.py`
- `test_find_cdp2.py`
- `test_find_click.py`
- `test_isolated.py`
- `test_isolated_nav.py`
- `test_js.py`
- `test_obj.py`
- `test_persistent.py`
- `test_x11.py`

These files were manual diagnostics/probes outside the canonical `tests/` tree. Several hardcoded local scratch paths; `test_fetch.py` was incomplete. No canonical workflow references these root files.


### Systemd entrypoint reconciliation — 2026-09-22

- `packaging/systemd/anny-runtime.service` was removed on 2026-09-22 because it was a divergent startup definition using `python -m runtime.core.engine`.
- `scripts/install.sh` is the canonical installer and generates a service executing `/usr/local/bin/anny-runtime server` (system mode) or the equivalent user-local CLI path.
- `cli/main.py::cmd_server` calls `runtime.admin.server.start_admin_server()`, which creates the canonical admin/runtime path.
- There is now one supported Runtime service-generation source: the installer. Git history preserves the removed static unit.


### Root metadata cleanup — 2026-09-22

Removed from the active root tree after reference checks:
- `evidence_001d.json` — historical Google Colab/browser evidence from MISSION-001D; no current workflow or code reference.
- `023_QWEN_INTEGRATION_EVIDENCE.md` — historical Qwen integration certification note tied to an old scratch path; canonical Runtime tests remain under `tests/test_023_qwen_integration.py`.
- `DEPENDENCY-INVENTORY.json` — stale secondary dependency inventory; contained source paths such as `runtime/adapters/...` that are not current tree paths and presented a second dependency truth beside `requirements.txt`.

Preserved:
- `requirements.txt` as the active packaging dependency declaration;
- release checksum metadata;
- README/license/git metadata.


### Root directory cleanup — 2026-09-22

Removed:
- `scratch/` and its one-off evidence/source-rewrite scripts.
- `adapters/fabric_client.py` and empty `adapters/__init__.py`; this was a disconnected stub `FabricClient` that always returned `FABRIC_UNAVAILABLE` and was not referenced by the Runtime code path.

Preserved:
- `systemd/anny-browser-broker.service`, because it targets the real `runtime/browser/broker_server.py` and remains a distinct browser-broker service surface.
- `audit/` remains historical evidence and is not an active Runtime source.
- `tools/certification/**` was removed on 2026-09-22; historical commit history is the audit trail.


### Audit/certification surface cleanup — 2026-09-22

Removed:
- `audit/customer_zero_008/**` — historical customer-zero onboarding audit snapshots; not referenced by current workflows and superseded by canonical durable evidence in the control-plane repository.
- `tools/certification/**` — historical certification/evidence generators and logs tied to obsolete mission snapshots; no current workflow references these paths.

The Runtime repository remains the execution substrate. Current organizational/certification evidence belongs in the canonical control plane rather than in old Runtime-side report generators.
