# LEGACY-CLEANUP-POLICY-001

Status: ACTIVE
Scope: ANNY Runtime

## Purpose

Prevent an obsolete implementation path, compatibility branch, mock path, or superseded contract from remaining available long enough to become the default path in a later milestone.

## Rule

Every milestone that introduces or replaces an execution path MUST perform a legacy-surface review in the same milestone cycle.

The review must identify:

- superseded modules and functions;
- duplicate implementations of the same contract;
- obsolete HTTP routes and UI controls;
- compatibility aliases with no remaining caller;
- mock/fallback behavior that can fabricate a valid-looking runtime result;
- stale tests that validate only the superseded path;
- stale documentation or evidence that can be mistaken for current state.

## Deletion gate

A legacy surface may be deleted only after its replacement is present and the current test/evidence chain no longer depends on it.

When deletion is safe, removal MUST occur in the same milestone rather than being deferred indefinitely.

If deletion is not yet safe, the milestone MUST record:

- exact legacy path;
- current callers/dependencies;
- replacement path;
- reason deletion is blocked;
- explicit next milestone for removal.

## Fail-closed requirements

The cleanup process MUST NOT:

- silently preserve an obsolete path as a hidden fallback;
- convert an unavailable executor/model into a mock success;
- mark a stubbed activation as ACTIVATED;
- delete evidence that is still required to establish a historical milestone.

Historical evidence may remain as evidence, but it must be clearly labeled historical and must not be treated as current implementation truth.

## Verification

A milestone closeout is not complete until the legacy review is represented in durable evidence with:

1. inspected legacy surfaces;
2. deleted/deprecated paths;
3. remaining exceptions and their removal gate;
4. current test results;
5. actual commit SHA containing the cleanup.

## ANNY Runtime principle

New work should make the future state smaller and more canonical, not accumulate parallel branches. When a contract becomes canonical, the previous implementation path must either be removed or explicitly quarantined with a documented retirement condition.
