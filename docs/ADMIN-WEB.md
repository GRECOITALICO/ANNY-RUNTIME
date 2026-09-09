# ANNY Runtime Administration Web Panel

The ANNY Runtime includes a built-in, local-only web administration panel designed for observability, diagnostics, and credential management.

## Purpose

The Administration Panel is strictly an **observability and administration window** into the Runtime. 

It is NOT:
- An AI Agent or Provider (like ChatGPT or Claude)
- A replacement for the ANNY abstract organizational model
- A backdoor to bypass the Runtime Capability Gate
- A shell for executing arbitrary commands or GitHub mutations

All mutations (except specific administrative credential rotations) must still pass through the standard ANNY Authorization pipeline and CapabilityGate.

## Configuration

By default, the panel is active and binds only to the local loopback interface to prevent unauthorized LAN access.

```yaml
# ~/.anny-runtime/config.yaml
admin:
  enabled: true
  host: 127.0.0.1
  port: 3643
  session_ttl_seconds: 1800
```

### Port Selection
The default port is `3643`. The Runtime will auto-detect if the port is busy and select an alternative. It will **never** use port `3434`, as this is strictly reserved for the CONRRAD legacy architecture.

## Accessing the Panel

1. Start the Runtime (`anny-runtime start`)
2. Open a browser on the same machine to `http://127.0.0.1:3643/`
3. A local admin session will be automatically established for connections originating from `127.0.0.1`.

## Features

- **Dashboard:** Real-time health, operations, and status overview.
- **GitHub Connection:** Manage the runtime's GitHub identity securely.
- **Fabric Status:** Monitor durable state reconciliation with the operational repository.
- **Sessions & Operations:** View active ANNY sessions and executions without exposing their sensitive contextual payloads.
- **Diagnostics:** Run the equivalent of `anny-runtime doctor` visually.
