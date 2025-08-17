#!/usr/bin/env python3
"""
PostToolUse hook for PROJECT_INDEX.dsl updates.
Simplified: regenerate DSL on each edit to ensure consistency.
"""

import json
import sys
import os
import subprocess
from pathlib import Path


def run_reindex(project_root: str) -> bool:
    """Run project_index.py to regenerate PROJECT_INDEX.dsl."""
    try:
        # Prefer local project_index.py
        project_index_path = None
        check_dir = Path(project_root)
        while check_dir != check_dir.parent:
            candidate = check_dir / 'project_index.py'
            if candidate.exists():
                project_index_path = str(candidate)
                break
            check_dir = check_dir.parent
        
        if project_index_path is None:
            system_index = Path.home() / '.claude-code-project-index' / 'scripts' / 'project_index.py'
            if system_index.exists():
                project_index_path = str(system_index)
        
        if project_index_path is None:
            return False
        
        result = subprocess.run(
            [sys.executable, project_index_path],
            cwd=project_root,
            capture_output=True,
            text=True
        )
        # Optional: echo stderr for debugging in Claude console
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"Hook reindex error: {e}", file=sys.stderr)
        return False


def main():
    try:
        # Read hook input
        input_data = json.load(sys.stdin)
        tool_name = input_data.get('tool_name', '')
        if tool_name not in ['Write', 'Edit', 'MultiEdit']:
            return

        # Find project root by looking for PROJECT_INDEX.dsl
        current_dir = Path(os.getcwd())
        project_root = current_dir
        check_dir = current_dir
        dsl_path = None
        while check_dir != check_dir.parent:
            potential = check_dir / 'PROJECT_INDEX.dsl'
            if potential.exists():
                dsl_path = potential
                project_root = check_dir
                break
            check_dir = check_dir.parent

        if dsl_path is None:
            return

        # Regenerate DSL
        run_reindex(str(project_root))
    except Exception as e:
        print(f"Hook error: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()
