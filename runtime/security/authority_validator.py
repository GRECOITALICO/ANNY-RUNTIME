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

    def validate_context(
        self,
        context: ExecutionContext,
        expected_external_generation: int | None = None,
    ) -> ExecutionContext:
        if expected_external_generation is not None and not context.matches_external_generation(expected_external_generation):
            raise SecurityViolationError("External ExecutionContext generation mismatch.")

        now = datetime.datetime.now(context.expires_at.tzinfo)
        if not context.is_valid(now):
            raise SecurityViolationError("Context has expired or is not currently valid.")
            
        valid_capabilities = set()
        for cap in context.capabilities:
            if self.auth_store.check(context, cap):
                valid_capabilities.add(cap)
                
        return replace(context, capabilities=valid_capabilities)
