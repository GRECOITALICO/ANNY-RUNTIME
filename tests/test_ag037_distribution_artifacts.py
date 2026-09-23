"""
AG-037 Distribution Artifact Tests.
Physical verification of the end-to-end distribution pipeline:
  build → artifact → checksum → corrupt rejection → extract → install → identity → health
"""
import hashlib
import os
import shutil
import socket
import subprocess
import tarfile
import time
from pathlib import Path

import httpx
import pytest


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
    """Build a clean release artifact from the current HEAD (must be clean tree)."""
    result = subprocess.run(
        ["./scripts/build_release.sh"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Failed to build artifact:\n{result.stdout}\n{result.stderr}"
    )

    commit_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    ).stdout.strip()
    short_sha = commit_sha[:7]

    tarball_name = f"ANNY-RUNTIME-v0.4.0-{short_sha}.tar.gz"
    tarball_path = repo_root / tarball_name
    checksum_path = repo_root / f"{tarball_name}.sha256"

    assert tarball_path.exists(), f"Artifact not found: {tarball_path}"
    assert checksum_path.exists(), f"Checksum not found: {checksum_path}"

    return {
        "tarball_path": tarball_path,
        "checksum_path": checksum_path,
        "tarball_name": tarball_name,
        "short_sha": short_sha,
        "commit_sha": commit_sha,
    }


# ---------------------------------------------------------------------------
# POSITIVE: checksum matches
# ---------------------------------------------------------------------------

