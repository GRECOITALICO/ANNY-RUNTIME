import json
import datetime
import fcntl
from pathlib import Path


class StaleGenerationError(Exception):
    """Raised when runtime generation fencing fails."""
    pass


class RuntimeGeneration:
    """Generation counter for runtime fencing."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.filepath = self.data_dir / "generation.json"
        self._current_gen = 0
        self._load()

    def _load(self) -> None:
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._current_gen = data.get("generation", 0)
            except (json.JSONDecodeError, OSError):
                self._current_gen = 0
        else:
            self._current_gen = 0

    @property
    def current(self) -> int:
        return self._current_gen

    def increment(self) -> int:
        """Atomically increments and persists the generation."""
        if not self.filepath.exists():
            self.filepath.touch(exist_ok=True)
            
        with open(self.filepath, "r+", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                data = f.read()
                current = 0
                if data:
                    try:
                        jdata = json.loads(data)
                        current = jdata.get("generation", 0)
                    except json.JSONDecodeError:
                        pass
                
                self._current_gen = current + 1
                
                f.seek(0)
                f.truncate()
                json.dump({
                    "generation": self._current_gen,
                    "incremented_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }, f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                
        return self._current_gen

    def validate(self, generation: int) -> bool:
        """Returns True if generation matches current."""
        return generation == self._current_gen

    def fence(self, generation: int) -> None:
        """Raises StaleGenerationError if generation != current."""
        if not self.validate(generation):
            raise StaleGenerationError(f"Generation mismatch. Expected {self._current_gen}, got {generation}")
