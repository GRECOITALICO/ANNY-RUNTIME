# Security

## Least Privilege
The ANNY-RUNTIME is explicitly designed to operate without root privileges.
Even when installed system-wide via `sudo bash scripts/install.sh`, the installer detects the invoking `SUDO_USER` and explicitly binds the service execution and file ownerships to that unprivileged user. 

## Systemd Hardening
When deployed in system-wide mode, the `anny-runtime.service` unit automatically applies standard process hardening:
- `NoNewPrivileges=yes`
- `PrivateTmp=yes`
- `ProtectSystem=full`
- `ProtectHome=yes` (Protected because state operates from `/var/lib`)
- `RestrictSUIDSGID=yes`

## Port Security
- The runtime exposes its web administrative interface on `127.0.0.1:3643`.
- **Port 3434 is strictly forbidden** globally inside the codebase due to structural reservations. If `3643` is occupied, the runtime will auto-negotiate an alternative port within a defined upper block.

## Credentials
- `ANNY-RUNTIME` never stores secrets or credentials inside the source code or log files.
- Authorization tokens are strictly stored encrypted or within the protected `secrets/` state directory (`chmod 700`).
