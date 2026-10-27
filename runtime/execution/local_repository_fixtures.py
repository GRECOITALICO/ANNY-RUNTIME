"""Small immutable repository fixtures for local-native repository tasks."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def fixture_hash(files: dict[str, str]) -> str:
    """Return a deterministic identity for a fixture's complete initial tree."""
    return hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


_TEXT_NORMALIZER_FILES = {
    "text_normalizer.py": "def normalize_title(value: str) -> str:\n    if not isinstance(value, str):\n        raise TypeError('value must be a string')\n    return ' '.join(value.split())\n",
    "test_text_normalizer.py": "import unittest\nfrom text_normalizer import normalize_title\n\nclass TextNormalizerTests(unittest.TestCase):\n    def test_collapses_whitespace(self):\n        self.assertEqual(normalize_title('  ANNY    Runtime  '), 'ANNY Runtime')\n\nif __name__ == '__main__':\n    unittest.main()\n",
}

LOCAL_REPOSITORY_FIXTURES: dict[str, dict[str, Any]] = {
    "local.python.text-normalizer.fixture.v1": {
        "id": "local.python.text-normalizer.fixture.v1",
        "files": _TEXT_NORMALIZER_FILES,
        "initial_hash": fixture_hash(_TEXT_NORMALIZER_FILES),
        "provenance": "LOCAL_STATIC_TEST_FIXTURE",
    },
}


def get_fixture(fixture_id: str) -> dict[str, Any] | None:
    fixture = LOCAL_REPOSITORY_FIXTURES.get(fixture_id)
    if fixture is None:
        return None
    return {**fixture, "files": dict(fixture["files"])}
