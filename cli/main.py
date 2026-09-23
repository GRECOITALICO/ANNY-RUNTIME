#!/usr/bin/env python3
"""ANNY Runtime CLI."""
import sys
import os
import argparse
import logging
import json
import shutil
import socket
import subprocess
from pathlib import Path

from runtime.core.config import (
    RuntimeConfig,
    RuntimeConfigError,
    get_data_dir,
    get_install_mode,
    get_runtime_dir,
)

from runtime.core.version import __version__ as VERSION

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("anny-runtime")


def cmd_version(args):
    print(f"ANNY Runtime v{VERSION}")


def cmd_status(args):
    DATA_DIR = get_data_dir()
    install_mode = get_install_mode()
    identity_file = DATA_DIR / "identity" / "runtime_identity.json"
    print(f"ANNY Runtime v{VERSION}")
    print(f"Install Mode:    {install_mode}")
    print(f"Data Directory:  {DATA_DIR}")
    print(f"Runtime Dir:     {get_runtime_dir()}")
    try:
        config = RuntimeConfig.load()
        print(f"Admin Port:      {config.admin_port}")
    except RuntimeConfigError as exc:
        print(f"Admin Port:      UNVERIFIED ({exc})")
    print()
    
    # Identity
    if identity_file.exists():
        with open(identity_file) as f:
            identity = json.load(f)
        print(f"  Runtime ID:      {identity.get('runtime_id', 'UNKNOWN')}")
        print(f"  Installation ID: {identity.get('installation_id', 'UNKNOWN')}")
        print(f"  Identity:        READY")
    else:
        print(f"  Identity:        NOT INITIALIZED")
    
    # GitHub
    github_file = DATA_DIR / "secrets" / "github_credential.json"
    if github_file.exists():
        print(f"  GitHub:          CONNECTED")
    else:
        print(f"  GitHub:          NOT CONNECTED")
    
    # Fabric
    fabric_file = DATA_DIR / "secrets" / "fabric_registration.json"
    if fabric_file.exists():
        print(f"  Fabric:          CONNECTED")
    else:
        print(f"  Fabric:          NOT CONNECTED")
    
    print()


def cmd_doctor(args):
    import platform
    results = []
    
    def check(name, condition, detail=""):
        status = "PASS" if condition else "FAIL"
        results.append((name, status, detail))
        icon = "✓" if condition else "✗"
        print(f"  [{status}] {icon} {name}" + (f" — {detail}" if detail else ""))
    
    print(f"ANNY Runtime Diagnostics v{VERSION}")
    print()
    
    # OS
    check("Operating System", sys.platform == "linux", f"{platform.system()} {platform.release()}")
    
    # Python
    py_ok = sys.version_info >= (3, 11)
    check("Python >= 3.11", py_ok, f"{sys.version.split()[0]}")
    
    try:
        config = RuntimeConfig.load()
    except RuntimeConfigError as exc:
        check("Runtime configuration", False, str(exc))
        print()
        print("  Diagnostics blocked: RUNTIME_HEALTH=UNVERIFIED")
        return 1

    # Data directory
    DATA_DIR = Path(config.data_dir)
    check("Data directory exists", DATA_DIR.exists(), str(DATA_DIR))
    
    # Identity
    id_file = DATA_DIR / "identity" / "runtime_identity.json"
    check("Identity initialized", id_file.exists())
    
    # Private key
    pk_file = DATA_DIR / "identity" / "private_key.pem"
    if pk_file.exists():
        perms = oct(pk_file.stat().st_mode)[-3:]
        check("Private key permissions", perms == "600", f"mode={perms}")
    else:
        check("Private key exists", False)
    
    # Port
    port = config.admin_port
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('127.0.0.1', port))
            port_ok = True
    except OSError:
        port_ok = False
    check("Admin port bindable (not runtime health)", port_ok, f"port={port}")
    
    # Forbidden port
    check("Port 3434 not used", port != 3434, "Reserved by CONRRAD")
    
    # Cryptography
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        check("cryptography library", True)
    except ImportError:
        check("cryptography library", False, "pip install cryptography>=41.0.0")
    
    # Systemd
    install_mode = get_install_mode()
    if install_mode == "system":
        systemd_unit = Path("/etc/systemd/system/anny-runtime.service")
    else:
        systemd_unit = Path.home() / ".config" / "systemd" / "user" / "anny-runtime.service"
    check("Systemd unit installed", systemd_unit.exists(), f"mode={install_mode}")
    
    # Sandbox
    sandbox_dir = DATA_DIR / "sandboxes"
    sandbox_ok = sandbox_dir.exists() or sandbox_dir.parent.exists()
    check("Sandbox directory", sandbox_ok, str(sandbox_dir))

    
    print()
    fails = sum(1 for _, s, _ in results if s == "FAIL")
    if fails == 0:
        print("  Local prerequisites passed; RUNTIME_HEALTH=UNVERIFIED.")
    else:
        print(f"  {fails} check(s) failed.")
    return 0 if fails == 0 else 1


