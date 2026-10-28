# Local plan 010 — one bounded correction

Task `ANNY-RUNTIME-LOCAL-PLAN-010` keeps model authority limited to complete
content for the two registered fixture files. Runtime gives the model the
immutable fixture source and hashes, then alone builds the task id, capability,
allowlist, preimage hashes, limits, command, evidence references, and steps.

Before a workspace exists, Runtime parses both proposed files with `ast`. It
requires `initials(value)`, valid Python, preservation of the non-trivial
`test_collapses_whitespace`, and recognisable tests for ordinary multiword
initials, whitespace normalization, empty input, spaces-only input, and
`TypeError` on non-string input.

The orchestrator allows at most two model generations: an initial proposal and,
only after a deterministic correctable validation denial, one prompt containing
that denial. It revalidates the complete corrected content from scratch. Any
final denial persists `execution=null`; no workspace or Podman runner is
created. A valid initial result never triggers a correction. Re-running an
already persisted Task 010 returns its evidence and cannot execute again.

The Task 009 denial remains separate and unchanged. Task 010 evidence uses its
own `ANNY-RUNTIME-LOCAL-PLAN-010-*` identity and is written locally with mode
`0600`; the Control Center reads it through its read-only local-plan evidence
endpoint.

## Real attempt, 2026-10-27

The recorded Task 010 attempt used two local generations. The first response
was denied as `MODEL_PROPOSAL_LACKS_NORMAL_WORDS_TEST`. Runtime sent that exact
deterministic deficiency as the sole correction reason. The second full-file
response was denied as `MODEL_PROPOSAL_LACKS_INITIALS_TEST`: it preserved the
legacy test but still did not call `initials` in its new tests. No workspace was
created, no Podman runner was invoked, and `execution` remains `null`.

The durable evidence is
`local://native-executions/planning/ANNY-RUNTIME-LOCAL-PLAN-010-3ac7388cefcb6448.json`
with result hash
`e5496992e09f24fddc362687608175efe0ea25ca0fe6c111bfe525607cad2c5e`.
