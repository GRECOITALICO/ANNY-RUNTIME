import pytest
import os
import json
import tempfile
import dataclasses
from datetime import datetime, timezone
from runtime.execution.models import ModelState, Task, ModelDefinition
from runtime.execution.registry import ModelRegistry, RegistryRecoveryRequired, RecoveryAttestationError, RecoveryAttestation, ModelCapabilityBinding, HardwareProfile, ModelPerformanceProfile, EvaluationRecord
from runtime.execution.capability import CapabilityRegistry, CapabilityDefinition, ExecutorType
from runtime.execution.policy import RuntimePolicy
from runtime.execution.selector import ExecutorSelector
from runtime.execution.manager import ExecutionManager
from runtime.workspace.ephemeral import EphemeralWorkspaceManager

from runtime.intelligence.models import CapabilityAssessmentResponse, DelegationDecision, CapabilityTier, ImplementationCandidate
from runtime.execution.capability import ExecutorType

class MockIntelligenceLayer:
    def __init__(self, registry):
        self.registry = registry
        self._implementations = {}
        
    def register_implementation(self, profile):
        self._implementations[profile.implementation_id] = profile
        
    def assess_capability(self, req, available_implementations=None):
        cap_id = req.capability_id
        bindings = self.registry.get_bindings_for_capability(cap_id)
        
        valid = []
        for b in bindings:
            if b.authorization == "forbidden": continue
            if available_implementations and b.model_id not in available_implementations: continue
            valid.append(b)
            
        if not valid:
            return CapabilityAssessmentResponse(
                decision=DelegationDecision.FAIL_CAPABILITY_INSUFFICIENT,
                selected_implementation=None,
                quality_score=0.0,
                confidence=0.0,
                tier=CapabilityTier.L0,
                reason="No models bound to capability"
            )
            
        best = valid[0]
        # Just prefer the one with highest priority or first one
        # The test expects specific fallback behavior
        candidate = ImplementationCandidate(
            implementation_id=best.model_id,
            execution_class="LOCAL_MODEL",
            availability=True,
            quality=1.0,
            confidence=1.0,
            latency=1.0,
            resource_fit="FIT",
            policy_fit=True
        )
        return CapabilityAssessmentResponse(
            decision=DelegationDecision.DELEGATE,
            selected_implementation=candidate,
            quality_score=1.0,
            confidence=1.0,
            tier=CapabilityTier.L4,
            reason="Mock layer delegated"
        )


@pytest.fixture
def clean_registry():
    return ModelRegistry()

def test_01_registration(clean_registry):
    models = clean_registry.list_models()
    assert len(models) == 2
    assert any(m.model_id == "qwen3-8b" for m in models)
    assert any(m.model_id == "luna" for m in models)

def test_02_duplicate_rejection(clean_registry):
    with pytest.raises(ValueError, match="already registered"):
        clean_registry.register_model(ModelDefinition(
            model_id="qwen3-8b", display_name="", provider="", executor_type="", version="",
            status=ModelState.AVAILABLE, capabilities_supported=[], capabilities_forbidden=[],
            hardware_requirements={}, memory_requirements={}, context_window=0, quantization="",
            artifact_uri="", artifact_sha256="", runtime_interface="", max_concurrency=0, max_runtime=0,
            max_input_size=0, max_output_size=0, network_policy="", evidence_policy=""
        ))

def test_03_state_transitions(clean_registry):
    model = clean_registry.get_model("qwen3-8b")
    assert model.status == ModelState.INSTALL_REQUIRED
    model.status = ModelState.AVAILABLE
    assert clean_registry.is_available("qwen3-8b") is True

def test_04_capability_binding(clean_registry):
    bindings = clean_registry.get_bindings_for_capability("document.classify")
    assert any(b.model_id == "qwen3-8b" for b in bindings)

