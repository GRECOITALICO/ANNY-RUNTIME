import datetime
from dataclasses import dataclass

@dataclass
class PendingSubmissionAuthorization:
    auth_id: str
    session_id: str
    target_id: str
    expected_method: str
    expected_url: str
    expected_frame_id: str
    issued_at: float
    expires_at: float

@dataclass(frozen=True)
class BrowserActionAuthorization:
    action_id: str              # Unique ID for this specific approved action
    capability: str             # e.g., "BROWSER_EXTERNAL_SUBMIT"
    session_id: str             # Bound to the specific browser session
    target_id: str              # Broker-owned ID of the form/button
    consequence_class: str      # e.g., "EXTERNAL_CONSEQUENCE"
    issued_by: str              # L1 / human approver
    issued_at: datetime.datetime
    expires_at: datetime.datetime
    requires_review: bool       
    evidence_policy: str        # e.g., "FULL_DOM_SNAPSHOT_AND_TRACE"

    def is_valid(self, current_time: datetime.datetime, session_id: str, target_id: str) -> bool:
        if self.session_id != session_id:
            return False
        if self.target_id != target_id:
            return False
        if current_time > self.expires_at:
            return False
        if current_time < self.issued_at:
            return False
        return True
