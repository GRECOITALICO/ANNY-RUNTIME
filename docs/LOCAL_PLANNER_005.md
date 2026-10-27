# Local Planner 005 — Ollama adapter and operational path

## Fixed local boundary

`OllamaLocalProvider` only uses these fixed loopback URLs:

- `http://127.0.0.1:11434/api/tags`
- `http://127.0.0.1:11434/api/generate`

It accepts neither an endpoint from a request nor a model-selected endpoint.
Redirects, non-200 responses, timeouts, invalid JSON, empty responses, and
responses over 64 KiB are rejected. Generation uses non-streaming JSON output,
`num_predict=256`, and a maximum request timeout of fifteen seconds. It cannot
execute a tool, shell command, script, or model-returned text.

## Availability states

Discovery lists a local model as `LOCAL_MODEL_UNVERIFIED`; that state does not
make the planner available. Only the explicit, bounded inference probe can set
`LOCAL_MODEL_READY` with `inference_status=VERIFIED`. The Control Center reads
the persisted result only and never triggers that probe.

## Operational entry point

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

At the last explicit inspection, Ollama client version `0.32.5` was installed,
but no loopback service or local model was reachable. The persisted state is
`LOCAL_RUNTIME_WITHOUT_MODEL`; no inference or model-planned execution occurred.