def cmd_identity_bootstrap(args):
    DATA_DIR = get_data_dir()
    id_dir = DATA_DIR / "identity"
    id_file = id_dir / "runtime_identity.json"
    
    if id_file.exists() and not getattr(args, 'force', False):
        print("Identity already exists. Use --force to regenerate.")
        return
    
    id_dir.mkdir(parents=True, exist_ok=True)
    
    # Add parent to path for imports
    runtime_root = Path(__file__).resolve().parent.parent
    if str(runtime_root) not in sys.path:
        sys.path.insert(0, str(runtime_root))
    
    try:
        from runtime.identity.runtime_identity import RuntimeIdentityManager
        manager = RuntimeIdentityManager(str(DATA_DIR))
        identity = manager.create_identity()
        print(f"Identity created: {identity.runtime_id}")
        print(f"Installation ID:  {identity.installation_id}")
    except ImportError as exc:
        logger.error("Canonical RuntimeIdentityManager is unavailable; refusing alternate identity generation.")
        raise RuntimeError("CANONICAL_IDENTITY_MANAGER_UNAVAILABLE") from exc


def cmd_server(args):
    runtime_root = Path(__file__).resolve().parent.parent
    if str(runtime_root) not in sys.path:
        sys.path.insert(0, str(runtime_root))
    
    try:
        from runtime.admin.server import start_admin_server
        config = RuntimeConfig.load()
        port = args.port if getattr(args, 'port', None) is not None else config.admin_port
        start_admin_server(host=config.admin_host, port=port)
    except (ImportError, RuntimeConfigError) as e:
        logger.error(f"Cannot start server: {e}")
        sys.exit(1)


def cmd_install(args):
    script = Path(__file__).resolve().parent.parent / "scripts" / "install.sh"
    if script.exists():
        os.execvp("bash", ["bash", str(script)])
    else:
        print("Error: install.sh not found.")
        sys.exit(1)


