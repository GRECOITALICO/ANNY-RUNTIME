#!/usr/bin/env python3
"""
Physical Validation Script — Mission 001D-R5-B
Governed Interaction: FIND + CLICK
Executes all 12 required steps including stale-target test
and physical security tests.
"""
import sys
import time
import json

sys.path.insert(0, '/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME')
from runtime.browser.manager import BrowserSessionManager

manager = BrowserSessionManager()

results = {}

def report(step, result, detail=""):
    status = "PASS" if result else "FAIL"
    results[step] = status
    print(f"[{status}] {step}: {detail}")
    if not result:
        print(f"  !! DETAIL: {detail}")

# ─── 1. Start governed browser ────────────────────────────────────────────────
print("\n=== STEP 1: Start browser ===")
res = manager._send_ipc("START_BROWSER", url="about:blank")
report("START_BROWSER", res.get("status") == "ok", res)
time.sleep(2)

# ─── 2. Navigate to test page ─────────────────────────────────────────────────
print("\n=== STEP 2: Navigate to example.com ===")
res = manager.navigate("https://example.com")
report("NAVIGATE", res.get("status") == "ok", res)
time.sleep(2)

# ─── 3. OBSERVE ───────────────────────────────────────────────────────────────
print("\n=== STEP 3: Observe ===")
res = manager.observe()
obs = res.get("observation", {})
report("OBSERVE", res.get("status") == "ok" and obs.get("title") == "Example Domain", res)

# ─── 4. FIND a known visible target ──────────────────────────────────────────
print("\n=== STEP 4: Find 'Learn more' link ===")
res = manager.find({"text": "learn", "tag": "a"})
targets = res.get("targets", [])
report("FIND", res.get("status") == "ok" and len(targets) > 0, f"{len(targets)} targets found")

target_id = None
if targets:
    target_id = targets[0]["target_id"]
    print(f"  target_id={target_id!r} role={targets[0].get('role')} text={targets[0].get('text')!r}")
    report("TARGET_ID_FORMAT", target_id.startswith("bt_"), target_id)

# ─── 5. CLICK target_id ──────────────────────────────────────────────────────
print("\n=== STEP 5: Click target ===")
if target_id:
    res = manager.click(target_id)
    report("CLICK", res.get("status") == "ok" and res.get("result") == "success", res)
    post_obs = res.get("observation", {})
    report("POST_CLICK_OBSERVATION", bool(post_obs.get("url")), post_obs)
    time.sleep(1)
else:
    report("CLICK", False, "No target_id from FIND")
    report("POST_CLICK_OBSERVATION", False, "skipped")

# ─── 6. OBSERVE after click ───────────────────────────────────────────────────
print("\n=== STEP 6: Observe post-click ===")
res = manager.observe()
report("POST_CLICK_OBSERVE", res.get("status") == "ok", res.get("observation", {}).get("url"))

# ─── 7. Attempt reuse of stale target_id ─────────────────────────────────────
print("\n=== STEP 7: Stale target test (reuse target_id after navigation) ===")
if target_id:
    res = manager.click(target_id)
    # After navigation the page context is fresh — target must be stale
    stale = res.get("status") == "error" and "TARGET_STALE" in res.get("message", "")
    report("TARGET_STALE_REJECTION", stale, res)
else:
    report("TARGET_STALE_REJECTION", False, "No target_id to test")

# ─── SECURITY TESTS ──────────────────────────────────────────────────────────
print("\n=== SECURITY TESTS ===")

# Forged target_id
res = manager.click("bt_forged-00000000-fake")
report("SEC_FORGED_TARGET_ID", res.get("status") == "error", res)

# Unknown target_id  
res = manager.click("bt_completely-unknown-id")
report("SEC_UNKNOWN_TARGET_ID", res.get("status") == "error", res)

# CLICK with selector (should be rejected at IPC - manager sends it, broker validates)
# The IPC doesn't reject it at protocol level - the tool layer does.
# Test at the tool layer:
from runtime.mcp.tools import browser_interaction_click, ToolImplementationError
try:
    browser_interaction_click({"target_id": "bt_1", "selector": "#btn"}, {})
    report("SEC_SELECTOR_REJECTED", False, "Should have raised ToolImplementationError")
except ToolImplementationError as e:
    report("SEC_SELECTOR_REJECTED", True, str(e))

# CLICK with x/y coordinates
try:
    browser_interaction_click({"target_id": "bt_1", "x": 100, "y": 200}, {})
    report("SEC_COORDINATES_REJECTED", False, "Should have raised ToolImplementationError")
except ToolImplementationError as e:
    report("SEC_COORDINATES_REJECTED", True, str(e))

# CLICK with script
try:
    browser_interaction_click({"target_id": "bt_1", "script": "alert(1)"}, {})
    report("SEC_SCRIPT_REJECTED", False, "Should have raised ToolImplementationError")
except ToolImplementationError as e:
    report("SEC_SCRIPT_REJECTED", True, str(e))

# CLICK with raw CDP method
try:
    browser_interaction_click({"target_id": "bt_1", "method": "Runtime.evaluate"}, {})
    report("SEC_RAW_CDP_REJECTED", False, "Should have raised ToolImplementationError")
except ToolImplementationError as e:
    report("SEC_RAW_CDP_REJECTED", True, str(e))

# FIND with script injection
from runtime.mcp.tools import browser_interaction_find
try:
    browser_interaction_find({"query": {"script": "steal()"}}, {})
    report("SEC_FIND_SCRIPT_INJECT", False, "Should have raised ToolImplementationError")
except ToolImplementationError as e:
    report("SEC_FIND_SCRIPT_INJECT", True, str(e))

# ─── 8. Terminate browser ─────────────────────────────────────────────────────
print("\n=== STEP 8: Terminate browser ===")
res = manager._send_ipc("STOP_BROWSER")
report("STOP_BROWSER", res.get("status") == "ok", res)

# ─── SUMMARY ─────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("PHYSICAL VALIDATION SUMMARY")
print("="*60)
passed = sum(1 for v in results.values() if v == "PASS")
failed = sum(1 for v in results.values() if v == "FAIL")
for k, v in results.items():
    mark = "✓" if v == "PASS" else "✗"
    print(f"  {mark} {k}: {v}")
print(f"\nTotal: {passed} PASS, {failed} FAIL")
sys.exit(0 if failed == 0 else 1)
