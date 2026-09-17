# ANNY Runtime — Recovery Playbook 001

## Purpose

This is the operational procedure to use after:

- token exhaustion;
- loss of ChatGPT/Claude context;
- local Runtime restart;
- machine restart;
- interrupted mutation;
- network loss;
- GitHub outage;
- failed update;
- corrupted workspace;
- partial implementation.

## Rule 1 — Never resume from memory

Start from the repository and durable evidence.

## Rule 2 — Determine the last trusted point

Build this tuple:

```yaml
remote_head:
runtime_identity:
tenant_id:
fabric_node:
last_verified_milestone:
current_mission:
current_task:
current_state:
next_action:
blockers:
```

If any required value cannot be established, do not infer it.

## Rule 3 — Reconcile before mutate

```text
read
→ verify
→ reconcile
→ decide
→ mutate
→ evidence
```

Never:

```text
remember
→ mutate
→ hope
```

## Token-loss procedure

### Step 1

Open `docs/RECONSTRUCTION-MASTER-001.md`.

### Step 2

Run the bootstrap reconstruction procedure in `docs/BOOTSTRAP-RECONSTRUCTION-PROTOCOL-001.md`.

### Step 3

Verify the actual `main` HEAD and compare it with the commit recorded by the last milestone.

### Step 4

Read the milestone record and evidence references.

### Step 5

Read current mission/task/next-action artifacts if available in the active workspace/repository.

### Step 6

Run the tests associated with the last verified milestone.

### Step 7

Determine whether the last action completed, partially completed, or failed.

### Step 8

If the state is ambiguous, create a reconciliation checkpoint rather than continuing the old action.

### Step 9

Resume only the durable `NEXT_ACTION` after prerequisites are verified.

### Step 10

At the next checkpoint, append evidence and a new milestone record.

## Interrupted mutation procedure

If an operation was interrupted:

1. inspect continuity records;
2. inspect event records;
3. inspect repository HEAD/history;
4. inspect workspace state;
5. inspect execution receipts;
6. compare expected and actual state;
7. classify the operation;
8. reconcile or roll back only under the defined contract.

Do not blindly rerun a mutation because it may duplicate an already committed effect.

## Runtime restart procedure

After process restart:

```text
load persistent identity
→ load generation
→ load continuity journal
→ recover interrupted operations
→ reconcile stale workers
→ verify Fabric/GitHub binding
→ rerun required bootstrap gates
→ expose state
```

## Update failure procedure

If an update fails:

```text
FAILED
→ preserve known-good active runtime
→ retain candidate/evidence
→ classify failure
→ rollback if activation had occurred and policy permits
→ verify health
→ record outcome
```

The current updater defines rollback state conceptually, but its methods are not yet proof of real rollback behavior. fileciteturn114file0

## Sync failure procedure

A Sync failure must never be transformed into a successful or activated state.

Required final state:

```text
FAILED
or
BLOCKED
or
UNKNOWN
```

The canonical SYNC contract requires a trace/evidence record and explicitly separates Sync from Stage and Activate. fileciteturn117file0

## GitHub/Fabric divergence

If Runtime and remote repository disagree:

```text
STOP
→ record both observations
→ identify authoritative source
→ reconcile
→ rerun bootstrap
```

No local cache is allowed to silently override remote truth.

## Recovery output

Every recovery must finish with a durable checkpoint:

```yaml
recovery_id:
reason:
observed_head:
pre_recovery_state:
recovered_state:
last_verified_milestone:
reconciliation_result:
remaining_blockers:
next_action:
evidence_refs:
```

## Human handoff

When handing the Runtime to another human or model, provide only the durable reconstruction tuple plus links/IDs to evidence. Never rely on a narrative such as "we were almost done".
