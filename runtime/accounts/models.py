import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

class AccountStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DISCONNECTED = "DISCONNECTED"

@dataclass
class Account:
    account_id: str
    github_principal: str
    account_type: str
    credential_ref: str
    status: AccountStatus
    created_at: datetime
