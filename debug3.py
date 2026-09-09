import urllib.parse
from runtime.admin.server import AdminServer
from runtime.admin.auth import AdminSessionManager
from runtime.admin.github import GitHubAuthManager
from runtime.secrets.backend import FileSecretBackend
import tempfile
import shutil
from unittest.mock import MagicMock

data_dir = tempfile.mkdtemp()
try:
    secret_backend = FileSecretBackend(data_dir, b"0"*32)
    gh_mgr = GitHubAuthManager(secret_backend)
    auth_mgr = AdminSessionManager(data_dir, "rt-123")
    server = AdminServer("127.0.0.1", 0, auth_mgr, MagicMock(), gh_mgr, secret_backend=secret_backend, bootstrap_snapshot={})

    context = {}
    server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
    
    session = context.get('admin_session')
    
    gh_status = gh_mgr.get_status().to_dict()
    auth_status = gh_status.get('auth_status', 'UNKNOWN')
    is_first_run = gh_mgr and not gh_mgr.has_token()
    
    print("auth_status:", auth_status)
    print("is_first_run:", is_first_run)
    print("session exists:", session is not None)
    if session:
        print("session.scope:", session.scope)

finally:
    shutil.rmtree(data_dir)
