from runtime.security.execution_context import ExecutionContext

class GenerationFence:
    def __init__(self, initial_generation: int = 1):
        self._current = initial_generation
        
    @property
    def current(self) -> int:
        return self._current
        
    def advance(self) -> None:
        self._current += 1
        
    def validate(self, context: ExecutionContext) -> bool:
        return context.generation == self._current
