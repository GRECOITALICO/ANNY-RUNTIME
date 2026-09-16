import sys
import time
import threading
import tempfile
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── HTML fixture ──────────────────────────────────────────────────────────────
FORM_HTML = b"""<!DOCTYPE html>
<html>
<body>
  <form>
    <select id="test-select" aria-label="Select Menu">
      <option value="opt1">Option 1</option>
      <option value="opt2">Option 2</option>
      <option value="opt3">Option 3</option>
      <option value="opt4">Ambiguous Option</option>
      <option value="opt5">Ambiguous Option</option>
    </select>
    <input type="checkbox" id="test-check1" aria-label="Checkbox 1" />
    <input type="checkbox" id="test-check2" aria-label="Checkbox 2" checked />
    <input type="radio" name="group1" id="test-radio1" value="r1" aria-label="Radio 1" />
    <input type="radio" name="group1" id="test-radio2" value="r2" aria-label="Radio 2" checked />
    <input type="radio" name="group1" id="test-radio3" value="r3" aria-label="Radio 3" />
  </form>
</body>
</html>
"""


class _OnePageHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(FORM_HTML))
        self.end_headers()
        self.wfile.write(FORM_HTML)

    def log_message(self, *args):
        pass  # suppress access log noise


def _start_http_server():
    srv = HTTPServer(("127.0.0.1", 0), _OnePageHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, port


# ── Helpers ───────────────────────────────────────────────────────────────────
def print_step(msg):
    print(f"\n=== {msg} ===")

def print_pass(msg):
    print(f"[PASS] {msg}")

def print_fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print_step("Starting physical validation for Governed Forms (001D-R5-B-PHASE3)")

    srv, port = _start_http_server()
    test_url = f"http://127.0.0.1:{port}/"
    print(f"  Test server: {test_url}")

    import uuid
    from runtime.browser.broker_server import BrowserBroker, _validate_profile
    broker = BrowserBroker()
    broker.profile_name = f"test-r5b3-{uuid.uuid4().hex[:8]}"
    broker.profile_dir = _validate_profile(broker.profile_name)

    try:
        # ── 1. Start browser ─────────────────────────────────────────────────
        print_step("1. Start browser and load form page")
        start_res = broker.start_browser(test_url)
        if start_res and start_res.get("status") == "error":
            print_fail(f"Failed to start browser: {start_res}")
        time.sleep(2)

        # ── 2. OBSERVE (sanity) ──────────────────────────────────────────────
        print_step("2. OBSERVE (initial)")
        obs = broker.observe()
        if obs.get("status") == "error":
            print_fail(f"OBSERVE failed: {obs}")
        print(f"  page title: {obs.get('observation', {}).get('title')}")

        # ── 3. SELECT ────────────────────────────────────────────────────────
        print_step("3. FIND select element")
        find_sel = broker.find({"tag": "select"})
        if not find_sel.get("targets"):
            print_fail(f"Could not find select element. find_res={find_sel}")
        sel_target = find_sel["targets"][0]["target_id"]
        print(f"  target_id={sel_target}")

        print_step("4. SELECT 'Option 2' by label text")
        sel_res = broker.select(sel_target, "Option 2")
        if sel_res.get("status") != "ok":
            print_fail(f"SELECT failed: {sel_res}")
        print_pass("SELECT succeeded")

        # Verify selection reflected in metadata
        find_sel2 = broker.find({"tag": "select"})
        meta = find_sel2["targets"][0]
        sel_opts = meta.get("selected_options", [])
        if "Option 2" not in sel_opts:
            print_fail(f"SELECT state not updated; selected_options={sel_opts}")
        print_pass(f"SELECT state confirmed: selected_options={sel_opts}")

        # ── 4. SELECT by value (Should Fail) ─────────────────────────────────
        print_step("5. SELECT 'opt3' by option value (expect OPTION_NOT_FOUND)")
        sel_res2 = broker.select(sel_target, "opt3")
        if sel_res2.get("status") != "error" or "OPTION_NOT_FOUND" not in sel_res2.get("message", ""):
            print_fail(f"Expected OPTION_NOT_FOUND when matching raw value, got: {sel_res2}")
        print_pass("Value matching blocked: OPTION_NOT_FOUND correctly returned")

        # ── 4b. SELECT ambiguous match ───────────────────────────────────────
        print_step("5b. SELECT 'Ambiguous Option' (expect AMBIGUOUS_MATCH)")
        ambig_res = broker.select(sel_target, "Ambiguous Option")
        if ambig_res.get("status") != "error" or "AMBIGUOUS_MATCH" not in ambig_res.get("message", ""):
            print_fail(f"Expected AMBIGUOUS_MATCH, got: {ambig_res}")
        print_pass("AMBIGUOUS_MATCH correctly returned")

        # ── 5. OPTION_NOT_FOUND ──────────────────────────────────────────────
        print_step("6. SELECT nonexistent option (expect OPTION_NOT_FOUND)")
        bad_sel = broker.select(sel_target, "Does Not Exist")
        if bad_sel.get("status") != "error" or "OPTION_NOT_FOUND" not in bad_sel.get("message", ""):
            print_fail(f"Expected OPTION_NOT_FOUND, got: {bad_sel}")
        print_pass("OPTION_NOT_FOUND correctly returned")

        # ── 6. CHECK ────────────────────────────────────────────────────────
        print_step("7. FIND checkboxes")
        find_chk = broker.find({"tag": "input", "type": "checkbox"})
        targets = find_chk.get("targets", [])
        if len(targets) < 2:
            print_fail(f"Expected 2 checkboxes, got {len(targets)}")
        chk1_id = targets[0]["target_id"]
        chk2_id = targets[1]["target_id"]
        chk1_checked_init = targets[0].get("checked")
        chk2_checked_init = targets[1].get("checked")
        print(f"  chk1 initial checked={chk1_checked_init}")
        print(f"  chk2 initial checked={chk2_checked_init}")

        print_step("8. CHECK checkbox 1 (unchecked -> checked)")
        chk_res = broker.check(chk1_id)
        if chk_res.get("status") != "ok":
            print_fail(f"CHECK failed: {chk_res}")
        print_pass("CHECK succeeded")

        print_step("9. UNCHECK checkbox 2 (checked -> unchecked)")
        unchk_res = broker.uncheck(chk2_id)
        if unchk_res.get("status") != "ok":
            print_fail(f"UNCHECK failed: {unchk_res}")
        print_pass("UNCHECK succeeded")

        # Verify post-check states
        find_chk2 = broker.find({"tag": "input", "type": "checkbox"})
        c1 = find_chk2["targets"][0].get("checked")
        c2 = find_chk2["targets"][1].get("checked")
        if not c1:
            print_fail(f"Checkbox 1 should be checked but got checked={c1}")
        if c2:
            print_fail(f"Checkbox 2 should be unchecked but got checked={c2}")
        print_pass(f"CHECK/UNCHECK state verified: c1={c1}, c2={c2}")

        # CHECK idempotency (already checked)
        print_step("10. CHECK checkbox 1 again (idempotency)")
        idem = broker.check(chk1_id)
        if idem.get("status") != "ok":
            print_fail(f"CHECK idempotency failed: {idem}")
        print_pass("CHECK idempotency: ok")

        # ── 7. RADIO ─────────────────────────────────────────────────────────
        print_step("11. FIND radio buttons")
        find_rad = broker.find({"tag": "input", "type": "radio"})
        rad_targets = find_rad.get("targets", [])
        if len(rad_targets) < 3:
            print_fail(f"Expected 3 radio buttons, got {len(rad_targets)}")
        rad1_id = rad_targets[0]["target_id"]
        rad2_id = rad_targets[1]["target_id"]

        print(f"  radio1 initial checked={rad_targets[0].get('checked')}")
        print(f"  radio2 initial checked={rad_targets[1].get('checked')}")

        print_step("12. CHECK radio 1 (switches group)")
        rad_chk = broker.check(rad1_id)
        if rad_chk.get("status") != "ok":
            print_fail(f"Radio CHECK failed: {rad_chk}")
        print_pass("Radio CHECK succeeded")

        # Verify radio group exclusivity
        find_rad2 = broker.find({"tag": "input", "type": "radio"})
        r1 = find_rad2["targets"][0].get("checked")
        r2 = find_rad2["targets"][1].get("checked")
        if not r1:
            print_fail(f"Radio 1 should be checked after CHECK, got checked={r1}")
        if r2:
            print_fail(f"Radio 2 should be unchecked after switching group, got checked={r2}")
        print_pass(f"Radio group exclusivity: r1={r1}, r2={r2}")

        print_step("13. UNCHECK radio 1 (must be blocked)")
        rad_unchk = broker.uncheck(rad1_id)
        if rad_unchk.get("status") != "error":
            print_fail(f"Radio UNCHECK should have failed, got: {rad_unchk}")
        if "TARGET_UNSUPPORTED_ACTION" not in rad_unchk.get("message", ""):
            print_fail(f"Expected TARGET_UNSUPPORTED_ACTION, got: {rad_unchk}")
        print_pass("Radio UNCHECK correctly blocked with TARGET_UNSUPPORTED_ACTION")

        # ── 8. STALE target guard ────────────────────────────────────────────
        print_step("14. Stale target guard")
        stale_res = broker.select("bt_nonexistent", "Option 1")
        if stale_res.get("status") != "error" or "TARGET_STALE" not in stale_res.get("message", ""):
            print_fail(f"Expected TARGET_STALE, got: {stale_res}")
        print_pass("Stale target guard: TARGET_STALE correctly returned")

        # ── 9. IPC Schema validation ─────────────────────────────────────────
        print_step("15. _REQUIRED_FIELDS schema check")
        from runtime.browser.broker_server import _REQUIRED_FIELDS, _validate_schema
        for cmd in ("SELECT", "CHECK", "UNCHECK"):
            if cmd not in _REQUIRED_FIELDS:
                print_fail(f"{cmd} not in _REQUIRED_FIELDS")
        print_pass("SELECT, CHECK, UNCHECK all registered in _REQUIRED_FIELDS")

        assert _validate_schema({"command": "SELECT", "target_id": "t1", "option_identity": "opt1"})[0], "SELECT schema should be valid"
        assert not _validate_schema({"command": "SELECT", "target_id": "t1"})[0], "SELECT missing option_identity should be invalid"
        assert _validate_schema({"command": "CHECK", "target_id": "t1"})[0], "CHECK schema should be valid"
        assert _validate_schema({"command": "UNCHECK", "target_id": "t1"})[0], "UNCHECK schema should be valid"
        print_pass("Schema validation correct for all three commands")

        # ── Done ─────────────────────────────────────────────────────────────
        print_step("ALL PHASE 3 CHECKS PASSED")

    finally:
        broker.stop_browser()
        srv.shutdown()


if __name__ == "__main__":
    main()
