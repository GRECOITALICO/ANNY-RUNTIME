# ANNY-RUNTIME Installation Guide

ANNY-RUNTIME can be installed in two modes:

## 1. System-Wide Installation (Recommended)
This installs the runtime globally and executes the systemd service strictly as an unprivileged user (your current `SUDO_USER`).

```bash
git clone <PUBLIC_REPOSITORY>
cd ANNY-RUNTIME
sudo bash scripts/install.sh
```

**Architecture Setup**:
- **Binary**: `/usr/local/bin/anny-runtime`
- **Application Files**: `/opt/anny-runtime/`
- **State and Identities**: `/var/lib/anny-runtime/`
- **Service**: `/etc/systemd/system/anny-runtime.service`

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now anny-runtime
```

## 2. User-Local Installation
Use this if you do not have root privileges. The runtime will be scoped strictly to your user directory.

```bash
bash scripts/install.sh
```

**Architecture Setup**:
- **Binary**: `~/.local/bin/anny-runtime`
- **Application Files & State**: `~/.local/share/anny-runtime/` and `~/.anny-runtime/`
- **Service**: `~/.config/systemd/user/anny-runtime.service`

Enable and start the service:
```bash
systemctl --user daemon-reload
systemctl --user enable --now anny-runtime
```

## Verification
Access the admin interface at `http://127.0.0.1:3643`. Run `anny-runtime doctor` to verify system health.
