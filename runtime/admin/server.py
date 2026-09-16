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
from runtime.core.config import RuntimeConfig, get_data_dir
from runtime.core.engine import RuntimeEngine

logger = logging.getLogger(__name__)


class AdminRequestHandler(BaseHTTPRequestHandler):
    """Handles admin HTTP requests."""

    server: 'AdminServer'

    def do_GET(self):
        context: Dict[str, Any] = dict(self.server.router.context)
        if not self.server.middleware.process_request('GET', self.path, self.headers, context):
            self.server.middleware.process_response(context)
            self.server.router.context.update({'set_cookies': context.get('set_cookies', [])})
            self.server.router._redirect(self, context.get('redirect_to', '/login'))
            return

        saved_context = dict(self.server.router.context)
        self.server.router.context.update(context)
        try:
            self.server.middleware.process_response(context)
            self.server.router.context.update({'set_cookies': context.get('set_cookies', [])})
            self.server.router.dispatch_get(self.path, self)
        finally:
            for key in list(self.server.router.context.keys()):
                if key not in saved_context and key not in ('bootstrap_snapshot',):
                    del self.server.router.context[key]
            self.server.router.context.update({k: v for k, v in saved_context.items()
                                               if k not in ('admin_session', 'set_cookies', 'new_session_id', 'secure_cookie')})

    def do_POST(self):
        context: Dict[str, Any] = dict(self.server.router.context)
        if not self.server.middleware.process_request('POST', self.path, self.headers, context):
            self.server.middleware.process_response(context)
            self.server.router.context.update({'set_cookies': context.get('set_cookies', [])})
            self.server.router._redirect(self, context.get('redirect_to', '/login'))
            return

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
            self.server.middleware.process_response(context)
            self.server.router.context.update({'set_cookies': context.get('set_cookies', [])})
            self.server.router._redirect(self, context.get('redirect_to', '/'))
            return

        saved_context = dict(self.server.router.context)
        self.server.router.context.update(context)
        try:
            self.server.router.dispatch_post(self.path, form_data, self)
            self.server.middleware.process_response(self.server.router.context)
        finally:
            for key in list(self.server.router.context.keys()):
                if key not in saved_context and key not in ('bootstrap_snapshot',):
                    del self.server.router.context[key]
            self.server.router.context.update({k: v for k, v in saved_context.items()
                                               if k not in ('admin_session', 'set_cookies', 'new_session_id', 'secure_cookie', 'destroy_session')})

    def log_message(self, format, *args):
        logger.debug(f"Admin HTTP: {self.client_address[0]} - {format % args}")


class LoopbackIPv4Server(socketserver.ThreadingMixIn, HTTPServer):
    """Threaded HTTP server bound to 127.0.0.1 (IPv4 loopback)."""
    daemon_threads = True


class LoopbackIPv6Server(socketserver.ThreadingMixIn, HTTPServer):
    """Threaded HTTP server bound to ::1 (IPv6 loopback)."""
    daemon_threads = True
    address_family = __import__('socket').AF_INET6

    def server_bind(self):
        import socket
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        super().server_bind()


ThreadedHTTPServer = LoopbackIPv4Server


