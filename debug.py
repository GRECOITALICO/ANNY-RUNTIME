import urllib.parse
from runtime.admin.server import AdminServer
from runtime.admin.auth import AdminSessionManager
from runtime.admin.github import GitHubAuthManager
from runtime.secrets.backend import FileSecretBackend
from unittest.mock import MagicMock
import tempfile
data_dir = tempfile.mkdtemp()
secret_backend = FileSecretBackend(data_dir, b"0"*32)
gh_mgr = GitHubAuthManager(secret_backend)
auth_mgr = AdminSessionManager(data_dir, "rt-123")
server = AdminServer("127.0.0.1", 0, auth_mgr, MagicMock(), gh_mgr, secret_backend=secret_backend, bootstrap_snapshot={})
context = {}
server.middleware.process_request("GET", "/", {'Host': '127.0.0.1'}, context)
server.router.context = context
status = gh_mgr.get_status().to_dict()
print(status)
