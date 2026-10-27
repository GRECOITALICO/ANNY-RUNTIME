# L0 audit 011 — governed delegation coverage

## Scope and source limits

This audit is read-only against `CONRRAD-ENGINEERING` and `ANNY-OPERATIONAL`.
The former checkout contains nine structural artifacts and no canonical sheet
catalog or the claimed 1,560 candidate records. Consequently, it is not
evidence-based to classify those 1,560 purported sheets or promote any of their
identifiers to canonical IDs. The machine-readable matrix in
`L0_COVERAGE_MATRIX_011.json` instead covers the twelve Runtime capability
definitions actually observed.

`ANNY-OPERATIONAL/state/CURRENT_STATE.yaml` was read only. It keeps R1A review
active and M8 unexecuted; this audit neither mutates it nor authorizes M8 work.

## Observed governed path

`ANNY request → CapabilityRegistry → RuntimePolicy → Orchestrator / ExecutorSelector
→ ExecutionManager → WorkerManager → executor → validator/evidence → result`.

For non-inferential capabilities, the Orchestrator selects `deterministic-v1`
before model assessment; the model registry is not consulted to satisfy that
work. The deterministic executor implements filesystem metadata/list/hash,
repository inspect/search/read/diff, and artifact metadata. The Task 011
fixture test executes those eight handlers and checks the Manager-selected
deterministic route has no model identity and preserves the disabled-network
policy. `schema.validate` is registered but has no deterministic handler;
`fabric.read` needs a configured Fabric client and was not run. Neither is
claimed as successful.

## Inference coverage and blocking finding

The only registered inferential candidate is `document.classify`. The verified
local Ollama catalog contains `qwen2.5-coder:1.5b`, but the governed
`WorkerManager` LOCAL_MODEL branch does not use Ollama: it requires
`QWEN_MODEL_PATH` and `llama_cpp` via `QwenModelExecutor`. There is no typed,
authorized Ollama implementation registered in `ModelRegistry`, nor an IPC
bridge into the network-disabled task container. A direct Ollama call would be
diagnostic only and cannot establish the governed L0 delegation path.

Therefore **zero inferential Runtime executions passed end-to-end** in this
audit. The concrete next deficiency is to add a bounded local-Ollama executor
implementation to the existing `CapabilityRegistry → Orchestrator →
WorkerManager` path, with a typed request/result contract, deterministic output
validator, evidence writer, and the existing network/secret isolation intact.
No parallel router or container network exception is justified by this audit.

## Luna discrepancy

`ModelRegistry._register_initial_models()` still seeds `model_id="luna"` as an
AVAILABLE `REMOTE_MODEL`, and `WorkerManager` carries a legacy fallback string
for it. That conflicts with the stated architecture: Luna is ChatGPT acting as
ANNY/L0, not a Runtime model provider. It was not invoked or used as fallback.
This audit records it as a legacy-registry discrepancy; correcting it requires a
separate compatibility migration because existing registry tests and profiles
reference it.

## Evidence actually observed

Local commands, all with exit code 0:

- `pytest -q tests/test_deterministic_local_execution.py tests/test_ag041_orchestration_kernel.py tests/test_023c_qwen_executor.py tests/test_022_model_registry.py` — 52 passed, 5 skipped.
- `pytest -q tests/test_l0_audit_011.py tests/test_deterministic_local_execution.py tests/test_workspace_execution_018.py tests/test_registry_019.py tests/test_worker_020.py tests/test_ag041_orchestration_kernel.py tests/test_ag043_executor_registry_reconciliation.py tests/test_023c_qwen_executor.py tests/test_022_model_registry.py tests/test_local_planner.py tests/test_local_native_execution.py tests/test_control_center_projections.py tests/test_batch9_conrrad_truth.py tests/test_sync_service.py tests/test_control_center_http_surface.py tests/test_local_conrrad_simulator_provider.py` — 247 passed, 5 skipped.
- `ollama list` — exact `qwen2.5-coder:1.5b` present; no model download.

`PYTHONPATH=. pytest -q` was also attempted and exited 1: 810 passed, 26
skipped, 3 failed, and 5 errors. The five distribution errors require a clean
working tree; the remaining failures are outside this audit's changed files.
They are recorded as checkout-wide pre-existing validation blockers, not as a
successful full-suite result.

These demonstrate deterministic routes and the local model's availability only.
They do not certify general autonomy, universal L0 coverage, or an inferential
end-to-end Runtime path.
