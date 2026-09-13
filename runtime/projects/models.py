import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

class ProjectStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    SUSPENDED = "SUSPENDED"

@dataclass
class Project:
    project_id: str
    account_id: str
    name: str
    repository_id: Optional[str]
    status: ProjectStatus
    created_at: datetime
