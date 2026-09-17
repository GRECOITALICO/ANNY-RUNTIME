# ANNY Runtime — Build, Test and Release Discipline 001

## 1. Goal

Ensure a future engineer/model can reconstruct not only the source tree but the proof that each milestone was valid.

## 2. Build phases

```text
RECONSTRUCT
   ↓
DISCOVER
   ↓
IMPLEMENT
   ↓
UNIT TEST
   ↓
INTEGRATION TEST
   ↓
NEGATIVE / FAIL-CLOSED TEST
   ↓
EVIDENCE CAPTURE
   ↓
MILESTONE RECORD
   ↓
COMMIT
```

## 3. Baseline tests

Before changing a P0 subsystem:

1. establish the current commit;
2. run the applicable deterministic bootstrap tests;
3. record pass/fail counts;
4. capture environment limitations;
5. never overwrite evidence from the prior state.

The deterministic bootstrap milestone `a9771d11e3bf49fb1170a8a1140fc9887ac6e97a` recorded 42 passing tests at that point in history. A future session must rerun the current test suite instead of treating the old count as current evidence.

## 4. Test classes

### Unit

Prove individual contracts and state transitions.

### Integration

Prove module-to-module boundaries, persistence, API behavior and repository/Fabric interactions.

### Negative / fail-closed

Prove:

- missing identity blocks;
- missing tenant blocks;
- stale generation blocks;
- missing authority blocks;
- unavailable source remains UNKNOWN/BLOCKED;
- invalid signature/provenance does not pass;
- sync failure does not become success;
- activation does not occur during Sync-only operation.

### Recovery

Interrupt operations at each durable boundary and verify that restart/recovery can classify and reconcile them.

### Replay / idempotency

Repeat the same request and prove that duplicated execution does not create an unbounded or contradictory state transition.

## 5. Evidence capture

Each milestone should retain:

```yaml
commit_sha:
branch:
changed_paths:
test_command:
test_result:
negative_tests:
runtime_environment:
external_dependencies:
evidence_artifacts:
known_failures:
```

## 6. Release gate

Do not use these terms interchangeably:

```text
CODE EXISTS
IMPLEMENTED
TESTED
VERIFIED
CERTIFIED
RELEASED
ACTIVE
```

Each means a different evidence threshold.

## 7. Sync release tests

Before declaring Sync complete, tests must cover at least:

- successful discovery and comparison;
- no-update/current state;
- candidate discovered and verified;
- source unavailable;
- authority unknown;
- corrupt/invalid candidate;
- repeated Sync idempotency;
- Sync without activation;
- explicit Stage;
- explicit Activate;
- failed activation;
- rollback after a verified activation failure;
- durable trace/evidence on success and failure;
- sanitized API responses.

## 8. Recovery release tests

For every mutation protocol:

```text
before prepare
mid-prepare
between prepare and finalize
after commit before finalize
normal finalization
post-restart reconciliation
```

The expected recovery classification must be documented.

## 9. Browser/API release tests

Verify:

- primary Control Center loads before long bootstrap work completes;
- live state is refreshed from backend truth;
- bootstrap verification is distinct from Sync;
- controls become unavailable when required authority is absent;
- secrets never appear in HTML/JSON/telemetry;
- errors remain explicit and non-successful.

## 10. Release notes requirements

Every meaningful release must state:

- current version;
- source commit;
- bootstrap status;
- test result;
- changed contracts;
- evidence references;
- known blockers;
- rollback method;
- whether Sync is implemented/verified/live/evidenced.

## 11. No false green

A green test that exercises a stub, mock, or unreachable code path is not proof of product functionality. Acceptance tests must prove the real operational path whenever the milestone claims live behavior.
