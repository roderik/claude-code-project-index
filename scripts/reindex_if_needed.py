#!/usr/bin/env python3
"""
Stop hook for PROJECT_INDEX.json full reindex
This is the DEPLOYMENT VERSION to be placed in ~/.claude/scripts/

Key differences from reindex_if_needed.py:
- Self-contained without external dependencies
- Simplified checks (no external change detection)
- Can create minimal index if project_index.py not found
- Designed to work from any location
"""

import json
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime


def check_index_features(index_path):
    """Check if index has all required features."""
    try:
        with open(index_path, 'r') as f:
            index = json.load(f)
        
        # Check for required features
        if 'project_structure' not in index:
            return True, "Missing project structure tree"
        
        if index.get('tree_needs_refresh', False):
            return True, "Directory tree needs refresh"
        
        return False, None
    except:
        return True, "Cannot read index file"


def check_index_staleness(index_path, threshold_hours=24):
    """Check if index is older than threshold."""
    try:
        # Check file modification time
        index_mtime = os.path.getmtime(index_path)
        current_time = datetime.now().timestamp()
        age_hours = (current_time - index_mtime) / 3600
        
        return age_hours > threshold_hours
    except:
        return True  # If can't check, assume stale


def check_missing_documentation(index_path, project_root):
    """Check if important documentation files are missing from index."""
    try:
        with open(index_path, 'r') as f:
            index = json.load(f)
        
        doc_map = index.get('documentation_map', {})
        
        # Check for common documentation files
        important_docs = ['README.md', 'ARCHITECTURE.md', 'API.md', 'CONTRIBUTING.md']
        
        for doc in important_docs:
            doc_path = Path(project_root) / doc
            if doc_path.exists() and doc not in doc_map:
                return True
        
        return False
    except:
        return True


def check_structural_changes(index_path, project_root):
    """Check if directory structure has significantly changed."""
    try:
        with open(index_path, 'r') as f:
            index = json.load(f)
        
        # Count current directories
        dir_count = 0
        for item in Path(project_root).rglob('*'):
            if item.is_dir() and not any(part.startswith('.') for part in item.parts):
                dir_count += 1
        
        # Compare with indexed count
        indexed_dirs = index.get('stats', {}).get('total_directories', 0)
        
        # If directory count changed by more than 20%, reindex
        if indexed_dirs > 0:
            change_ratio = abs(dir_count - indexed_dirs) / indexed_dirs
            return change_ratio > 0.2
        
        return False
    except:
        return False


def count_hook_updates(index_path):
    """Count how many files were updated by hooks vs full index."""
    try:
        with open(index_path, 'r') as f:
            index = json.load(f)
        
        hook_count = 0
        total_count = 0
        
        for file_path, info in index.get('files', {}).items():
            total_count += 1
            if info.get('updated_by_hook', False):
                hook_count += 1
        
        return hook_count, total_count
    except:
        return 0, 0


def run_reindex(project_root):
    """Run the project_index.py script to perform full reindex."""
    try:
        # First try to find project_index.py in the project
        project_index_path = None
        check_dir = Path(project_root)
        while check_dir != check_dir.parent:
            potential_path = check_dir / 'project_index.py'
            if potential_path.exists():
                project_index_path = str(potential_path)
                break
            check_dir = check_dir.parent
        
        if project_index_path:
            # Run the local project_index.py
            result = subprocess.run(
                [sys.executable, project_index_path],
                cwd=project_root,
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        
        # Try the system-installed version
        system_index_path = Path.home() / '.claude-code-project-index' / 'scripts' / 'project_index.py'
        if system_index_path.exists():
            result = subprocess.run(
                [sys.executable, str(system_index_path)],
                cwd=project_root,
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        else:
            # Try to create a minimal index
            index = {
                'indexed_at': datetime.now().isoformat(),
                'root': '.',
                'project_structure': {
                    'type': 'tree',
                    'root': '.',
                    'tree': ['.']
                },
                'documentation_map': {},
                'directory_purposes': {},
                'stats': {
                    'total_files': 0,
                    'total_directories': 0,
                    'fully_parsed': {},
                    'listed_only': {},
                    'markdown_files': 0
                },
                'files': {}
            }
            
            index_path = Path(project_root) / 'PROJECT_INDEX.json'
            with open(index_path, 'w') as f:
                json.dump(index, f, indent=2)
            
            return True
            
    except Exception as e:
        print(f"Error running reindex: {e}", file=sys.stderr)
        return False


def main():
    """Main hook entry point."""
    # Check if we're in a git repository or have a PROJECT_INDEX.json
    current_dir = Path.cwd()
    index_path = None
    project_root = current_dir
    
    # Search up the directory tree
    check_dir = current_dir
    while check_dir != check_dir.parent:
        # Check for PROJECT_INDEX.json
        potential_index = check_dir / 'PROJECT_INDEX.json'
        if potential_index.exists():
            index_path = potential_index
            project_root = check_dir
            break
        
        # Check for .git directory
        if (check_dir / '.git').is_dir():
            project_root = check_dir
            index_path = check_dir / 'PROJECT_INDEX.json'
            break
            
        check_dir = check_dir.parent
    
    if not index_path or not index_path.exists():
        # No index exists - skip silently (manual creation via /index)
        return
    
    # Check if index needs refresh
    needs_reindex = False
    reason = ""
    
    # 1. Check for missing features
    missing_features, feature_reason = check_index_features(index_path)
    if missing_features:
        needs_reindex = True
        reason = feature_reason
    
    # 2. Check staleness (once a week)
    elif check_index_staleness(index_path, threshold_hours=168):
        needs_reindex = True
        reason = "Index is over a week old"
    
    # 3. Check for missing documentation
    elif check_missing_documentation(index_path, project_root):
        needs_reindex = True
        reason = "New documentation files detected"
    
    # 4. Check for structural changes
    elif check_structural_changes(index_path, project_root):
        needs_reindex = True
        reason = "Directory structure changed significantly"
    
    # 5. Check hook update ratio
    else:
        hook_count, total_count = count_hook_updates(index_path)
        if total_count > 20 and hook_count / total_count > 0.5:
            needs_reindex = True
            reason = f"Many incremental updates ({hook_count}/{total_count})"
    
    # Perform reindex if needed
    if needs_reindex:
        if run_reindex(project_root):
            output = {"suppressOutput": False}
            print(f"♻️  Reindexed project: {reason}")
            sys.stdout.write(json.dumps(output) + '\n')
        else:
            print(f"Failed to reindex: {reason}", file=sys.stderr)


if __name__ == '__main__':
    main()