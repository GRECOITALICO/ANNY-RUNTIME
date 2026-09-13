import json
import logging
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional

from .models import Account, AccountStatus

logger = logging.getLogger(__name__)

class AccountRegistry:
    MAX_ACCOUNTS = 5

    def __init__(self, data_dir: str):
        self.accounts_dir = Path(data_dir) / "accounts"
        self.accounts_dir.mkdir(parents=True, exist_ok=True)
        self._accounts = {}
        self.load()

    def load(self) -> None:
        self._accounts = {}
        if not self.accounts_dir.exists():
            return
            
        for path in self.accounts_dir.glob("*.json"):
            if path.is_file():
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                    acc = Account(
                        account_id=data["account_id"],
                        github_principal=data["github_principal"],
                        account_type=data["account_type"],
                        credential_ref=data["credential_ref"],
                        status=AccountStatus(data["status"]),
                        created_at=datetime.fromisoformat(data["created_at"])
                    )
                    self._accounts[acc.account_id] = acc
                except Exception as e:
                    logger.error(f"Failed to load account from {path}: {e}")

    def save(self, account: Account) -> None:
        path = self.accounts_dir / f"{account.account_id}.json"
        data = {
            "account_id": account.account_id,
            "github_principal": account.github_principal,
            "account_type": account.account_type,
            "credential_ref": account.credential_ref,
            "status": account.status.value,
            "created_at": account.created_at.isoformat()
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def create_account(self, github_principal: str, account_type: str = "personal") -> Account:
        if len(self._accounts) >= self.MAX_ACCOUNTS:
            raise ValueError(f"Maximum of {self.MAX_ACCOUNTS} accounts reached")
            
        existing = self.find_by_principal(github_principal)
        if existing:
            return existing

        account_id = f"acct-{uuid.uuid4().hex[:8]}"
        account = Account(
            account_id=account_id,
            github_principal=github_principal,
            account_type=account_type,
            credential_ref=f"{account_id}-github-token",
            status=AccountStatus.ACTIVE,
            created_at=datetime.now(timezone.utc)
        )
        self._accounts[account_id] = account
        self.save(account)
        return account

    def get_account(self, account_id: str) -> Optional[Account]:
        return self._accounts.get(account_id)

    def find_by_principal(self, github_principal: str) -> Optional[Account]:
        for acc in self._accounts.values():
            if acc.github_principal.lower() == github_principal.lower():
                return acc
        return None

    def list_accounts(self) -> List[Account]:
        return list(self._accounts.values())

    def delete_account(self, account_id: str) -> bool:
        if account_id in self._accounts:
            del self._accounts[account_id]
            path = self.accounts_dir / f"{account_id}.json"
            if path.exists():
                path.unlink()
            return True
        return False
