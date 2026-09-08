# ANNY Continuity Model

## Principles

1. **Durable Source of Truth**: Conversation memory and transient process state are ephemeral interfaces. The canonical operational state resides in the dynamically resolved operational repository. Customer Zero may use `GRECOITALICO/ANNY-OPERATIONAL`.
2. **Sequential Mission Protocol**: Operational work follows sequential active missions defined in `state/CURRENT_MISSION.yaml`.
3. **No Inference**: Missing evidence or unverified references result in `BLOCKED` or `DEGRADED` status rather than assumed defaults.

## Continuity Status Classification

- `CONSISTENT`: Canonical state, GitHub topology, and local runtime state agree with zero critical blockers.
- `DEGRADED`: System is functional, but non-critical references or active blockers exist.
- `CONFLICTED`: Canonical state and observed GitHub state disagree (e.g. missing repository or branch).
- `UNKNOWN`: Insufficient evidence to establish continuity status.
- `BLOCKED`: Required canonical references or authorization access are missing.

## Process Death & State Reconstruction

When an `ANNY-RUNTIME` process terminates or crashes:
1. Local generation counter increments.
2. Interrupted operations are marked in `journal/`.
3. The bootstrap resolver re-reads the operational repository from GitHub/local storage.
4. Operational state (Current Mission, Current Task, Next Action, Blockers) is reconstructed deterministically without relying on conversation context.
