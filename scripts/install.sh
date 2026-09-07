#!/bin/bash
set -e

# Fail-fast trap
function cleanup_on_fail {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo ""
        echo "======================================"
        echo "INSTALLATION_FAILED (Exit code: $exit_code)"
        echo "======================================"
        if [ -n "$STAGING_DIR" ] && [ -d "$STAGING_DIR" ]; then
            echo "Rolling back partial installation from $STAGING_DIR..."
            if [ "$EUID" -eq 0 ]; then
                sudo rm -rf "$STAGING_DIR"
            else
                rm -rf "$STAGING_DIR"
            fi
        fi
        exit $exit_code
    fi
}
trap cleanup_on_fail EXIT

echo "Installing ANNY Runtime v0.2..."

# 1. Platform Detection
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
  echo "Error: ANNY-RUNTIME requires Linux."
  exit 1
fi

# 2. Dual-Mode Paths and Configuration
if [ "$EUID" -eq 0 ]; then
  echo "Running in SYSTEM-WIDE mode."
  INSTALL_MODE="system"
  FINAL_INSTALL_DIR="/opt/anny-runtime"
  DATA_DIR="/var/lib/anny-runtime"
  BIN_DIR="/usr/local/bin"
  SYSTEMD_DIR="/etc/systemd/system"
  SERVICE_USER="${SUDO_USER:-root}"
  
  if [ "$SERVICE_USER" == "root" ]; then
      echo "WARNING: Running ANNY-RUNTIME as root is not recommended."
  fi
else
  echo "Running in USER-LOCAL mode."
  INSTALL_MODE="user"
  FINAL_INSTALL_DIR="$HOME/.local/share/anny-runtime"
  DATA_DIR="$HOME/.anny-runtime"
  BIN_DIR="$HOME/.local/bin"
  SYSTEMD_DIR="$HOME/.config/systemd/user"
  SERVICE_USER="$USER"
fi

# 3. Transactional Staging
STAGING_DIR="${FINAL_INSTALL_DIR}.staging.$$"
echo "Using staging directory: $STAGING_DIR"

# 4. Idempotence Check
POLICY="UPGRADE"
if [ ! -d "$FINAL_INSTALL_DIR" ]; then
    POLICY="INSTALL"
elif ! "$FINAL_INSTALL_DIR/venv/bin/python3" -c "import sys" 2>/dev/null; then
    POLICY="REPAIR"
fi

echo "[POLICY] $POLICY"

# 5. Directory Creation & Permissions
mkdir -p "$STAGING_DIR"
mkdir -p "$DATA_DIR/identity"
mkdir -p "$DATA_DIR/journal"
mkdir -p "$DATA_DIR/workspaces"
mkdir -p "$DATA_DIR/secrets"

if [ "$EUID" -eq 0 ]; then
    chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"
    chown -R "$SERVICE_USER:$SERVICE_USER" "$STAGING_DIR"
fi

chmod 700 "$DATA_DIR/identity"
chmod 700 "$DATA_DIR/secrets"

# 6. Environment & Dependencies
echo "Installing dependencies in staging..."
if [ "$EUID" -eq 0 ] && [ "$SERVICE_USER" != "root" ]; then
    sudo -u "$SERVICE_USER" python3 -m venv "$STAGING_DIR/venv"
    sudo -u "$SERVICE_USER" "$STAGING_DIR/venv/bin/pip" install -q -r "$(dirname "$0")/../requirements.txt"
else
    python3 -m venv "$STAGING_DIR/venv"
    "$STAGING_DIR/venv/bin/pip" install -q -r "$(dirname "$0")/../requirements.txt"
fi

# 7. Copy Source Code
echo "Copying runtime source to staging..."
if [ "$(dirname "$0")" != "$FINAL_INSTALL_DIR/scripts" ]; then
    cp -r "$(dirname "$0")/.."/* "$STAGING_DIR/"
    if [ "$EUID" -eq 0 ]; then
        chown -R "$SERVICE_USER:$SERVICE_USER" "$STAGING_DIR"
    fi
fi

# 8. Activation (Swap staging with final)
echo "Activating installation..."
if [ -d "$FINAL_INSTALL_DIR" ]; then
    if [ "$EUID" -eq 0 ]; then
        sudo rm -rf "${FINAL_INSTALL_DIR}.old" || true
        sudo mv "$FINAL_INSTALL_DIR" "${FINAL_INSTALL_DIR}.old"
        sudo mv "$STAGING_DIR" "$FINAL_INSTALL_DIR"
        sudo rm -rf "${FINAL_INSTALL_DIR}.old"
    else
        rm -rf "${FINAL_INSTALL_DIR}.old" || true
        mv "$FINAL_INSTALL_DIR" "${FINAL_INSTALL_DIR}.old"
        mv "$STAGING_DIR" "$FINAL_INSTALL_DIR"
        rm -rf "${FINAL_INSTALL_DIR}.old"
    fi
else
    if [ "$EUID" -eq 0 ]; then
        sudo mv "$STAGING_DIR" "$FINAL_INSTALL_DIR"
    else
        mv "$STAGING_DIR" "$FINAL_INSTALL_DIR"
    fi
fi
STAGING_DIR="" # Prevent rollback after activation

# 9. CLI Registration
echo "Registering CLI..."
mkdir -p "$BIN_DIR"
cat << EOF > "$BIN_DIR/anny-runtime"
#!/bin/bash
export ANNY_INSTALL_MODE="$INSTALL_MODE"
export ANNY_DATA_DIR="$DATA_DIR"
export PYTHONPATH="$FINAL_INSTALL_DIR:\$PYTHONPATH"
exec "$FINAL_INSTALL_DIR/venv/bin/python3" "$FINAL_INSTALL_DIR/cli/main.py" "\$@"
EOF
chmod +x "$BIN_DIR/anny-runtime"

# 10. Systemd Registration
echo "Configuring Systemd..."
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
WorkingDirectory=$FINAL_INSTALL_DIR
Environment=PYTHONUNBUFFERED=1
Environment=ANNY_INSTALL_MODE=system
Environment=ANNY_DATA_DIR=$DATA_DIR

# Hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ProtectHome=yes
RestrictSUIDSGID=yes

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable anny-runtime.service
else
    cat << EOF > "$SYSTEMD_DIR/anny-runtime.service"
[Unit]
Description=ANNY Runtime Node
After=network.target

[Service]
Type=simple
ExecStart=$BIN_DIR/anny-runtime server
Restart=on-failure
WorkingDirectory=$FINAL_INSTALL_DIR
Environment=PYTHONUNBUFFERED=1
Environment=ANNY_INSTALL_MODE=user
Environment=ANNY_DATA_DIR=$DATA_DIR

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable anny-runtime.service
fi

# 11. Initial Identity Creation
echo "Bootstrapping Identity..."
if [ "$EUID" -eq 0 ] && [ "$SERVICE_USER" != "root" ]; then
    sudo -u "$SERVICE_USER" "$BIN_DIR/anny-runtime" identity-bootstrap
else
    "$BIN_DIR/anny-runtime" identity-bootstrap
fi

# Clear failure trap
trap - EXIT

echo "Installation complete."
echo "Run 'anny-runtime doctor' to verify."
echo "Admin panel defaults to http://127.0.0.1:3643"
