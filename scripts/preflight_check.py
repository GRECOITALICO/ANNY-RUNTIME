#!/usr/bin/env python3
import os
import sys
import importlib
import ast
import json

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

def parse_requirements(base_dir):
    req_file = os.path.join(base_dir, 'requirements.txt')
    reqs = set()
    if os.path.exists(req_file):
        with open(req_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    import re
                    match = re.match(r'^([a-zA-Z0-9_\-]+)(?:\[[a-zA-Z0-9_\-,]+\])?(?:[=><~]+.*)?$', line)
                    if not match:
                        print(f"REQUIREMENT_PARSE_UNKNOWN: {line}", file=sys.stderr)
                        sys.exit(1)
                    pkg = match.group(1).strip()
                    reqs.add(pkg.lower())
    return reqs

def load_inventory(base_dir):
    inv_file = os.path.join(base_dir, 'DEPENDENCY-INVENTORY.json')
    mapping = {}
    if os.path.exists(inv_file):
        with open(inv_file, 'r') as f:
            data = json.load(f)
            for item in data:
                mapping[item['import']] = item['python_package']
    return mapping

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
    inventory = load_inventory(base_dir)
    
    errors = []
    
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
        if imp not in inventory:
            errors.append(f"DEPENDENCY_MAPPING_MISSING: Import '{imp}' is not in DEPENDENCY-INVENTORY.json")
            continue
        pkg_name = inventory[imp]
        used_requirements.add(pkg_name.lower())
        if pkg_name.lower() not in requirements:
            errors.append(f"DEPENDENCY_PREFLIGHT_FAILED: Import '{imp}' requires package '{pkg_name}' which is NOT in requirements.txt.")
            
    # Validate requirement usage
    for req in requirements:
        if req not in used_requirements:
            errors.append(f"DEPENDENCY_UNUSED: Requirement '{req}' in requirements.txt is not explicitly imported.")
            
    # 2. Runtime Import Test
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
                        
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        sys.exit(1)
        
    print("DEPENDENCY_PREFLIGHT_PASS")

if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..'))
    run_preflight(project_root)
