# Formal Release Identity Contract (RELEASE-IDENTITY-001)

This document establishes the formal contract for how ANNY Runtime defines, verifies, and distributes releases.

## Core Concepts

A "Release Identity" is the unequivocal mapping between a semantic version, a specific state of the source code, and the final binary distribution artifact. 

### VERSION
The single source of truth for the ANNY Runtime version is `runtime/core/version.py`. This file must be updated before cutting a release.
The CLI, installer, release builder, and physical-evidence helper load this
value from that Python module; none may derive a second version with text
parsing or a hard-coded literal.

### SOURCE COMMIT
Every release must map to exactly one 40-character Git commit SHA. The repository working tree must be clean (no uncommitted changes). We never use a short SHA as the canonical source identity, though it may be used in artifact names for brevity.

### ARTIFACT
The binary distribution artifact is a `tar.gz` archive containing the exported repository state, bundled securely. The naming convention is `ANNY-RUNTIME-v<VERSION>-<SHORT-SHA>.tar.gz`.

### HASH
To ensure integrity, every artifact is accompanied by a SHA-256 checksum file: `ANNY-RUNTIME-v<VERSION>-<SHORT-SHA>.tar.gz.sha256`. The hash must be independently re-computable and match the artifact exactly.

### EMBEDDED IDENTITY
During the build process, the runtime's own metadata (`runtime/core/version.py` within the tarball) is dynamically updated to burn in the `SOURCE COMMIT` and `BUILD TIMESTAMP`. This guarantees that an extracted runtime can always self-report its exact provenance.

### BUILD TIMESTAMP
The UTC time the artifact was produced.

### PROVENANCE
The verifiable chain linking the `ARTIFACT` back to its `SOURCE COMMIT` through the `EMBEDDED IDENTITY` and `HASH`.

### DEPENDENCY PREFLIGHT
`requirements.txt` is the canonical dependency declaration. The explicit
import-to-distribution mapping in `scripts/preflight_check.py` is an
implementation detail used to check it; `DEPENDENCY-INVENTORY.json` is
historical/derived evidence only and cannot affect installer admission.
The installer runs the preflight through its newly created virtual environment
in isolated Python mode. A clean preflight proves only that this environment's
declared dependencies are installed and compatible; it does not certify a
release or a running service.

## Artifact Scope and Historical Metadata

Only a release artifact accompanied by its actual checksum payload can advance
to **IDENTIFIED**. A checksum sidecar without the matching archive is retained
as historical metadata and is `UNVERIFIED` for byte-level integrity. Local
ignored build outputs are likewise `LOCAL_UNPUBLISHED` until a durable release
record and publication process exist. Neither category is an active release.

`scripts/physical-cert-helper.sh` may export operator evidence. Its archive is
an evidence bundle, not an ANNY Runtime release artifact and must not be used
as release provenance.

## Lifecycle States

It is critical to distinguish between the stages of a release:

1. **IDENTIFIED**: An artifact has been generated, hashed, and mapped to a commit. It has a formal identity.
2. **TESTED**: The artifact has passed the required suite of automated and manual tests.
3. **VERIFIED**: The artifact's provenance, integrity, and test results have been durably recorded and audited.
4. **RELEASED**: The artifact has been formally published and distributed for use. (Note: A verified identity does NOT automatically mean the artifact is released).
5. **ACTIVE**: The release is currently the deployed and running version in a production environment.

## Reproducibility

Currently, the release builder injects a `BUILD TIMESTAMP` into the embedded identity. 
- **Source Identity Reproducible**: `true`. Two builds from the same commit will map to the exact same source state and version.
- **Byte-Identical Reproducible**: `false`. Because the build time is dynamically embedded, two separate build executions on the exact same commit will produce artifacts with different SHA-256 hashes due to the changing timestamp string.
