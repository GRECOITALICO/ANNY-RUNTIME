import re

with open("tests/physical_r5c_submit_deny.py", "r") as f:
    content = f.read()

# Add textarea to form HTML
html_pattern = r'    <button type="submit" id="test-submit" aria-label="Submit Form">Submit</button>'
html_repl = r'''    <button type="submit" id="test-submit" aria-label="Submit Form">Submit</button>
    <textarea id="test-textarea" aria-label="Comments"></textarea>'''
content = content.replace(html_pattern, html_repl)

# Add tests D2, F, G, H, I
test_code = """
    # ── D2: type() with '\\n' on textarea → ALLOWED ──────────────────────────
    print_step("6B. type() with newline on textarea (expect SUCCESS)")
    find_ta = broker.find({"tag": "textarea"})
    ta_targets = find_ta.get("targets", [])
    if not ta_targets:
        print_fail("Could not find textarea")
        sys.exit(1)
    ta_id = ta_targets[0]["target_id"]
    ta_res = broker.type(ta_id, "hello\\nworld")
    if ta_res.get("status") != "ok":
        print_fail(f"Expected SUCCESS from textarea newline type, got: {ta_res}")
        sys.exit(1)
    print_pass("type(textarea, '\\n') succeeded")

    # ── F: Programmatic form.submit() → blocked by CDP ───────────────────────
    print_step("8. Programmatic form.submit() (expect blocked by Fetch intercept)")
    broker._cdp_request("Runtime.evaluate", {
        "expression": "document.getElementById('test-form').submit();"
    })
    time.sleep(0.5)
    if _submissions_received > 0:
        print_fail(f"form.submit() bypassed broker! Submissions: {_submissions_received}")
        sys.exit(1)
    print_pass("form.submit() blocked by CDP Fetch intercept")

    # ── G: Programmatic requestSubmit() → blocked by CDP ──────────────────────
    print_step("9. Programmatic form.requestSubmit() (expect blocked)")
    broker._cdp_request("Runtime.evaluate", {
        "expression": "document.getElementById('test-form').requestSubmit();"
    })
    time.sleep(0.5)
    if _submissions_received > 0:
        print_fail(f"form.requestSubmit() bypassed broker! Submissions: {_submissions_received}")
        sys.exit(1)
    print_pass("form.requestSubmit() blocked by CDP Fetch intercept")

    # ── H: Valid runtime-issued authorization ────────────────────────────────
    print_step("10. Valid runtime-issued authorization")
    auth_res = broker.issue_auth(submit_btn_id, broker._session_id, 300)
    auth_id = auth_res["auth_id"]
    print_pass(f"Issued auth_id: {auth_id}")
    
    sub_res = broker.submit(submit_btn_id, auth_id)
    if sub_res.get("status") != "ok":
        print_fail(f"Expected SUCCESS for authorized submit, got: {sub_res}")
        sys.exit(1)
        
    time.sleep(1)
    
    if _submissions_received == 0:
        print_fail(f"Authorized submit did not reach server! Submissions: {_submissions_received}")
        sys.exit(1)
    print_pass("Authorized submission reached server successfully")

    print_step("11. Verify no navigation and no server submissions")
"""

content = re.sub(r'    # ── E: No navigation / no server submissions ──────────────────────────────.*?    print_step\("7\. Verify no navigation and no server submissions"\)', test_code, content, flags=re.DOTALL)

with open("tests/physical_r5c_submit_deny.py", "w") as f:
    f.write(content)
