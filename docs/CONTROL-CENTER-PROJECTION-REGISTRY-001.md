# Control Center Projection Registry

## Purpose

The ANNY Runtime Control Center is an extensible operational surface. Its visible cards,
tables, navigation targets and drill-downs are projections of authoritative Runtime,
CONRRAD, GitHub, Fabric, evidence and related sources.

The projection registry is the canonical contract for those projections.

## Inventory rule

The registry is **open-ended**.

- `master_inventory_boundary = OPEN_ENDED_1000_PLUS`
- `inventory_limit = null`
- `initial_p0_viewport_target = 349`

The value 349 controls initial prominence and viewport planning only. It never limits the
master inventory. P1/P2/P3 definitions remain registered and discoverable.

Do not manufacture definitions solely to reach a target count.

## Projection definition

Every projection definition carries at least:

- stable `projection_id`
- human-readable `title`
- `section`
- `priority`
- `current_status`
- `truth_class`
- `source_authority`
- `freshness`
- `evidence_ref`
- `failure_reason`
- `dependencies`
- `visibility_policy`
- `route_or_detail`
- `renderer`
- `sort_order`
- `tags`
- `implementation_status`

## Truth rules
The bootstrap boundary now enforces the same CONRRAD-first sequence that the Control Center exposes:
`CONRRAD_BOOTSTRAP_PREFLIGHT` -> `CONRRAD_MANIFEST_AND_TRUST_VERIFIED` -> `CONRRAD_DEPENDENCY_REGISTRY_LOADED` -> GitHub.
These gates require an injected external CONRRAD client. A missing client fails closed; GitHub is not contacted through this bootstrap path.
Successful dependency completion requires every mandatory service to report `ONLINE_VERIFIED` and `VERIFIED` trust.
The bootstrap report now exposes an explicit `bootstrap_state` and `conrrad_dependencies` transport channel.
An empty dependency list means that no external CONRRAD registry observation has been attached to the report;
the Control Center must continue to project the safe NOT_CONFIGURED/UNKNOWN state in that case.



The Control Center's `/api/status` projection is a read-only observation surface, not an authority source.
The CONRRAD boundary is considered verified only when all eight mandatory services have externally
supplied records with `online_status=ONLINE_VERIFIED` and `trust_status=VERIFIED`.

When no external registry observation exists, the UI renders the eight required service names with
`online_status=NOT_CONFIGURED`, `trust_status=UNKNOWN`, `evidence_ref=UNKNOWN`, and a `BLOCKED` gate.
Configured Runtime values such as a Fabric organization/repository are not treated as live proof of
external connectivity, admission, trust, or tenant binding.

UI rendering must preserve the distinction between:

- `FACT`
- `HYPOTHESIS`
- `UNKNOWN`
- `UNVERIFIED`

A projection must not convert missing evidence into a positive operational status.

`source_authority` identifies where the projection is expected to obtain truth. It does
not grant authority to the UI.

The Control Center also exposes descriptive `truth_sources` metadata through `/api/status`.
These labels identify the observed source used for primary displayed fields; they never upgrade
the associated `truth_class` or operational state.

The server-provided `/api/status` timestamp is rendered as `TRUTH AS OF`. The browser clock is
not used as the verification timestamp. `configured_endpoint`, when present, is explicitly
configuration-derived and is not evidence of reachability. `main_execution_verified` remains
false until independent authoritative execution evidence establishes it.

## Availability rules

Implementation states are:

- `BOUND`: an existing runtime/UI capability is wired to the projection.
- `PARTIAL`: some projection surface exists but authoritative or complete data is missing.
- `PLANNED`: intentionally represented in the master inventory but not yet implemented.
- `BLOCKED`: implementation exists or is described, but safe execution/display is blocked.
- `NOT_IMPLEMENTED`: explicitly unsupported in the current Runtime.

Navigation uses `ACTIVE`, `ALIAS`, or `PLANNED`. Planned navigation is rendered as
non-clickable rather than as a broken route.

## API

The read-only endpoint is:

`GET /api/control-center/projections`

Supported query parameters:

- `q`
- `priority`
- `section`
- `implementation_status`
- `truth_class`
- `freshness`
- `tag`
- `projection_id`
- `limit` (1..200)
- `offset` (>= 0)

The API returns the complete registry summary plus the filtered page. Exact
`projection_id` queries are used for drill-down.

## UI behavior

The Control Center registry surface supports:

- text search
- priority filtering
- implementation-status filtering
- truth-class filtering
- pagination
- manual refresh
- projection detail drill-down

Dynamic backend-fed values must be escaped before HTML insertion. New UI code should
prefer DOM construction and `textContent` over raw `innerHTML`.

## Safe lifecycle

The projection registry is read-only. It does not authorize or mutate Runtime state.

In particular, SYNC `stage`, `activate`, and `rollback` must remain visibly blocked or
not implemented while the underlying backend capabilities are stubs or fail-closed.
The first-level Control Center shell exposes `SYNC NOW` and reads `/api/sync/status` as a
separate governed surface. SYNC is not equivalent to VERIFY, STAGE, ACTIVATE or ROLLBACK.
`STAGE`, `ACTIVATE` and `ROLLBACK` remain disabled in the GUI while their physical lifecycle
implementations are stubs or fail-closed. A `VERIFIED` sync candidate therefore never causes
those controls to become enabled by itself.

No Control Center projection may bypass CONRRAD-first ordering, Runtime authorization,
or evidence requirements.

## Extension rule

When a new operational surface is created:

1. add its stable projection definition;
2. declare source authority and truth class;
3. declare freshness/evidence expectations;
4. declare dependencies and implementation state;
5. bind the route/panel/detail surface;
6. add regression coverage;
7. keep older priority definitions in the registry.

The registry is the catalog; the viewport is only a view of the catalog.
