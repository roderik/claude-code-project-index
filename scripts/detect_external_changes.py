#!/usr/bin/env python3
"""
Detect files that changed outside of Claude's control
Used by Stop hook to trigger incremental updates (DSL index)
"""

import os
from pathlib import Path
from datetime import datetime
from index_utils import git_root, git_ls_unignored_files


def get_file_mtime(file_path):
    """Get file modification time as timestamp."""
    try:
        return os.path.getmtime(file_path)
    except:
        return 0


def detect_external_changes(index_path, project_root):
    """
    Detect files that were modified externally since last index.
    Returns list of changed file paths.
    """
    try:
        # Get index timestamp
        index_time = os.path.getmtime(index_path)
        changed_files = []

        # Parse DSL to get list of indexed files (F lines)
        indexed = set()
        try:
            for line in Path(index_path).read_text(encoding='utf-8', errors='ignore').splitlines():
                if line.startswith('F '):
                    # Format: F path lang=... parsed=...
                    parts = line.split()
                    if len(parts) >= 2:
                        indexed.add(parts[1])
        except Exception:
            pass

        root_path = Path(project_root)
        code_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.rs', '.java', '.rb', '.php', '.sh', '.bash'}

        # Check indexed files for changes or removal
        for rel_path in list(indexed):
            file_path = root_path / rel_path
            if not file_path.exists():
                changed_files.append(rel_path)
                continue
            if get_file_mtime(file_path) > index_time:
                changed_files.append(rel_path)

        # Detect new files not in index (prefer Git-aware listing)
        repo = git_root(root_path)
        scope_files = git_ls_unignored_files(repo, root_path) if repo is not None else None
        if scope_files is not None:
            for rel in scope_files:
                if Path(rel).suffix not in code_extensions:
                    continue
                if str(rel) not in indexed and get_file_mtime(root_path / rel) > index_time:
                    changed_files.append(str(rel))
        else:
            for file_path in root_path.rglob('*'):
                if file_path.is_file() and file_path.suffix in code_extensions:
                    rel_path = str(file_path.relative_to(root_path))
                    if any(part in {'.git', '__pycache__', '.venv', 'venv'} for part in file_path.parts):
                        continue
                    if rel_path not in indexed and get_file_mtime(file_path) > index_time:
                        changed_files.append(rel_path)

        return changed_files
    except Exception:
        return []


def check_git_changes(project_root):
    """
    Optional: Check git for uncommitted changes as additional signal.
    Returns True if working directory has changes.
    """
    try:
        import subprocess
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        return bool(result.stdout.strip())
    except:
        return False


if __name__ == '__main__':
    # Test mode
    import sys
    if len(sys.argv) > 2:
        index_path = sys.argv[1]
        project_root = sys.argv[2]
        
        changes = detect_external_changes(index_path, project_root)
        if changes:
            print(f"Found {len(changes)} external changes:")
            for path in changes[:10]:  # Show first 10
                print(f"  - {path}")
        else:
            print("No external changes detected")
