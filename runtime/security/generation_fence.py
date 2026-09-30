class GenerationFence:
    def __init__(self, initial_generation: int = 1):
        self._current = initial_generation
        
    @property
    def current(self) -> int:
        return self._current
        
    def advance(self) -> None:
        self._current += 1
        
    def validate(self, runtime_generation: int) -> bool:
        """Validate only the local RuntimeGeneration fence value."""
        return isinstance(runtime_generation, int) and runtime_generation == self._current
