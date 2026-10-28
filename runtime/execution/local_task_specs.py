"""Authorized structured plans for local-native demonstration artifacts.

These plans are submitted to the generic dispatcher.  No model has generated
or interpreted them, therefore their provenance remains STRUCTURED_AUTHORIZED_PLAN.
"""
from __future__ import annotations

import hashlib

from runtime.execution.local_native import PLANNER, PROFILE
from runtime.execution.local_repository_fixtures import get_fixture


def _spec(task_id: str, request: str, objective: str, capability: str, files: dict[str, str]) -> dict:
    paths = sorted(files)
    steps = [{"operation": "write_file", "arguments": {"path": path, "content": content}} for path, content in files.items()]
    steps += [
        {"operation": "read_file", "arguments": {"path": paths[0]}},
        {"operation": "inspect_structure", "arguments": {"paths": paths}},
        {"operation": "sha256", "arguments": {"paths": paths}},
        {"operation": "run_tests", "arguments": {"command": "python-unittest-q"}},
    ]
    return {
        "task_id": task_id, "request": request, "objective": objective,
        "execution_profile": PROFILE, "requested_capabilities": [capability], "steps": steps,
        "allowed_files": paths, "allowed_test_commands": ["python-unittest-q"],
        "acceptance_criteria": ["Generated files remain in the task workspace", "The allowlisted unittest runner exits successfully"],
        "evidence_references": [f"local://native-executions/{task_id}.json"], "planner": PLANNER,
    }


def safe_slug_task_spec(request: str = "Implement safe_slug(text) with Unicode-safe separator normalization and unit tests.") -> dict:
    return _spec("ANNY-RUNTIME-NATIVE-SAFE-SLUG-001", request, "Create and test a Unicode-safe safe_slug utility.", "experimental.local.safe_slug.v1", {
        "safe_slug.py": "def safe_slug(text: str) -> str:\n    if not isinstance(text, str):\n        raise TypeError('text must be a string')\n    parts = []\n    separator = False\n    for char in text.lower():\n        if char.isalnum():\n            parts.append(char)\n            separator = False\n        elif not separator:\n            parts.append('-')\n            separator = True\n    return ''.join(parts).strip('-')\n",
        "test_safe_slug.py": "import unittest\nfrom safe_slug import safe_slug\n\nclass SafeSlugTests(unittest.TestCase):\n    def test_contract(self):\n        self.assertEqual(safe_slug('Hello, Runtime!'), 'hello-runtime')\n        self.assertEqual(safe_slug('  ANNY__Local  Runtime  '), 'anny-local-runtime')\n        self.assertEqual(safe_slug('Conrrad: Bogotá'), 'conrrad-bogotá')\n        self.assertEqual(safe_slug(''), '')\n\nif __name__ == '__main__':\n    unittest.main()\n",
    })


