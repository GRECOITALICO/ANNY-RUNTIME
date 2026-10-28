# Local plan 009 — bounded real model attempt

Task `ANNY-RUNTIME-LOCAL-PLAN-009` permits exactly one model-planned change to
the static `local.python.text-normalizer.fixture.v1` fixture. The model returns
only a JSON summary plus complete replacement content for `text_normalizer.py`
and `test_text_normalizer.py`. Runtime supplies the fixture identity and hashes,
capability, permitted paths, patch preimages, resource limits, runner command,
task identity, and execution steps.

The validator rejects malformed or oversized JSON, paths other than those two
files, duplicates, missing files, removal of `test_collapses_whitespace`, absent
`initials` test coverage, a proposal/spec hash mismatch, an unverified model,
or divergent reuse of the fixed task id. A rejection is persisted with
`execution=null`; it cannot create a workspace or invoke Podman.

## Real attempt, 2026-10-27

The verified local `qwen2.5-coder:1.5b` model produced JSON for the requested
Spanish `initials` task. Runtime assigned plan task id
`ANNY-RUNTIME-LOCAL-PLAN-009-3ac7388cefcb6448` and checked the registered
fixture hash `75d32b5577b08179204409ec9cadcb7d55eb3283064c05b859ef7f586dd9f70c`.
It rejected the proposal with `MODEL_PROPOSAL_LACKS_INITIALS_TEST`: the model
preserved the legacy whitespace test but supplied no new `initials` tests.

No private workspace was created, no Podman runner was invoked, and no Runtime
or canonical-repository file was changed. The durable, mode-`0600` evidence is
`local://native-executions/planning/ANNY-RUNTIME-LOCAL-PLAN-009-968bf1a6e1d8d1c5.json`.
Its response hash is
`71fcd87d0d0e81f70a44f70b6ba42bbe833fa91b4f83e7537b708849b7d52bcd` and its
result hash is
`8e9ec7270f6dba4814133fb790dc8bf06072fa183419dd41b2c701cfb77f00fe`.

This is a controlled failure demonstration, not a claim of general autonomy or
equivalence with Codex.
