from dataclasses import dataclass

@dataclass
class RuntimePolicy:
    version: str = "1.0.0"
    allow_llm: bool = False
    enforce_strict_isolation: bool = True
