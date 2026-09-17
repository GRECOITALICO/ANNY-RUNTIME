# DETERMINISTIC-OBSERVABILITY-001 — CLOSEOUT CONTRACT SPECIFICATION 001

## Serial
AG-012

## Purpose
This document defines the durable, mathematically valid closeout contract for
milestone verification. It explicitly excludes commit self-reference and
separates implementation identity from evidence identity.

---

## 1. Implementation Identity (`commit_sha`)

The `commit_sha` field in the ledger identifies the **implementation commit**:
the Git commit that introduces the functional code, tests, and configuration
constituting the milestone's deliverable.

**Requirements:**
- Must exist and be resolvable in GitHub.
- Must be an ancestor of every `evidence_closeout_commit`.
- Must remain stable: it does not change when later evidence commits are added.
- Is **not** required to equal any evidence or closeout commit.
- Is **not** required to contain its own SHA in any file.

**Canonical value for DETERMINISTIC-OBSERVABILITY-001:**
```
c8f21e7888227cc64a02ec9c9bd008e3ed463307
```

---

## 2. Evidence Identity (`evidence_closeout_commits`)

The `evidence_closeout_commits` list records one or more Git commits that
contain durable evidence of the milestone's verification or audit history.

**Requirements:**
- Each SHA must exist and be resolvable in GitHub.
- Each SHA must be reachable (via `git log`) from `refs/heads/main`.
- Each SHA must have the `implementation_commit_sha` as an ancestor
  (`git merge-base --is-ancestor <impl> <evidence>` must exit 0).
- The list may grow over time as additional audits are committed.
- No entry is required to equal `commit_sha`.

**Verification command:**
```bash
git merge-base --is-ancestor <impl_sha> <evidence_sha> && echo PASS || echo FAIL
git cat-file -t <evidence_sha>  # must return "commit"
```

---

## 3. Ancestry Verification

To establish that evidence is downstream of implementation:

```bash
git merge-base --is-ancestor <impl_sha> <evidence_sha>
# exit 0 = PASS, non-zero = FAIL
```

This must pass for every commit listed in `evidence_closeout_commits`.

---

## 4. Branch Inclusion Verification

To establish that a commit is reachable from `main`:

```bash
git branch --contains <sha> | grep -q '\bmain\b' && echo PASS || echo FAIL
```

Or equivalently:

```bash
git merge-base --is-ancestor <sha> refs/heads/main && echo PASS || echo FAIL
```

This must pass for every commit listed in `evidence_closeout_commits` and for
the `current_documentation_anchor`.

---

## 5. Current Documentation Anchor

The `current_documentation_anchor.commit_sha` identifies the durable Git commit
that contains the current governing documentation for the milestone.

**Requirements:**
- Must exist and be resolvable in GitHub.
- Must be reachable from `refs/heads/main`.
- Is updated to the most recent evidence/governance commit after each serial.
- Is **never** set to a value that does not yet exist (no forward reference).
- Is **not** required to equal the implementation commit or any specific
  evidence commit; it is simply the most recent governance commit at time of
  writing.

---

## 6. Conditions for `VERIFIED`

A milestone may be set to `VERIFIED` only when ALL of the following are true:

1. `implementation_commit_sha` resolves as a `commit` object in GitHub.
2. At least one `evidence_closeout_commit` resolves as a `commit` object in
   GitHub.
3. `implementation_commit_sha` is an ancestor of every
   `evidence_closeout_commit`.
4. Every `evidence_closeout_commit` is reachable from `refs/heads/main`.
5. `current_documentation_anchor.commit_sha` resolves and is reachable from
   `refs/heads/main`.
6. All required evidence files listed in `evidence_files` exist in the tree of
   the most recent `evidence_closeout_commit`.
7. All previously `VERIFIED` milestones remain `VERIFIED` (no regression).
8. The observability test suite passes at the implementation commit (13/13
   focused observability tests green).

---

## 7. Conditions Forcing `IMPLEMENTED_NOT_VERIFIED`

A milestone must remain or be reset to `IMPLEMENTED_NOT_VERIFIED` if ANY of
the following is true:

- `implementation_commit_sha` does not resolve in GitHub.
- No `evidence_closeout_commit` resolves in GitHub.
- `implementation_commit_sha` is not an ancestor of any
  `evidence_closeout_commit`.
- Any `evidence_closeout_commit` is not reachable from `refs/heads/main`.
- `current_documentation_anchor` does not resolve.
- Any required evidence file is absent from the evidence commit tree.
- A previously `VERIFIED` milestone has been regressed.
- The observability test suite has not been executed or is not green.

---

## 8. Explicit Exclusion of Commit Self-Reference

**The following is expressly prohibited:**

> Requiring a Git commit to contain its own final SHA in any file within its
> own tree.

**Rationale:** A Git commit's SHA is determined by hashing the entire tree,
parent list, author, timestamp, and message. Any file within the tree that
references the commit's SHA would create a fixed-point requirement: the content
of the file affects the SHA, but the SHA must be known before the file is
written. This is equivalent to finding a SHA-1 fixed point, which is
computationally infeasible without intentional SHA-1 manipulation.

**Consequence:** The `commit_sha` field in the ledger identifies the
implementation commit. It does not need to equal the commit that writes or
updates the ledger entry. The ledger entry for a milestone may be updated in a
subsequent commit, and that subsequent commit SHA is then the
`current_documentation_anchor`, not the `commit_sha`.

---

## Contract Status
REPAIRED — AG-012

## Author Serial
AG-012
