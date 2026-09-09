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
    server.router.context = context
    html = server.router.handle_dashboard(urllib.parse.urlparse("/"))
    
    print("HTML Length:", len(html))
    print("Does it contain github_token?", 'name="github_token"' in html)
    print("Does it contain UNAUTHORIZED?", 'UNAUTHORIZED' in html)
    print("HTML Snippet:", html[:500])
    if 'name="github_token"' not in html:
        print("Full HTML:", html)
finally:
    shutil.rmtree(data_dir)
