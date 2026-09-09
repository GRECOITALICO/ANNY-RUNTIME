#!/usr/bin/env python3
import os
import sys
import importlib

def run_preflight(base_dir):
    sys.path.insert(0, base_dir)
    target_dirs = ['runtime', 'cli']
    
    missing_deps = []
    
    for d in target_dirs:
        dir_path = os.path.join(base_dir, d)
        if not os.path.exists(dir_path):
            continue
            
        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.endswith('.py'):
                    # Convert file path to module path
                    rel_path = os.path.relpath(os.path.join(root, file), base_dir)
                    mod_path = rel_path.replace(os.sep, '.')[:-3]
                    if mod_path.endswith('.__init__'):
                        mod_path = mod_path[:-9]
                        
                    try:
                        importlib.import_module(mod_path)
                    except (ModuleNotFoundError, ImportError) as e:
                        missing_deps.append((mod_path, str(e)))
                        
    if missing_deps:
        print("DEPENDENCY_PREFLIGHT_FAILED", file=sys.stderr)
        print("The following modules failed to import due to missing dependencies:", file=sys.stderr)
        for mod, err in missing_deps:
            print(f" - {mod}: {err}", file=sys.stderr)
        sys.exit(1)
        
    print("DEPENDENCY_PREFLIGHT_PASS")

if __name__ == '__main__':
    # Try to resolve base directory relative to the script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..'))
    run_preflight(project_root)
