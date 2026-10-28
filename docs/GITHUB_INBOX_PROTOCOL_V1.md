# GitHub inbox protocol v1

The only Runtime inbox is the private GitHub Issues surface of
`GRECOITALICO/ANNY-RUNTIME-CANARY-INBOX`. The worker may add comments to, and
close, only the same authorized issue. It never writes repository contents,
branches, workflows, or another repository.

## Request

An issue title must begin exactly with `[ANNY TASK v1]`. Its body must be one
JSON object, with exactly these top-level fields:

```json
{
  "schema_version": "anny.github-task.v1",
  "request_id": "unique-request-id",
  "capability": "runtime.ping",
  "input": {},
  "constraints": {}
}
```

Only the configured GitHub actor may submit a request. The explicit `self`
configuration is resolved only once at activation to the principal of the
verified encrypted token; it is never accepted without that verification.
Supported capabilities
are `runtime.ping`, `filesystem.list_text_files`, and `filesystem.read_text`.
The latter accepts a simple `.txt` filename and `max_bytes` from 1 through
16384. The Runtime rejects unknown fields, malformed JSON, PRs, unauthorized
actors, paths, links, non-UTF-8 files, and policy violations before execution.

## Response and recovery

The worker posts an `anny.task-ack.v1` JSON comment before execution, then a
single `anny.task-result.v1` JSON comment containing issue number, request ID,
terminal status, result, and evidence correlation. It re-reads issue comments
to verify each publication before closing the issue.

State is written atomically with mode `0600` under the local Runtime data
directory. The design prevents a completed result from running twice after a
normal restart. It does not claim distributed exactly-once execution: a remote
GitHub outage after an execution can require replaying the stored terminal
result, which is why request and issue correlation remain mandatory.
