# ANNY Runtime

The ANNY Runtime is the physical local execution environment for the ANNY autonomous system.

## The Experience

```text
install ANNY Runtime once
↓
connect GitHub
↓
Runtime starts with OS
↓
open ChatGPT or Claude
↓
connect same GitHub
↓
"inicia bootstrap como ANNY"
↓
"inicia bootstrap como KIRA"
↓
ANNY uses local Runtime for execution
```

## Architecture

This is NOT another autonomous agent wrapper (like OpenHands or Aider). This is a foundational capability execution gateway:

```text
ANNY (Cloud DTO)
    ↓
ANNY Runtime Protocol (v0.1)
    ↓
ANNY Runtime (Local)
    ↓
ANNY-owned execution paths
    ↓
OS (Linux / WSL2)
```

It is permanently resident on your machine (via systemd), strictly scoped by Tenant/Workspace, and completely independent of any specific AI model provider.