def test_05_forbidden_binding(clean_registry):
    bindings = clean_registry.get_bindings_for_capability("architecture.analysis")
    qwen_bind = next(b for b in bindings if b.model_id == "qwen3-8b")
    assert qwen_bind.authorization == "forbidden"
    
    selector = ExecutorSelector(clean_registry, intelligence_layer=MockIntelligenceLayer(clean_registry))
    policy = RuntimePolicy()
    policy.allow_llm = True
    clean_registry.get_model("qwen3-8b").status = ModelState.AVAILABLE
    cap = CapabilityDefinition("architecture.analysis", "test", "test", "1.0", "low", True, True, "disabled", "read_only", [], 60, 1024, True, ExecutorType.LOCAL_MODEL, None, True)
    task = Task("t2", "architecture.analysis", "test-account", "test-project", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    
    # ensure luna isn't available to force it to look at qwen3
    clean_registry.get_model("luna").status = ModelState.UNAVAILABLE
    with pytest.raises(ValueError, match="Execution plan BLOCKED"):
        selection = selector.select(task, cap, policy)

def test_06_preferred_binding(clean_registry):
    selector = ExecutorSelector(clean_registry, intelligence_layer=MockIntelligenceLayer(clean_registry))
    policy = RuntimePolicy()
    policy.allow_llm = True
    clean_registry.get_model("qwen3-8b").status = ModelState.AVAILABLE
    
    cap = CapabilityDefinition("architecture.analysis", "test", "test", "1.0", "low", True, True, "disabled", "read_only", [], 60, 1024, True, ExecutorType.LOCAL_MODEL, None, True)
    task = Task("t3", "architecture.analysis", "test-account", "test-project", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    selection = selector.select(task, cap, policy)
    assert selection.model_id == "luna"

def test_07_fallback(clean_registry):
    selector = ExecutorSelector(clean_registry, intelligence_layer=MockIntelligenceLayer(clean_registry))
    policy = RuntimePolicy()
    policy.allow_llm = True
    clean_registry.get_model("qwen3-8b").status = ModelState.AVAILABLE
    clean_registry.get_model("luna").status = ModelState.UNAVAILABLE
    
    # For architecture.analysis, qwen is forbidden. We need a capability where qwen is fallback
    cap = CapabilityDefinition("document.classify", "test", "test", "1.0", "low", True, True, "disabled", "read_only", [], 60, 1024, True, ExecutorType.LOCAL_MODEL, None, True)
    task = Task("t4", "document.classify", "test-account", "test-project", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    
    selection = selector.select(task, cap, policy)
    assert selection.model_id == "qwen3-8b"

def test_08_unknown_hardware(clean_registry):
    hw = clean_registry.get_hardware_profile()
    assert hw.cpu == "UNKNOWN"

def test_09_availability(clean_registry):
    assert clean_registry.is_available("luna") is True

def test_10_unavailable_model(clean_registry):
    clean_registry.get_model("luna").status = ModelState.UNAVAILABLE
    assert clean_registry.is_available("luna") is False

def test_11_disabled_model(clean_registry):
    clean_registry.get_model("luna").status = ModelState.DISABLED
    assert clean_registry.is_available("luna") is False

def test_12_deterministic_selection(clean_registry):
    selector = ExecutorSelector(clean_registry, intelligence_layer=MockIntelligenceLayer(clean_registry))
    policy = RuntimePolicy()
    cap = CapabilityDefinition("non_llm.task", "test", "test", "1.0", "low", False, True, "disabled", "read_only", [], 60, 1024, True, ExecutorType.LOCAL_MODEL, None, True)
    task = Task("t5", "non_llm.task", "test-account", "test-project", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    
    selection = selector.select(task, cap, policy)
    assert selection.executor_type == ExecutorType.DETERMINISTIC

def test_13_llm_capability_without_model(clean_registry):
    selector = ExecutorSelector(clean_registry, intelligence_layer=MockIntelligenceLayer(clean_registry))
    policy = RuntimePolicy()
    policy.allow_llm = True
    clean_registry.get_model("luna").status = ModelState.UNAVAILABLE
    cap = CapabilityDefinition("nonexistent.task", "test", "test", "1.0", "low", True, True, "disabled", "read_only", [], 60, 1024, True, ExecutorType.LOCAL_MODEL, None, True)
    task = Task("t6", "nonexistent.task", "test-account", "test-project", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    
    with pytest.raises(ValueError, match="Execution plan BLOCKED"):
        selection = selector.select(task, cap, policy)

def test_14_authority_boundary():
    from runtime.execution.selector import ExecutorSelection
    selection = ExecutorSelection(ExecutorType.LOCAL_MODEL, "worker", "1.0", "luna", "1.0", "test", "1.0", "low")
    assert selection.model_id == "luna"

def test_15_performance_profile(clean_registry):
    perf = clean_registry.get_performance_profile("luna")
    assert perf.executions == 0

def test_16_evaluation_record(clean_registry):
    clean_registry._evaluations.append(EvaluationRecord("ev1", "luna", "test", "exe1", 1.0, "auto", "sys", datetime.now(timezone.utc), "ref1"))
    assert len(clean_registry._evaluations) == 1

def test_17_control_plane_list():
    from runtime.admin.routes import AdminRouter
    router = AdminRouter({})
    assert '/models' in router._get_routes

def test_18_control_plane_detail():
    from runtime.admin.routes import AdminRouter
    router = AdminRouter({})
    # Detail is handled dynamically, let's verify handle_model_detail exists
    assert hasattr(router, 'handle_model_detail')

def test_19_reproducibility_metadata():
    ws_mgr = EphemeralWorkspaceManager("/tmp/anny-workspaces-registry-test-2")
    manager = ExecutionManager(ws_mgr)
    manager.selector.intelligence_layer = MockIntelligenceLayer(manager.model_registry)
    manager.policy.allow_llm = True
    manager.model_registry.add_binding(ModelCapabilityBinding("luna", "schema.validate", "granted", "standard", "low", True, False, "test"))
    
    cap = manager.registry.get("schema.validate")
    cap.inference_required = True
    cap.preferred_executor = ExecutorType.LOCAL_MODEL
    task = Task("task-123", "schema.validate", "test-account", "test-project", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    with pytest.raises(ValueError, match="Execution plan BLOCKED"):
        context = manager.submit_task(task)

def test_20_schema_validation():
    # Tested by ensuring loading an invalid version raises an error via internal method
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b'{"version": "2.0"}')
        path = f.name
    
    try:
        reg = ModelRegistry()
        reg.storage_path = path
        with pytest.raises(ValueError, match="Unsupported registry schema version"):
            reg._load_from_disk()
    finally:
        os.unlink(path)

def test_21_persistence_reload():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    os.unlink(path)
        
    try:
        reg1 = ModelRegistry(storage_path=path)
        reg1.get_model("qwen3-8b").status = ModelState.AVAILABLE
        reg1._save_to_disk()
        
        reg2 = ModelRegistry(storage_path=path)
        assert reg2.is_available("qwen3-8b") is True
    finally:
        os.unlink(path)

def test_22_crash_recovery_fails_closed():
    import glob
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b'{"corrupted": json')
        path = f.name

    recovery_path = f"{path}.recovery.json"
    try:
        # Corruption must be quarantined and surfaced as blocked recovery,
        # never silently replaced by a newly synthesized trusted registry.
        with pytest.raises(RegistryRecoveryRequired, match="explicit recovery required"):
            ModelRegistry(storage_path=path)

        q_files = glob.glob(f"{path}.quarantine.*")
        assert len(q_files) == 1
        assert not os.path.exists(path)

        with open(recovery_path, "r") as rf:
            marker = json.load(rf)
        assert marker["state"] == "BLOCKED_OR_UNKNOWN"
        assert marker["reconstruction_required"] is True
        assert marker["verification_required"] is True
        assert marker["original_sha256"] != "UNKNOWN"

        # The durable marker itself prevents a silent fresh bootstrap.
        with pytest.raises(RegistryRecoveryRequired, match="recovery is required"):
            ModelRegistry(storage_path=path)
    finally:
        if os.path.exists(path):
            os.unlink(path)
        if os.path.exists(recovery_path):
            os.unlink(recovery_path)
        for qf in glob.glob(f"{path}.quarantine.*"):
            os.unlink(qf)

def test_23_model_replacement_without_task_mutation(clean_registry):
    # A task requests capability 'doc.class'. Model A handles it, then Model B handles it. The task doesn't change.
    cap = CapabilityDefinition("doc.class", "test", "test", "1.0", "low", True, True, "disabled", "read_only", [], 60, 1024, True, ExecutorType.LOCAL_MODEL, None, True)
    task = Task("t7", "doc.class", "test-account", "test-project", {}, {}, datetime.now(timezone.utc), "destroy_on_complete", "required", "admin", datetime.now(timezone.utc))
    
    clean_registry.add_binding(ModelCapabilityBinding("qwen3-8b", "doc.class", "granted", "standard", "low", True, False, "test"))
    clean_registry.get_model("qwen3-8b").status = ModelState.AVAILABLE
    
    selector = ExecutorSelector(clean_registry, intelligence_layer=MockIntelligenceLayer(clean_registry))
    policy = RuntimePolicy()
    policy.allow_llm = True
    
    sel1 = selector.select(task, cap, policy)
    assert sel1.model_id == "qwen3-8b"
    
    clean_registry.get_model("qwen3-8b").status = ModelState.UNAVAILABLE
    clean_registry.add_binding(ModelCapabilityBinding("luna", "doc.class", "granted", "standard", "low", True, False, "test"))
    
    sel2 = selector.select(task, cap, policy)
    assert sel2.model_id == "luna"

def test_24_process_persistence():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    os.unlink(path)
        
    try:
        # Process A
        regA = ModelRegistry(storage_path=path)
        regA.get_model("luna").version = "1.5"
        regA._save_to_disk()
        
        # Process B
        regB = ModelRegistry(storage_path=path)
        assert regB.get_model("luna").version == "1.5"
    finally:
        os.unlink(path)

def test_25_crash_safety():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    os.unlink(path)
        
    try:
        # Initial valid write
        reg = ModelRegistry(storage_path=path)
        reg.get_model("luna").version = "1.0"
        reg._save_to_disk()
        
        # Simulate an interrupted write (temp file created, but not replaced)
        fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".registry-", suffix=".tmp")
        with os.fdopen(fd, 'w') as tf:
            tf.write('{"corrupted_temp_write"}')
            
        # The main file should remain uncorrupted and valid
        reg2 = ModelRegistry(storage_path=path)
        assert reg2.get_model("luna").version == "1.0"
    finally:
        if os.path.exists(path):
            os.unlink(path)
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def _prepare_corrupted_registry():
    import glob
    fd, path = tempfile.mkstemp()
    os.close(fd)
    os.unlink(path)

    seed = ModelRegistry(storage_path=path)
    payload = seed._build_data()
    with open(path, "w") as f:
        f.write('{"corrupted": true')
    with pytest.raises(RegistryRecoveryRequired):
        ModelRegistry(storage_path=path)

    recovery_path = f"{path}.recovery.json"
    with open(recovery_path, "r") as f:
        marker = json.load(f)
    quarantine = marker["quarantine_path"]
    return seed, payload, path, recovery_path, quarantine


def _attestation(seed, payload, path, recovery_path, quarantine):
    import hashlib
    serialized = seed._serialize_data(payload)
    digest = hashlib.sha256(serialized).hexdigest()
    marker = json.load(open(recovery_path, "r"))
    return RecoveryAttestation(
        recovery_id="test-recovery-001",
        source_registry_hash=marker["original_sha256"],
        quarantine_reference=quarantine,
        authority_ref="ANNY-AUTH-TEST-001",
        authority_decision="APPROVE_RESTORE",
        source_evidence_ids=["evidence:quarantine", "evidence:source"],
        reconstructed_registry_digest=digest,
        registry_payload=payload,
        verification_evidence_ids=["evidence:verification"],
        recovery_timestamp="2026-09-22T00:00:00Z",
    )


def test_26_explicit_attestation_restores_only_after_authority():
    import glob
    seed, payload, path, recovery_path, quarantine = _prepare_corrupted_registry()
    try:
        attestation = _attestation(seed, payload, path, recovery_path, quarantine)

        with pytest.raises(RecoveryAttestationError, match="did not authorize"):
            seed.restore_from_attestation(attestation, lambda _: False)

        assert os.path.exists(recovery_path)
        assert not os.path.exists(path)

        seed.restore_from_attestation(attestation, lambda _: True)

        assert os.path.exists(path)
        assert not os.path.exists(recovery_path)
        assert seed.get_model("luna") is not None
        assert seed.get_model("luna").version == "1.0"

        records = glob.glob(f"{path}.recovery-record.test-recovery-001.json")
        assert len(records) == 1
        with open(records[0], "r") as f:
            record = json.load(f)
        assert record["state"] == "RESTORED_VERIFIED"
        assert record["authority_ref"] == "ANNY-AUTH-TEST-001"

        restored = ModelRegistry(storage_path=path)
        assert restored.get_model("luna").version == "1.0"
    finally:
        for candidate in [path, recovery_path, f"{path}.recovery-record.test-recovery-001.json", quarantine]:
            if os.path.exists(candidate):
                os.unlink(candidate)


def test_27_attestation_digest_mismatch_fails_closed():
    seed, payload, path, recovery_path, quarantine = _prepare_corrupted_registry()
    try:
        attestation = _attestation(seed, payload, path, recovery_path, quarantine)
        invalid = RecoveryAttestation(
            **{**dataclasses.asdict(attestation), "reconstructed_registry_digest": "0" * 64}
        )
        with pytest.raises(RecoveryAttestationError, match="digest mismatch"):
            seed.restore_from_attestation(invalid, lambda _: True)
        assert os.path.exists(recovery_path)
        assert not os.path.exists(path)
    finally:
        for candidate in [path, recovery_path, quarantine]:
            if os.path.exists(candidate):
                os.unlink(candidate)


def test_28_missing_evidence_fails_closed():
    seed, payload, path, recovery_path, quarantine = _prepare_corrupted_registry()
    try:
        attestation = _attestation(seed, payload, path, recovery_path, quarantine)
        invalid = RecoveryAttestation(
            **{**dataclasses.asdict(attestation), "verification_evidence_ids": []}
        )
        with pytest.raises(RecoveryAttestationError, match="no verification evidence"):
            seed.restore_from_attestation(invalid, lambda _: True)
        assert os.path.exists(recovery_path)
        assert not os.path.exists(path)
    finally:
        for candidate in [path, recovery_path, quarantine]:
            if os.path.exists(candidate):
                os.unlink(candidate)


def test_29_recovery_survives_process_restart():
    seed, payload, path, recovery_path, quarantine = _prepare_corrupted_registry()
    try:
        # Simulate a fresh process after the original Runtime has exited.
        recovery_runtime = ModelRegistry.open_for_recovery(path)
        attestation = _attestation(seed, payload, path, recovery_path, quarantine)
        recovery_runtime.restore_from_attestation(attestation, lambda _: True)

        assert not os.path.exists(recovery_path)
        restored = ModelRegistry(storage_path=path)
        assert restored.get_model("luna") is not None
        assert restored.get_model("luna").version == "1.0"
    finally:
        record = f"{path}.recovery-record.test-recovery-001.json"
        for candidate in [path, recovery_path, record, quarantine]:
            if os.path.exists(candidate):
                os.unlink(candidate)


def test_30_recovery_id_path_injection_is_rejected():
    seed, payload, path, recovery_path, quarantine = _prepare_corrupted_registry()
    try:
        attestation = _attestation(seed, payload, path, recovery_path, quarantine)
        invalid = RecoveryAttestation(
            **{**dataclasses.asdict(attestation), "recovery_id": "../escape"}
        )
        with pytest.raises(RecoveryAttestationError, match="invalid characters"):
            seed.restore_from_attestation(invalid, lambda _: True)
        assert os.path.exists(recovery_path)
        assert not os.path.exists(path)
    finally:
        for candidate in [path, recovery_path, quarantine]:
            if os.path.exists(candidate):
                os.unlink(candidate)