def cmd_uninstall(args):
    DATA_DIR = get_data_dir()
    print("ANNY Runtime Uninstall")
    print()
    print("This will remove:")
    print(f"  - Software:  {get_runtime_dir()}")
    if get_install_mode() == "system":
        print(f"  - Systemd:   /etc/systemd/system/anny-runtime.service")
        print(f"  - CLI:       /usr/local/bin/anny-runtime")
    else:
        print(f"  - Systemd:   ~/.config/systemd/user/anny-runtime.service")
        print(f"  - CLI:       ~/.local/bin/anny-runtime")
    print()
    print("The following will be PRESERVED unless --purge is specified:")
    print(f"  - Identity:  {DATA_DIR}/identity")
    print(f"  - Journal:   {DATA_DIR}/journal")
    print(f"  - Secrets:   {DATA_DIR}/secrets")
    print()
    
    if not getattr(args, 'yes', False):
        confirm = input("Proceed? [y/N] ")
        if confirm.lower() != 'y':
            print("Cancelled.")
            return
    
    install_mode = get_install_mode()
    expected_runtime_dir = (
        Path("/opt/anny-runtime")
        if install_mode == "system"
        else Path.home() / ".local" / "share" / "anny-runtime"
    )
    expected_data_dir = (
        Path("/var/lib/anny-runtime")
        if install_mode == "system"
        else Path.home() / ".anny-runtime"
    )

    def remove_path(path: Path, expected: Path, recursive: bool = False) -> None:
        if not path.exists() and not path.is_symlink():
            return
        candidate = path.expanduser().absolute()
        managed_target = expected.expanduser().absolute()
        if candidate != managed_target:
            raise RuntimeError(
                f"Refusing uninstall target outside the managed Runtime scope: {path}"
            )
        if candidate in (Path("/"), Path.home()) or str(candidate) in ("", "."):
            raise RuntimeError(f"Refusing unsafe uninstall target: {path}")
        if install_mode == "system":
            args = ["sudo", "rm", "-rf" if recursive else "-f", str(path)]
            subprocess.run(args, check=True)
        elif recursive:
            shutil.rmtree(path)
        else:
            path.unlink()

    # Remove systemd
    if install_mode == "system":
        unit = Path("/etc/systemd/system/anny-runtime.service")
        disable_cmd = ["sudo", "systemctl", "disable", "anny-runtime.service"]
    else:
        unit = Path.home() / ".config" / "systemd" / "user" / "anny-runtime.service"
        disable_cmd = ["systemctl", "--user", "disable", "anny-runtime.service"]

    if unit.exists():
        result = subprocess.run(disable_cmd, check=False)
        if result.returncode not in (0, 1):
            raise RuntimeError("Failed to disable the Runtime systemd unit")
        remove_path(unit, unit)
        if install_mode == "system":
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
        print("  Removed systemd unit.")

    # Remove CLI symlink
    cli_link = (
        Path("/usr/local/bin/anny-runtime")
        if install_mode == "system"
        else Path.home() / ".local" / "bin" / "anny-runtime"
    )
    if cli_link.exists() or cli_link.is_symlink():
        remove_path(cli_link, cli_link)
        print("  Removed CLI.")

    # Remove software
    install_dir = get_runtime_dir()
    if install_dir.exists():
        remove_path(install_dir, expected_runtime_dir, recursive=True)
        print("  Removed software.")
    
    if getattr(args, 'purge', False):
        print()
        print("  WARNING: Purging all state (identity, journal, secrets)...")
        if DATA_DIR.exists():
            remove_path(DATA_DIR, expected_data_dir, recursive=True)
            print("  State purged.")
    
    print()
    print("Uninstall complete.")


def main():
    parser = argparse.ArgumentParser(description=f"ANNY Runtime CLI v{VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    subparsers.add_parser("version", help="Show version").set_defaults(func=cmd_version)
    subparsers.add_parser("status", help="Show runtime status").set_defaults(func=cmd_status)
    subparsers.add_parser("doctor", help="Run diagnostics").set_defaults(func=cmd_doctor)
    subparsers.add_parser("install", help="Install ANNY Runtime").set_defaults(func=cmd_install)
    
    p_uninstall = subparsers.add_parser("uninstall", help="Uninstall ANNY Runtime")
    p_uninstall.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    p_uninstall.add_argument("--purge", action="store_true", help="Also remove identity, journal, secrets")
    p_uninstall.set_defaults(func=cmd_uninstall)
    
    p_server = subparsers.add_parser("server", help="Start admin web server")
    p_server.add_argument("--port", type=int, default=None)
    p_server.set_defaults(func=cmd_server)
    
    p_id = subparsers.add_parser("identity-bootstrap", help="Create initial identity")
    p_id.add_argument("--force", action="store_true", help="Regenerate existing identity")
    p_id.set_defaults(func=cmd_identity_bootstrap)
    
    args = parser.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
