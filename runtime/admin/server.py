"""Admin HTTP Server using Python stdlib.

Binds to local interface, integrates router and middleware.
"""
import logging
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Any

from runtime.admin.routes import AdminRouter
from runtime.admin.middleware import AdminMiddleware

logger = logging.getLogger(__name__)


class AdminRequestHandler(BaseHTTPRequestHandler):
    """Handles admin HTTP requests."""
    
    server: 'AdminServer' # Type hint for the custom server instance

    def do_GET(self):
        context: Dict[str, Any] = {}
        if not self.server.middleware.process_request('GET', self.path, self.headers, context):
            self.server.router._redirect(self, context.get('redirect_to', '/login'))
            return
            
        self.server.router.dispatch_get(self.path, self)

    def do_POST(self):
        context: Dict[str, Any] = {}
        if not self.server.middleware.process_request('POST', self.path, self.headers, context):
            self.server.router._redirect(self, context.get('redirect_to', '/login'))
            return
            
        # Parse form data
        content_type = self.headers.get('content-type', '')
        ctype = content_type.split(';')[0].strip().lower()
        
        form_data = {}
        if ctype == 'application/x-www-form-urlencoded':
            length = int(self.headers.get('content-length', 0))
            if length > 0:
                body = self.rfile.read(length).decode('utf-8')
                import urllib.parse
                form_data = urllib.parse.parse_qs(body)
                
        if not self.server.middleware.process_post_body(self.path, form_data, context):
            self.server.router._redirect(self, context.get('redirect_to', '/'))
            return
            
        # Execute POST handler
        self.server.router.dispatch_post(self.path, form_data, self)
        
        # Post-process (cookies)
        self.server.middleware.process_response(context)
        
    def log_message(self, format, *args):
        """Override to use standard logger."""
        logger.debug(f"Admin HTTP: {self.client_address[0]} - {format % args}")


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""
    daemon_threads = True


class AdminServer:
    """Manages the threaded HTTP server lifecycle."""
    
    def __init__(self, host: str, port: int, auth_manager, audit_manager, github_manager, secret_backend=None, event_bus=None, runtime_engine=None, local_operational_path=None, bootstrap_snapshot=None):
        self.host = host
        self.port = port
        self.server = None
        self.thread = None
        
        # Initialize context for router
        self.admin_context = {
            'auth_manager': auth_manager,
            'audit_manager': audit_manager,
            'github_manager': github_manager,
            'secret_backend': secret_backend,
            'event_bus': event_bus if event_bus else "UNKNOWN",
            'runtime_engine': runtime_engine if runtime_engine else "UNKNOWN",
            'local_operational_path': local_operational_path,
            'bootstrap_snapshot': bootstrap_snapshot
        }
        
        self.router = AdminRouter(self.admin_context)
        self.middleware = AdminMiddleware(auth_manager, github_manager=github_manager)
        
    def start(self):
        """Start the server in a background thread."""
        try:
            self.server = ThreadedHTTPServer((self.host, self.port), AdminRequestHandler)
            # Inject references into the server instance so handlers can access them
            self.server.router = self.router
            self.server.middleware = self.middleware
            
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            logger.info(f"Admin Server started at http://{self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to start Admin Server on {self.host}:{self.port} - {e}")
            return False
            
    def stop(self):
        """Stop the server cleanly."""
        if self.server:
            logger.info("Stopping Admin Server...")
            self.server.shutdown()
            self.server.server_close()
            if self.thread:
                self.thread.join(timeout=2.0)
            logger.info("Admin Server stopped")

def start_admin_server(host: str, port: int):
    """Convenience function to instantiate and run the AdminServer."""
    import time
    import sys
    from runtime.core.config import get_data_dir
    from runtime.identity.runtime_identity import RuntimeIdentity
    from runtime.admin.auth import AdminSessionManager
    from runtime.admin.audit import AdminAuditLog
    from runtime.admin.github import GitHubAuthManager
    from runtime.secrets.backend import FileSecretBackend
    
    # Initialize basic components required by the server
    data_dir = get_data_dir()
    identity_manager = RuntimeIdentity.load(data_dir)
    auth_manager = AdminSessionManager(str(data_dir), identity_manager.runtime_id)
    audit_manager = AdminAuditLog(str(data_dir), identity_manager.runtime_id)
    secret_backend = FileSecretBackend(str(data_dir / "secrets"), identity_manager._private_key)
    github_manager = GitHubAuthManager(secret_backend)
    
    if not auth_manager.load_bootstrap_token():
        auth_manager.generate_bootstrap_token()
        
    # P0-A & P0-B: Initialize Bootstrap once per runtime lifecycle.
    from runtime.continuity.operational import OperationalRepositoryProvider
    from runtime.continuity.bootstrap import CustomerZeroBootstrapResolver
    from runtime.github.client import GitHubClient
    from runtime.github.discovery import OrganizationDiscoveryService

    github_client = GitHubClient(secret_backend=secret_backend) if github_manager.has_token() else None
    
    disc_repos_raw = []
    if github_client:
        try:
            disc = OrganizationDiscoveryService(github_client)
            disc_repos_raw = disc.discover_repositories()
        except Exception as e:
            logger.warning(f"Startup discovery failed: {e}")

    # Enforce PRODUCTION environment boundary here
    provider = OperationalRepositoryProvider(github_client=github_client, environment="PRODUCTION")
    resolver = CustomerZeroBootstrapResolver(provider=provider, event_bus=None)
    bootstrap_result = resolver.resolve()
    
    bootstrap_snapshot = {
        'result': bootstrap_result,
        'discovered_repos': disc_repos_raw
    }
    
    # Standalone CLI startup does not instantiate event_bus or runtime_engine.
    # Passing None will be translated to UNKNOWN by AdminServer.
    server = AdminServer(
        host=host, 
        port=port, 
        auth_manager=auth_manager, 
        audit_manager=audit_manager, 
        github_manager=github_manager,
        secret_backend=secret_backend,
        event_bus=None,
        runtime_engine=None,
        local_operational_path=None,
        bootstrap_snapshot=bootstrap_snapshot
    )
    
    if server.start():
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt, shutting down...")
        finally:
            server.stop()
    else:
        logger.error("Failed to start admin server")
        sys.exit(1)
