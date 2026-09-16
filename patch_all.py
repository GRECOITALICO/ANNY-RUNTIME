import sys

with open("runtime/browser/broker_server.py", "r") as f:
    lines = f.readlines()

out = []
# Add global import time
out.append("import time\n")

for line in lines:
    if "def _handle_cdp_event" in line:
        out.append(line)
        out.append("        if 'error' in event:\n")
        out.append("            import sys\n")
        out.append("            print(f'[DEBUG CDP ERROR] {event}', file=sys.stderr)\n")
    elif "if method == \"Fetch.requestPaused\":" in line:
        out.append(line)
        out.append("            import sys\n")
        out.append("            req = event.get('params', {}).get('request', {})\n")
        out.append("            print(f'[DEBUG Fetch] Paused {req.get(\"method\")} to {req.get(\"url\")}', file=sys.stderr)\n")
    elif "self._send_cdp_async(\"Fetch.continueRequest\", {\"requestId\": request_id})" in line:
        out.append("                            import sys\n")
        out.append("                            print(f'[DEBUG Fetch] Authorized POST, continuing {request_id}', file=sys.stderr)\n")
        out.append(line)
    elif "if (typeof form.requestSubmit === 'function') {" in line:
        out.append("""            if (typeof form.requestSubmit === 'function') {
                try {
                    let submitter = (this.nodeType === 1 && (this.type === 'submit' || this.type === 'image')) ? this : null;
                    if (!submitter && this.parentElement && this.parentElement.type === 'submit') submitter = this.parentElement;
                    if (submitter) form.requestSubmit(submitter);
                    else form.requestSubmit();
                } catch(e) { form.submit(); }
""")
    elif "form.requestSubmit(this);" in line:
        pass
    elif "return {\"status\": \"ok\", \"result\": \"success\", \"action\": {\"type\": \"submit\", \"target_id\": target_id}, \"observation\": obs.get(\"observation\")}" in line:
        out.append("""            return {
                "status": "ok",
                "result": "REQUEST_ACCEPTED",
                "action": {"type": "submit", "target_id": target_id, "authorization_used": True},
                "request": {"method": pending.expected_method, "destination": pending.expected_url},
                "observation": obs.get("observation")
            }
""")
    elif "return {\"status\": \"ok\", \"result\": \"success\", \"action\": {\"type\": \"submit\", \"target_id\": target_id}, \"observation_error\": obs.get(\"message\")}" in line:
        out.append("""        return {
            "status": "ok",
            "result": "POST_ACTION_FAILED",
            "action": {"type": "submit", "target_id": target_id, "authorization_used": True},
            "request": {"method": pending.expected_method, "destination": pending.expected_url},
            "observation_error": obs.get("message")
        }
""")
    elif "obs = self.observe()" in line and "Immediately return a post-action observation" not in line:
        out.append("        time.sleep(1.5)\n")
        out.append(line)
    else:
        out.append(line)

with open("runtime/browser/broker_server.py", "w") as f:
    f.writelines(out)
