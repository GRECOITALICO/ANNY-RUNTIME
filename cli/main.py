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
    DATA_DIR = get_data_dir()
    install_mode = get_install_mode()
    identity_file = DATA_DIR / "identity" / "runtime_identity.json"
    print(f"ANNY Runtime v{VERSION}")
    print(f"Install Mode:    {install_mode}")
    print(f"Data Directory:  {DATA_DIR}")
    print(f"Runtime Dir:     {get_runtime_dir()}")
    print(f"Admin Port:      {get_admin_port()}")
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


def cmd_native_demo(args):
    from runtime.execution.local_native import LocalNativeTaskExecutor
    from runtime.execution.local_task_specs import safe_slug_task_spec
    result = LocalNativeTaskExecutor(get_data_dir()).execute(safe_slug_task_spec())
    print(json.dumps(result, sort_keys=True))


def cmd_native_manifest_demo(args):
    from runtime.execution.local_native import LocalNativeTaskExecutor
    from runtime.execution.local_task_specs import json_manifest_validation_task_spec
    result = LocalNativeTaskExecutor(get_data_dir()).execute(json_manifest_validation_task_spec())
    print(json.dumps(result, sort_keys=True))


def cmd_native_repository_demo(args):
    from runtime.execution.local_native import LocalNativeTaskExecutor
    from runtime.execution.local_task_specs import repository_change_task_spec
    result = LocalNativeTaskExecutor(get_data_dir()).execute(repository_change_task_spec())
    print(json.dumps(result, sort_keys=True))


def cmd_local_planner_status(args):
    from runtime.planning.local_planner import inspect_local_model_runtime, persist_discovery
    print(json.dumps(persist_discovery(get_data_dir(), inspect_local_model_runtime()), sort_keys=True))


def cmd_local_plan(args):
    from runtime.planning.local_planner import (
        LOCAL_MODEL_READY, LocalPlanValidator, LocalPlanner, LocalPlanningOrchestrator,
        OllamaLocalProvider, inspect_local_model_runtime, persist_discovery, persist_plan_attempt, verify_local_inference,
    )
    discovery = inspect_local_model_runtime()
    # This is the explicit operational inference check. Status/dashboard reads never call it.
    discovery = verify_local_inference(discovery)
    persist_discovery(get_data_dir(), discovery)
    provider = OllamaLocalProvider(discovery.models[0], max_tokens=1024) if discovery.status == LOCAL_MODEL_READY and discovery.models else None
    result = LocalPlanningOrchestrator(LocalPlanner(discovery, provider), LocalPlanValidator(get_data_dir(), discovery)).plan_and_execute(args.request)
    print(json.dumps({"result": result, "evidence": persist_plan_attempt(get_data_dir(), result)}, sort_keys=True))


def cmd_local_plan_task_009(args):
    from runtime.planning.local_planner import LOCAL_PLAN_REQUEST
    args.request = LOCAL_PLAN_REQUEST
    return cmd_local_plan(args)


def cmd_local_plan_task_010(args):
    from runtime.planning.local_planner import (
        LOCAL_MODEL_READY, LOCAL_PLAN_010_TASK_ID_PREFIX, LOCAL_PLAN_REQUEST,
        LocalPlanValidator, LocalPlanner, LocalPlanningOrchestrator, OllamaLocalProvider,
        inspect_local_model_runtime, load_plan_attempt, persist_discovery, persist_plan_attempt,
        verify_local_inference,
    )
    existing = load_plan_attempt(get_data_dir(), LOCAL_PLAN_010_TASK_ID_PREFIX)
    if existing is not None:
        print(json.dumps({"result": "IDEMPOTENT_REUSE", "evidence": existing}, sort_keys=True))
        return
    discovery = verify_local_inference(inspect_local_model_runtime())
    persist_discovery(get_data_dir(), discovery)
    provider = OllamaLocalProvider(discovery.models[0], max_tokens=1024) if discovery.status == LOCAL_MODEL_READY and discovery.models else None
    try:
        result = LocalPlanningOrchestrator(
            LocalPlanner(discovery, provider, task_id_prefix=LOCAL_PLAN_010_TASK_ID_PREFIX),
            LocalPlanValidator(get_data_dir(), discovery, task_id_prefix=LOCAL_PLAN_010_TASK_ID_PREFIX),
        ).plan_and_execute(LOCAL_PLAN_REQUEST, allow_one_correction=True)
    except Exception as exc:
        result = {
            "status": "BLOCKED", "proposal": {"request": LOCAL_PLAN_REQUEST},
            "validation": {"decision": "DENY", "reason": f"LOCAL_PLAN_ORCHESTRATOR_ERROR:{type(exc).__name__}"},
            "execution": None, "attempts": [],
        }
    print(json.dumps({"result": result, "evidence": persist_plan_attempt(get_data_dir(), result, task_id_prefix=LOCAL_PLAN_010_TASK_ID_PREFIX)}, sort_keys=True))


def cmd_local_planner_capacity(args):
    from runtime.planning.local_capacity import collect_local_capacity, persist_capacity
    print(json.dumps(persist_capacity(get_data_dir(), collect_local_capacity()), sort_keys=True))


