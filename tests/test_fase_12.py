import urllib.request
import urllib.parse
import re
import subprocess
import json

def run_fase_12():
    logs = []
    def log(msg):
        print(msg)
        logs.append(msg)
        
    try:
        # GET /
        base_url = "http://127.0.0.1:3643"
        req1 = urllib.request.Request(base_url)
        with urllib.request.urlopen(req1) as resp:
            html = resp.read().decode('utf-8')
            cookie_header = resp.headers.get('Set-Cookie', '')
            session_id_match = re.search(r'admin_session_id=([^;]+)', cookie_header)
            session_id = session_id_match.group(1) if session_id_match else None
            
            csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', html)
            csrf_token = csrf_match.group(1) if csrf_match else None
            
        log("status: 200")
        log("route: GET /")
        log(f"Set-Cookie: {'YES' if session_id else 'NO'}")
        log(f"CSRF result: {'YES' if csrf_token else 'NO'}")

        if not session_id or not csrf_token:
            log("FAILED TO GET SESSION OR CSRF")
            return
            
        # Get existing operator token
        proc = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True)
        token = proc.stdout.strip()
        if not token:
            log("FAILED TO GET GH TOKEN")
            return

        # POST /github/token
        data = urllib.parse.urlencode({'github_token': token, 'csrf_token': csrf_token}).encode('utf-8')
        req2 = urllib.request.Request(f"{base_url}/github/token", data=data)
        req2.add_header('Cookie', f'admin_session_id={session_id}')
        req2.add_header('Content-Type', 'application/x-www-form-urlencoded')
        
        try:
            with urllib.request.urlopen(req2) as resp2:
                final_html = resp2.read().decode('utf-8')
                final_url = resp2.url
                final_cookie = resp2.headers.get('Set-Cookie', '')
                final_status = resp2.status
        except urllib.error.HTTPError as e:
            final_status = e.code
            final_url = e.url
            final_cookie = e.headers.get('Set-Cookie', '')
            
        log(f"status: {final_status}")
        log(f"route: POST /github/token -> redirect -> {final_url}")
        
        final_session_id_match = re.search(r'admin_session_id=([^;]+)', final_cookie)
        final_session_id = final_session_id_match.group(1) if final_session_id_match else None
        
        if final_session_id and final_session_id != session_id:
            log("session transition: ONBOARDING_ONLY revoked, NORMAL SESSION created")
        else:
            log("session transition: NO CHANGE OR FAILED")

    except Exception as e:
        log(f"ERROR: {str(e)}")
        
    with open("fase_12_logs.json", "w") as f:
        json.dump(logs, f, indent=2)

if __name__ == "__main__":
    run_fase_12()
