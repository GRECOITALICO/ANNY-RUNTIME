import pytest
import tempfile
import os

@pytest.fixture(autouse=True, scope="session")
def setup_global_test_env():
    """Ensure all tests run with a temporary data directory to avoid touching real ~/.anny-runtime"""
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ANNY_DATA_DIR"] = tmp
        yield
        if "ANNY_DATA_DIR" in os.environ:
            del os.environ["ANNY_DATA_DIR"]
