#!/usr/bin/env python3
"""
Project Index for Claude Code
Provides spatial-architectural awareness to prevent code duplication and misplacement.

Features:
- Directory tree structure visualization
- Markdown documentation mapping with section headers
- Directory purpose inference
- Full function and class signatures with type annotations
- Multi-language support (parsed vs listed)

Usage: python project_index.py
Output: PROJECT_INDEX.dsl
"""

__version__ = "0.1.0"

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Import shared utilities
from index_utils import (
    IGNORE_DIRS, PARSEABLE_LANGUAGES, CODE_EXTENSIONS, MARKDOWN_EXTENSIONS,
    DIRECTORY_PURPOSES, extract_python_signatures, extract_javascript_signatures,
    extract_shell_signatures, extract_markdown_structure, infer_file_purpose, 
    infer_directory_purpose, get_language_name, should_index_file,
    git_root, git_ls_unignored_files
)
from index_utils import extract_signatures_auto

# Limits to keep it fast and simple
MAX_FILES = 10000
MAX_TREE_DEPTH = 5


def generate_tree_structure(root_path: Path, max_depth: int = MAX_TREE_DEPTH, allowed_dirs: Optional[set] = None) -> List[str]:
    """Generate a compact ASCII tree representation.
    If allowed_dirs is provided, only include directories that are in this set.
    """
    tree_lines = []
    
    def should_include_dir(path: Path) -> bool:
        """Check if directory should be included in tree."""
        if not path.is_dir() or path.name.startswith('.'):
            return False
        if allowed_dirs is not None:
            try:
                rel = path.relative_to(root_path)
            except Exception:
                return False
            return rel in allowed_dirs or str(rel) == '.'
        return path.name not in IGNORE_DIRS

    def add_tree_level(path: Path, prefix: str = "", depth: int = 0):
        """Recursively build tree structure."""
        if depth > max_depth:
            if any(should_include_dir(p) for p in path.iterdir() if p.is_dir()):
                tree_lines.append(prefix + "└── ...")
            return

        try:
            items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        except PermissionError:
            return

        # Filter items
        dirs = [item for item in items if should_include_dir(item)]

        # Important files to show in tree
        important_files = [
            item for item in items
            if item.is_file() and (
                item.name in ['README.md', 'CLAUDE.md', 'package.json', 'requirements.txt',
                             'Cargo.toml', 'go.mod', 'pom.xml', 'build.gradle',
                             'setup.py', 'pyproject.toml', 'Makefile', 'turbo.json', 'tsconfig.json', 'babel.config.js', 'vite.config.js']
            )
        ]

        all_items = dirs + important_files

        for i, item in enumerate(all_items):
            is_last = i == len(all_items) - 1
            current_prefix = "└── " if is_last else "├── "

            name = item.name
            if item.is_dir():
                name += "/"
                # Add file count for directories
                try:
                    file_count = sum(1 for f in item.rglob('*') if f.is_file() and f.suffix in CODE_EXTENSIONS)
                    if file_count > 0:
                        name += f" ({file_count} files)"
                except:
                    pass

            tree_lines.append(prefix + current_prefix + name)

            if item.is_dir():
                next_prefix = prefix + ("    " if is_last else "│   ")
                add_tree_level(item, next_prefix, depth + 1)

    # Start with root
    tree_lines.append(".")
    add_tree_level(root_path, "")
    return tree_lines


# These functions are now imported from index_utils


