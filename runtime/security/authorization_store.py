import json
import os
from dataclasses import asdict, dataclass
from typing import Dict, Optional

from runtime.security.execution_context import ExecutionContext

@dataclass
class Grant:
    tenant_id: str
    actor_id: str
    capability: str
    workspace_id: str
    generation: int
    
class AuthorizationStore:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self._grants: Dict[str, Grant] = {}
        
    def _make_key(self, tenant_id: str, actor_id: str, capability: str, workspace_id: str) -> str:
        return f"{tenant_id}:{actor_id}:{capability}:{workspace_id}"

    def grant(self, tenant_id: str, actor_id: str, capability: str, workspace_id: str, generation: int) -> None:
        key = self._make_key(tenant_id, actor_id, capability, workspace_id)
        self._grants[key] = Grant(tenant_id, actor_id, capability, workspace_id, generation)
        
    def revoke(self, tenant_id: str, actor_id: str, capability: str, workspace_id: str) -> None:
        key = self._make_key(tenant_id, actor_id, capability, workspace_id)
        if key in self._grants:
            del self._grants[key]
            
    def check(self, context: ExecutionContext, capability: str) -> bool:
        key_specific = self._make_key(context.tenant_id, context.actor_id, capability, context.workspace_id)
        key_wildcard = self._make_key(context.tenant_id, context.actor_id, capability, "*")
        
        grant = self._grants.get(key_specific) or self._grants.get(key_wildcard)
        if not grant:
            return False
            
        return grant.generation == context.generation
        
    def load(self) -> None:
        if os.path.exists(self.filepath):
            with open(self.filepath, "r") as f:
                data = json.load(f)
                self._grants = {
                    k: Grant(**v) for k, v in data.items()
                }
                
    def save(self) -> None:
        data = {k: asdict(v) for k, v in self._grants.items()}
        os.makedirs(os.path.dirname(os.path.abspath(self.filepath)), exist_ok=True)
        with open(self.filepath, "w") as f:
            json.dump(data, f)