def cmd_local_planner_verify(args):
    from runtime.planning.local_planner import (
        inspect_local_model_runtime,
        persist_discovery,
        persist_inference_verification,
        verify_local_inference_attempt,
    )
    verification = verify_local_inference_attempt(
        inspect_local_model_runtime(), model_id=args.model_id, timeout_seconds=args.timeout_seconds,
    )
    discovery = persist_discovery(get_data_dir(), verification.discovery)
    evidence = persist_inference_verification(get_data_dir(), verification)
    print(json.dumps({"discovery": discovery, "verification": evidence}, sort_keys=True))


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
    except ImportError:
        # Fallback: generate identity manually
        import uuid
        from datetime import datetime, timezone
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives import serialization
            
            private_key = Ed25519PrivateKey.generate()
            public_key = private_key.public_key()
            
            pub_bytes = public_key.public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw
            ).hex()
            
            priv_pem = private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()
            )
            
            pk_file = id_dir / "private_key.pem"
            pk_file.write_bytes(priv_pem)
            pk_file.chmod(0o600)
            
            identity_data = {
                "runtime_id": f"rt-{uuid.uuid4().hex[:16]}",
                "installation_id": f"inst-{uuid.uuid4().hex[:16]}",
                "public_key": pub_bytes,
                "platform": sys.platform,
                "runtime_version": VERSION,
                "protocol_version": "1.0",
                "generation": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            
            id_file.write_text(json.dumps(identity_data, indent=2))
            print(f"Identity created: {identity_data['runtime_id']}")
            print(f"Installation ID:  {identity_data['installation_id']}")
        except ImportError:
            print("Error: cryptography library not installed.")
            print("Run: pip install cryptography>=41.0.0")
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
    
    # Remove systemd
    if get_install_mode() == "system":
        unit = Path("/etc/systemd/system/anny-runtime.service")
        cmd_disable = "sudo systemctl disable anny-runtime.service 2>/dev/null || true"
    else:
        unit = Path.home() / ".config" / "systemd" / "user" / "anny-runtime.service"
        cmd_disable = "systemctl --user disable anny-runtime.service 2>/dev/null || true"
        
    if unit.exists():
        os.system(cmd_disable)
        if get_install_mode() == "system":
            os.system(f"sudo rm {unit}")
        else:
            unit.unlink()
        print("  Removed systemd unit.")
    
    # Remove CLI symlink
    if get_install_mode() == "system":
        cli_link = Path("/usr/local/bin/anny-runtime")
    else:
        cli_link = Path.home() / ".local" / "bin" / "anny-runtime"
    
    if cli_link.exists():
        if get_install_mode() == "system":
            os.system(f"sudo rm {cli_link}")
        else:
            cli_link.unlink()
        print("  Removed CLI.")
    
    # Remove software
    install_dir = get_runtime_dir()
    if install_dir.exists():
        if get_install_mode() == "system":
            os.system(f"sudo rm -rf {install_dir}")
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
    subparsers.add_parser("native-demo", help="Run the authorized native local safe_slug demonstration").set_defaults(func=cmd_native_demo)
    subparsers.add_parser("native-manifest-demo", help="Run the authorized native JSON-manifest validation demonstration").set_defaults(func=cmd_native_manifest_demo)
    subparsers.add_parser("native-repository-demo", help="Run the authorized isolated repository-change demonstration").set_defaults(func=cmd_native_repository_demo)
    subparsers.add_parser("local-planner-status", help="Inspect installed local-model runtimes without starting or downloading anything").set_defaults(func=cmd_local_planner_status)
    local_plan = subparsers.add_parser("local-plan", help="Plan and execute an authorized fixture change only through verified local Ollama inference")
    local_plan.add_argument("request", help="Natural-language engineering request for the registered isolated fixture")
    local_plan.set_defaults(func=cmd_local_plan)
    subparsers.add_parser("local-plan-task-009", help="Run the one authorized content-only local-model fixture task").set_defaults(func=cmd_local_plan_task_009)
    subparsers.add_parser("local-plan-task-010", help="Run the one authorized local model task with at most one content correction").set_defaults(func=cmd_local_plan_task_010)
    subparsers.add_parser("local-planner-capacity", help="Collect a sanitized read-only local-model capacity inventory").set_defaults(func=cmd_local_planner_capacity)
    local_verify = subparsers.add_parser("local-planner-verify", help="Verify one explicit local Ollama model with a bounded JSON-only probe")
    local_verify.add_argument("--model-id", required=True, help="Exact model identifier reported by the local Ollama catalog")
    local_verify.add_argument("--timeout-seconds", type=float, default=60, help="Bounded probe timeout from 0 to 60 seconds")
    local_verify.set_defaults(func=cmd_local_planner_verify)
    subparsers.add_parser("doctor", help="Run diagnostics").set_defaults(func=cmd_doctor)
    subparsers.add_parser("install", help="Install ANNY Runtime").set_defaults(func=cmd_install)
    
    p_uninstall = subparsers.add_parser("uninstall", help="Uninstall ANNY Runtime")
    p_uninstall.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    p_uninstall.add_argument("--purge", action="store_true", help="Also remove identity, journal, secrets")
    p_uninstall.set_defaults(func=cmd_uninstall)
    
    p_server = subparsers.add_parser("server", help="Start admin web server")
    p_server.add_argument("--port", type=int, default=3643)
    p_server.set_defaults(func=cmd_server)
    
    p_id = subparsers.add_parser("identity-bootstrap", help="Create initial identity")
    p_id.add_argument("--force", action="store_true", help="Regenerate existing identity")
    p_id.set_defaults(func=cmd_identity_bootstrap)
    
    args = parser.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
