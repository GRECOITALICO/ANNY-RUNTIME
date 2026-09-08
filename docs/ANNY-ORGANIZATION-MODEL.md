# ANNY Organization Model

## Organization & Project Topology

ANNY manages operational continuity for organizations across three main repository categories:

1. **ANNY Core**:
   - `ANNY-RUNTIME`: Runtime execution engine codebase.
   - `ANNY-OPERATIONAL` / `ANNY`: Canonical operational memory, constitution, missions, and state.

2. **Customer Project Universe**:
   - `CONRRAD-CORE` and department repositories (`CONRRAD-PRODUCT`, `CONRRAD-ENGINEERING`, `CONRRAD-MARKETING`, etc.).
   - Discovered dynamically via GitHub organization discovery.

3. **Legacy Archive**:
   - Archived repositories preserved for historical evidence.

## Discovery Rules

- Organization discovery is performed read-only via GitHub API (`/user/orgs`, `/orgs/{org}/repos`).
- Repositories are grouped logically based on discovered topology without mutating repository settings or creating artificial remotes.
- Repository Fabric is currently unconfigured (`NOT_CONFIGURED`).
