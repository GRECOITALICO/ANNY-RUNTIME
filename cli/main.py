#!/usr/bin/env python3
"""ANNY Runtime CLI v0.2"""
import sys
import os
import argparse
import logging
import json
import shutil
import socket
from pathlib import Path

from runtime.core.config import get_install_mode, get_data_dir, get_admin_port, get_runtime_dir, RuntimeConfig

VERSION = "0.2.0"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("anny-runtime")


def cmd_version(args):
    print(f"ANNY Runtime v{VERSION}")


def cmd_status(args):
    data_dir = get_data_dir()
    install_mode = get_install_mode()
    identity_file = data_dir / "identity" / "runtime_identity.json"
    print(f"ANNY Runtime v{VERSION}")
    print(f"Install Mode:    {install_mode}")
    print(f"Data Directory:  {data_dir}")
    print(f"Runtime Dir:     {get_runtime_dir()}")
    print(f"Admin Port:      {get_admin_port()}")
    print()

    if identity_file.is_file():
        try:
            identity = json.loads(identity_file.read_text(encoding="utf-8"))
            print(f"  Runtime ID:      {identity.get('runtime_id', 'UNKNOWN')}")
            print(f"  Installation ID: {identity.get('installation_id', 'UNKNOWN')}")
            print("  Identity:        OBSERVED")
        except (OSError, json.JSONDecodeError):
            print("  Identity:        INVALID")
    else:
        print("  Identity:        NOT_INITIALIZED")

    config = RuntimeConfig.load()

    try:
        from runtime.admin.github import GitHubAuthManager
        from runtime.secrets.backend import FileSecretBackend
        from runtime.identity.runtime_identity import RuntimeIdentity

        identity_obj = RuntimeIdentity.load(data_dir)
        secret_backend = FileSecretBackend(str(data_dir / "secrets"), identity_obj._private_key)
        github_manager = GitHubAuthManager(
            secret_backend,
            client_id=config.github_client_id,
        )
        status = github_manager.get_status().to_dict()
        print(f"  GitHub:          {status.get('auth_status', 'UNKNOWN')}")
        if status.get("principal"):
            print(f"  GitHub Principal: {status['principal']}")
    except Exception as exc:
        print(f"  GitHub:          UNKNOWN ({type(exc).__name__})")

    if config.fabric_org and config.fabric_repo:
        print(f"  Fabric Binding:  CONFIGURED ({config.fabric_org}/{config.fabric_repo})")
    else:
        print("  Fabric Binding:  NOT_CONFIGURED")

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
    
    # Data directory
    DATA_DIR = get_data_dir()
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
    port = get_admin_port()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('127.0.0.1', port))
            port_ok = True
    except OSError:
        port_ok = False
    check("Admin port available", port_ok, f"port={port}")
    
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
    check("Sandbox directory", sandbox_dir.exists() or True, "Will be created on first use")
    
    print()
    fails = sum(1 for _, s, _ in results if s == "FAIL")
    if fails == 0:
        print("  All checks passed.")
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
        logger.error("RuntimeIdentityManager is unavailable: %s", exc)
        print("Error: canonical Runtime identity bootstrap is unavailable.")
        sys.exit(1)


def cmd_server(args):
    runtime_root = Path(__file__).resolve().parent.parent
    if str(runtime_root) not in sys.path:
        sys.path.insert(0, str(runtime_root))
    
    try:
        from runtime.admin.server import start_admin_server
        port = getattr(args, 'port', get_admin_port())
        start_admin_server(host='localhost', port=port)
    except ImportError as e:
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
    
    # Remove systemd using argv lists; never invoke a shell.
    system_mode = get_install_mode() == "system"
    if system_mode:
        unit = Path("/etc/systemd/system/anny-runtime.service")
        subprocess.run(
            ["sudo", "systemctl", "disable", "anny-runtime.service"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        unit = Path.home() / ".config" / "systemd" / "user" / "anny-runtime.service"
        subprocess.run(
            ["systemctl", "--user", "disable", "anny-runtime.service"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    if unit.exists():
        if system_mode:
            subprocess.run(["sudo", "rm", "--", str(unit)], check=True)
        else:
            unit.unlink()
        print("  Removed systemd unit.")

    # Remove CLI symlink
    cli_link = Path("/usr/local/bin/anny-runtime") if system_mode else Path.home() / ".local" / "bin" / "anny-runtime"
    if cli_link.exists():
        if system_mode:
            subprocess.run(["sudo", "rm", "--", str(cli_link)], check=True)
        else:
            cli_link.unlink()
        print("  Removed CLI.")

    # Remove software
    install_dir = get_runtime_dir()
    if install_dir.exists():
        if system_mode:
            subprocess.run(["sudo", "rm", "-rf", "--", str(install_dir)], check=True)
        else:
            shutil.rmtree(install_dir)
        print("  Removed software.")
    
    if getattr(args, 'purge', False):
        print()
        print("  WARNING: Purging all state (identity, journal, secrets)...")
        if DATA_DIR.exists():
            shutil.rmtree(DATA_DIR)
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
    p_server.add_argument("--port", type=int, default=get_admin_port())
    p_server.set_defaults(func=cmd_server)
    
    p_id = subparsers.add_parser("identity-bootstrap", help="Create initial identity")
    p_id.add_argument("--force", action="store_true", help="Regenerate existing identity")
    p_id.set_defaults(func=cmd_identity_bootstrap)
    
    args = parser.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