def build_index(root_dir: str) -> Tuple[Dict, int]:
    """Build the enhanced index with architectural awareness."""
    root = Path(root_dir)
    index = {
        'indexed_at': datetime.now().isoformat(),
        'root': str(root),
        'project_structure': {
            'type': 'tree',
            'root': '.',
            'tree': []
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
        'files': {},
        'dependency_graph': {}
    }

    # Generate directory tree
    print("📊 Building directory tree...")
    # Prepare Git-aware file list
    repo_root = git_root(root)
    allowed_files_rel: List[Path] = []
    if repo_root is not None:
        files = git_ls_unignored_files(repo_root, root)
        if files is not None:
            allowed_files_rel = [Path(p) for p in files]
    
    # Build allowed directories set if using Git file list
    allowed_dirs = None
    if allowed_files_rel:
        allowed_dirs = set()
        for rel_file in allowed_files_rel:
            parent = rel_file.parent
            while True:
                allowed_dirs.add(parent)
                if str(parent) == '.' or parent == parent.parent:
                    break
                parent = parent.parent
    
    index['project_structure']['tree'] = generate_tree_structure(root, allowed_dirs=allowed_dirs)

    file_count = 0
    dir_count = 0
    skipped_count = 0
    directory_files = {}  # Track files per directory

    # Walk the directory tree
    print("🔍 Indexing files...")
    if allowed_files_rel:
        # Git-aware iteration: only non-ignored files under root
        iterable = [(root / rel) for rel in sorted(allowed_files_rel)]
    else:
        iterable = list(root.rglob('*'))
    
    for file_path in iterable:
        if file_count >= MAX_FILES:
            print(f"⚠️  Stopping at {MAX_FILES} files (project too large)")
            break
        
        if file_path.is_dir():
            # In Git-aware mode, only include allowed dirs
            if allowed_dirs is None:
                if not any(part in IGNORE_DIRS for part in file_path.parts):
                    dir_count += 1
                    directory_files[file_path] = []
            else:
                try:
                    rel_dir = file_path.relative_to(root)
                except Exception:
                    continue
                if rel_dir in allowed_dirs:
                    dir_count += 1
                    directory_files[file_path] = []
            continue
        
        if not file_path.is_file():
            continue
        
        if not should_index_file(file_path, root):
            skipped_count += 1
            continue

        # Track files in their directories
        parent_dir = file_path.parent
        if parent_dir not in directory_files:
            directory_files[parent_dir] = []
        directory_files[parent_dir].append(file_path.name)

        # Get relative path and language
        rel_path = file_path.relative_to(root)

        # Handle markdown files specially
        if file_path.suffix in MARKDOWN_EXTENSIONS:
            doc_structure = extract_markdown_structure(file_path)
            if doc_structure['sections'] or doc_structure['architecture_hints']:
                index['documentation_map'][str(rel_path)] = doc_structure
                index['stats']['markdown_files'] += 1
            continue

        # Handle code files
        language = get_language_name(file_path.suffix)

        # Base info for all files
        file_info = {
            'language': language,
            'parsed': False
        }

        # Add file purpose if we can infer it
        file_purpose = infer_file_purpose(file_path)
        if file_purpose:
            file_info['purpose'] = file_purpose

        # Try ast-grep / rg(solidity) / built-in
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            extracted = extract_signatures_auto(file_path, content)
            if extracted.get('functions') or extracted.get('classes'):
                file_info.update(extracted)
                file_info['parsed'] = True
                # Update stats
                lang_key = PARSEABLE_LANGUAGES.get(file_path.suffix, language)
                index['stats']['fully_parsed'][lang_key] = \
                    index['stats']['fully_parsed'].get(lang_key, 0) + 1
            else:
                index['stats']['listed_only'][language] = \
                    index['stats']['listed_only'].get(language, 0) + 1
        except Exception:
            index['stats']['listed_only'][language] = \
                index['stats']['listed_only'].get(language, 0) + 1

        # Add to index
        index['files'][str(rel_path)] = file_info
        file_count += 1

        # Progress indicator every 100 files
        if file_count % 100 == 0:
            print(f"  Indexed {file_count} files...")

    # Infer directory purposes
    print("🏗️  Analyzing directory purposes...")
    for dir_path, files in directory_files.items():
        if files:  # Only process directories with files
            purpose = infer_directory_purpose(dir_path, files)
            if purpose:
                rel_dir = str(dir_path.relative_to(root))
                if rel_dir != '.':
                    index['directory_purposes'][rel_dir] = purpose

    index['stats']['total_files'] = file_count
    # In Git-aware mode, directories are not iterated explicitly; compute from parent map
    if allowed_files_rel:
        dir_count = len(directory_files)
    index['stats']['total_directories'] = dir_count

    # Build dependency graph
    print("🔗 Building dependency graph...")
    dependency_graph = {}

    for file_path, file_info in index['files'].items():
        if file_info.get('imports'):
            # Normalize imports to resolve relative paths
            file_dir = Path(file_path).parent
            dependencies = []

            for imp in file_info['imports']:
                # Handle relative imports
                if imp.startswith('.'):
                    # Resolve relative import
                    if imp.startswith('./'):
                        # Same directory
                        resolved = str(file_dir / imp[2:])
                    elif imp.startswith('../'):
                        # Parent directory
                        parts = imp.split('/')
                        up_levels = len([p for p in parts if p == '..'])
                        target_dir = file_dir
                        for _ in range(up_levels):
                            target_dir = target_dir.parent
                        remaining = '/'.join(p for p in parts if p != '..')
                        resolved = str(target_dir / remaining) if remaining else str(target_dir)
                    else:
                        # Module import like from . import X
                        resolved = str(file_dir)

                    # Try to find actual file
                    for ext in ['.py', '.js', '.ts', '.jsx', '.tsx', '']:
                        potential_file = resolved + ext
                        if potential_file in index['files'] or potential_file.replace('\\', '/') in index['files']:
                            dependencies.append(potential_file.replace('\\', '/'))
                            break
                else:
                    # External dependency or absolute import
                    dependencies.append(imp)

            if dependencies:
                dependency_graph[file_path] = dependencies

    # Only add if not empty
    if dependency_graph:
        index['dependency_graph'] = dependency_graph

    # Build bidirectional call graph
    print("📞 Building call graph...")
    call_graph = {}
    called_by_graph = {}

    # Process all files to build call relationships
    for file_path, file_info in index['files'].items():
        if not isinstance(file_info, dict):
            continue

        # Process functions in this file
        if 'functions' in file_info:
            for func_name, func_data in file_info['functions'].items():
                if isinstance(func_data, dict) and 'calls' in func_data:
                    # Track what this function calls
                    full_func_name = f"{file_path}:{func_name}"
                    call_graph[full_func_name] = func_data['calls']

                    # Build reverse index (called_by)
                    for called in func_data['calls']:
                        if called not in called_by_graph:
                            called_by_graph[called] = []
                        called_by_graph[called].append(func_name)

        # Process methods in classes
        if 'classes' in file_info:
            for class_name, class_data in file_info['classes'].items():
                if isinstance(class_data, dict) and 'methods' in class_data:
                    for method_name, method_data in class_data['methods'].items():
                        if isinstance(method_data, dict) and 'calls' in method_data:
                            # Track what this method calls
                            full_method_name = f"{file_path}:{class_name}.{method_name}"
                            call_graph[full_method_name] = method_data['calls']

                            # Build reverse index
                            for called in method_data['calls']:
                                if called not in called_by_graph:
                                    called_by_graph[called] = []
                                called_by_graph[called].append(f"{class_name}.{method_name}")

    # Add called_by information back to functions
    for file_path, file_info in index['files'].items():
        if not isinstance(file_info, dict):
            continue

        if 'functions' in file_info:
            for func_name, func_data in file_info['functions'].items():
                if func_name in called_by_graph:
                    if isinstance(func_data, dict):
                        func_data['called_by'] = called_by_graph[func_name]
                    else:
                        # Convert string signature to dict
                        index['files'][file_path]['functions'][func_name] = {
                            'signature': func_data,
                            'called_by': called_by_graph[func_name]
                        }

        if 'classes' in file_info:
            for class_name, class_data in file_info['classes'].items():
                if isinstance(class_data, dict) and 'methods' in class_data:
                    for method_name, method_data in class_data['methods'].items():
                        full_name = f"{class_name}.{method_name}"
                        if method_name in called_by_graph or full_name in called_by_graph:
                            callers = called_by_graph.get(method_name, []) + called_by_graph.get(full_name, [])
                            if callers:
                                if isinstance(method_data, dict):
                                    method_data['called_by'] = list(set(callers))
                                else:
                                    # Convert string signature to dict
                                    class_data['methods'][method_name] = {
                                        'signature': method_data,
                                        'called_by': list(set(callers))
                                    }

    # Add staleness check
    week_old = datetime.now().timestamp() - 7 * 24 * 60 * 60
    index['staleness_check'] = week_old

    return index, skipped_count


# infer_file_purpose is now imported from index_utils


def _dsl_escape(value: str) -> str:
    """Escape newlines and tabs for DSL payloads."""
    if value is None:
        return ''
    return str(value).replace('\n', ' ').replace('\t', ' ')


def _render_file_block(path: str, info: Dict) -> List[str]:
    """Render a single file entry to DSL lines."""
    lines: List[str] = []
    lang = info.get('language', 'unknown')
    parsed = '1' if info.get('parsed') else '0'
    purpose = info.get('purpose')
    base = f"F {path} lang={lang} parsed={parsed}"
    if purpose:
        base += f" purpose={_dsl_escape(purpose)}"
    lines.append(base)

    # Imports
    imports = info.get('imports') or []
    if imports:
        lines.append(f"I {path}= " + ','.join(sorted(set(imports))))

    # Functions
    funcs = info.get('functions') or {}
    for fname, fdata in funcs.items():
        if isinstance(fdata, dict):
            sig = fdata.get('signature', '')
            calls = fdata.get('calls') or []
            called_by = fdata.get('called_by') or []
        else:
            sig = fdata
            calls, called_by = [], []
        line = f"FN {path}::{fname} {_dsl_escape(sig)}"
        if calls:
            line += " C=" + ','.join(sorted(set(calls)))
        if called_by:
            line += " B=" + ','.join(sorted(set(called_by)))
        lines.append(line)

    # Classes and methods
    classes = info.get('classes') or {}
    for cname, cdata in classes.items():
        if isinstance(cdata, dict):
            inherits = cdata.get('inherits') or cdata.get('extends')
            ctype = cdata.get('type')
            header = f"CL {path}::{cname}"
            if inherits:
                header += " extends=" + ','.join(inherits if isinstance(inherits, list) else [inherits])
            if ctype:
                header += f" type={ctype}"
            lines.append(header)
            methods = cdata.get('methods') or {}
            for mname, mdata in methods.items():
                if isinstance(mdata, dict):
                    msig = mdata.get('signature', '')
                    mcalls = mdata.get('calls') or []
                    mcalled_by = mdata.get('called_by') or []
                else:
                    msig = mdata
                    mcalls, mcalled_by = [], []
                mline = f"M {path}::{cname}.{mname} {_dsl_escape(msig)}"
                if mcalls:
                    mline += " C=" + ','.join(sorted(set(mcalls)))
                if mcalled_by:
                    mline += " B=" + ','.join(sorted(set(mcalled_by)))
                lines.append(mline)
        else:
            lines.append(f"CL {path}::{cname}")
    return lines


def render_dsl(index: Dict) -> str:
    """Render the entire index into a compact, line-oriented DSL."""
    lines: List[str] = []
    stats = index.get('stats', {})
    lines.append(f"! PROJECT_INDEX DSL v{__version__}")
    lines.append(
        "P root=" + _dsl_escape(index.get('root', '.')) +
        f" indexed_at={_dsl_escape(index.get('indexed_at',''))} files={stats.get('total_files',0)}" +
        f" dirs={stats.get('total_directories',0)} md={stats.get('markdown_files',0)}"
    )

    # Directory tree
    for t in index.get('project_structure', {}).get('tree', [])[:1000]:
        lines.append("T " + _dsl_escape(t))

    # Directory purposes
    for d, purpose in sorted(index.get('directory_purposes', {}).items()):
        lines.append(f"D {d}/ {_dsl_escape(purpose)}")

    # Documentation insights (lightweight)
    for doc, info in sorted(index.get('documentation_map', {}).items()):
        sections = len(info.get('sections', [])) if isinstance(info, dict) else 0
        if sections:
            lines.append(f"MD {doc} sections={sections}")

    # Files
    for path, info in sorted(index.get('files', {}).items()):
        if isinstance(info, dict):
            lines.extend(_render_file_block(path, info))
        else:
            lines.append(f"F {path} lang=unknown parsed=0")

    # Dependencies (simple)
    for src, deps in sorted(index.get('dependency_graph', {}).items()):
        if deps:
            lines.append(f"DEP {src}= " + ','.join(sorted(set(deps))))

    return '\n'.join(lines) + '\n'


def print_summary(index: Dict, skipped_count: int):
    """Print a helpful summary of what was indexed."""
    stats = index['stats']

    # Add warning if no files were found
    if stats['total_files'] == 0:
        print("\n⚠️  WARNING: No files were indexed!")
        print("   This might mean:")
        print("   • You're in the wrong directory")
        print("   • All files are being ignored (check .gitignore)")
        print("   • The project has no supported file types")
        print(f"\n   Current directory: {os.getcwd()}")
        print("   Try running from your project root directory.")
        return

    print(f"\n📊 Project Analysis Complete:")
    print(f"   📁 {stats['total_directories']} directories indexed")
    print(f"   📄 {stats['total_files']} code files found")
    print(f"   📝 {stats['markdown_files']} documentation files analyzed")

    # Show fully parsed languages
    if stats['fully_parsed']:
        print("\n✅ Languages with full parsing:")
        for lang, count in sorted(stats['fully_parsed'].items()):
            print(f"   • {count} {lang.capitalize()} files (with signatures)")

    # Show listed-only languages
    if stats['listed_only']:
        print("\n📋 Languages listed only:")
        for lang, count in sorted(stats['listed_only'].items()):
            print(f"   • {count} {lang.capitalize()} files")

    # Show documentation insights
    if index['documentation_map']:
        print(f"\n📚 Documentation insights:")
        for doc_file, info in list(index['documentation_map'].items())[:3]:
            print(f"   • {doc_file}: {len(info['sections'])} sections")

    # Show directory purposes
    if index['directory_purposes']:
        print(f"\n🏗️  Directory structure:")
        for dir_path, purpose in list(index['directory_purposes'].items())[:5]:
            print(f"   • {dir_path}/: {purpose}")

    if skipped_count > 0:
        print(f"\n   (Skipped {skipped_count} files in ignored directories)")


def main():
    """Run the enhanced indexer."""
    print("🚀 Building Project Index...")
    print("   Analyzing project structure and documentation...")

    # Build index for current directory
    index, skipped_count = build_index('.')

    # Save DSL index
    output_path = Path('PROJECT_INDEX.dsl')
    output_path.write_text(render_dsl(index), encoding='utf-8')

    # Print summary
    print_summary(index, skipped_count)

    print(f"\n💾 Saved to: {output_path}")
    print("\n✨ Claude now has architectural awareness of your project!")
    print("   • Knows WHERE to place new code")
    print("   • Understands project structure")
    print("   • Can navigate documentation")
    print("\n📌 Benefits:")
    print("   • Prevents code duplication")
    print("   • Ensures proper file placement")
    print("   • Maintains architectural consistency")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--version':
        print(f"PROJECT_INDEX v{__version__}")
        sys.exit(0)
    main()
