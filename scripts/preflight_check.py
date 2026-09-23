#!/usr/bin/env python3
import ast
import importlib
import importlib.metadata
import os
import re
import sys

# The project has one requirements source of truth.  Python import names that
# differ from distribution names live here, beside the preflight validator,
# instead of in a second mutable inventory file.
CANONICAL_IMPORT_TO_PACKAGE = {
    "cryptography": "cryptography",
    "azure": "azure-identity",
    "dateutil": "python-dateutil",
    "httpx": "httpx",
    "llama_cpp": "llama-cpp-python",
    "mcp": "mcp",
    "psutil": "psutil",
    "websocket": "websocket-client",
    "yaml": "PyYAML",
}

def get_stdlib_module_names():
    if sys.version_info >= (3, 10):
        return sys.stdlib_module_names
    else:
        import sysconfig
        stdlib_path = sysconfig.get_path('stdlib')
        names = set(sys.builtin_module_names)
        if stdlib_path and os.path.exists(stdlib_path):
            for f in os.listdir(stdlib_path):
                if f.endswith('.py'): names.add(f[:-3])
                elif '.' not in f: names.add(f)
        return names

def normalize_package_name(name):
    """Normalize a distribution name using the packaging-name convention."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirements(base_dir):
    """Read the single canonical dependency declaration.

    requirements.txt is deliberately the only dependency source.  Historical
    inventories are evidence inputs, never policy inputs for installation or
    preflight.
    """
    req_file = os.path.join(base_dir, 'requirements.txt')
    reqs = {}
    if os.path.exists(req_file):
        with open(req_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    match = re.match(
                        r'^([a-zA-Z0-9_.\-]+)(?:\[[a-zA-Z0-9_\-,]+\])?'
                        r'((?:[=><~!]=?[^,\s]+(?:,[=><~!]=?[^,\s]+)*)?)$',
                        line,
                    )
                    if not match:
                        print(f"REQUIREMENT_PARSE_UNKNOWN: {line}", file=sys.stderr)
                        sys.exit(1)
                    pkg = match.group(1).strip()
                    reqs[normalize_package_name(pkg)] = match.group(2) or ""
    return reqs

def _version_tuple(value):
    """Return a conservative comparable tuple for ordinary release versions."""
    parts = []
    for part in re.split(r"[.+-]", value):
        match = re.match(r"(\d+)", part)
        if not match:
            break
        parts.append(int(match.group(1)))
    return tuple(parts)


def _satisfies_version(installed, specifiers):
    """Evaluate the simple PEP 440 comparisons used by this requirements file.

    Unsupported or malformed constraints fail closed instead of silently
    declaring a clean preflight.
    """
    if not specifiers:
        return True
    installed_tuple = _version_tuple(installed)
    if not installed_tuple:
        return False
    for specifier in specifiers.split(","):
        match = re.fullmatch(r"(===|==|!=|>=|<=|>|<|~=)([^\s]+)", specifier)
        if not match:
            return False
        operator, requested = match.groups()
        requested_tuple = _version_tuple(requested)
        if not requested_tuple:
            return False
        if operator in ("==", "==="):
            ok = installed == requested
        elif operator == "!=":
            ok = installed != requested
        elif operator == ">=":
            ok = installed_tuple >= requested_tuple
        elif operator == "<=":
            ok = installed_tuple <= requested_tuple
        elif operator == ">":
            ok = installed_tuple > requested_tuple
        elif operator == "<":
            ok = installed_tuple < requested_tuple
        else:  # ~=: compatible release, sufficient for the declared policy.
            ok = installed_tuple >= requested_tuple and installed_tuple[:1] == requested_tuple[:1]
        if not ok:
            return False
    return True


def validate_installed_requirements(requirements):
    """Return deterministic errors for absent or incompatible distributions."""
    errors = []
    for package, specifiers in requirements.items():
        try:
            installed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"DEPENDENCY_NOT_INSTALLED: {package}")
            continue
        if not _satisfies_version(installed, specifiers):
            errors.append(
                f"DEPENDENCY_VERSION_INCOMPATIBLE: {package} installed={installed} required={specifiers}"
            )
    return errors

def find_imports_in_file(filepath):
    imports = set()
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=filepath)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    imports.add(n.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    imports.add(node.module.split('.')[0])
    except Exception as e:
        print(f"STATIC_PARSE_ERROR in {filepath}: {e}", file=sys.stderr)
        print("DEPENDENCY_PREFLIGHT_FAILED", file=sys.stderr)
        sys.exit(1)
    return imports

def run_preflight(base_dir):
    sys.path.insert(0, base_dir)
    target_dirs = ['runtime', 'cli']
    local_packages = set(['runtime', 'cli', 'contracts', 'adapters', 'audit', 'packaging', 'scripts', 'tests'])
    stdlib = get_stdlib_module_names()
    
    requirements = parse_requirements(base_dir)
    import_mapping = CANONICAL_IMPORT_TO_PACKAGE
    
    errors = []
    warnings = []
    
    all_imports = set()
    # 1. AST Analysis
    for d in target_dirs:
        dir_path = os.path.join(base_dir, d)
        if not os.path.exists(dir_path):
            continue
        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    all_imports.update(find_imports_in_file(filepath))
                    
    # Validate imports against requirements
    used_requirements = set()
    for imp in all_imports:
        if imp in stdlib or imp in local_packages:
            continue
        # Map import name to package name explicitly
        if imp not in import_mapping:
            errors.append(f"DEPENDENCY_MAPPING_MISSING: Import '{imp}' has no canonical package mapping")
            continue
        pkg_name = import_mapping[imp]
        normalized_package = normalize_package_name(pkg_name)
        used_requirements.add(normalized_package)
        if normalized_package not in requirements:
            errors.append(f"DEPENDENCY_PREFLIGHT_FAILED: Import '{imp}' requires package '{pkg_name}' which is NOT in requirements.txt.")
            
    # Check for unused declared dependencies (warning only)
    for req in requirements:
        if req not in used_requirements:
            warnings.append(f"DEPENDENCY_UNUSED: Requirement '{req}' in requirements.txt is not explicitly imported.")

    # 2. The declared distributions must be present and compatible in the
    # current interpreter.  install.sh runs this under the fresh installer
    # venv, so host-level packages cannot be treated as installation evidence.
    errors.extend(validate_installed_requirements(requirements))

    # 3. Runtime Import Test
    for d in target_dirs:
        dir_path = os.path.join(base_dir, d)
        if not os.path.exists(dir_path):
            continue
            
        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.endswith('.py'):
                    rel_path = os.path.relpath(os.path.join(root, file), base_dir)
                    mod_path = rel_path.replace(os.sep, '.')[:-3]
                    if mod_path.endswith('.__init__'):
                        mod_path = mod_path[:-9]
                        
                    try:
                        importlib.import_module(mod_path)
                    except ModuleNotFoundError as e:
                        errors.append(f"DEPENDENCY_MISSING: {mod_path} -> {e}")
                    except ImportError as e:
                        errors.append(f"IMPORT_ERROR: {mod_path} -> {e}")
                    except Exception as e:
                        errors.append(f"IMPORT_RUNTIME_SIDE_EFFECT: {mod_path} -> {e} ({type(e).__name__})")

    # Output warnings (non-fatal)
    if warnings:
        for w in warnings:
            print(f"DEPENDENCY_PREFLIGHT_WARNING: {w}", file=sys.stderr)

    # Output errors (fatal)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        print("DEPENDENCY_PREFLIGHT_FAILED", file=sys.stderr)
        sys.exit(1)
        
    print("DEPENDENCY_PREFLIGHT_PASS")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        project_root = os.path.abspath(sys.argv[1])
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(script_dir, '..'))
    run_preflight(project_root)
