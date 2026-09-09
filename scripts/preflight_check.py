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
                    pkg = line.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0].split('<')[0].split('>')[0].strip()
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
    except Exception:
        pass
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
    for imp in all_imports:
        if imp in stdlib or imp in local_packages:
            continue
        # Map import name to package name if in inventory
        pkg_name = inventory.get(imp, imp)
        if pkg_name.lower() not in requirements:
            errors.append(f"DEPENDENCY_PREFLIGHT_FAILED: Import '{imp}' requires package '{pkg_name}' which is NOT in requirements.txt.")
            
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
