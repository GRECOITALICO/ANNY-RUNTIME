import sys
import time
import subprocess
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.browser.broker_server import BrowserBroker

def print_step(msg):
    print(f"\n\033[1;34m=== {msg} ===\033[0m")

def print_pass(msg):
    print(f"\033[1;32m[PASS] {msg}\033[0m")

def print_fail(msg):
    print(f"\033[1;31m[FAIL] {msg}\033[0m")
    sys.exit(1)

def main():
    print_step("Starting physical validation for Broker-Owned Target Authority (001D-R5-B-HARDENING)")

    b = BrowserBroker()
    
    try:
        print_step("1. Initialize and load test page")
        res = b.start_browser("about:blank")
        if res["status"] != "ok":
            print_fail(f"Failed to start browser: {res}")
        time.sleep(2)
        
        # Inject our test DOM via evaluate
        b._cdp_request("Runtime.evaluate", {
            "expression": "document.body.innerHTML = '<a id=\"target-link\">Click Me</a>';"
        })
        
        print_step("2. Perform FIND")
        find_res = b.find({"tag": "a"})
        if find_res["status"] != "ok" or not find_res.get("targets"):
            print_fail(f"FIND failed: {find_res}")
        
        target_id = find_res["targets"][0]["target_id"]
        print_pass(f"Found target_id: {target_id}")
        
        print_step("3. Test Page Tampering (Global wipe)")
        # We try to destroy window.__annyTargets if it existed, or just mutate the DOM window
        b._cdp_request("Runtime.evaluate", {
            "expression": "window.__annyTargets = {}; window.Math.random = () => 0;"
        })
        
        click_res = b.click(target_id)
        if click_res["status"] != "ok":
            print_fail(f"Page tampering affected CLICK! Result: {click_res}")
        print_pass("CLICK succeeded even after page tampering.")

        print_step("4. Test Reload Invalidation")
        # Find a new target
        b._cdp_request("Runtime.evaluate", {
            "expression": "document.body.innerHTML = '<a id=\"target-link2\">Click Me Again</a>';"
        })
        find_res2 = b.find({"tag": "a"})
        target_id2 = find_res2["targets"][0]["target_id"]
        
        # Reload the page
        b._cdp_request("Page.reload")
        time.sleep(2)
        
        # Click should fail with TARGET_STALE because backendNodeId is gone
        click_res2 = b.click(target_id2)
        if click_res2["status"] != "error" or "TARGET_STALE" not in click_res2.get("message", ""):
            print_fail(f"Reload did not invalidate target! Result: {click_res2}")
        print_pass("Reload correctly invalidated the target with TARGET_STALE.")

        print_step("5. Test Session Restart Invalidation")
        b._cdp_request("Runtime.evaluate", {
            "expression": "document.body.innerHTML = '<a id=\"target-link3\">Click Me Three</a>';"
        })
        find_res3 = b.find({"tag": "a"})
        target_id3 = find_res3["targets"][0]["target_id"]
        
        # Restart browser
        b.stop_browser()
        time.sleep(2)
        b.start_browser("about:blank")
        time.sleep(2)
        
        click_res3 = b.click(target_id3)
        if click_res3["status"] != "error" or "TARGET_STALE" not in click_res3.get("message", ""):
            print_fail(f"Session restart did not invalidate target! Result: {click_res3}")
        print_pass("Session restart correctly invalidated the target with TARGET_STALE.")

        print_step("ALL PHYSICAL HARDENING TESTS PASSED")

    finally:
        b.stop_browser()

if __name__ == "__main__":
    main()
