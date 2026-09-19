import os
import subprocess
import tarfile
import tempfile
import json
import shutil
import pytest
import time
import httpx
from pathlib import Path
import socket

def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    s.listen(1)
    port = s.getsockname()[1]
    s.close()
    return port

@pytest.fixture(scope="session")
def repo_root():
    return Path(__file__).parent.parent.absolute()

@pytest.fixture(scope="session")
def build_artifact(repo_root):
    # Ensure build_release has been run and get artifact path
    result = subprocess.run(["./scripts/build_release.sh"], cwd=repo_root, capture_output=True, text=True)
    assert result.returncode == 0, f"Failed to build artifact: {result.stdout} {result.stderr}"
    
    commit_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True).stdout.strip()
    short_sha = commit_sha[:7]
    tarball_name = f"ANNY-RUNTIME-v0.4.0-{short_sha}.tar.gz"
    
    tarball_path = repo_root / tarball_name
    checksum_path = repo_root / f"{tarball_name}.sha256"
    
    assert tarball_path.exists()
    assert checksum_path.exists()
    
    return {
        "tarball_path": tarball_path,
        "checksum_path": checksum_path,
        "tarball_name": tarball_name,
        "short_sha": short_sha,
        "commit_sha": commit_sha
    }

def test_positive_checksum(build_artifact):
    # Test that sha256sum -c succeeds
    result = subprocess.run(["sha256sum", "-c", build_artifact["checksum_path"].name], cwd=build_artifact["tarball_path"].parent, capture_output=True, text=True)
    assert result.returncode == 0, f"Checksum verification failed: {result.stdout}"

def test_negative_checksum_corrupted_artifact(build_artifact, tmp_path):
    # Copy to tmp
    shutil.copy(build_artifact["tarball_path"], tmp_path)
    shutil.copy(build_artifact["checksum_path"], tmp_path)
    
    # Corrupt artifact
    with open(tmp_path / build_artifact["tarball_name"], "a") as f:
        f.write("corrupted")
        
    result = subprocess.run(["sha256sum", "-c", build_artifact["checksum_path"].name], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0
    assert "FAILED" in result.stdout

def test_negative_wrong_checksum(build_artifact, tmp_path):
    shutil.copy(build_artifact["tarball_path"], tmp_path)
    
    # Create wrong checksum
    wrong_checksum = "0" * 64
    with open(tmp_path / build_artifact["checksum_path"].name, "w") as f:
        f.write(f"{wrong_checksum}  {build_artifact['tarball_name']}\n")
        
    result = subprocess.run(["sha256sum", "-c", build_artifact["checksum_path"].name], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0
    assert "FAILED" in result.stdout

def test_artifact_content_audit(build_artifact):
    forbidden_patterns = [".git/", ".env", "server.log", "server.pid"]
    with tarfile.open(build_artifact["tarball_path"], "r:gz") as tar:
        names = tar.getnames()
        
        # Verify required
        assert any(n.endswith("scripts/install.sh") for n in names)
        assert any(n.endswith("runtime/core/version.py") for n in names)
        
        # Verify forbidden
        for name in names:
            for forbidden in forbidden_patterns:
                assert forbidden not in name, f"Found forbidden path in artifact: {name}"

def test_isolated_install_and_health(build_artifact, tmp_path):
    extract_dir = tmp_path / "extract"
    install_dir = tmp_path / "install"
    data_dir = tmp_path / "data"
    
    extract_dir.mkdir()
    install_dir.mkdir()
    data_dir.mkdir()
    
    # Extract
    with tarfile.open(build_artifact["tarball_path"], "r:gz") as tar:
        tar.extractall(path=extract_dir)
        
    build_dir_name = f"ANNY-RUNTIME-v0.4.0-{build_artifact['short_sha']}_build"
    source_dir = extract_dir / build_dir_name
    
    # Install
    env = os.environ.copy()
    env["FINAL_INSTALL_DIR"] = str(install_dir)
    env["DATA_DIR"] = str(data_dir)
    
    install_script = source_dir / "scripts" / "install.sh"
    result = subprocess.run([str(install_script)], env=env, cwd=source_dir, capture_output=True, text=True)
    assert result.returncode == 0, f"Installation failed: {result.stdout}\n{result.stderr}"
    
    # Assert post-install identity
    installed_version_py = install_dir / "runtime" / "core" / "version.py"
    assert installed_version_py.exists()
    content = installed_version_py.read_text()
    assert f'__commit__ = "{build_artifact["commit_sha"]}"' in content
    assert f'__version__ = "0.4.0"' in content
    
    # Start runtime
    port = get_free_port()
    cli_bin = install_dir / "venv" / "bin" / "python3"
    cli_script = install_dir / "cli" / "main.py"
    
    env["ANNY_PORT"] = str(port)
    env["ANNY_DATA_DIR"] = str(data_dir)
    env["ANNY_INSTALL_MODE"] = "user"
    
    proc = subprocess.Popen([str(cli_bin), str(cli_script), "server"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for liveness
    live = False
    for _ in range(10):
        try:
            resp = httpx.get(f"http://127.0.0.1:{port}/health/live", timeout=1.0)
            if resp.status_code == 200:
                live = True
                break
        except Exception:
            pass
        time.sleep(1)
        
    if not live:
        proc.terminate()
        out, err = proc.communicate()
        pytest.fail(f"Runtime failed to become live. Stdout:\n{out.decode()}\nStderr:\n{err.decode()}")
        
    # Check readiness
    resp = httpx.get(f"http://127.0.0.1:{port}/health/ready")
    assert resp.status_code in (200, 503) # 503 if not fully ready (e.g., config missing), but endpoint exists
    
    # Check status identity
    resp = httpx.get(f"http://127.0.0.1:{port}/api/status")
    assert resp.status_code == 200
    status_data = resp.json()
    assert status_data["identity"]["runtime_version"] == "0.4.0"
    
    proc.terminate()
    proc.wait()