def test_positive_checksum(build_artifact):
    """sha256sum -c on a pristine artifact must succeed (exit 0)."""
    result = subprocess.run(
        ["sha256sum", "-c", build_artifact["checksum_path"].name],
        cwd=build_artifact["tarball_path"].parent,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Checksum verification failed:\n{result.stdout}\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# NEGATIVE 1: corrupted artifact → checksum must fail
# ---------------------------------------------------------------------------

def test_negative_checksum_corrupted_artifact(build_artifact, tmp_path):
    """Appending bytes to the artifact must cause sha256sum -c to fail."""
    shutil.copy(build_artifact["tarball_path"], tmp_path)
    shutil.copy(build_artifact["checksum_path"], tmp_path)

    corrupted = tmp_path / build_artifact["tarball_name"]
    with open(corrupted, "ab") as f:
        f.write(b"CORRUPTED_SENTINEL_BYTES")

    result = subprocess.run(
        ["sha256sum", "-c", build_artifact["checksum_path"].name],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    # Only check return code — output is locale-dependent
    assert result.returncode != 0, "Corrupted artifact should have failed checksum"


# ---------------------------------------------------------------------------
# NEGATIVE 2: wrong checksum → verification must fail
# ---------------------------------------------------------------------------

def test_negative_wrong_checksum(build_artifact, tmp_path):
    """A zeroed-out checksum file must cause sha256sum -c to fail."""
    shutil.copy(build_artifact["tarball_path"], tmp_path)

    wrong_hash = "0" * 64
    wrong_checksum_file = tmp_path / build_artifact["checksum_path"].name
    wrong_checksum_file.write_text(
        f"{wrong_hash}  {build_artifact['tarball_name']}\n"
    )

    result = subprocess.run(
        ["sha256sum", "-c", wrong_checksum_file.name],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, "Wrong checksum should have failed verification"


# ---------------------------------------------------------------------------
# ARTIFACT CONTENT AUDIT
# ---------------------------------------------------------------------------

def test_artifact_content_audit(build_artifact):
    """Verify required paths present and forbidden paths absent in the tarball."""
    forbidden_patterns = [".git/", "server.log", "server.pid", "server2.log"]

    with tarfile.open(build_artifact["tarball_path"], "r:gz") as tar:
        names = tar.getnames()

    # Required paths
    assert any(n.endswith("scripts/install.sh") for n in names), (
        "scripts/install.sh not found in artifact"
    )
    assert any(n.endswith("runtime/core/version.py") for n in names), (
        "runtime/core/version.py not found in artifact"
    )

    # Forbidden paths
    for name in names:
        for forbidden in forbidden_patterns:
            assert forbidden not in name, (
                f"Found forbidden path in artifact: {name}"
            )


# ---------------------------------------------------------------------------
# ISOLATED INSTALL: extract → symlink existing venv → identity → health
# ---------------------------------------------------------------------------

def test_isolated_install_and_health(build_artifact, repo_root, tmp_path):
    """
    Physical isolated install/health verification.

    Because the sandbox has no network access, we cannot pip-install into a
    fresh venv from PyPI.  Instead we:
      1. Extract the artifact into a temp dir.
      2. Symlink the repo's already-resolved venv into the install dir (this is
         the same dependency set — install.sh would have produced an identical
         result in a networked environment).
      3. Verify the embedded identity (version + commit) in the extracted source.
      4. Start the runtime from the extracted source and probe the health endpoints.

    This tests the extractability, embedded identity, and runtime liveness
    of the distribution artifact under sandbox constraints.
    """
    extract_dir = tmp_path / "extract"
    install_dir = tmp_path / "install"
    data_dir = tmp_path / "data"

    extract_dir.mkdir()
    install_dir.mkdir()
    data_dir.mkdir()

    # --- 1. EXTRACTION ---
    with tarfile.open(build_artifact["tarball_path"], "r:gz", format=tarfile.PAX_FORMAT) as tar:
        tar.extractall(path=extract_dir, filter="data")

    build_dir_name = (
        f"ANNY-RUNTIME-v0.4.0-{build_artifact['short_sha']}_build"
    )
    source_dir = extract_dir / build_dir_name
    assert source_dir.exists(), f"Extracted build dir not found: {source_dir}"

    # --- 2. EMBEDDED IDENTITY VERIFICATION ---
    extracted_version_py = source_dir / "runtime" / "core" / "version.py"
    assert extracted_version_py.exists()
    content = extracted_version_py.read_text()
    assert f'__version__ = "0.4.0"' in content, (
        "Embedded __version__ does not match"
    )
    assert f'__commit__ = "{build_artifact["commit_sha"]}"' in content, (
        f"Embedded __commit__ does not match source commit {build_artifact['commit_sha']}"
    )

    # --- 3. COPY SOURCES TO INSTALL DIR (mirrors what install.sh does) ---
    for item in source_dir.iterdir():
        dest = install_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    # Use system python3 (all deps are available system-wide in this environment)
    python_bin = Path("python3")
    # If the repo has a venv, prefer it; otherwise use system python3
    repo_venv_python = repo_root / "venv" / "bin" / "python3"
    if repo_venv_python.exists():
        python_bin = repo_venv_python
        (install_dir / "venv").symlink_to(repo_root / "venv")

    # Verify the runtime package is importable from install dir
    check = subprocess.run(
        [str(python_bin), "-c", "import runtime"],
        env={**os.environ, "PYTHONPATH": str(install_dir)},
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, (
        f"runtime package not importable:\n{check.stderr}"
    )

    # --- 4. BOOTSTRAP IDENTITY (mirrors install.sh step 11) ---
    port = get_free_port()
    cli_script = install_dir / "cli" / "main.py"
    assert cli_script.exists(), f"CLI script not found: {cli_script}"

    env = {
        **os.environ,
        "PYTHONPATH": str(install_dir),
        "ANNY_ADMIN_PORT": str(port),
        "ANNY_DATA_DIR": str(data_dir),
        "ANNY_INSTALL_MODE": "user",
    }

    bootstrap_result = subprocess.run(
        [str(python_bin), str(cli_script), "identity-bootstrap"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert bootstrap_result.returncode == 0, (
        f"identity-bootstrap failed:\n{bootstrap_result.stdout}\n{bootstrap_result.stderr}"
    )

    # --- 5. START RUNTIME ---

    proc = subprocess.Popen(
        [str(python_bin), str(cli_script), "server", "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        # --- 5. LIVENESS ---
        live = False
        last_err = None
        last_resp = None
        import urllib.request
        import urllib.error
        import json

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        for _ in range(15):
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/health/live")
                with opener.open(req, timeout=1.0) as resp:
                    if resp.getcode() == 200:
                        live = True
                        break
                    last_resp = f"{resp.getcode()}: {resp.read().decode('utf-8', errors='ignore')}"
            except urllib.error.HTTPError as e:
                last_resp = f"{e.code}: {e.read().decode('utf-8', errors='ignore')}"
                last_err = e
            except Exception as e:
                last_err = e
            time.sleep(1)

        if not live:
            proc.terminate()
            out, err = proc.communicate(timeout=5)
            pytest.fail(
                f"Runtime failed to become live. Last error: {last_err}, Last resp: {last_resp}\nStdout:\n{out.decode()}\nStderr:\n{err.decode()}"
            )

        # --- 6. READINESS (200 or 503 are both valid; endpoint must exist) ---
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/health/ready")
            with opener.open(req, timeout=3.0) as resp:
                readiness_code = resp.getcode()
        except urllib.error.HTTPError as e:
            readiness_code = e.code
        assert readiness_code in (200, 503), (
            f"Unexpected readiness status: {readiness_code}"
        )

        # --- 7. STATUS / RUNTIME IDENTITY ---
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/status")
            with opener.open(req, timeout=3.0) as resp:
                status_code = resp.getcode()
                body = resp.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            status_code = e.code
            body = ""
            
        assert status_code == 200, (
            f"/api/status returned {status_code}"
        )
        status_data = json.loads(body)
        assert status_data.get("runtime_version") == "0.4.0", f"Version mismatch in status: {status_data}"
        # This isolated install intentionally has no GitHub/Fabric binding.
        # The Runtime must therefore remain administratively available while
        # fail-closing in ADMIN_MODE, rather than appearing RUNNING/ready.
        assert status_data.get("runtime_state") == "ADMIN_MODE", f"Unexpected state in status: {status_data}"
        assert status_data.get("anny_ready") is False
        assert status_data.get("runtime_health") == "DEGRADED"

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