def json_manifest_validation_task_spec() -> dict:
    return _spec("ANNY-RUNTIME-NATIVE-JSON-MANIFEST-002", "Create a Python utility that validates JSON manifests and reports structured errors.", "Create and test JSON-object manifest validation for required id, name, and version fields.", "experimental.local.json_manifest_validation.v1", {
        "manifest_validator.py": "import json\n\nREQUIRED_FIELDS = ('id', 'name', 'version')\n\ndef validate_manifest_json(raw: str) -> dict:\n    try:\n        document = json.loads(raw)\n    except json.JSONDecodeError as exc:\n        return {'valid': False, 'errors': [{'code': 'INVALID_JSON', 'message': str(exc)}]}\n    if not isinstance(document, dict):\n        return {'valid': False, 'errors': [{'code': 'DOCUMENT_NOT_OBJECT'}]}\n    errors = []\n    for field in REQUIRED_FIELDS:\n        value = document.get(field)\n        if value is None:\n            errors.append({'code': 'MISSING_FIELD', 'field': field})\n        elif not isinstance(value, str) or not value.strip():\n            errors.append({'code': 'INVALID_FIELD', 'field': field})\n    return {'valid': not errors, 'errors': errors}\n",
        "test_manifest_validator.py": "import unittest\nfrom manifest_validator import validate_manifest_json\n\nclass ManifestValidatorTests(unittest.TestCase):\n    def test_valid_document(self):\n        self.assertEqual(validate_manifest_json('{\\\"id\\\": \\\"a\\\", \\\"name\\\": \\\"ANNY\\\", \\\"version\\\": \\\"1\\\"}'), {'valid': True, 'errors': []})\n    def test_missing_fields(self):\n        result = validate_manifest_json('{\\\"id\\\": \\\"a\\\"}')\n        self.assertEqual({item['field'] for item in result['errors']}, {'name', 'version'})\n    def test_wrong_types(self):\n        result = validate_manifest_json('{\\\"id\\\": 3, \\\"name\\\": \\\"\\\", \\\"version\\\": []}')\n        self.assertEqual({item['field'] for item in result['errors']}, {'id', 'name', 'version'})\n    def test_invalid_json(self):\n        self.assertEqual(validate_manifest_json('{bad')['errors'][0]['code'], 'INVALID_JSON')\n\nif __name__ == '__main__':\n    unittest.main()\n",
    })


def repository_change_task_spec() -> dict:
    """Authorized plan to extend a private fixture with Unicode title casing."""
    fixture = get_fixture("local.python.text-normalizer.fixture.v1")
    assert fixture is not None
    module = fixture["files"]["text_normalizer.py"]
    test = fixture["files"]["test_text_normalizer.py"]
    changed_module = module + "\n\ndef normalize_display_name(value: str) -> str:\n    return normalize_title(value).title()\n"
    changed_test = test.replace("from text_normalizer import normalize_title", "from text_normalizer import normalize_display_name, normalize_title").replace("    def test_collapses_whitespace(self):", "    def test_display_name(self):\n        self.assertEqual(normalize_display_name('  aNNY   runtime '), 'Anny Runtime')\n\n    def test_collapses_whitespace(self):")
    changes = [
        {"path": "text_normalizer.py", "expected_sha256": hashlib.sha256(module.encode()).hexdigest(), "content": changed_module},
        {"path": "test_text_normalizer.py", "expected_sha256": hashlib.sha256(test.encode()).hexdigest(), "content": changed_test},
    ]
    task_id = "ANNY-RUNTIME-REPO-TASK-003"
    return {
        "task_id": task_id,
        "request": "Extend an isolated Python fixture with display-name normalization and tests.",
        "objective": "Apply verified content patches only to a private fixture workspace and pass its tests.",
        "execution_profile": PROFILE,
        "requested_capabilities": ["experimental.local.repository_change.v1"],
        "fixture_id": fixture["id"], "fixture_initial_hash": fixture["initial_hash"],
        "changes": changes,
        "execution_limits": {"timeout_seconds": 30, "memory_mb": 256, "cpus": 1, "pids": 64},
        "steps": [
            {"operation": "create_fixture", "arguments": {"fixture_id": fixture["id"], "initial_hash": fixture["initial_hash"]}},
            *[{"operation": "apply_patch", "arguments": change} for change in changes],
            {"operation": "read_file", "arguments": {"path": "text_normalizer.py"}},
            {"operation": "inspect_structure", "arguments": {"paths": ["text_normalizer.py", "test_text_normalizer.py"]}},
            {"operation": "sha256", "arguments": {"paths": ["text_normalizer.py", "test_text_normalizer.py"]}},
            {"operation": "run_tests", "arguments": {"command": "python-unittest-q"}},
        ],
        "allowed_files": ["text_normalizer.py", "test_text_normalizer.py"],
        "allowed_test_commands": ["python-unittest-q"],
        "acceptance_criteria": ["Fixture initial hash is verified", "Only declared private fixture files change", "The containerized unittest runner passes"],
        "evidence_references": [f"local://native-executions/{task_id}.json"], "planner": PLANNER,
    }
