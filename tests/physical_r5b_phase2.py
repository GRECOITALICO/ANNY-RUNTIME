import sys
import time
import base64
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.browser.manager import BrowserSessionManager

def print_step(msg):
    print(f"\n=== {msg} ===")

def print_pass(msg):
    print(f"[PASS] {msg}")

def print_fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)

# Synthetic test value as required by policy
TEST_VALUE = "ANNY_R5B2_TEST_VALUE"

def main():
    print_step("Starting physical validation for Governed Text Input (001D-R5-B-PHASE2)")

    html = """
    <!DOCTYPE html>
    <html>
    <body>
        <input type="text" id="test-text" aria-label="Text Input" />
        <textarea id="test-textarea" aria-label="Text Area"></textarea>
        <input type="password" id="test-password" aria-label="Password Input" />
        <input type="hidden" id="test-hidden" aria-label="Hidden Input" />
        <input type="file" id="test-file" aria-label="File Input" />
        <script>
            window.testState = { textChanged: false, textCleared: false };
            document.getElementById('test-text').addEventListener('input', (e) => {
                if (e.target.value === "ANNY_R5B2_TEST_VALUEAPPEND") {
                    window.testState.textChanged = true;
                }
                if (e.target.value === "") {
                    window.testState.textCleared = true;
                }
            });
        </script>
    </body>
    </html>
    """
    import tempfile
    tmp_path = Path(tempfile.gettempdir()) / "r5b_test.html"
    tmp_path.write_text(html, encoding="utf-8")
    test_url = f"file://{tmp_path.absolute()}"

    import uuid
    from runtime.browser.broker_server import BrowserBroker
    broker = BrowserBroker()
    broker.profile_name = f"test-r5b-{uuid.uuid4().hex[:8]}"
    broker.profile_dir = Path(broker.profile_name)
    from runtime.browser.broker_server import _validate_profile
    broker.profile_dir = _validate_profile(broker.profile_name)
    
    try:
        print_step("1. Initialize and load test page")
        start_res = broker.start_browser(test_url)
        if start_res and start_res.get("status") == "error":
            print_fail(f"Failed to start browser: {start_res}")
        # Give it a moment to load
        time.sleep(2)
        
        print_step("2. OBSERVE (Initial)")
        obs = broker.observe()
        print(obs)
        
        print_step("3. FIND text input")
        find_res = broker.find({"tag": "input", "type": "text"})
        if not find_res.get("targets"):
            print_fail(f"Could not find text input. find_res: {find_res}")
        text_target = find_res["targets"][0]["target_id"]
        
        # Verify text value is NOT exposed in finding
        if "value" in find_res["targets"][0] or "text" in find_res["targets"][0] and TEST_VALUE in find_res["targets"][0].get("text", ""):
            print_fail("FIND exposed the field value!")
            
        print_pass(f"Found text target: {text_target}")

        print_step("4. FILL text input")
        fill_res = broker.fill(text_target, TEST_VALUE)
        if fill_res.get("status") != "ok":
            print_fail(f"FILL failed: {fill_res}")
            
        # Verify observation doesn't leak text
        if TEST_VALUE in str(fill_res.get("observation")):
            print_fail("FILL observation leaked the text value!")
            
        print_pass("FILL succeeded safely")

        print_step("5. TYPE additional synthetic text")
        type_res = broker.type(text_target, "APPEND")
        if type_res.get("status") != "ok":
            print_fail(f"TYPE failed: {type_res}")
            
        print_step("6. Verify content changed safely")
        # Check window.testState
        state_check = broker._cdp_request("Runtime.evaluate", {"expression": "window.testState.textChanged", "returnByValue": True})
        if not state_check.get("result", {}).get("value"):
            print_fail("Content was not successfully changed by FILL+TYPE")
        print_pass("Content changed verified via safe test indicator")
            
        print_step("7. CLEAR text input")
        clear_res = broker.clear(text_target)
        if clear_res.get("status") != "ok":
            print_fail(f"CLEAR failed: {clear_res}")
            
        print_step("8. Verify cleared state")
        state_check = broker._cdp_request("Runtime.evaluate", {"expression": "window.testState.textCleared", "returnByValue": True})
        if not state_check.get("result", {}).get("value"):
            print_fail("Content was not successfully cleared by CLEAR")
        print_pass("Content cleared verified via safe test indicator")
            
        print_step("9. FIND textarea")
        find_textarea = broker.find({"tag": "textarea"})
        if not find_textarea.get("targets"):
            print_fail("Could not find textarea")
        textarea_target = find_textarea["targets"][0]["target_id"]
        
        print_step("10. FILL textarea")
        fill_ta = broker.fill(textarea_target, TEST_VALUE)
        if fill_ta.get("status") != "ok":
            print_fail(f"FILL textarea failed: {fill_ta}")
            
        print_step("11. CLEAR textarea")
        clear_ta = broker.clear(textarea_target)
        if clear_ta.get("status") != "ok":
            print_fail(f"CLEAR textarea failed: {clear_ta}")
            
        print_step("12. FIND password input")
        find_pw = broker.find({"tag": "input"})
        pw_target = None
        for t in find_pw.get("targets", []):
            if t.get("name", "").lower() == "password input":
                pw_target = t["target_id"]
                break
                
        if not pw_target:
            print_fail("Could not find password input")
            
        print_step("13. Attempt FILL on password input")
        fill_pw = broker.fill(pw_target, TEST_VALUE)
        if fill_pw.get("status") == "ok":
            print_fail("FILL on password input succeeded! This is a severe security violation.")
            
        if fill_pw.get("message") != "TARGET_PROTECTED":
            print_fail(f"Expected TARGET_PROTECTED, got: {fill_pw.get('message')}")
            
        print_pass("Password field correctly rejected with TARGET_PROTECTED")

        print_step("14. Inspect for absence of submitted text")
        # Ensure we didn't log TEST_VALUE in the result object
        if TEST_VALUE in str(fill_pw):
            print_fail("Rejected FILL leaked the text value in the error message!")
            
        print_pass("All evidence correctly redacted.")
        
    finally:
        print_step("15. Cleanly terminate browser")
        broker.stop_browser()

    print_step("ALL PHYSICAL PHASE 2 TESTS PASSED")


if __name__ == "__main__":
    main()
