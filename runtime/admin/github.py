"""GitHub authorization manager.

Primary onboarding method: GitHub Device Flow (RFC 8628).
Recovery/migration method: GitHub Access Token (manual).

Token values are stored via SecretBackend and NEVER returned to the browser.
Only status information (connected, principal, scopes) is exposed through DTOs."""
import json
import logging
import time
import urllib.request
import urllib.parse
import urllib.error
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from runtime.telemetry.telemetry import TelemetryEnvelope
from runtime.telemetry.context import TraceContext

logger = logging.getLogger(__name__)

GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_USER_URL = "https://api.github.com/user"


@dataclass
class GitHubDeviceFlowState:
    """State for an in-progress GitHub Device Flow authorization."""
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int
    started_at: float = field(default_factory=time.time)


@dataclass
class GitHubCredentialState:
    """Internal state for the GitHub credential.
    Token value is NEVER exposed to the browser."""
    principal: Optional[str] = None
    auth_status: str = "UNAUTHORIZED"
    token_status: str = "MISSING"
    token_expiry: Optional[str] = None
    scopes: List[str] = field(default_factory=list)
    last_validation: Optional[str] = None
    last_failure: Optional[str] = None
    last_failure_reason: Optional[str] = None


class GitHubAuthManager:
    """Manages GitHub authorization.

    Primary onboarding method: GitHub Device Flow (RFC 8628).
    Recovery/migration method: GitHub Access Token (manual).

    Token values are stored via SecretBackend and NEVER returned to the browser.
    Only status information (connected, principal, scopes) is exposed.
    """

    GITHUB_TOKEN_REF = "github-access-token"
    GITHUB_STATE_REF = "github-state"

    def __init__(self, secret_backend, client_id: str = "", telemetry_collector=None):
        self.secret_backend = secret_backend
        self.client_id = client_id
        self.telemetry_collector = telemetry_collector
        self.state = GitHubCredentialState()
        self._device_flow: Optional[GitHubDeviceFlowState] = None
        self._load_state()

    def _load_state(self) -> None:
        """Load persisted credential state (not the token itself)."""
        try:
            state_bytes = self.secret_backend.retrieve(self.GITHUB_STATE_REF)
            if state_bytes:
                data = json.loads(state_bytes.decode('utf-8'))
                self.state = GitHubCredentialState(**data)
        except Exception as e:
            logger.warning(f"Failed to load GitHub state: {e}")

    def _save_state(self) -> None:
        """Persist credential state (not the token)."""
        try:
            state_json = json.dumps(asdict(self.state)).encode('utf-8')
            self.secret_backend.store(self.GITHUB_STATE_REF, state_json)
        except Exception as e:
            logger.error(f"Failed to save GitHub state: {e}")

    def get_status(self):
        """Return a sanitized status DTO. Never returns token values."""
        from runtime.admin.dto import GitHubStatusDTO
        return GitHubStatusDTO(
            connected=self.state.auth_status == "AUTHORIZED",
            principal=self.state.principal,
            auth_status=self.state.auth_status,
            token_status=self.state.token_status,
            token_expiry=self.state.token_expiry,
            scopes=list(self.state.scopes),
            last_validation=self.state.last_validation,
            last_failure=self.state.last_failure,
            last_failure_reason=self.state.last_failure_reason
        )

    def initiate_device_flow(self) -> Optional[GitHubDeviceFlowState]:
        """Start the GitHub Device Flow. Returns GitHubDeviceFlowState or None."""
        if not self.client_id:
            logger.warning("GitHub client_id not configured")
            return None
        try:
            data = urllib.parse.urlencode({
                'client_id': self.client_id,
                'scope': 'repo read:org'
            }).encode('utf-8')
            req = urllib.request.Request(
                GITHUB_DEVICE_CODE_URL, data=data,
                headers={'Accept': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode('utf-8'))

            self._device_flow = GitHubDeviceFlowState(
                device_code=result['device_code'],
                user_code=result['user_code'],
                verification_uri=result['verification_uri'],
                expires_in=result.get('expires_in', 900),
                interval=result.get('interval', 5)
            )
            return self._device_flow
        except Exception as e:
            logger.error(f"Failed to initiate device flow: {e}")
            self.state.last_failure = datetime.now(timezone.utc).isoformat()
            self.state.last_failure_reason = str(e)
            self._save_state()
            return None

    def poll_device_flow(self) -> dict:
        """Poll GitHub for device flow completion. Returns dict with 'status' key."""
        if not self._device_flow:
            return {'status': 'NO_ACTIVE_FLOW'}
        elapsed = time.time() - self._device_flow.started_at
        if elapsed > self._device_flow.expires_in:
            self._device_flow = None
            return {'status': 'EXPIRED'}
        try:
            data = urllib.parse.urlencode({
                'client_id': self.client_id,
                'device_code': self._device_flow.device_code,
                'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
            }).encode('utf-8')
            req = urllib.request.Request(
                GITHUB_ACCESS_TOKEN_URL, data=data,
                headers={'Accept': 'application/json'}
            )
            if self.telemetry_collector:
                self.telemetry_collector.emit(TelemetryEnvelope.create(
                    component="github_auth",
                    event_type="github.request.started",
                    metadata={"operation": "poll_device_flow"}
                ))
            start_time = time.time()
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    result = json.loads(resp.read().decode('utf-8'))
                duration = int((time.time() - start_time) * 1000)
                if self.telemetry_collector:
                    self.telemetry_collector.emit(TelemetryEnvelope.create(
                        component="github_auth",
                        event_type="github.request.completed",
                        duration_ms=duration,
                        metadata={"operation": "poll_device_flow", "status_code": resp.getcode()}
                    ))
            except Exception as e:
                duration = int((time.time() - start_time) * 1000)
                if self.telemetry_collector:
                    self.telemetry_collector.emit(TelemetryEnvelope.create(
                        component="github_auth",
                        event_type="github.request.failed",
                        duration_ms=duration,
                        metadata={"operation": "poll_device_flow", "error": type(e).__name__}
                    ))
                raise e

            if 'access_token' in result:
                token = result['access_token']
                self.secret_backend.store(
                    self.GITHUB_TOKEN_REF, token.encode('utf-8'))
                self._device_flow = None
                self.validate()
                return {'status': 'AUTHORIZED'}

            error = result.get('error', 'unknown')
            if error == 'authorization_pending':
                return {'status': 'PENDING'}
            elif error == 'slow_down':
                if self._device_flow:
                    self._device_flow.interval += 5
                return {'status': 'SLOW_DOWN'}
            elif error == 'expired_token':
                self._device_flow = None
                return {'status': 'EXPIRED'}
            elif error == 'access_denied':
                self._device_flow = None
                return {'status': 'DENIED'}
            else:
                return {'status': 'ERROR', 'error': error}
        except Exception as e:
            logger.error(f"Device flow poll failed: {e}")
            return {'status': 'ERROR', 'error': str(e)}

    def validate(self) -> bool:
        """Validate the current GitHub token by calling the GitHub API."""
        token_bytes = self.secret_backend.retrieve(self.GITHUB_TOKEN_REF)
        if not token_bytes:
            self.state.auth_status = "UNAUTHORIZED"
            self.state.token_status = "MISSING"
            self.state.principal = None
            self.state.scopes = []
            self._save_state()
            return False

        token = token_bytes.decode('utf-8')
        try:
            req = urllib.request.Request(
                GITHUB_API_USER_URL,
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
            )
            if self.telemetry_collector:
                self.telemetry_collector.emit(TelemetryEnvelope.create(
                    component="github_auth",
                    event_type="github.request.started",
                    metadata={"operation": "validate"}
                ))
            start_time = time.time()
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    user_data = json.loads(resp.read().decode('utf-8'))
                    scopes_header = resp.headers.get('X-OAuth-Scopes', '')
                duration = int((time.time() - start_time) * 1000)
                if self.telemetry_collector:
                    self.telemetry_collector.emit(TelemetryEnvelope.create(
                        component="github_auth",
                        event_type="github.request.completed",
                        duration_ms=duration,
                        metadata={"operation": "validate", "status_code": resp.getcode()}
                    ))
            except Exception as e:
                duration = int((time.time() - start_time) * 1000)
                if self.telemetry_collector:
                    self.telemetry_collector.emit(TelemetryEnvelope.create(
                        component="github_auth",
                        event_type="github.request.failed",
                        duration_ms=duration,
                        metadata={"operation": "validate", "error": type(e).__name__}
                    ))
                raise e

            self.state.principal = user_data.get('login', 'unknown')
            self.state.auth_status = "AUTHORIZED"
            self.state.token_status = "VALID"
            self.state.scopes = [s.strip() for s in scopes_header.split(',')
                                 if s.strip()]
            self.state.last_validation = datetime.now(timezone.utc).isoformat()
            self.state.last_failure = None
            self.state.last_failure_reason = None
            self._save_state()
            logger.info(f"GitHub validation successful: {self.state.principal}")
            return True

        except urllib.error.HTTPError as e:
            self.state.auth_status = "EXPIRED" if e.code == 401 else "DEGRADED"
            self.state.token_status = "EXPIRED" if e.code == 401 else "UNKNOWN"
            self.state.last_failure = datetime.now(timezone.utc).isoformat()
            self.state.last_failure_reason = f"HTTP {e.code}"
            self._save_state()
            return False

        except Exception as e:
            self.state.auth_status = "DEGRADED"
            self.state.token_status = "UNKNOWN"
            self.state.last_failure = datetime.now(timezone.utc).isoformat()
            self.state.last_failure_reason = str(e)
            self._save_state()
            return False

    def disconnect(self) -> None:
        """Remove the GitHub credential."""
        self.secret_backend.delete(self.GITHUB_TOKEN_REF)
        self.state = GitHubCredentialState()
        self._save_state()
        logger.info("GitHub disconnected")

    def has_token(self) -> bool:
        """Check if a token exists without exposing it."""
        return self.secret_backend.exists(self.GITHUB_TOKEN_REF)

    def store_and_validate_token(self, token: str) -> dict:
        """Store a GitHub token (recovery/migration) and validate it.
        
        Returns a dict with:
          - success: bool
          - principal: str or None
          - scopes: list[str]
          - error: str or None (safe message, no token content)
        """
        try:
            req = urllib.request.Request(
                GITHUB_API_USER_URL,
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
            )
            if self.telemetry_collector:
                self.telemetry_collector.emit(TelemetryEnvelope.create(
                    component="github_auth",
                    event_type="github.request.started",
                    metadata={"operation": "store_and_validate_token"}
                ))
            start_time = time.time()
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    user_data = json.loads(resp.read().decode('utf-8'))
                    scopes_header = resp.headers.get('X-OAuth-Scopes', '')
                duration = int((time.time() - start_time) * 1000)
                if self.telemetry_collector:
                    self.telemetry_collector.emit(TelemetryEnvelope.create(
                        component="github_auth",
                        event_type="github.request.completed",
                        duration_ms=duration,
                        metadata={"operation": "store_and_validate_token", "status_code": resp.getcode()}
                    ))
            except Exception as e:
                duration = int((time.time() - start_time) * 1000)
                if self.telemetry_collector:
                    self.telemetry_collector.emit(TelemetryEnvelope.create(
                        component="github_auth",
                        event_type="github.request.failed",
                        duration_ms=duration,
                        metadata={"operation": "store_and_validate_token", "error": type(e).__name__}
                    ))
                raise e

            principal = user_data.get('login', 'unknown')
            scopes = [s.strip() for s in scopes_header.split(',') if s.strip()]
            
            if 'repo' not in scopes or 'read:org' not in scopes:
                missing = [s for s in ('repo', 'read:org') if s not in scopes]
                return {'success': False, 'principal': principal, 'scopes': scopes, 'error': f'Missing required scopes: {", ".join(missing)}'}
            
            self.secret_backend.store(self.GITHUB_TOKEN_REF, token.encode('utf-8'))
            self.state.principal = principal
            self.state.auth_status = "AUTHORIZED"
            self.state.token_status = "VALID"
            self.state.scopes = scopes
            self.state.last_validation = datetime.now(timezone.utc).isoformat()
            self.state.last_failure = None
            self.state.last_failure_reason = None
            self._save_state()
            logger.info(f"GitHub validation successful: {self.state.principal}")
            return {'success': True, 'principal': principal, 'scopes': scopes, 'error': None}
        
        except urllib.error.HTTPError as e:
            error_msg = f"HTTP {e.code}"
            if e.code in (401, 403):
                error_msg = "GitHub connection failed. Token may be invalid or expired."
            return {'success': False, 'principal': None, 'scopes': [], 'error': error_msg}
        except Exception as e:
            return {'success': False, 'principal': None, 'scopes': [], 'error': f"Connection error: {type(e).__name__}"}
