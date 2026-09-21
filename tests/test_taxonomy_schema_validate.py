from runtime.intelligence.taxonomy import (
    is_deterministic,
    is_local_inference,
    requires_benchmark,
    validate_capability_id,
)


def test_schema_validate_is_deterministic():
    assert validate_capability_id("schema.validate")
    assert is_deterministic("schema.validate") is True
    assert is_local_inference("schema.validate") is False
    assert requires_benchmark("schema.validate") is False
