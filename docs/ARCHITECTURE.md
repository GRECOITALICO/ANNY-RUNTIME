# Architecture

The ANNY-RUNTIME operates autonomously from its deployment source directory. Once installed, the source directory is no longer required.

## Distribution Model
- Distributed as a standalone Linux Service.
- Dependencies are isolated inside a private virtual environment (`venv`) managed automatically by `install.sh`.
- The system operates independent of Python packaging semantics (no `pyproject.toml` is used for runtime operations).

## State Layout (System-Wide)
- **`/var/lib/anny-runtime/`**: Persistent runtime state. Contains cryptographic identities, secrets, workspaces, and operation journals. This directory is strictly owned by the unprivileged service user and protected by `chmod 700`.
- **`/opt/anny-runtime/`**: The static application files and isolated Python virtual environment.
- **`/usr/local/bin/anny-runtime`**: The global CLI entry point.
- **`/etc/systemd/system/anny-runtime.service`**: The daemon configuration. No secrets or tokens are stored in the systemd configuration.

## Independence
The system is deliberately designed to separate the local state of the host running the agent from the local user operating the machine. A system-wide runtime maintains only one canonical identity.
