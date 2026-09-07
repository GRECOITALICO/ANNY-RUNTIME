# ANNY-RUNTIME v0.2: Golden Installation Guide

This guide describes how to install and bootstrap ANNY-RUNTIME on a completely clean machine. 
It assumes no prior knowledge of ANNY and no existing state or cached credentials.

## 1. Prerequisites

Before installing, ensure your host environment meets the following requirements:
- **Operating System**: Linux
- **Python**: Version 3.11 or higher
- **System Utilities**: `git`, `systemd` (user-level access), `bash`
- **Network**: Internet access to install pip packages (specifically `cryptography>=41.0.0`)

## 2. Clone the Repository

Download the ANNY-RUNTIME source code. If you do not have direct access, obtain the latest v0.2 release tarball.
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

All checks should show `[PASS] ✓`. If `Python` or `Cryptography` fails, ensure your environment paths are correct.

## 5. Start the Runtime Server

Start the ANNY-RUNTIME background daemon:

```bash
systemctl --user start anny-runtime.service
```

*(If you do not want to use systemd, you can run it interactively via `anny-runtime server`)*.

Check its status:
```bash
anny-runtime status
```
This should show your new `Runtime ID` and state that Identity is `READY`.

## 6. First-Run Setup (Browser)

The Runtime is now waiting for administrative initialization. 

1. Open your web browser and navigate to: **http://127.0.0.1:3643**
2. You will be presented with the **ANNY RUNTIME First-Run Dashboard**.
3. **Identity Verification**: Confirm your new Runtime Identity pairs successfully.
4. **GitHub Connection**: Click "CONNECT GITHUB" and follow the OAuth/PAT flow. The credentials will be securely brokered and stored.
5. **Fabric Connection**: Click "CONNECT FABRIC" to register this installation with the central mesh.
6. **Enrollment**: Join an existing tenant or create a new one.

Once all steps are green, the status will show **ANNY READY**.

## 7. Execute First Operation

Through the UI or CLI (if configured), trigger a simple read-only operation (e.g. `System Status Check`).
Verify that the operation executes successfully inside a Level 1 Sandbox and produces a receipt in `~/.anny-runtime/journal`.

## 8. Persistence Check (Reboot)

To guarantee the installation is robust:
1. Reboot your machine.
2. The `anny-runtime.service` should start automatically.
3. Check `anny-runtime status` — your Runtime ID, Installation ID, and Fabric connection should be preserved without requiring re-authentication.

## 9. Troubleshooting

- **Admin panel unreachable**: Ensure port `3643` is not blocked by a local firewall, and verify the service is running (`systemctl --user status anny-runtime`).
- **Cryptography installation error**: Ensure `python3-dev` and build tools are installed if building from source.

## 10. Uninstall

To completely remove the runtime:

```bash
# Removes software, CLI, and systemd hooks. Preserves state (identity, journals).
anny-runtime uninstall

# Destructive removal of everything, including cryptographic identities:
anny-runtime uninstall --purge
```
