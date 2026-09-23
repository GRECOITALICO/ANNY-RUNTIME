"""Physical release-artifact provenance reconstruction for Batch 4A (#23)."""
import ast
import hashlib
import os
import re
import subprocess
import tarfile
from pathlib import Path

import pytest


ARTIFACT_NAME = re.compile(
    r"^ANNY-RUNTIME-v(?P<version>[0-9]+(?:\.[0-9]+)*)-"
    r"(?P<short_commit>[0-9a-f]{7,40})\.tar\.gz$"
)
SIDECAR_LINE = re.compile(r"^(?P<digest>[0-9a-f]{64})\s+\*?(?P<filename>.+)$")


def _assignment_values(source: str) -> dict[str, str]:
    """Extract literal version metadata without importing an archive member."""
    values = {}
    for node in ast.parse(source).body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            values[node.targets[0].id] = node.value.value
    return values


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _physical_artifact() -> Path:
    configured = os.environ.get("ANNY_RELEASE_ARTIFACT")
    if not configured:
        pytest.skip("physical release artifact was not supplied")
    artifact = Path(configured).resolve()
    assert artifact.is_file(), f"physical artifact does not exist: {artifact}"
    return artifact


def test_physical_artifact_reconstructs_full_release_identity():
    """Require filename, archive metadata, Git source, hash, and sidecar to agree."""
    artifact = _physical_artifact()
    root = Path(__file__).resolve().parents[1]
    name_match = ARTIFACT_NAME.fullmatch(artifact.name)
    assert name_match, f"invalid release artifact filename: {artifact.name}"

    source_commit = _git(root, "rev-parse", "--verify", f"{name_match['short_commit']}^{{commit}}")
    assert _git(root, "rev-parse", "--short=7", source_commit) == name_match["short_commit"]

    sidecar = artifact.with_name(f"{artifact.name}.sha256")
    assert sidecar.is_file(), f"checksum sidecar missing: {sidecar}"
    sidecar_records = [
        line.strip()
        for line in sidecar.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(sidecar_records) == 1, "sidecar must contain exactly one checksum record"
    sidecar_match = SIDECAR_LINE.fullmatch(sidecar_records[0])
    assert sidecar_match, f"invalid sidecar record: {sidecar_records[0]}"
    assert sidecar_match["filename"] == artifact.name
    assert sidecar_match["digest"] == hashlib.sha256(artifact.read_bytes()).hexdigest()

    with tarfile.open(artifact, "r:gz") as archive:
        members = [
            member for member in archive.getmembers()
            if member.name.endswith("/runtime/core/version.py")
        ]
        assert len(members) == 1, "archive must contain exactly one runtime version metadata file"
        embedded_source = archive.extractfile(members[0])
        assert embedded_source is not None
        embedded = _assignment_values(embedded_source.read().decode("utf-8"))

    source = _assignment_values(_git(root, "show", f"{source_commit}:runtime/core/version.py"))
    assert embedded["__version__"] == name_match["version"]
    assert embedded["__version__"] == source["__version__"]
    assert embedded["__commit__"] == source_commit
    assert embedded["__commit__"] not in {"dev", "unknown", "HEAD"}
    assert re.fullmatch(r"[0-9a-f]{40}", embedded["__commit__"])
    assert _git(root, "rev-parse", "--verify", f"{embedded['__commit__']}^{{commit}}") == source_commit
    assert embedded["__build_time__"] not in {"", "unknown"}
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", embedded["__build_time__"])
