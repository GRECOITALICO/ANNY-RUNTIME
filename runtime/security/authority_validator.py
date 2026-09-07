import datetime
from dataclasses import replace

from runtime.security.execution_context import ExecutionContext
from runtime.security.authorization_store import AuthorizationStore
from runtime.security.generation_fence import GenerationFence

class SecurityViolationError(Exception):
    pass

class AuthorityValidator:
    def __init__(self, auth_store: AuthorizationStore, gen_fence: GenerationFence):
        self.auth_store = auth_store
        self.gen_fence = gen_fence

    def validate_context(self, context: ExecutionContext) -> ExecutionContext:
        if context.generation != self.gen_fence.current:
            raise SecurityViolationError("Context generation mismatch.")
            
        now = datetime.datetime.now(context.expires_at.tzinfo)
        if now > context.expires_at:
            raise SecurityViolationError("Context has expired.")
            
        valid_capabilities = set()
        for cap in context.capabilities:
            if self.auth_store.check(context, cap):
                valid_capabilities.add(cap)
                
        return replace(context, capabilities=valid_capabilities)
