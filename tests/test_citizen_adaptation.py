import base64
import hashlib
import json
from pathlib import Path

import pytest

from runtime.control_plane import RuntimeControlPlaneClient
from runtime.continuity.engine import ContinuityEngine
from runtime.evolution import ReleaseVerifier
from runtime.evolution.manager import EvolutionError, RuntimeEvolutionManager


def _public_bytes(private_key):
    from cryptography.hazmat.primitives import serialization
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def test_continuity_fresh_state_is_coherent(tmp_path):
    engine = ContinuityEngine(str(tmp_path))
    assert engine.status["state"] == "COHERENT"
    assert engine.status["generation"] == 0


def test_continuity_corruption_blocks_coherence(tmp_path):
    continuity = Path(tmp_path) / "continuity"
    continuity.mkdir()
    (continuity / "event_records.jsonl").write_text('{not-json}\n', encoding="utf-8")
    engine = ContinuityEngine(str(tmp_path))
    assert engine.status["state"] == "BLOCKED"
    assert engine.load_errors


def test_control_plane_is_best_effort_when_unconfigured():
    client = RuntimeControlPlaneClient(None)
    response = client.heartbeat({"runtime_id": "RUNTIME-TEST"})
    assert response.ok is False
    assert response.error == "CONTROL_PLANE_NOT_CONFIGURED"


def _signed_descriptor(private_key, artifact_hash, key_id):
    unsigned = {
        "version": "1.0.1",
        "artifact": "anny-runtime.bin",
        "artifact_sha256": artifact_hash,
        "runtime_version": "0.4.0",
        "compatibility": ">=0.4.0,<0.5.0",
        "signing_key_id": key_id,
    }
    payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = private_key.sign(payload)
    return {**unsigned, "signature": base64.b64encode(signature).decode("ascii")}


def test_release_descriptor_and_artifact_verification(tmp_path):
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"anny-test-artifact")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    private_key = Ed25519PrivateKey.generate()

    verifier = ReleaseVerifier(_public_bytes(private_key), "test-key-1")
    descriptor = _signed_descriptor(private_key, digest, "test-key-1")
    parsed = verifier.verify_descriptor(descriptor)
    assert parsed.version == "1.0.1"
    assert verifier.verify_artifact(parsed, artifact)

    descriptor["artifact_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="invalid release signature"):
        verifier.verify_descriptor(descriptor)


def test_evolution_prepare_commit_and_rollback(tmp_path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    artifact = tmp_path / "candidate.bin"
    artifact.write_bytes(b"v2")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    private_key = Ed25519PrivateKey.generate()
    verifier = ReleaseVerifier(_public_bytes(private_key), "test-key-2")
    descriptor = _signed_descriptor(private_key, digest, "test-key-2")

    install = tmp_path / "installed.bin"
    install.write_bytes(b"v1")
    manager = RuntimeEvolutionManager(str(tmp_path))
    prepared = manager.prepare(descriptor, str(artifact), verifier)
    committed = manager.commit(prepared["transaction_id"], str(install))
    assert install.read_bytes() == b"v2"
    assert committed["status"] == "COMMITTED"

    rolled = manager.rollback(prepared["transaction_id"])
    assert rolled["status"] == "ROLLED_BACK"
    assert install.read_bytes() == b"v1"


def test_evolution_rejects_bad_artifact(tmp_path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    artifact = tmp_path / "candidate.bin"
    artifact.write_bytes(b"v2")
    private_key = Ed25519PrivateKey.generate()
    verifier = ReleaseVerifier(_public_bytes(private_key), "test-key-3")
    descriptor = _signed_descriptor(private_key, "0" * 64, "test-key-3")

    manager = RuntimeEvolutionManager(str(tmp_path))
    with pytest.raises(EvolutionError, match="sha256 mismatch"):
        manager.prepare(descriptor, str(artifact), verifier)
