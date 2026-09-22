# ANNY-RUNTIME v0.4.x: Golden Installation Guide

This guide describes how to install and bootstrap ANNY-RUNTIME on a completely clean machine.
It assumes no prior knowledge of ANNY and no existing state or cached credentials.

The canonical runtime version is defined by `runtime/core/version.py`. Release artifact identity is governed by `docs/RELEASE-IDENTITY-001.md`.

## 1. Prerequisites

Before installing, ensure your host environment meets the following requirements:
- **Operating System**: Linux
- **Python**: Version 3.11 or higher
- **System Utilities**: `git`, `systemd` (user-level access), `bash`
- **Network**: Internet access to install pip packages (specifically `cryptography>=41.0.0`)

## 2. Clone the Repository

Download the ANNY-RUNTIME source code. For a release artifact, use an artifact whose version, source commit and SHA-256 checksum are recorded under the release identity contract.

```bash
git clone https://github.com/GRECOITALICO/ANNY-RUNTIME.git
cd ANNY-RUNTIME
```

## 3. Install the Runtime

Execute the primary installation script. This script will create necessary directories, set up a Python virtual environment, install dependencies, and register the systemd service.

```bash
bash scripts/install.sh
```

**What this does:**
1. Creates `~/.local/share/anny-runtime` (Software) and `~/.anny-runtime` (Data/State).
2. Generates an initial cryptographic `RuntimeIdentity` securely stored in `~/.anny-runtime/identity`.
3. Symlinks the CLI to `~/.local/bin/anny-runtime`.
4. Installs the `anny-runtime.service` to your user systemd directory.

## 4. Verify Installation

Check that the installation succeeded by running the internal diagnostics tool:

```bash
anny-runtime doctor
```

Treat any reported PASS as informational until the full Runtime verification suite has been executed for the target milestone.

## 5. Start the Runtime Server

Start the ANNY-RUNTIME background daemon:

```bash
systemctl --user start anny-runtime.service
```

(If you do not want to use systemd, you can run it interactively via `anny-runtime server`.)

Check its status:
```bash
anny-runtime status
```

This should report the Runtime identity and current state from the canonical runtime control surfaces.

## 6. First-Run Setup (Browser)

The Runtime may expose its administrative control surface locally after startup.

1. Open the configured local admin endpoint.
2. Follow the current authentication/initialization flow exposed by the running Runtime.
3. Confirm Runtime identity and authorization state through the actual Runtime evidence/receipt surfaces.
4. Do not treat a green UI state as certification, routing authorization, or production readiness without the corresponding durable evidence.

## 7. Execute First Operation

Through the UI or CLI (if configured), trigger a simple read-only operation.

Verify that the operation executes through the canonical execution path and produces a durable receipt/evidence record. Do not infer successful execution from an audit log entry alone.

## 8. Persistence Check (Reboot)

To verify installation persistence:
1. Reboot the machine.
2. Confirm the `anny-runtime.service` starts automatically when configured.
3. Check `anny-runtime status` and the durable Runtime state/evidence.

## 9. Troubleshooting

- **Admin panel unreachable**: verify the configured admin port and the running service state rather than relying on a hard-coded port assumption.
- **Cryptography installation error**: ensure `python3-dev` and required build tools are available when building dependencies from source.

## 10. Uninstall

To completely remove the runtime:

```bash
# Removes software, CLI, and systemd hooks. Preserves state (identity, journals).
anny-runtime uninstall

# Destructive removal of everything, including cryptographic identities:
anny-runtime uninstall --purge
```

The `--purge` operation is destructive and must not be treated as a normal troubleshooting step.
