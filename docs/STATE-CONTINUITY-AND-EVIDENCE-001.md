# ANNY Runtime — State, Continuity and Evidence Contract 001

## 1. Purpose

Prevent loss of work when a model session ends, tokens are exhausted, a local process restarts, or an execution is interrupted.

## 2. Canonical hierarchy

```text
Organization / Authority
        ↓
Mission
        ↓
Task
        ↓
Step
        ↓
Execution / Operation
        ↓
Evidence / Receipt / Event
        ↓
State transition
        ↓
Next Action
```

Each layer must be addressable independently.

## 3. Work item identity

Every meaningful unit of work must have a stable identifier. At minimum:

```yaml
mission_id:
task_id:
step_id:
operation_id:
execution_id:
workspace_id:
actor_id:
```

An identifier may not be silently recycled for a different logical work item.

## 4. Continuity record

A continuity record should capture, as applicable:

- mission/task/step;
- actor;
- runtime identity;
- state before / state after;
- repository and branch;
- observed commits;
- files affected;
- tests;
- evidence references;
- decisions;
- blockers;
- Fabric bindings;
- current step;
- next action;
- handoff information.

## 5. Event record

Every important transition must be representable as an event containing at least:

```yaml
event_sequence:
mission_id:
task_id:
step_id:
actor:
event_type:
inputs:
commits:
evidence_refs:
test_refs:
decision:
state_change:
status:
verification:
certification:
```

## 6. Append-only principle

Continuity and event history are append-oriented. Corrections create a new evidence-bearing state/event; they do not erase the historical fact that an earlier state existed.

## 7. Two-phase mutation

Repository mutation operations must follow a prepare/finalize contract where the operation requires transactional continuity:

```text
PREPARE_MUTATION
    ↓
perform/validate controlled operation
    ↓
FINALIZE_MUTATION
    ↓
commit + evidence + state transition
```

The Runtime implementation introduced this continuity model in `0d1e37164a827d7adcc0f4c3defdaf55a13ff3`.

If a process dies between phases, reconciliation must classify the unfinished state instead of assuming success.

## 8. Reconciliation states

At minimum, the recovery model must distinguish states such as:

- prepared but not committed;
- committed but not finalized;
- orphaned / requires reconciliation;
- verified complete;
- failed;
- blocked.

## 9. Generation fencing

A recovered or stale worker must not continue writing under an old execution generation.

```text
old generation
     X
current generation
```

The execution context must be validated against the current runtime generation before effects occur.

## 10. Execution receipt

Every governed execution should produce a receipt containing, at minimum:

- receipt ID;
- operation/execution/runtime/workspace identity;
- actor/session/tenant;
- tool/capability;
- status;
- timestamps;
- generation;
- exit/result information;
- sanitized metadata.

No secret, private key, token or credential belongs in a browser-visible or durable evidence object unless a specific secure secret-storage contract explicitly allows it.

## 11. Evidence status

Evidence must preserve epistemic status:

```text
FACT
HYPOTHESIS
UNKNOWN
UNVERIFIED
BLOCKED
```

`UNKNOWN` means no sufficient evidence was found. `UNVERIFIED` means a claim or implementation exists but has not been validated in the current required context.

## 12. Checkpoint rule

A model session may end at any point. Before the end of a meaningful unit, the Runtime must be able to persist:

```yaml
checkpoint:
  mission_id:
  task_id:
  step_id:
  current_state:
  work_completed:
  work_unverified:
  evidence_refs:
  test_refs:
  commit_sha:
  blocker_refs:
  next_action:
  resume_conditions:
```

This is the minimum information required to continue without relying on chat history.


## 12A. Organizational interaction checkpoint rule

The organizational control plane imposes a stronger continuity requirement on ANNY/L0, registered L1 directors, and registered L2 workers:

constitution/INTERACTION-CHECKPOINT-RULE-001.yaml

Every meaningful operational response or interaction that advances work must create or reference a durable auditable checkpoint before continuation. A checkpoint records state and evidence; it never creates or expands authority.

Minimum checkpoint fields include actor, level, mission/task/step, current state, completed work, unverified work, evidence/test references, commit SHA when applicable, blockers, next action, resume conditions, and untouched/forbidden scope.

Missing checkpoint is a continuation blocker. Conversation history is never a substitute for the durable checkpoint.

## 13. Handoff rule

A handoff is valid only when it contains enough information for another actor/session to identify:

- what was done;
- what was not done;
- what evidence proves completion;
- what remains unverified;
- what the next allowed action is;
- what must not be touched.

## 14. No false completion

The following are not proof of completion:

- code exists;
- a UI button exists;
- a method returns `True` in a stub;
- a test mock passes;
- an old commit once passed;
- a browser page renders;
- an actor says it is done.

Completion requires the evidence appropriate to the hito.

## 15. Reconstruction principle

A new session should be able to reproduce the previous conclusion from repository evidence without asking the previous session what happened.

That is the acceptance test for durable continuity.
