import sys

with open("runtime/browser/broker_server.py", "r") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "if (typeof form.requestSubmit === 'function') {" in line:
        new_lines.append("""            if (typeof form.requestSubmit === 'function') {
                try {
                    let submitter = (this.nodeType === 1 && (this.type === 'submit' || this.type === 'image')) ? this : null;
                    if (!submitter && this.parentElement && this.parentElement.type === 'submit') {
                        submitter = this.parentElement;
                    }
                    if (submitter) form.requestSubmit(submitter);
                    else form.requestSubmit();
                } catch(e) { form.submit(); }
""")
    elif "form.requestSubmit(this);" in line:
        pass # remove
    elif 'res = self._cdp_request("Runtime.callFunctionOn"' in line:
        new_lines.append('        import sys\n')
        new_lines.append('        print("[DEBUG] Calling Runtime.callFunctionOn...", file=sys.stderr)\n')
        new_lines.append('        res = self._cdp_request("Runtime.callFunctionOn", {\n')
    elif 'val = res.get("result", {}).get("value", {})' in line:
        new_lines.append('        print(f"[DEBUG] Runtime.callFunctionOn returned: {res}", file=sys.stderr)\n')
        new_lines.append(line)
    elif '# Give the browser a brief moment to complete the request' in line:
        new_lines.append(line)
        new_lines.append('        time.sleep(1.5)\n')
        new_lines.append('        print("[DEBUG] Calling observe()...", file=sys.stderr)\n')
    else:
        new_lines.append(line)

with open("runtime/browser/broker_server.py", "w") as f:
    f.writelines(new_lines)
