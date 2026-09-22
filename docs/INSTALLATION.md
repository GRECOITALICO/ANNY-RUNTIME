# ANNY-RUNTIME Installation Guide

ANNY-RUNTIME is distributed through the repository and installed with the canonical installer:

`scripts/install.sh`

The installer is the only supported source for the Runtime systemd/user-service definition. Do not copy a separate static service file.

## System-Wide Installation

```bash
git clone <PUBLIC_REPOSITORY>
cd ANNY-RUNTIME
ANNY_GITHUB_CLIENT_ID=<PUBLIC_GITHUB_OAUTH_CLIENT_ID> sudo -E bash scripts/install.sh
```

The GitHub OAuth client ID is public application metadata, not a credential. It may also be supplied later through `config.yaml` as `github_client_id`. When no client ID is configured, first-run onboarding still provides the validated access-token fallback.

The installer creates:

- Binary: `/usr/local/bin/anny-runtime`
- Application: `/opt/anny-runtime/`
- State and identity: `/var/lib/anny-runtime/`
- Service: `/etc/systemd/system/anny-runtime.service`

Start or enable it with:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now anny-runtime
```

## User-Local Installation

```bash
bash scripts/install.sh
```

The installer creates:

- Binary: `~/.local/bin/anny-runtime`
- Application: `~/.local/share/anny-runtime/`
- State: `~/.anny-runtime/`
- Service: `~/.config/systemd/user/anny-runtime.service`

Start or enable it with:

```bash
systemctl --user daemon-reload
systemctl --user enable --now anny-runtime
```

## Verification

```bash
anny-runtime doctor
anny-runtime status
```

The admin interface binds to loopback by default at `http://127.0.0.1:3643`.

## GitHub onboarding

On first start, ANNY Runtime creates a restricted onboarding session.

When `ANNY_GITHUB_CLIENT_ID` or `github_client_id` is configured, the UI offers GitHub Device Flow. The manual GitHub access-token path remains available as a fallback.

Runtime never stores raw GitHub credentials in source files, HTML, status DTOs or audit records.

## Configuration

The canonical Runtime configuration file is:

- system-wide: `/var/lib/anny-runtime/config.yaml`
- user-local: `~/.anny-runtime/config.yaml`

Example:

```yaml
github_client_id: "<PUBLIC_GITHUB_OAUTH_CLIENT_ID>"
fabric_org: "<FABRIC_ORG>"
fabric_repo: "<FABRIC_REPO>"
```

`fabric_org` and `fabric_repo` are required for the Repository Fabric binding. The Runtime must fail closed when either is absent; it must never invent a Fabric repository.

## Uninstall

```bash
anny-runtime uninstall
anny-runtime uninstall --purge
```

`--purge` removes local Runtime state, including the encrypted credential store and Runtime identity. This is intentionally destructive and is not part of normal upgrades.
