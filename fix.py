import sys
import re

with open("runtime/browser/broker_server.py", "r") as f:
    code = f.read()

# 1. Add time import
code = code.replace("import os\n", "import os\nimport time\n")

# 2. Fix JS logic
old_js = """            if (typeof form.requestSubmit === 'function') {
                form.requestSubmit(this);
            } else {
                form.submit();
            }"""
new_js = """            if (typeof form.requestSubmit === 'function') {
                try {
                    let submitter = (this.nodeType === 1 && (this.type === 'submit' || this.type === 'image')) ? this : null;
                    if (!submitter && this.parentElement && this.parentElement.type === 'submit') submitter = this.parentElement;
                    if (submitter) form.requestSubmit(submitter);
                    else form.requestSubmit();
                } catch(e) {
                    form.submit();
                }
            } else {
                form.submit();
            }"""
code = code.replace(old_js, new_js)

# 3. Add sleep before observe and fix return format
old_ret = """        # Immediately return a post-action observation
        obs = self.observe()
        if obs.get("status") == "ok":
            return {"status": "ok", "result": "success", "action": {"type": "submit", "target_id": target_id}, "observation": obs.get("observation")}
        return {"status": "ok", "result": "success", "action": {"type": "submit", "target_id": target_id}, "observation_error": obs.get("message")}"""

new_ret = """        # Give the browser a brief moment to complete the request and navigation
        time.sleep(1.5)

        # Immediately return a post-action observation
        obs = self.observe()
        if obs.get("status") == "ok":
            return {
                "status": "ok",
                "result": "REQUEST_ACCEPTED",
                "action": {"type": "submit", "target_id": target_id, "authorization_used": True},
                "request": {"method": pending.expected_method, "destination": pending.expected_url},
                "observation": obs.get("observation")
            }
        return {
            "status": "ok",
            "result": "POST_ACTION_FAILED",
            "action": {"type": "submit", "target_id": target_id, "authorization_used": True},
            "request": {"method": pending.expected_method, "destination": pending.expected_url},
            "observation_error": obs.get("message")
        }"""
code = code.replace(old_ret, new_ret)

# 4. Add postData to Fetch.continueRequest if present
old_continue = 'self._send_cdp_async("Fetch.continueRequest", {"requestId": request_id})'
new_continue = 'self._send_cdp_async("Fetch.continueRequest", {"requestId": request_id, "postData": req.get("postData")} if "postData" in req else {"requestId": request_id})'
code = code.replace(old_continue, new_continue)

with open("runtime/browser/broker_server.py", "w") as f:
    f.write(code)
