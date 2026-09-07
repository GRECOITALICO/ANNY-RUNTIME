#!/bin/bash
set -e

echo "Installing ANNY Runtime v0.2..."

# 1. Platform Detection
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
  echo "Error: ANNY-RUNTIME requires Linux."
  exit 1
fi

# 2. Dual-Mode Paths
if [ "$EUID" -eq 0 ]; then
  echo "Running in SYSTEM-WIDE mode."
  INSTALL_DIR="/opt/anny-runtime"
  DATA_DIR="/var/lib/anny-runtime"
  BIN_DIR="/usr/local/bin"
  SYSTEMD_DIR="/etc/systemd/system"
  SERVICE_USER="${SUDO_USER:-root}"
  
  if [ "$SERVICE_USER" == "root" ]; then
      echo "WARNING: Running ANNY-RUNTIME as root is not recommended."
  fi
else
  echo "Running in USER-LOCAL mode."
  INSTALL_DIR="$HOME/.local/share/anny-runtime"
  DATA_DIR="$HOME/.anny-runtime"
  BIN_DIR="$HOME/.local/bin"
  SYSTEMD_DIR="$HOME/.config/systemd/user"
  SERVICE_USER="$USER"
fi

# 3. Idempotence Check
POLICY="UPGRADE"
if [ ! -d "$INSTALL_DIR" ]; then
    POLICY="INSTALL"
elif [ -f "$INSTALL_DIR/venv/bin/python3" ]; then
    POLICY="REPAIR"
fi

echo "[POLICY] $POLICY"

# 4. Directory Creation & Permissions
mkdir -p "$INSTALL_DIR"
mkdir -p "$DATA_DIR/identity"
mkdir -p "$DATA_DIR/journal"
mkdir -p "$DATA_DIR/workspaces"
mkdir -p "$DATA_DIR/secrets"

if [ "$EUID" -eq 0 ]; then
    chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"
    chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
fi

chmod 700 "$DATA_DIR/identity"
chmod 700 "$DATA_DIR/secrets"

# 5. Environment & Dependencies
# Run pip as the service user to avoid polluting root cache, unless we are root
if [ "$EUID" -eq 0 ] && [ "$SERVICE_USER" != "root" ]; then
    sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -q -r "$(dirname "$0")/../requirements.txt" || true
else
    python3 -m venv "$INSTALL_DIR/venv"
    "$INSTALL_DIR/venv/bin/pip" install -q -r "$(dirname "$0")/../requirements.txt" || true
fi

# 6. CLI Registration
mkdir -p "$BIN_DIR"
cat << EOF > "$BIN_DIR/anny-runtime"
#!/bin/bash
EXEC_DIR=\$(dirname \$(readlink -f \$0))
INSTALL_DIR="$INSTALL_DIR"
if [ ! -d "\$INSTALL_DIR" ]; then
    INSTALL_DIR="\$(pwd)" # Fallback for dev mode
fi
export PYTHONPATH="\$INSTALL_DIR:\$PYTHONPATH"
exec "\$INSTALL_DIR/venv/bin/python3" "\$INSTALL_DIR/cli/main.py" "\$@"
EOF
chmod +x "$BIN_DIR/anny-runtime"

# Copy source code if not in dev mode (for standalone)
if [ "$(dirname "$0")" != "$INSTALL_DIR/scripts" ]; then
    cp -r "$(dirname "$0")/.."/* "$INSTALL_DIR/"
    if [ "$EUID" -eq 0 ]; then
        chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
    fi
fi

# 7. Systemd Registration
mkdir -p "$SYSTEMD_DIR"

if [ "$EUID" -eq 0 ]; then
    cat << EOF > "$SYSTEMD_DIR/anny-runtime.service"
[Unit]
Description=ANNY Runtime Node
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
ExecStart=$BIN_DIR/anny-runtime server
Restart=on-failure
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONUNBUFFERED=1

# Hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ProtectHome=yes
RestrictSUIDSGID=yes

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload || true
    systemctl enable anny-runtime.service || true
else
    cat << EOF > "$SYSTEMD_DIR/anny-runtime.service"
[Unit]
Description=ANNY Runtime Node
After=network.target

[Service]
Type=simple
ExecStart=$BIN_DIR/anny-runtime server
Restart=on-failure
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload || true
    systemctl --user enable anny-runtime.service || true
fi

# 8. Initial Identity Creation
if [ "$EUID" -eq 0 ] && [ "$SERVICE_USER" != "root" ]; then
    sudo -u "$SERVICE_USER" "$BIN_DIR/anny-runtime" identity-bootstrap || true
else
    "$BIN_DIR/anny-runtime" identity-bootstrap || true
fi

echo "Installation complete."
echo "Run 'anny-runtime doctor' to verify."
echo "Admin panel will be available at http://127.0.0.1:3643"
