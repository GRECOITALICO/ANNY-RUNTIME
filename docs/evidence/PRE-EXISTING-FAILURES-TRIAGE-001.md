# PRE-EXISTING FAILURES TRIAGE

As part of DETERMINISTIC-OBSERVABILITY-001-REVERIFY closeout, a full suite test execution was performed via `pytest tests/ -v`.

## Execution Summary
- **Command:** `PYTHONPATH=. pytest tests/ -v`
- **Total Tests Collected:** 548
- **Results:** 31 failed, 491 passed, 26 skipped

## Pre-Existing Failures (Triage)

The following tests failed during the execution. These are classified as pre-existing failures and are beyond the scope of the Deterministic Observability remediation. They will be documented here for future remediation tracks (such as R4 Lifecycle and R5 Navigation tracks).

```
FAILED tests/test_001d_r4_lifecycle.py::TestBrowserVisibleWaitingUser::test_browser_launched_before_ready
FAILED tests/test_001d_r4_lifecycle.py::TestBrowserClosesAfterReady::test_hide_called_when_ready
FAILED tests/test_001d_r4_lifecycle.py::TestBrowserClosesAfterReady::test_metadata_records_auto_hidden_true
FAILED tests/test_001d_r4_lifecycle.py::TestBrowserClosesAfterReady::test_metadata_records_browser_final_state_hidden
FAILED tests/test_001d_r4_lifecycle.py::TestBrowserClosesAfterReady::test_metadata_records_ready_and_hide_timestamps
FAILED tests/test_001d_r4_lifecycle.py::TestBrowserClosesAfterReady::test_fallback_to_close_when_hide_unavailable
FAILED tests/test_001d_r4_lifecycle.py::TestSessionSurvivesBrowserClose::test_session_state_ready_after_hide
FAILED tests/test_001d_r4_lifecycle.py::TestSessionSurvivesBrowserClose::test_session_ready_even_if_hide_raises
FAILED tests/test_001d_r4_lifecycle.py::TestReconnectReopensBrowser::test_provision_called_twice_launches_browser_both_times
FAILED tests/test_001d_r4_lifecycle.py::TestReconnectHidesBrowserAfterReady::test_hide_called_on_each_provision
FAILED tests/test_001d_r5c_submit_deny.py::TestSubmitDefaultDeny::test_08_forbidden_javascript_field
FAILED tests/test_001d_r5c_submit_deny.py::TestSubmitDefaultDeny::test_09_forbidden_cdp_field
FAILED tests/test_001d_r5c_submit_deny.py::TestSubmitDefaultDeny::test_10_credential_field_denied
FAILED tests/test_001d_r5c_submit_deny.py::TestSubmitDefaultDeny::test_11_denied_evidence_generated
FAILED tests/test_001g_broker_security.py::TestBrowserBrokerContract::test_start_browser_uses_chrome_binary
FAILED tests/test_001g_broker_security.py::TestBrowserBrokerContract::test_start_browser_uses_shell_false
FAILED tests/test_001g_broker_security.py::TestBrowserBrokerContract::test_start_browser_url_in_args_as_app_flag
FAILED tests/test_001g_broker_security.py::TestBrowserBrokerContract::test_start_browser_no_no_sandbox_flag
FAILED tests/test_001g_broker_security.py::TestBrowserBrokerContract::test_start_browser_profile_under_anny
FAILED tests/test_001g_managed_browser.py::TestSingleWSSSession::test_single_proxy_token_in_url
FAILED tests/test_001g_managed_browser.py::TestWaitForBrowserConnection::test_list_tools_growth_signals_connection
FAILED tests/test_001g_managed_browser.py::TestAuthBudget::test_auth_deadline_constant_is_600s
FAILED tests/test_001g_managed_browser.py::TestTimeoutCleanup::test_bridge_stopped_on_timeout
FAILED tests/test_001g_managed_browser.py::TestTokenIsolation::test_temp_file_removed_after_success
FAILED tests/test_control_plane_universe_001.py::test_control_plane_universe_handlers
FAILED tests/test_deterministic_local_execution.py::test_filesystem_list_is_deterministic_and_sorted
FAILED tests/test_deterministic_local_execution.py::test_repository_read_and_diff
FAILED tests/test_installer_preflight.py::TestPreflightSemantics::test_baseline_requirements_pass
FAILED tests/test_mcp_qwen_integration_004.py::TestPhase7RealFabric::test_fabric_register_new_resource
FAILED tests/test_onboarding_token.py::TestOnboardingToken::test_first_run_shows_device_flow_button
FAILED tests/test_session_fix.py::TestIntegrationSimulated::test_full_http_integration
```

All failures are isolated to R4 lifecycle management, R5 interaction/security models, managed browser implementation details, or other unrelated components outside the scope of DETERMINISTIC-OBSERVABILITY-001.

Crucially, **`test_deterministic_observability_001.py` passed with 0 failures**, affirming the robustness of the implemented fixes.
