import json
import logging
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional

from .models import Project, ProjectStatus

logger = logging.getLogger(__name__)

class ProjectRegistry:
    def __init__(self, data_dir: str):
        self.projects_dir = Path(data_dir) / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self._projects = {}
        self.load()

    def load(self) -> None:
        self._projects = {}
        if not self.projects_dir.exists():
            return
            
        for path in self.projects_dir.glob("*.json"):
            if path.is_file():
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                    proj = Project(
                        project_id=data["project_id"],
                        account_id=data["account_id"],
                        name=data["name"],
                        repository_id=data.get("repository_id"),
                        status=ProjectStatus(data["status"]),
                        created_at=datetime.fromisoformat(data["created_at"])
                    )
                    self._projects[proj.project_id] = proj
                except Exception as e:
                    logger.error(f"Failed to load project from {path}: {e}")

    def save(self, project: Project) -> None:
        path = self.projects_dir / f"{project.project_id}.json"
        data = {
            "project_id": project.project_id,
            "account_id": project.account_id,
            "name": project.name,
            "repository_id": project.repository_id,
            "status": project.status.value,
            "created_at": project.created_at.isoformat()
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def create_project(self, account_id: str, name: str, repository_id: Optional[str] = None) -> Project:
        project_id = f"proj-{uuid.uuid4().hex[:8]}"
        project = Project(
            project_id=project_id,
            account_id=account_id,
            name=name,
            repository_id=repository_id,
            status=ProjectStatus.ACTIVE,
            created_at=datetime.now(timezone.utc)
        )
        self._projects[project_id] = project
        self.save(project)
        return project

    def get_project(self, project_id: str) -> Optional[Project]:
        return self._projects.get(project_id)

    def list_projects(self, account_id: Optional[str] = None) -> List[Project]:
        if account_id:
            return [p for p in self._projects.values() if p.account_id == account_id]
        return list(self._projects.values())

    def delete_project(self, project_id: str) -> bool:
        if project_id in self._projects:
            del self._projects[project_id]
            path = self.projects_dir / f"{project_id}.json"
            if path.exists():
                path.unlink()
            return True
        return False
