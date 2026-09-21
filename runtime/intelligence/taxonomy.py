"""Capability Taxonomy for ANNY Local Intelligence Layer.

Defines stable capability IDs (Phase 2-3 of MISSION-032).
ANNY uses these IDs as contracts; physical implementations are hidden from ANNY.

Separation:
  - DETERMINISTIC: filesystem, search, git, patch, terminal, debug, pytest
  - LOCAL_INFERENCE: analysis, summarization, classification, etc.
  - ANNY_SELF: fallback when local quality is insufficient
  - EXTERNAL_INFERENCE: external delegation path
"""

from typing import FrozenSet

# Deterministic capabilities: no inference benchmark required (Phase 31).
DETERMINISTIC_CAPABILITIES: FrozenSet[str] = frozenset([
    "filesystem.read", "filesystem.write", "filesystem.list",
    "schema.validate",
    "search.index", "search.query",
    "git.clone", "git.commit", "git.diff", "git.log",
    "patch.apply", "patch.parse", "patch.review",
    "terminal.execute", "terminal.pty",
    "debug.attach", "debug.breakpoint",
    "pytest.run", "pytest.parse",
    "workspace.index", "workspace.search",
])

# Local inference capabilities: require real benchmark certification (Phase 32).
LOCAL_INFERENCE_CAPABILITIES: FrozenSet[str] = frozenset([
    "text.summarization", "text.classification", "text.rewriting",
    "data.extraction", "data.analysis",
    "reasoning.analysis", "reasoning.comparison",
    "code.understanding", "code.generation", "code.editing",
    "test.generation", "bug.diagnosis",
    "tool.use", "tool.planning",
    "document.summarize", "document.classify",
    "architecture.analysis",
])

ALL_CAPABILITIES: FrozenSet[str] = DETERMINISTIC_CAPABILITIES | LOCAL_INFERENCE_CAPABILITIES

CAPABILITY_FAMILIES = {
    "language":      ["text.summarization", "text.classification", "text.rewriting"],
    "information":   ["data.extraction", "data.analysis"],
    "reasoning":     ["reasoning.analysis", "reasoning.comparison"],
    "code":          ["code.understanding", "code.generation", "code.editing", "test.generation", "bug.diagnosis"],
    "tool":          ["tool.use", "tool.planning"],
    "document":      ["document.summarize", "document.classify"],
    "schema":        ["schema.validate"],
    "architecture":  ["architecture.analysis"],
    "filesystem":    ["filesystem.read", "filesystem.write", "filesystem.list"],
    "search":        ["search.index", "search.query"],
    "git":           ["git.clone", "git.commit", "git.diff", "git.log"],
    "patch":         ["patch.apply", "patch.parse", "patch.review"],
    "terminal":      ["terminal.execute", "terminal.pty"],
    "debug":         ["debug.attach", "debug.breakpoint"],
    "pytest":        ["pytest.run", "pytest.parse"],
    "workspace":     ["workspace.index", "workspace.search"],
}


def is_deterministic(capability_id: str) -> bool:
    return capability_id in DETERMINISTIC_CAPABILITIES

def is_local_inference(capability_id: str) -> bool:
    return capability_id in LOCAL_INFERENCE_CAPABILITIES

def requires_benchmark(capability_id: str) -> bool:
    return is_local_inference(capability_id)

def get_family(capability_id: str) -> str:
    for family, members in CAPABILITY_FAMILIES.items():
        if capability_id in members:
            return family
    return "unknown"

def validate_capability_id(capability_id: str) -> bool:
    return capability_id in ALL_CAPABILITIES
