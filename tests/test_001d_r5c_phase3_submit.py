"""
001D-R5-C-PHASE3 Unit Tests: Authorized Form Submission
Tests the end-to-end authorized submit flow, evidence, and redaction.

Required cases:
1. authorized submit (returns REQUEST_ACCEPTED)
2. auth consumed (single use check via registry)
3. reuse rejected (MISSING/INVALID_AUTH -> DENIED)
4. wrong target (DENIED)
5. expired auth (DENIED)
6. stale target (DENIED)
7. wrong session (DENIED)
8. post-action observation (returned securely)
9. evidence (contains expected fields)
10. sensitive-data redaction (passwords removed from observation)
"""

import pytest
import datetime
from unittest.mock import MagicMock, patch
from runtime.mcp.tools import browser_interaction_submit, ToolImplementationError

@pytest.fixture
def mock_manager():
    with patch("runtime.mcp.tools.BrowserSessionManager") as MockManager:
        instance = MockManager.return_value
        instance.profile = "colab"
        yield instance

# --- Case 1 & 8 & 9: Authorized submit, observation, and evidence ---
def test_01_authorized_submit(mock_manager):
    """Case 1: Authorized submit returns REQUEST_ACCEPTED and produces full evidence."""
    mock_manager.submit.return_value = {
        "status": "ok",
        "result": "REQUEST_ACCEPTED",
        "action": {"type": "submit", "authorization_used": True},
        "request": {"method": "POST", "destination": "http://example.com/submit"},
        "observation": {
            "url": "http://example.com/success",
            "title": "Success",
            "inputs": [{"name": "search", "type": "text", "value_present": True}]
        }
    }

    res = browser_interaction_submit({
        "target_id": "bt_valid",
        "authorization_id": "auth-123"
    }, {})

    assert res["status"] == "ok"
    assert res["result"] == "REQUEST_ACCEPTED"
    assert res["action"]["authorization_used"] is True
    assert res["request"]["method"] == "POST"
    assert res["request"]["destination"] == "http://example.com/submit"
    assert res["observation"]["url"] == "http://example.com/success"
    assert res["evidence"]["decision"] == "AUTHORIZED_AND_EXECUTED"
    assert res["evidence"]["consequence_class"] == "EXTERNAL_CONSEQUENCE"
    assert res["evidence"]["request_method"] == "POST"
    assert res["evidence"]["request_destination"] == "http://example.com/submit"
    assert "authorization_id" not in res["evidence"]  # Redacted from evidence

# --- Case 10: Sensitive-data redaction ---
def test_10_sensitive_data_redaction(mock_manager):
    """Case 10: Sensitive inputs (passwords) have their value metadata scrubbed."""
    mock_manager.submit.return_value = {
        "status": "ok",
        "result": "REQUEST_ACCEPTED",
        "action": {"type": "submit", "authorization_used": True},
        "request": {"method": "POST", "destination": "http://example.com/login"},
        "observation": {
            "url": "http://example.com/dashboard",
            "inputs": [
                {"name": "username", "type": "text", "value_present": True},
                {"name": "password", "type": "password", "value_present": True}, # Sensitive
                {"name": "auth_token", "type": "hidden", "value_present": True}  # Sensitive
            ]
        }
    }

    res = browser_interaction_submit({"target_id": "bt_valid", "authorization_id": "auth-123"}, {})
    obs = res["observation"]
    inputs = obs["inputs"]
    
    # Username is safe, so value_present is preserved
    assert inputs[0]["name"] == "username"
    assert inputs[0]["value_present"] is True

    # Password and auth_token are sensitive, value_present is scrubbed
    assert inputs[1]["name"] == "password"
    assert "value_present" not in inputs[1]

    assert inputs[2]["name"] == "auth_token"
    assert "value_present" not in inputs[2]


# --- Negative Cases ---

def test_04_wrong_target(mock_manager):
    """Case 4: Target mismatch in authorization."""
    mock_manager.submit.return_value = {
        "status": "error",
        "message": "AUTHORIZATION_TARGET_MISMATCH"
    }
    res = browser_interaction_submit({"target_id": "bt_wrong", "authorization_id": "auth-123"}, {})
    
    assert res["status"] == "DENIED"
    assert res["reason"] == "AUTHORIZATION_TARGET_MISMATCH"
    assert res["evidence"]["decision"] == "DENIED"
    assert res["evidence"]["consequence_class"] == "EXTERNAL_CONSEQUENCE"

def test_05_expired_auth(mock_manager):
    """Case 5: Auth expired."""
    mock_manager.submit.return_value = {
        "status": "error",
        "message": "AUTHORIZATION_EXPIRED"
    }
    res = browser_interaction_submit({"target_id": "bt_valid", "authorization_id": "auth-123"}, {})
    
    assert res["status"] == "DENIED"
    assert res["reason"] == "AUTHORIZATION_EXPIRED"

def test_06_stale_target(mock_manager):
    """Case 6: Target is stale in browser state."""
    mock_manager.submit.return_value = {
        "status": "error",
        "message": "TARGET_STALE"
    }
    res = browser_interaction_submit({"target_id": "bt_valid", "authorization_id": "auth-123"}, {})
    
    assert res["status"] == "DENIED"
    assert res["reason"] == "TARGET_STALE"

def test_07_wrong_session(mock_manager):
    """Case 7: Auth issued for a different session."""
    mock_manager.submit.return_value = {
        "status": "error",
        "message": "AUTHORIZATION_SESSION_MISMATCH"
    }
    res = browser_interaction_submit({"target_id": "bt_valid", "authorization_id": "auth-123"}, {})
    
    assert res["status"] == "DENIED"
    assert res["reason"] == "AUTHORIZATION_SESSION_MISMATCH"

def test_missing_auth(mock_manager):
    """Immediate DENIED if no auth_id is provided to tool."""
    res = browser_interaction_submit({"target_id": "bt_valid"}, {})
    assert res["status"] == "DENIED"
    assert res["reason"] == "MISSING_AUTHORIZATION"
    assert res["evidence"]["decision"] == "DENIED"

def test_invalid_auth(mock_manager):
    """Case 3: Reuse rejected (or invalid) auth."""
    mock_manager.submit.return_value = {
        "status": "error",
        "message": "INVALID_AUTHORIZATION"
    }
    res = browser_interaction_submit({"target_id": "bt_valid", "authorization_id": "auth-reused"}, {})
    assert res["status"] == "DENIED"
    assert res["reason"] == "INVALID_AUTHORIZATION"

def test_forbidden_input(mock_manager):
    """Caller tries to inject method/action."""
    with pytest.raises(ToolImplementationError, match="Forbidden"):
        browser_interaction_submit({
            "target_id": "bt_valid",
            "authorization_id": "auth-123",
            "method": "POST"
        }, {})
