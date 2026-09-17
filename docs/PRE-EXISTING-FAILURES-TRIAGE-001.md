# PRE-EXISTING-FAILURES-TRIAGE-001

## Pre-existing Failures Triage Review

TEST_ID | TEST_PATH | ERROR | FIRST_OBSERVED_IN_CURRENT_RUN | OBSERVED_COMMIT | RELATED_TO_OBSERVABILITY | EVIDENCE | CLASSIFICATION | FOLLOW_UP_GATE
--- | --- | --- | --- | --- | --- | --- | --- | ---
test_browser_launched_before_ready | tests/test_001d_r4_lifecycle.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_hide_called_when_ready | tests/test_001d_r4_lifecycle.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_metadata_records_auto_hidden_true | tests/test_001d_r4_lifecycle.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_metadata_records_browser_final_state_hidden | tests/test_001d_r4_lifecycle.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_metadata_records_ready_and_hide_timestamps | tests/test_001d_r4_lifecycle.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_fallback_to_close_when_hide_unavailable | tests/test_001d_r4_lifecycle.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_session_state_ready_after_hide | tests/test_001d_r4_lifecycle.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_session_ready_even_if_hide_raises | tests/test_001d_r4_lifecycle.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_provision_called_twice_launches_browser_both_times | tests/test_001d_r4_lifecycle.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_hide_called_on_each_provision | tests/test_001d_r4_lifecycle.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_08_forbidden_javascript_field | tests/test_001d_r5c_submit_deny.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_09_forbidden_cdp_field | tests/test_001d_r5c_submit_deny.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_10_credential_field_denied | tests/test_001d_r5c_submit_deny.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_11_denied_evidence_generated | tests/test_001d_r5c_submit_deny.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_start_browser_uses_chrome_binary | tests/test_001g_broker_security.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_start_browser_uses_shell_false | tests/test_001g_broker_security.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_start_browser_url_in_args_as_app_flag | tests/test_001g_broker_security.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_start_browser_no_no_sandbox_flag | tests/test_001g_broker_security.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_start_browser_profile_under_anny | tests/test_001g_broker_security.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_single_proxy_token_in_url | tests/test_001g_managed_browser.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_list_tools_growth_signals_connection | tests/test_001g_managed_browser.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_auth_deadline_constant_is_600s | tests/test_001g_managed_browser.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_bridge_stopped_on_timeout | tests/test_001g_managed_browser.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_temp_file_removed_after_success | tests/test_001g_managed_browser.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_control_plane_universe_handlers | tests/test_control_plane_universe_001.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_filesystem_list_is_deterministic_and_sorted | tests/test_deterministic_local_execution.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_repository_read_and_diff | tests/test_deterministic_local_execution.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_baseline_requirements_pass | tests/test_installer_preflight.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_fabric_register_new_resource | tests/test_mcp_qwen_integration_004.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_first_run_shows_device_flow_button | tests/test_onboarding_token.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
test_full_http_integration | tests/test_session_fix.py | AssertionError | TRUE | 98a6227d3b5784efd9909a0b7b1670d7124bd6f5 | FALSE | full_suite_output | PRE_EXISTING | TBD
