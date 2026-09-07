"""Admin HTTP Server using Python stdlib.

Binds to local interface, integrates router and middleware.
"""
import cgi
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
        ctype, pdict = cgi.parse_header(self.headers.get('content-type', ''))
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
    
    def __init__(self, host: str, port: int, auth_manager, audit_manager, github_manager, runtime_engine=None):
        self.host = host
        self.port = port
        self.server = None
        self.thread = None
        
        # Initialize context for router
        self.admin_context = {
            'auth_manager': auth_manager,
            'audit_manager': audit_manager,
            'github_manager': github_manager,
            'runtime_engine': runtime_engine
        }
        
        self.router = AdminRouter(self.admin_context)
        self.middleware = AdminMiddleware(auth_manager)
        
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
