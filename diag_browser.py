import sys
import os
import time
import subprocess

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from runtime.browser.manager import BrowserSessionManager

def main():
    print("EVENT: BROWSER_MANAGER_CREATE_ENTER")
    bmanager = BrowserSessionManager.create(profile="colab")
    
    # Overwrite the launch logic to capture stderr
    args = [
        bmanager.executable,
        f"--user-data-dir={bmanager.profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        "--app=about:blank"
    ]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print(f"EVENT: LAUNCH_SUCCESS PID={proc.pid}")
    time.sleep(2)
    alive = proc.poll() is None
    print(f"EVENT: PROCESS_ALIVE={alive}")
    if not alive:
        out, err = proc.communicate()
        print("STDOUT:", out)
        print("STDERR:", err)
    else:
        proc.terminate()

if __name__ == "__main__":
    main()
