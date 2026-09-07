import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from pathlib import Path

@dataclass
class ExecutionReceipt:
    receipt_id: str
    operation_id: str
    execution_id: str
    runtime_id: str
    workspace_id: str
    actor_id: str
    session_id: str
    tenant_id: str
    tool: str
    status: str
    started_at: str
    finished_at: str
    runtime_generation: int
    duration_ms: int
    exit_code: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class ReceiptStore:
    """Store for managing execution receipts."""
    def __init__(self, data_dir: str) -> None:
        self.data_dir = Path(data_dir)
        self.receipts_dir = self.data_dir / "receipts"
        self.receipts_dir.mkdir(parents=True, exist_ok=True)

    def store(self, receipt: ExecutionReceipt) -> None:
        date_str = receipt.started_at[:10] if len(receipt.started_at) >= 10 else "unknown"
        date_dir = self.receipts_dir / date_str
        date_dir.mkdir(parents=True, exist_ok=True)
        file_path = date_dir / f"{receipt.receipt_id}.json"
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(asdict(receipt), f, indent=2)

    def get(self, receipt_id: str) -> Optional[ExecutionReceipt]:
        for date_dir in self.receipts_dir.iterdir():
            if date_dir.is_dir():
                file_path = date_dir / f"{receipt_id}.json"
                if file_path.exists():
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return ExecutionReceipt(**data)
        return None

    def list_receipts(self, operation_id: Optional[str] = None, date: Optional[str] = None) -> List[ExecutionReceipt]:
        receipts = []
        dirs_to_check = [self.receipts_dir / date] if date else [d for d in self.receipts_dir.iterdir() if d.is_dir()]
        for date_dir in dirs_to_check:
            if date_dir.exists() and date_dir.is_dir():
                for file_path in date_dir.iterdir():
                    if file_path.name.endswith(".json"):
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            receipt = ExecutionReceipt(**data)
                            if operation_id is None or receipt.operation_id == operation_id:
                                receipts.append(receipt)
        return receipts
