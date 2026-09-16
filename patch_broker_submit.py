import re

with open("runtime/browser/broker_server.py", "r") as f:
    content = f.read()

# Add issue_auth
issue_auth_code = """    def issue_auth(self, target_id: str, session_id: str, expires_in: int = 300) -> dict:
        auth_id = str(uuid.uuid4())
        expires_at = time.time() + expires_in
        self.issued_authorizations[auth_id] = {
            "target_id": target_id,
            "session_id": session_id,
            "expires_at": expires_at
        }
        return {"status": "ok", "auth_id": auth_id}

    def submit"""
content = re.sub(r"    def submit", issue_auth_code, content, count=1)

# Modify submit
submit_pattern = r"""    def submit\(self, target_id: str, auth_object_dict: dict \| None = None\) -> dict:
.*?if not auth_object_dict:
            return \{"status": "error", "message": "MISSING_AUTHORIZATION"\}

        # Validate authorization object
        import datetime
        from runtime\.browser\.authorization import BrowserActionAuthorization
        
        try:
            auth_obj = BrowserActionAuthorization\(\*\*auth_object_dict\)
            if not auth_obj\.is_valid\(datetime\.datetime\.now\(datetime\.timezone\.utc\), self\._session_id, target_id\):
                return \{"status": "error", "message": "AUTHORIZATION_INVALID_OR_EXPIRED"\}
        except Exception:
            return \{"status": "error", "message": "AUTHORIZATION_MALFORMED"\}"""

submit_replacement = """    def submit(self, target_id: str, auth_id: str | None = None) -> dict:
        \"\"\"Submit target form. Required valid auth_id.\"\"\"
        if self.process is None or self.process.poll() is not None:
            return {"status": "error", "message": "Browser is not running."}

        target_record = self.targets.get(target_id)
        if not target_record or target_record["session_id"] != self._session_id:
            return {"status": "error", "message": "TARGET_STALE"}

        if not auth_id or auth_id not in self.issued_authorizations:
            return {"status": "error", "message": "MISSING_AUTHORIZATION"}

        auth = self.issued_authorizations[auth_id]
        if auth["session_id"] != self._session_id:
            return {"status": "error", "message": "AUTHORIZATION_SESSION_MISMATCH"}
        if auth["target_id"] != target_id:
            return {"status": "error", "message": "AUTHORIZATION_TARGET_MISMATCH"}
        if time.time() > auth["expires_at"]:
            return {"status": "error", "message": "AUTHORIZATION_EXPIRED"}

        # Authorized
        self._authorized_submit_pending = True"""

content = re.sub(r"    def submit\(self, target_id: str, auth_object_dict: dict \| None = None\) -> dict:.*?        # Execute JS to click submit or call form\.submit\(\)", submit_replacement + "\n        # Execute JS to click submit or call form.submit()", content, flags=re.DOTALL)

# Add ISSUE_AUTH to command handler
issue_cmd = """            elif command == "ISSUE_AUTH":
                response = self.server.broker.issue_auth(request["target_id"], request["session_id"], request.get("expires_in", 300))

            elif command == "NAVIGATE":"""
content = content.replace('            elif command == "NAVIGATE":', issue_cmd)

# Update SUBMIT command handler
submit_cmd = """            elif command == "SUBMIT":
                response = self.server.broker.submit(request["target_id"], request.get("auth_id"))"""
content = re.sub(r"            elif command == \"SUBMIT\":.*?                response = self\.server\.broker\.submit\(request\[\"target_id\"\], auth_obj\)", submit_cmd, content, flags=re.DOTALL)

with open("runtime/browser/broker_server.py", "w") as f:
    f.write(content)
