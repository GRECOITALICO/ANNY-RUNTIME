from runtime.intelligence.taxonomy import (
    DETERMINISTIC_CAPABILITIES,
    LOCAL_INFERENCE_CAPABILITIES,
    requires_benchmark,
    is_deterministic,
    is_local_inference,
)


def test_schema_validate_is_deterministic():
    assert "schema.validate" in DETERMINISTIC_CAPABILITIES
    assert "schema.validate" not in LOCAL_INFERENCE_CAPABILITIES
    assert is_deterministic("schema.validate") is True
    assert is_local_inference("schema.validate") is False
    assert requires_benchmark("schema.validate") is False