class AdminServer:
    """Manages the threaded HTTP server lifecycle."""

    def __init__(self, host: str, port: int, auth_manager, audit_manager, github_manager,
                 secret_backend=None, event_bus=None, runtime_engine=None,
                 local_operational_path=None, bootstrap_snapshot=None):
        self.host = host
        self.port = port
        self.server = None
        self.thread = None

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
        """Start dual-stack servers (127.0.0.1 + ::1) in background threads."""
        try:
            self.server4 = LoopbackIPv4Server(('127.0.0.1', self.port), AdminRequestHandler)
            self.server4.router = self.router
            self.server4.middleware = self.middleware
            self.thread4 = threading.Thread(target=self.server4.serve_forever, daemon=True)
            self.thread4.start()
            logger.info(f"Admin Server (IPv4) started at http://127.0.0.1:{self.port}")
        except Exception as e:
            logger.error(f"Failed to bind IPv4 (127.0.0.1:{self.port}): {e}")
            return False

        self.server6 = None
        self.thread6 = None
        try:
            self.server6 = LoopbackIPv6Server(('::1', self.port), AdminRequestHandler)
            self.server6.router = self.router
            self.server6.middleware = self.middleware
            self.thread6 = threading.Thread(target=self.server6.serve_forever, daemon=True)
            self.thread6.start()
            logger.info(f"Admin Server (IPv6) started at http://[::1]:{self.port}")
        except Exception as e:
            logger.warning(f"IPv6 loopback (::1:{self.port}) not available: {e} — IPv4-only mode")
            self.server6 = None
            self.thread6 = None

        return True

    def stop(self):
        """Stop all server sockets cleanly."""
        logger.info("Stopping Admin Server...")
        for srv, thr in [(getattr(self, 'server4', None), getattr(self, 'thread4', None)),
                         (getattr(self, 'server6', None), getattr(self, 'thread6', None))]:
            if srv:
                srv.shutdown()
                srv.server_close()
            if thr:
                thr.join(timeout=2.0)
        logger.info("Admin Server stopped")


def start_admin_server(host: str, port: int):
    """Convenience function to instantiate and run the AdminServer."""
    import time
    import sys
    from runtime.identity.runtime_identity import RuntimeIdentity
    from runtime.admin.auth import AdminSessionManager
    from runtime.admin.audit import AdminAuditLog
    from runtime.admin.github import GitHubAuthManager
    from runtime.secrets.backend import FileSecretBackend

    data_dir = get_data_dir()
    config = RuntimeConfig.load()
    config.data_dir = str(data_dir)

    identity_manager = RuntimeIdentity.load(data_dir)
    auth_manager = AdminSessionManager(str(data_dir), identity_manager.runtime_id)
    audit_manager = AdminAuditLog(str(data_dir), identity_manager.runtime_id)
    secret_backend = FileSecretBackend(str(data_dir / "secrets"), identity_manager._private_key)
    github_manager = GitHubAuthManager(secret_backend)

    from runtime.workspace.ephemeral import EphemeralWorkspaceManager
    from runtime.execution.manager import ExecutionManager
    from runtime.github.client import GitHubClient
    from runtime.github.discovery import OrganizationDiscoveryService
    github_client = GitHubClient(secret_backend=secret_backend) if github_manager.has_token() else None

    from runtime.fabric.github_adapter import GitHubFabricAdapter
    fabric_client = GitHubFabricAdapter(github_client=github_client, config=config) if github_client else None

    ephemeral_workspace_manager = EphemeralWorkspaceManager()
    execution_manager = ExecutionManager(
        workspace_manager=ephemeral_workspace_manager,
        audit_manager=audit_manager,
        github_client=github_client,
        fabric_client=fabric_client
    )

    disc_repos_raw = []
    if github_client:
        try:
            disc = OrganizationDiscoveryService(github_client)
            disc_repos_raw = disc.discover_repositories()
        except Exception as e:
            logger.warning(f"Startup discovery failed: {e}")

    engine = RuntimeEngine(config)

    server = AdminServer(
        host=host,
        port=port,
        auth_manager=auth_manager,
        audit_manager=audit_manager,
        github_manager=github_manager,
        secret_backend=secret_backend,
        event_bus=None,
        runtime_engine=engine,
        local_operational_path=None,
        bootstrap_snapshot={'result': None, 'discovered_repos': disc_repos_raw}
    )

    server.admin_context['execution_manager'] = execution_manager
    server.router.context['execution_manager'] = execution_manager

    def run_bootstrap():
        try:
            engine.startup(github_client=github_client, fabric_client=fabric_client)
        except Exception as e:
            logger.error(f"Runtime engine startup error: {e}")

    if server.start():
        t = threading.Thread(target=run_bootstrap, daemon=True)
        t.start()

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


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    config = RuntimeConfig.load()
    start_admin_server(config.admin_host, config.admin_port)
