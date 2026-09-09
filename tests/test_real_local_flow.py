import os
import sys
import tempfile
import urllib.request
import urllib.parse
import re
import threading
import time
import subprocess
import json
import logging

os.environ['no_proxy'] = '127.0.0.1,localhost'

# Ensure ANNY-RUNTIME is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from runtime.admin.server import start_admin_server

# Capture logs
log_stream = []
class ArrayLogHandler(logging.Handler):
    def emit(self, record):
        log_stream.append(self.format(record))

logging.basicConfig(level=logging.INFO)
root_logger = logging.getLogger()
handler = ArrayLogHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
root_logger.addHandler(handler)

def run_real_local_flow():
    # Fresh state
    data_dir = tempfile.mkdtemp(prefix="anny_data_")
    os.environ['ANNY_DATA_DIR'] = data_dir
    
    # Run server in a thread
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    
    def server_thread():
        # start_admin_server blocks indefinitely unless we interrupt or patch it.
        # But we can just use the AdminServer directly to have a clean shutdown.
        from runtime.identity.runtime_identity import RuntimeIdentity
        from runtime.admin.auth import AdminSessionManager
        from runtime.admin.audit import AdminAuditLog
        from runtime.admin.github import GitHubAuthManager
        from runtime.secrets.backend import FileSecretBackend
        from runtime.admin.server import AdminServer
        from pathlib import Path
        
        identity_manager = RuntimeIdentity.generate()
        identity_manager.save(data_dir)
        auth_manager = AdminSessionManager(data_dir, identity_manager.runtime_id)
        audit_manager = AdminAuditLog(data_dir, identity_manager.runtime_id)
        secret_backend = FileSecretBackend(os.path.join(data_dir, "secrets"), identity_manager._private_key)
        github_manager = GitHubAuthManager(secret_backend)
        
        server = AdminServer(
            host="127.0.0.1",
            port=port,
            auth_manager=auth_manager,
            audit_manager=audit_manager,
            github_manager=github_manager,
            secret_backend=secret_backend,
            event_bus=None,
            runtime_engine=None,
            local_operational_path=None,
            bootstrap_snapshot={'result': type('Mock', (), {'status': type('Mock', (), {'value': 'CONSISTENT'}), 'canonical_state': None}), 'discovered_repos': []}
        )
        server.start()
        return server

    server_instance = server_thread()
    time.sleep(1) # wait for server to bind

    try:
        # Get token
        proc = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True)
        token = proc.stdout.strip()
        if not token:
            print("No GH token found via gh auth token")
            return
            
        # GET /
        base_url = f"http://127.0.0.1:{port}"
        req1 = urllib.request.Request(base_url)
        try:
            with urllib.request.urlopen(req1) as resp:
                html = resp.read().decode('utf-8')
                cookie_header = resp.headers.get('Set-Cookie', '')
                session_id_match = re.search(r'admin_session_id=([^;]+)', cookie_header)
                session_id = session_id_match.group(1) if session_id_match else None
                
                csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', html)
                csrf_token = csrf_match.group(1) if csrf_match else None
        except urllib.error.HTTPError as e:
            print(f"HTTPError on GET /: {e.code} {e.reason}")
            print(e.read().decode('utf-8'))
            return

        if not session_id or not csrf_token:
            print("Failed to get session or CSRF token")
            return
            
        print(f"Got session: {session_id[:8]}... CSRF: {csrf_token[:8]}...")
        
        # POST /github/token
        data = urllib.parse.urlencode({'github_token': token, 'csrf_token': csrf_token}).encode('utf-8')
        req2 = urllib.request.Request(f"{base_url}/github/token", data=data)
        req2.add_header('Cookie', f'admin_session_id={session_id}')
        
        try:
            with urllib.request.urlopen(req2) as resp2:
                final_html = resp2.read().decode('utf-8')
                final_url = resp2.url
        except urllib.error.HTTPError as e:
            print(f"HTTP error: {e.code}")
            return

        print(f"Final URL: {final_url}")
        
    finally:
        server_instance.stop()
        
    # Write safe logs (excluding token)
    safe_logs = []
    for line in log_stream:
        if token in line:
            line = line.replace(token, "[REDACTED_TOKEN]")
        safe_logs.append(line)
        
    with open("real_local_flow_logs.json", "w") as f:
        json.dump(safe_logs, f, indent=2)

if __name__ == "__main__":
    run_real_local_flow()
