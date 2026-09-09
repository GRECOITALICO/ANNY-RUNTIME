#!/usr/bin/env python3
"""Tests for installer and preflight semantics (Operation 015)."""
import os
import sys
import ast
import json
import subprocess
import tempfile
import textwrap
import unittest


class TestInstallShNoSilentFailures(unittest.TestCase):
    """P0-A: Verify zero '|| true' in install.sh."""
    
    def test_no_or_true_in_install_sh(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        install_sh = os.path.join(script_dir, '..', 'scripts', 'install.sh')
        with open(install_sh, 'r') as f:
            content = f.read()
        self.assertNotIn('|| true', content,
            "install.sh must contain ZERO '|| true' patterns")
    
    def test_rollback_daemon_reload_is_observable(self):
        """P0-B: daemon-reload failure in rollback must be observable (not silenced)."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        install_sh = os.path.join(script_dir, '..', 'scripts', 'install.sh')
        with open(install_sh, 'r') as f:
            content = f.read()
        # Must contain explicit error handling for daemon-reload
        self.assertIn('if ! sudo systemctl daemon-reload', content)
        self.assertIn('if ! systemctl --user daemon-reload', content)
    
    def test_rollback_failure_classified_separately(self):
        """P0-B: ROLLBACK_FAILED must be reported distinctly from INSTALLATION_FAILED."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        install_sh = os.path.join(script_dir, '..', 'scripts', 'install.sh')
        with open(install_sh, 'r') as f:
            content = f.read()
        self.assertIn('ROLLBACK_FAILED', content)
        self.assertIn('installation_failure=true', content)
        self.assertIn('rollback_attempted=true', content)
        self.assertIn('rollback_success=', content)
        self.assertIn('rollback_failure=', content)


class TestPreflightSemantics(unittest.TestCase):
    """P0-C / P0-D: Preflight error and warning semantics."""

    def _make_project(self, tmpdir, py_code, requirements="", inventory=None):
        """Create a minimal project structure for preflight testing."""
        runtime_dir = os.path.join(tmpdir, 'runtime')
        os.makedirs(runtime_dir, exist_ok=True)
        with open(os.path.join(runtime_dir, '__init__.py'), 'w') as f:
            f.write('')
        with open(os.path.join(runtime_dir, 'module.py'), 'w') as f:
            f.write(py_code)
        with open(os.path.join(tmpdir, 'requirements.txt'), 'w') as f:
            f.write(requirements)
        if inventory is not None:
            with open(os.path.join(tmpdir, 'DEPENDENCY-INVENTORY.json'), 'w') as f:
                json.dump(inventory, f)

    def _run_preflight(self, tmpdir):
        """Run preflight_check.py in a subprocess against tmpdir."""
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              '..', 'scripts', 'preflight_check.py')
        result = subprocess.run(
            [sys.executable, script, tmpdir],
            cwd=tmpdir,
            env={**os.environ, 'PYTHONPATH': tmpdir},
            capture_output=True, text=True
        )
        return result

    def test_missing_dependency_fails(self):
        """Import that is mapped but not in requirements.txt → FAIL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_project(tmpdir,
                py_code='import yaml\n',
                requirements='',
                inventory=[{"import": "yaml", "python_package": "PyYAML",
                           "source_file": "test"}])
            result = self._run_preflight(tmpdir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('DEPENDENCY_PREFLIGHT_FAILED', result.stderr)

    def test_missing_inventory_mapping_fails(self):
        """Import without inventory entry → FAIL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_project(tmpdir,
                py_code='import someunknownpkg\n',
                requirements='',
                inventory=[])
            result = self._run_preflight(tmpdir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('DEPENDENCY_MAPPING_MISSING', result.stderr)

    def test_ast_parse_error_fails(self):
        """Syntax error in source → FAIL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_project(tmpdir,
                py_code='def broken(:\n',
                requirements='',
                inventory=[])
            result = self._run_preflight(tmpdir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('STATIC_PARSE_ERROR', result.stderr)

    def test_dynamic_import_failure_fails(self):
        """Module that imports a missing package at runtime → FAIL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_project(tmpdir,
                py_code='import nonexistent_package_xyz\n',
                requirements='nonexistent_package_xyz\n',
                inventory=[{"import": "nonexistent_package_xyz",
                           "python_package": "nonexistent_package_xyz",
                           "source_file": "test"}])
            result = self._run_preflight(tmpdir)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('DEPENDENCY_MISSING', result.stderr)

    def test_unused_requirement_produces_warning_not_error(self):
        """Requirement declared but not imported → WARNING, not FAIL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # runtime/module.py has no third-party imports
            self._make_project(tmpdir,
                py_code='import os\nimport sys\n',
                requirements='somepkg>=1.0\n',
                inventory=[])
            result = self._run_preflight(tmpdir)
            # Should PASS (exit 0) but emit warning
            self.assertEqual(result.returncode, 0,
                f"Unused requirement should not cause failure. stderr: {result.stderr}")
            self.assertIn('DEPENDENCY_PREFLIGHT_WARNING', result.stderr)
            self.assertIn('DEPENDENCY_UNUSED', result.stderr)

    def test_baseline_requirements_pass(self):
        """The actual project requirements must pass preflight."""
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              '..', 'scripts', 'preflight_check.py')
        project_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
        result = subprocess.run(
            [sys.executable, script],
            cwd=project_root,
            env={**os.environ, 'PYTHONPATH': project_root},
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0,
            f"Baseline preflight must PASS. stderr: {result.stderr}")
        self.assertIn('DEPENDENCY_PREFLIGHT_PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
