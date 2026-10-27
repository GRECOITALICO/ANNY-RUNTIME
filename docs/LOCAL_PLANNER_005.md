# Local Planner 005 — Ollama adapter and operational path

## Fixed local boundary

`OllamaLocalProvider` only uses these fixed loopback URLs:

- `http://127.0.0.1:11434/api/tags`
- `http://127.0.0.1:11434/api/generate`

It accepts neither an endpoint from a request nor a model-selected endpoint.
Redirects, non-200 responses, timeouts, invalid JSON, empty responses, and
responses over 64 KiB are rejected. Generation uses non-streaming JSON output,
`num_predict=256`, and a maximum request timeout of sixty seconds. It cannot
execute a tool, shell command, script, or model-returned text.

## Availability states

Discovery lists a local model as `LOCAL_MODEL_UNVERIFIED`; that state does not
make the planner available. Only the explicit, bounded inference probe can set
`LOCAL_MODEL_READY` with `inference_status=VERIFIED`. The Control Center reads
the persisted result only and never triggers that probe.

## Operational entry point

To verify a particular model without planning or executing a repository task:

```bash
PYTHONPATH=. python cli/main.py local-planner-verify --model-id qwen2.5-coder:1.5b --timeout-seconds 60
```

This command first reads the local loopback catalog and requires an exact model
identifier match. It then sends one fixed JSON-only probe through
`OllamaLocalProvider`. Success requires precisely `{"ok":true}`; HTTP 200 alone
is insufficient. The outcome is persisted, without the prompt or raw response,
at `native-executions/planning/local-inference-verification.json` alongside the
updated discovery record. The evidence includes the task identifier, initial
discovery, provider and model, HTTP status, duration, timeout, validation
outcome, response hash, result hash, and a sanitized failure reason where needed.

The verification entry point never creates a plan, workspace, or execution. It
does not alter dispatcher capabilities, permissions, or Podman constraints.

## Planning entry point

```bash
PYTHONPATH=. python cli/main.py local-plan "Add a bounded display-name change to the isolated fixture"
```

The command performs the explicit probe, persists its sanitized outcome, and
continues only when a real local Ollama model returns the required structured
response. It then follows:

`REQUEST → LOCAL_PROVIDER → PLAN_PROPOSAL → INDEPENDENT_VALIDATION → AUTHORIZED_EXECUTION → VERIFIED_EVIDENCE`

The independent validator matches the provider/model to discovery, verifies the
raw response hash and that its embedded plan equals the submitted plan, then
applies the pre-existing repository-change policy. Only the existing native
dispatcher can create a private fixture workspace and run Podman.

## Current machine evidence

Task 008 records real machine evidence only after its dedicated local verification
command completes. It is intentionally distinct from unit tests and does not
certify planning or engineering-task execution.
