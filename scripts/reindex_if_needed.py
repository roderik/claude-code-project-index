#!/usr/bin/env python3
"""
Stop hook for PROJECT_INDEX.dsl full reindex
This is the DEPLOYMENT VERSION to be placed in ~/.claude/scripts/

Key differences from reindex_if_needed.py:
- Self-contained without external dependencies
- Simplified checks (no external change detection)
- Can create minimal index if project_index.py not found
- Designed to work from any location
"""

import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime
from index_utils import git_root, git_ls_unignored_files


def check_index_features(index_path: Path):
    """Check DSL index has essential sections (header, meta, tree)."""
    try:
        text = index_path.read_text(encoding='utf-8', errors='ignore').splitlines()
        if not text:
            return True, "Empty DSL index"
        has_header = any(line.startswith('! PROJECT_INDEX DSL') for line in text[:3])
        has_meta = any(line.startswith('P ') for line in text[:50])
        has_tree = any(line.startswith('T ') for line in text)
        if not has_header or not has_meta or not has_tree:
            return True, "Missing required DSL sections"
        return False, None
    except Exception:
        return True, "Cannot read DSL index"


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


def check_missing_documentation(index_path: Path, project_root: Path):
    """Check if important docs exist but lack MD lines in DSL."""
    try:
        text = index_path.read_text(encoding='utf-8', errors='ignore').splitlines()
        md_lines = {line.split(' ', 1)[1].split(' ', 1)[0] for line in text if line.startswith('MD ')}
        important_docs = ['README.md', 'ARCHITECTURE.md', 'API.md', 'CONTRIBUTING.md']
        for doc in important_docs:
            if (project_root / doc).exists() and doc not in md_lines:
                return True
        return False
    except Exception:
        return True


def check_structural_changes(index_path: Path, project_root: Path):
    """Check if directory count changed >20% vs P dirs meta in DSL."""
    try:
        text = index_path.read_text(encoding='utf-8', errors='ignore')
        # Parse dirs=N from P line
        dirs_meta = 0
        for line in text.splitlines():
            if line.startswith('P '):
                m = __import__('re').search(r'\bdirs=(\d+)', line)
                if m:
                    dirs_meta = int(m.group(1))
                break
        # Count current directories using Git non-ignored files when available
        repo = git_root(project_root)
        if repo is not None:
            files = git_ls_unignored_files(repo, project_root) or []
            dirs = set()
            for rel in files:
                p = Path(rel).parent
                while True:
                    dirs.add(p)
                    if str(p) == '.' or p == p.parent:
                        break
                    p = p.parent
            dir_count = len(dirs)
        else:
            dir_count = sum(1 for p in project_root.rglob('*') if p.is_dir() and not any(part.startswith('.') for part in p.parts))
        if dirs_meta > 0:
            change_ratio = abs(dir_count - dirs_meta) / dirs_meta
            return change_ratio > 0.2
        return False
    except Exception:
        return False


def count_hook_updates(index_path: Path):
    """DSL has no per-file hook markers; return zeros."""
    return 0, 0


def run_reindex(project_root):
    """Run the project_index.py script to perform full reindex (DSL)."""
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
            # Create minimal DSL header if generator missing
            dsl = [
                '! PROJECT_INDEX DSL v0.1.0',
                f"P root=. indexed_at={datetime.now().isoformat()} files=0 dirs=0 md=0",
                'T .',
            ]
            (Path(project_root) / 'PROJECT_INDEX.dsl').write_text('\n'.join(dsl) + '\n', encoding='utf-8')
            return True
            
    except Exception as e:
        print(f"Error running reindex: {e}", file=sys.stderr)
        return False


def main():
    """Main hook entry point."""
    # Check if we're in a git repository or have a PROJECT_INDEX.dsl
    current_dir = Path.cwd()
    index_path = None
    project_root = current_dir
    
    # Search up the directory tree
    check_dir = current_dir
    while check_dir != check_dir.parent:
        # Check for PROJECT_INDEX.dsl
        potential_index = check_dir / 'PROJECT_INDEX.dsl'
        if potential_index.exists():
            index_path = potential_index
            project_root = check_dir
            break
        
        # Check for .git directory
        if (check_dir / '.git').is_dir():
            project_root = check_dir
            index_path = check_dir / 'PROJECT_INDEX.dsl'
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
    
    # No hook update ratio for DSL
    
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
