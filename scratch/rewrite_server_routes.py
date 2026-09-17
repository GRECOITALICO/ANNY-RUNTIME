import os
import re

with open("/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME/runtime/admin/server.py", "r") as f:
    code = f.read()

target_block = """            if self.path.split('?', 1)[0] == '/api/sync':
                sync_service = self.server.router.context.get('sync_service')
                if sync_service is None:
                    self.server.router._send_json(self, {
                        'status': 'failed',
                        'sync_state': 'FAILED',
                        'error_classification': 'SYNC_SERVICE_UNAVAILABLE',
                    }, status=503)
                else:
                    self.server.router._send_json(self, sync_service.start())
                self.server.middleware.process_response(self.server.router.context)
                return"""

new_block = """            if self.path.split('?', 1)[0] == '/api/sync':
                sync_service = self.server.router.context.get('sync_service')
                if sync_service is None:
                    self.server.router._send_json(self, {'status': 'failed', 'sync_state': 'FAILED', 'error_classification': 'SYNC_SERVICE_UNAVAILABLE'}, status=503)
                else:
                    self.server.router._send_json(self, sync_service.start())
                self.server.middleware.process_response(self.server.router.context)
                return

            if self.path.split('?', 1)[0] == '/api/sync/stage':
                sync_service = self.server.router.context.get('sync_service')
                if sync_service is None:
                    self.server.router._send_json(self, {'status': 'failed', 'sync_state': 'FAILED', 'error_classification': 'SYNC_SERVICE_UNAVAILABLE'}, status=503)
                else:
                    self.server.router._send_json(self, sync_service.stage())
                self.server.middleware.process_response(self.server.router.context)
                return

            if self.path.split('?', 1)[0] == '/api/sync/activate':
                sync_service = self.server.router.context.get('sync_service')
                if sync_service is None:
                    self.server.router._send_json(self, {'status': 'failed', 'sync_state': 'FAILED', 'error_classification': 'SYNC_SERVICE_UNAVAILABLE'}, status=503)
                else:
                    self.server.router._send_json(self, sync_service.activate())
                self.server.middleware.process_response(self.server.router.context)
                return

            if self.path.split('?', 1)[0] == '/api/sync/rollback':
                sync_service = self.server.router.context.get('sync_service')
                if sync_service is None:
                    self.server.router._send_json(self, {'status': 'failed', 'sync_state': 'FAILED', 'error_classification': 'SYNC_SERVICE_UNAVAILABLE'}, status=503)
                else:
                    self.server.router._send_json(self, sync_service.rollback())
                self.server.middleware.process_response(self.server.router.context)
                return"""

if target_block in code:
    code = code.replace(target_block, new_block)
    with open("/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME/runtime/admin/server.py", "w") as f:
        f.write(code)
    print("Updated server.py successfully.")
else:
    print("Could not find the target block in server.py")

