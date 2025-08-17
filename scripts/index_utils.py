#!/usr/bin/env python3
"""
Shared utilities for project indexing.
Contains common functionality used by both project_index.py and hook scripts.
"""

import re
import fnmatch
from pathlib import Path
import subprocess
from typing import Dict, List, Optional, Set, Tuple
import json

# What to ignore by default if Git isn't available
IGNORE_DIRS = {
    '.git', '__pycache__', '.venv', 'venv', 'env', '.idea', '.vscode', '.DS_Store'
}

# Languages we can fully parse (extract functions/classes)
PARSEABLE_LANGUAGES = {
    '.py': 'python',
    '.js': 'javascript', 
    '.ts': 'typescript',
    '.jsx': 'javascript',
    '.tsx': 'typescript',
    '.sh': 'shell',
    '.bash': 'shell'
}

# All code file extensions we recognize
CODE_EXTENSIONS = {
    # Currently parsed
    '.py', '.js', '.ts', '.jsx', '.tsx',
    # Common languages (listed but not parsed yet)
    '.go', '.rs', '.java', '.c', '.cpp', '.cc', '.cxx', 
    '.h', '.hpp', '.rb', '.php', '.swift', '.kt', '.scala', 
    '.cs', '.sh', '.bash', '.sql', '.r', '.R', '.lua', '.m',
    '.ex', '.exs', '.jl', '.dart', '.vue', '.svelte',
    # Configuration and data files
    '.json', '.html', '.css',
    # Smart contracts
    '.sol'
}

# Markdown files to analyze
MARKDOWN_EXTENSIONS = {'.md', '.markdown', '.rst'}

# Common directory purposes
DIRECTORY_PURPOSES = {
    'auth': 'Authentication and authorization logic',
    'models': 'Data models and database schemas',
    'views': 'UI views and templates',
    'controllers': 'Request handlers and business logic',
    'services': 'Business logic and external service integrations',
    'utils': 'Shared utility functions and helpers',
    'helpers': 'Helper functions and utilities',
    'tests': 'Test files and test utilities',
    'test': 'Test files and test utilities',
    'spec': 'Test specifications',
    'docs': 'Project documentation',
    'api': 'API endpoints and route handlers',
    'components': 'Reusable UI components',
    'lib': 'Library code and shared modules',
    'src': 'Source code root directory',
    'static': 'Static assets (images, CSS, etc.)',
    'public': 'Publicly accessible files',
    'config': 'Configuration files and settings',
    'scripts': 'Build and utility scripts',
    'middleware': 'Middleware functions and handlers',
    'migrations': 'Database migration files',
    'fixtures': 'Test fixtures and sample data'
}


def extract_function_calls_python(body: str, all_functions: Set[str]) -> List[str]:
    """Extract function calls from Python code body."""
    calls = set()
    
    # Pattern for function calls: word followed by (
    # Excludes: control flow keywords, built-ins we don't care about
    call_pattern = r'\b(\w+)\s*\('
    exclude_keywords = {
        'if', 'elif', 'while', 'for', 'with', 'except', 'def', 'class',
        'return', 'yield', 'raise', 'assert', 'print', 'len', 'str', 
        'int', 'float', 'bool', 'list', 'dict', 'set', 'tuple', 'type',
        'isinstance', 'issubclass', 'super', 'range', 'enumerate', 'zip',
        'map', 'filter', 'sorted', 'reversed', 'open', 'input', 'eval'
    }
    
    for match in re.finditer(call_pattern, body):
        func_name = match.group(1)
        if func_name in all_functions and func_name not in exclude_keywords:
            calls.add(func_name)
    
    # Also catch method calls like self.method() or obj.method()
    method_pattern = r'(?:self|cls|\w+)\.(\w+)\s*\('
    for match in re.finditer(method_pattern, body):
        method_name = match.group(1)
        if method_name in all_functions:
            calls.add(method_name)
    
    return sorted(list(calls))


def extract_function_calls_javascript(body: str, all_functions: Set[str]) -> List[str]:
    """Extract function calls from JavaScript/TypeScript code body."""
    calls = set()
    
    # Pattern for function calls
    call_pattern = r'\b(\w+)\s*\('
    exclude_keywords = {
        'if', 'while', 'for', 'switch', 'catch', 'function', 'class',
        'return', 'throw', 'new', 'typeof', 'instanceof', 'void',
        'console', 'Array', 'Object', 'String', 'Number', 'Boolean',
        'Promise', 'Math', 'Date', 'JSON', 'parseInt', 'parseFloat'
    }
    
    for match in re.finditer(call_pattern, body):
        func_name = match.group(1)
        if func_name in all_functions and func_name not in exclude_keywords:
            calls.add(func_name)
    
    # Method calls: obj.method() or this.method()
    method_pattern = r'(?:this|\w+)\.(\w+)\s*\('
    for match in re.finditer(method_pattern, body):
        method_name = match.group(1)
        if method_name in all_functions:
            calls.add(method_name)
    
    return sorted(list(calls))


def build_call_graph(functions: Dict, classes: Dict) -> Tuple[Dict, Dict]:
    """Build bidirectional call graph from extracted functions and methods."""
    calls_map = {}
    called_by_map = {}
    
    # Initialize maps for all functions
    all_funcs = set(functions.keys())
    for class_info in classes.values():
        if 'methods' in class_info:
            all_funcs.update(class_info['methods'].keys())
    
    # Build the reverse index
    for func_name in calls_map:
        if func_name in calls_map:
            for called_func in calls_map[func_name]:
                if called_func not in called_by_map:
                    called_by_map[called_func] = []
                if func_name not in called_by_map[called_func]:
                    called_by_map[called_func].append(func_name)
    
    return calls_map, called_by_map


def extract_python_signatures(content: str) -> Dict[str, Dict]:
    """Extract Python function and class signatures with full details for all files."""
    result = {
        'imports': [],
        'functions': {}, 
        'classes': {}, 
        'constants': {}, 
        'variables': [],
        'type_aliases': {},
        'enums': {},
        'call_graph': {}  # Track function calls for flow analysis
    }
    
    # Split into lines for line-by-line analysis
    lines = content.split('\n')
    
    # Track current class context
    current_class = None
    current_class_indent = -1
    class_stack = []  # For nested classes
    
    # First pass: collect all function and method names for call detection
    all_function_names = set()
    for line in lines:
        func_match = re.match(r'^(?:[ \t]*)(async\s+)?def\s+(\w+)\s*\(', line)
        if func_match:
            all_function_names.add(func_match.group(2))
    
    # Patterns
    class_pattern = r'^([ \t]*)class\s+(\w+)(?:\s*\((.*?)\))?:'
    func_pattern = r'^([ \t]*)(async\s+)?def\s+(\w+)\s*\((.*?)\)(?:\s*->\s*([^:]+))?:'
    property_pattern = r'^([ \t]*)(\w+)\s*:\s*([^=\n]+)'
    # Module-level constants (UPPERCASE_NAME = value)
    module_const_pattern = r'^([A-Z_][A-Z0-9_]*)\s*=\s*(.+)$'
    # Module-level variables with type annotations
    module_var_pattern = r'^(\w+)\s*:\s*([^=]+)\s*='
    # Class-level constants
    class_const_pattern = r'^([ \t]+)([A-Z_][A-Z0-9_]*)\s*=\s*(.+)$'
    # Import patterns
    import_pattern = r'^(?:from\s+([^\s]+)\s+)?import\s+(.+)$'
    # Type alias pattern
    type_alias_pattern = r'^(\w+)\s*=\s*(?:Union|Optional|List|Dict|Tuple|Set|Type|Callable|Literal|TypeVar|NewType|TypedDict|Protocol)\[.+\]$'
    # Decorator pattern
    decorator_pattern = r'^([ \t]*)@(\w+)(?:\(.*\))?$'
    # Docstring pattern (matches next line after function/class)
    docstring_pattern = r'^([ \t]*)(?:\'\'\'|""")(.+?)(?:\'\'\'|""")'
    
    # Dunder methods to skip (unless in critical files)
    skip_dunder = {'__repr__', '__str__', '__hash__', '__eq__', '__ne__', 
                   '__lt__', '__le__', '__gt__', '__ge__', '__bool__'}
    
    # First pass: Extract imports
    for line in lines:
        import_match = re.match(import_pattern, line.strip())
        if import_match:
            module, items = import_match.groups()
            if module:
                # from X import Y style
                result['imports'].append(module)
            else:
                # import X style
                for item in items.split(','):
                    item = item.strip().split(' as ')[0]  # Remove aliases
                    result['imports'].append(item)
    
    # Track decorators for next function/method
    pending_decorators = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Skip comments and docstrings
        if line.strip().startswith('#') or line.strip().startswith('"""') or line.strip().startswith("'''"):
            i += 1
            continue
        
        # Check for decorators
        decorator_match = re.match(decorator_pattern, line)
        if decorator_match:
            _, decorator_name = decorator_match.groups()
            pending_decorators.append(decorator_name)
            i += 1
            continue
        
        # Check for module-level constants (before checking classes)
        if not current_class:  # Only at module level
            # Check for type aliases first
            type_alias_match = re.match(type_alias_pattern, line)
            if type_alias_match:
                alias_name = type_alias_match.group(1)
                result['type_aliases'][alias_name] = line.split('=', 1)[1].strip()
                i += 1
                continue
            
            const_match = re.match(module_const_pattern, line)
            if const_match:
                const_name, const_value = const_match.groups()
                # Clean up the value (remove comments, strip quotes for readability)
                const_value = const_value.split('#')[0].strip()
                # Determine type from value
                if const_value.startswith(('{', '[')):
                    const_type = 'collection'
                elif const_value.startswith(("'", '"')):
                    const_type = 'str'
                elif const_value.replace('.', '').replace('-', '').isdigit():
                    const_type = 'number'
                else:
                    const_type = 'value'
                result['constants'][const_name] = const_type
                i += 1
                continue
            
            # Check for module-level typed variables
            var_match = re.match(module_var_pattern, line)
            if var_match:
                var_name, var_type = var_match.groups()
                if var_name not in result['variables'] and not var_name.startswith('_'):
                    result['variables'].append(var_name)
                i += 1
                continue
        
        # Check for class definition
        class_match = re.match(class_pattern, line)
        if class_match:
            indent, name, bases = class_match.groups()
            indent_level = len(indent)
            
            # Handle nested classes - pop from stack if dedented
            while class_stack and indent_level <= class_stack[-1][1]:
                class_stack.pop()
            
            # Only process top-level classes for the index
            if indent_level == 0:
                class_info = {'methods': {}, 'class_constants': {}}
                
                # Check for decorators on the class
                if pending_decorators:
                    class_info['decorators'] = pending_decorators.copy()
                    pending_decorators.clear()
                
                # Add inheritance info and check special types
                if bases:
                    base_list = [b.strip() for b in bases.split(',') if b.strip()]
                    if base_list:
                        class_info['inherits'] = base_list
                        
                        # Check for special class types
                        base_names_lower = [b.lower() for b in base_list]
                        if 'enum' in base_names_lower or any('enum' in b for b in base_names_lower):
                            class_info['type'] = 'enum'
                            # We'll extract enum values later
                        elif 'exception' in base_names_lower or 'error' in base_names_lower or any('exception' in b or 'error' in b for b in base_names_lower):
                            class_info['type'] = 'exception'
                        elif 'abc' in base_names_lower or 'protocol' in base_names_lower:
                            class_info['abstract'] = True
                
                # Extract docstring
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    doc_match = re.match(docstring_pattern, lines[i + 1])
                    if doc_match:
                        _, doc_content = doc_match.groups()
                        class_info['doc'] = doc_content.strip()
                
                result['classes'][name] = class_info
                current_class = name
                current_class_indent = indent_level
            
            # Add to stack
            class_stack.append((name, indent_level))
            i += 1
            continue
        
        # Check if we've left the current class (dedented to module level)
        if current_class and line.strip() and len(line) - len(line.lstrip()) <= current_class_indent:
            # Check if it's not just a blank line or comment
            if not line.strip().startswith('#'):
                current_class = None
                current_class_indent = -1
        
        # Check for class-level constants or enum values
        if current_class:
            # For enums, capture all uppercase attributes as values
            if result['classes'][current_class].get('type') == 'enum':
                # Enum value pattern (NAME = value or just NAME)
                enum_val_pattern = r'^([ \t]+)([A-Z_][A-Z0-9_]*)\s*(?:=\s*(.+))?$'
                enum_match = re.match(enum_val_pattern, line)
                if enum_match:
                    indent, enum_name, enum_value = enum_match.groups()
                    if len(indent) > current_class_indent:
                        if 'values' not in result['classes'][current_class]:
                            result['classes'][current_class]['values'] = []
                        result['classes'][current_class]['values'].append(enum_name)
                        i += 1
                        continue
            
            class_const_match = re.match(class_const_pattern, line)
            if class_const_match:
                indent, const_name, const_value = class_const_match.groups()
                if len(indent) > current_class_indent:
                    # Clean up the value
                    const_value = const_value.split('#')[0].strip()
                    # Determine type
                    if const_value.startswith(('{', '[')):
                        const_type = 'collection'
                    elif const_value.startswith(("'", '"')):
                        const_type = 'str'
                    elif const_value.replace('.', '').replace('-', '').isdigit():
                        const_type = 'number'
                    else:
                        const_type = 'value'
                    result['classes'][current_class]['class_constants'][const_name] = const_type
                    i += 1
                    continue
        
        # Check for function/method definition
        # First check if this line starts a function definition
        func_start_pattern = r'^([ \t]*)(async\s+)?def\s+(\w+)\s*\('
        func_start_match = re.match(func_start_pattern, line)
        
        if func_start_match:
            indent, is_async, name = func_start_match.groups()
            indent_level = len(indent)
            
            # Collect the full signature across multiple lines
            full_sig = line.rstrip()
            j = i
            
            # Keep collecting lines until we find the colon that ends the signature
            while j < len(lines) and not re.search(r'\).*:', lines[j]):
                j += 1
                if j < len(lines):
                    full_sig += ' ' + lines[j].strip()
            
            # Make sure we have a complete signature
            if j >= len(lines):
                i += 1
                continue
                
            # Now parse the complete signature
            complete_match = re.match(func_pattern, full_sig)
            if complete_match:
                indent, is_async, name, params, return_type = complete_match.groups()
                i = j  # Skip to the last line we processed
            else:
                # Failed to parse, skip this function
                i += 1
                continue
            
            # Clean params
            params = re.sub(r'\s+', ' ', params).strip()
            
            # Skip certain dunder methods (except __init__)
            if name in skip_dunder and name != '__init__':
                i += 1
                continue
            
            # Build function/method info
            func_info = {}
            
            # Build full signature
            signature = f"({params})"
            if return_type:
                signature += f" -> {return_type.strip()}"
            if is_async:
                signature = "async " + signature
            
            # Add decorators if any
            if pending_decorators:
                func_info['decorators'] = pending_decorators.copy()
                # Check for abstractmethod
                if 'abstractmethod' in pending_decorators:
                    if current_class:
                        result['classes'][current_class]['abstract'] = True
                pending_decorators.clear()
            
            # Extract docstring
            if i + 1 < len(lines):
                doc_match = re.match(docstring_pattern, lines[i + 1])
                if doc_match:
                    _, doc_content = doc_match.groups()
                    func_info['doc'] = doc_content.strip()
            
            # Extract function body to find calls
            func_body_start = i + 1
            func_body_lines = []
            func_indent = len(indent) if indent else 0
            
            # Skip past any docstring (but include it in body for now)
            body_idx = func_body_start
            
            # Collect function body - everything indented more than the def line
            while body_idx < len(lines):
                body_line = lines[body_idx]
                
                # Skip empty lines
                if not body_line.strip():
                    func_body_lines.append(body_line)
                    body_idx += 1
                    continue
                
                # Check indentation to see if we're still in the function
                line_indent = len(body_line) - len(body_line.lstrip())
                
                # If we hit a line that's not indented more than the function def, we're done
                if line_indent <= func_indent and body_line.strip():
                    break
                    
                func_body_lines.append(body_line)
                body_idx += 1
            
            # Extract calls from the body
            if func_body_lines:
                func_body = '\n'.join(func_body_lines)
                calls = extract_function_calls_python(func_body, all_function_names)
                if calls:
                    func_info['calls'] = calls
            
            # If we only have signature, store as string; otherwise as dict
            if len(func_info) == 0:
                func_info = signature
            else:
                func_info['signature'] = signature
            
            # Determine where to place this function
            if current_class and indent_level > current_class_indent:
                # It's a method of the current class
                result['classes'][current_class]['methods'][name] = func_info
            elif indent_level == 0:
                # It's a module-level function
                result['functions'][name] = func_info
        
        # Check for class properties
        if current_class:
            prop_match = re.match(property_pattern, line)
            if prop_match:
                indent, prop_name, prop_type = prop_match.groups()
                if len(indent) > current_class_indent and not prop_name.startswith('_'):
                    if 'properties' not in result['classes'][current_class]:
                        result['classes'][current_class]['properties'] = []
                    result['classes'][current_class]['properties'].append(prop_name)
        
        i += 1
    
    # Post-process - remove empty collections
    for class_name, class_info in result['classes'].items():
        if 'properties' in class_info and not class_info['properties']:
            del class_info['properties']
        if 'class_constants' in class_info and not class_info['class_constants']:
            del class_info['class_constants']
        if 'decorators' in class_info and not class_info['decorators']:
            del class_info['decorators']
        if 'values' in class_info and not class_info['values']:
            del class_info['values']
    
    # Remove empty module-level collections
    if not result['constants']:
        del result['constants']
    if not result['variables']:
        del result['variables']
    if not result['type_aliases']:
        del result['type_aliases']
    if not result['enums']:
        del result['enums']
    if not result['imports']:
        del result['imports']
    
    # Move enum classes to enums section
    enums_to_move = {}
    for class_name, class_info in list(result['classes'].items()):
        if class_info.get('type') == 'enum':
            enums_to_move[class_name] = {
                'values': class_info.get('values', []),
                'doc': class_info.get('doc', '')
            }
            del result['classes'][class_name]
    
    if enums_to_move:
        result['enums'] = enums_to_move
    
    return result


def extract_javascript_signatures(content: str) -> Dict[str, any]:
    """Extract JavaScript/TypeScript function and class signatures with full details."""
    result = {
        'imports': [],
        'functions': {}, 
        'classes': {}, 
        'constants': {}, 
        'variables': [],
        'type_aliases': {},
        'interfaces': {},
        'enums': {},
        'call_graph': {}  # Track function calls for flow analysis
    }
    
    # First pass: collect all function names for call detection
    all_function_names = set()
    # Regular functions
    for match in re.finditer(r'(?:async\s+)?function\s+(\w+)', content):
        all_function_names.add(match.group(1))
    # Arrow functions and const functions
    for match in re.finditer(r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(', content):
        all_function_names.add(match.group(1))
    # Method names
    for match in re.finditer(r'(\w+)\s*\([^)]*\)\s*{', content):
        all_function_names.add(match.group(1))
    
    # Extract imports first
    # import X from 'Y', import {X} from 'Y', import * as X from 'Y'
    import_pattern = r'import\s+(?:([^{}\s]+)|{([^}]+)}|\*\s+as\s+(\w+))\s+from\s+[\'"]([^\'"]+)[\'"]'
    for match in re.finditer(import_pattern, content):
        default_import, named_imports, namespace_import, module = match.groups()
        if module:
            result['imports'].append(module)
    
    # require() style imports
    require_pattern = r'(?:const|let|var)\s+(?:{[^}]+}|\w+)\s*=\s*require\s*\([\'"]([^\'"]+)[\'"]\)'
    for match in re.finditer(require_pattern, content):
        result['imports'].append(match.group(1))
    
    # Extract type aliases (TypeScript) - simpler approach with brace counting
    type_alias_pattern = r'(?:export\s+)?type\s+(\w+)\s*=\s*(.+?)(?:;[\s]*(?:(?:export\s+)?(?:type|const|let|var|function|class|interface|enum)\s+|\/\/|$))'
    
    for match in re.finditer(type_alias_pattern, content, re.MULTILINE | re.DOTALL):
        alias_name, alias_type = match.groups()
        # Clean up the type definition
        clean_type = ' '.join(alias_type.strip().split())
        
        # If it starts with { but seems incomplete, try to capture the full object
        if clean_type.startswith('{') and clean_type.count('{') > clean_type.count('}'):
            # Find the position after the = sign
            start_pos = match.start(2)
            brace_count = 0
            end_pos = start_pos
            
            # Count braces to find the complete type
            for i, char in enumerate(content[start_pos:]):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = start_pos + i + 1
                        break
            
            if end_pos > start_pos:
                complete_type = content[start_pos:end_pos].strip()
                clean_type = ' '.join(complete_type.split())
        
        result['type_aliases'][alias_name] = clean_type
    
    # Extract interfaces (TypeScript)
    interface_pattern = r'(?:export\s+)?interface\s+(\w+)(?:\s+extends\s+([^{]+))?\s*{'
    for match in re.finditer(interface_pattern, content):
        interface_name, extends = match.groups()
        interface_info = {}
        if extends:
            interface_info['extends'] = [e.strip() for e in extends.split(',')]
        # Extract first line of JSDoc if present
        jsdoc_match = re.search(r'/\*\*\s*\n?\s*\*?\s*([^@\n]+)', content[:match.start()])
        if jsdoc_match:
            interface_info['doc'] = jsdoc_match.group(1).strip()
        result['interfaces'][interface_name] = interface_info
    
    # Extract enums (TypeScript)
    enum_pattern = r'(?:export\s+)?enum\s+(\w+)\s*{'
    enum_matches = list(re.finditer(enum_pattern, content))
    for match in enum_matches:
        enum_name = match.group(1)
        # Find enum values
        start_pos = match.end()
        brace_count = 1
        end_pos = start_pos
        for i in range(start_pos, len(content)):
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_pos = i
                    break
        
        enum_body = content[start_pos:end_pos]
        # Extract enum values
        value_pattern = r'(\w+)\s*(?:=\s*[^,\n]+)?'
        values = re.findall(value_pattern, enum_body)
        result['enums'][enum_name] = {'values': values}
    
    # Extract module-level constants and variables
    # const CONSTANT_NAME = value
    const_pattern = r'(?:export\s+)?const\s+([A-Z_][A-Z0-9_]*)\s*=\s*([^;]+)'
    for match in re.finditer(const_pattern, content):
        const_name, const_value = match.groups()
        const_value = const_value.strip()
        if const_value.startswith(('{', '[')):
            const_type = 'collection'
        elif const_value.startswith(("'", '"', '`')):
            const_type = 'str'
        elif const_value.replace('.', '').replace('-', '').isdigit():
            const_type = 'number'
        else:
            const_type = 'value'
        result['constants'][const_name] = const_type
    
    # let/const variables (not uppercase)
    var_pattern = r'(?:export\s+)?(?:let|const)\s+([a-z]\w*)\s*(?::\s*\w+)?\s*='
    for match in re.finditer(var_pattern, content):
        var_name = match.group(1)
        if var_name not in result['variables']:
            result['variables'].append(var_name)
    
    # Find all classes first with their boundaries
    class_pattern = r'(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?'
    class_positions = {}  # {class_name: (start_pos, end_pos)}
    
    for match in re.finditer(class_pattern, content):
        class_name, extends = match.groups()
        start_pos = match.start()
        
        # Find the class body (between { and })
        brace_count = 0
        in_class = False
        end_pos = start_pos
        
        for i in range(match.end(), len(content)):
            if content[i] == '{':
                if not in_class:
                    in_class = True
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
                if brace_count == 0 and in_class:
                    end_pos = i
                    break
        
        class_positions[class_name] = (start_pos, end_pos)
        
        # Initialize class info
        class_info = {'methods': {}, 'static_constants': {}}
        if extends:
            class_info['extends'] = extends
            # Check for exception classes
            if extends.lower() in ['error', 'exception'] or 'error' in extends.lower():
                class_info['type'] = 'exception'
        
        # Extract JSDoc comment
        jsdoc_match = re.search(r'/\*\*\s*\n?\s*\*?\s*([^@\n]+)', content[:start_pos])
        if jsdoc_match:
            class_info['doc'] = jsdoc_match.group(1).strip()
        
        result['classes'][class_name] = class_info
    
    # Extract methods from classes
    method_patterns = [
        # Regular methods: methodName(...) { or async methodName(...) {
        r'^\s*(async\s+)?(\w+)\s*\((.*?)\)\s*(?::\s*([^{]+))?\s*{',
        # Arrow function properties: methodName = (...) => {
        r'^\s*(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*(?::\s*([^=]+))?\s*=>',
        # Constructor
        r'^\s*(constructor)\s*\(([^)]*)\)\s*{'
    ]
    
    for class_name, (start, end) in class_positions.items():
        class_content = content[start:end]
        
        for pattern in method_patterns:
            for match in re.finditer(pattern, class_content, re.MULTILINE):
                # Extract method name and params based on pattern
                if 'constructor' in pattern:
                    method_name = '__init__'  # Convert to Python-style
                    params = match.group(2)
                    return_type = None
                elif '=' in pattern:
                    method_name = match.group(1)
                    params = match.group(2)
                    return_type = match.group(3)
                else:
                    is_async = match.group(1)
                    method_name = match.group(2)
                    params = match.group(3)
                    return_type = match.group(4)
                
                # Skip getters/setters and keywords
                if method_name in ['get', 'set', 'if', 'for', 'while', 'switch', 'catch', 'try']:
                    continue
                
                method_info = {}
                
                # Build full signature
                params = re.sub(r'\s+', ' ', params).strip()
                signature = f"({params})"
                if return_type:
                    signature += f": {return_type.strip()}"
                if 'async' in str(match.group(0)):
                    signature = "async " + signature
                
                # Try to extract method body for call analysis
                method_start = match.end()
                # Find the opening brace
                brace_pos = class_content.find('{', method_start)
                if brace_pos != -1 and brace_pos - method_start < 100:
                    # Extract method body
                    brace_count = 1
                    body_start = brace_pos + 1
                    body_end = body_start
                    
                    for i in range(body_start, min(len(class_content), body_start + 3000)):
                        if class_content[i] == '{':
                            brace_count += 1
                        elif class_content[i] == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                body_end = i
                                break
                    
                    if body_end > body_start:
                        method_body = class_content[body_start:body_end]
                        calls = extract_function_calls_javascript(method_body, all_function_names)
                        if calls:
                            method_info['calls'] = calls
                
                # Store method info
                if method_info:
                    method_info['signature'] = signature
                    result['classes'][class_name]['methods'][method_name] = method_info
                else:
                    result['classes'][class_name]['methods'][method_name] = signature
        
        # Extract static constants in class
        static_const_pattern = r'static\s+([A-Z_][A-Z0-9_]*)\s*=\s*([^;]+)'
        for match in re.finditer(static_const_pattern, class_content):
            const_name, const_value = match.groups()
            const_value = const_value.strip()
            if const_value.startswith(('{', '[')):
                const_type = 'collection'
            elif const_value.startswith(("'", '"', '`')):
                const_type = 'str'
            elif const_value.replace('.', '').replace('-', '').isdigit():
                const_type = 'number'
            else:
                const_type = 'value'
            result['classes'][class_name]['static_constants'][const_name] = const_type
    
    # Extract standalone functions (not inside classes)
    func_patterns = [
        # Function declarations
        r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*(?:<[^>]+>)?\s*\(([^)]*)\)(?:\s*:\s*([^{]+))?',
        # Arrow functions assigned to const
        r'(?:export\s+)?const\s+(\w+)\s*(?::\s*[^=]+)?\s*=\s*(?:async\s+)?\(([^)]*)\)\s*(?::\s*([^=]+))?\s*=>'
    ]
    
    for pattern in func_patterns:
        for match in re.finditer(pattern, content):
            func_name = match.group(1)
            params = match.group(2) if match.lastindex >= 2 else ''
            return_type = match.group(3) if match.lastindex >= 3 else None
            
            # Check if this function is inside any class
            func_pos = match.start()
            inside_class = False
            for class_name, (start, end) in class_positions.items():
                if start <= func_pos <= end:
                    inside_class = True
                    break
            
            if not inside_class:
                func_info = {}
                
                # Build full signature
                params = re.sub(r'\s+', ' ', params).strip()
                signature = f"({params})"
                if return_type:
                    signature += f": {return_type.strip()}"
                if 'async' in match.group(0):
                    signature = "async " + signature
                
                # Try to extract function body for call analysis
                func_start = match.end()
                # Find the opening brace
                brace_pos = content.find('{', func_start)
                if brace_pos != -1 and brace_pos - func_start < 100:  # Reasonable distance
                    # Extract function body
                    brace_count = 1
                    body_start = brace_pos + 1
                    body_end = body_start
                    
                    for i in range(body_start, min(len(content), body_start + 5000)):  # Limit scan
                        if content[i] == '{':
                            brace_count += 1
                        elif content[i] == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                body_end = i
                                break
                    
                    if body_end > body_start:
                        func_body = content[body_start:body_end]
                        calls = extract_function_calls_javascript(func_body, all_function_names)
                        if calls:
                            func_info['calls'] = calls
                
                # Store function info
                if func_info:
                    func_info['signature'] = signature
                    result['functions'][func_name] = func_info
                else:
                    result['functions'][func_name] = signature
    
    # Clean up empty collections
    for class_name, class_info in result['classes'].items():
        if 'static_constants' in class_info and not class_info['static_constants']:
            del class_info['static_constants']
    
    # Remove empty module-level collections
    if not result['constants']:
        del result['constants']
    if not result['variables']:
        del result['variables']
    if not result['imports']:
        del result['imports']
    if not result['type_aliases']:
        del result['type_aliases']
    if not result['interfaces']:
        del result['interfaces']
    if not result['enums']:
        del result['enums']
    
    return result


def extract_function_calls_shell(body: str, all_functions: Set[str]) -> List[str]:
    """Extract function calls from shell script body."""
    calls = set()
    
    # In shell, functions are called just by name (no parentheses)
    # We need to be careful to avoid false positives
    for func_name in all_functions:
        # Look for function name at start of line or after common shell operators
        patterns = [
            rf'^\s*{func_name}\b',  # Start of line
            rf'[;&|]\s*{func_name}\b',  # After operators
            rf'\$\({func_name}\b',  # Command substitution
            rf'`{func_name}\b',  # Backtick substitution
        ]
        for pattern in patterns:
            if re.search(pattern, body, re.MULTILINE):
                calls.add(func_name)
                break
    
    return sorted(list(calls))


def extract_shell_signatures(content: str) -> Dict[str, any]:
    """Extract shell script function signatures and structure."""
    result = {
        'functions': {},
        'variables': [],
        'exports': {},
        'sources': [],
        'call_graph': {}  # Track function calls
    }
    
    lines = content.split('\n')
    
    # First pass: collect all function names
    all_function_names = set()
    for line in lines:
        # Style 1: function_name() {
        match1 = re.match(r'^(\w+)\s*\(\)\s*\{?', line)
        if match1:
            all_function_names.add(match1.group(1))
        # Style 2: function function_name {
        match2 = re.match(r'^function\s+(\w+)\s*\{?', line)
        if match2:
            all_function_names.add(match2.group(1))
    
    # Function patterns
    # Style 1: function_name() { ... }
    func_pattern1 = r'^(\w+)\s*\(\)\s*\{?'
    # Style 2: function function_name { ... }
    func_pattern2 = r'^function\s+(\w+)\s*\{?'
    
    # Variable patterns
    # Export pattern: export VAR=value
    export_pattern = r'^export\s+([A-Z_][A-Z0-9_]*)(=(.*))?'
    # Regular variable: VAR=value (uppercase)
    var_pattern = r'^([A-Z_][A-Z0-9_]*)=(.+)$'
    
    # Source patterns - handle quotes and command substitution
    source_patterns = [
        r'^(?:source|\.)\s+([\'"])([^\'"]+)\1',  # Quoted paths
        r'^(?:source|\.)\s+(\$\([^)]+\)[^\s]*)',  # Command substitution like $(dirname "$0")/file
        r'^(?:source|\.)\s+([^\s]+)',  # Unquoted paths
    ]
    
    # Track if we're in a function
    in_function = False
    current_function = None
    function_start_line = -1
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Skip empty lines and pure comments
        if not stripped or stripped.startswith('#!'):
            continue
            
        # Check for function definition (style 1)
        match = re.match(func_pattern1, stripped)
        if match:
            func_name = match.group(1)
            # Extract documentation comment if present
            doc = None
            if i > 0 and lines[i-1].strip().startswith('#'):
                doc = lines[i-1].strip()[1:].strip()
            
            # Try to find parameters from the function body
            params = []
            brace_count = 0
            in_func_body = False
            
            # Look for $1, $2, etc. usage in the function body only
            for j in range(i+1, min(i+20, len(lines))):
                line_content = lines[j].strip()
                
                # Track braces to know when we're in the function
                if '{' in line_content:
                    brace_count += line_content.count('{')
                    in_func_body = True
                if '}' in line_content:
                    brace_count -= line_content.count('}')
                    if brace_count <= 0:
                        break  # End of function
                
                # Only look for parameters inside the function body
                if in_func_body:
                    param_matches = re.findall(r'\$(\d+)', lines[j])
                    for p in param_matches:
                        param_num = int(p)
                        if param_num > 0 and param_num not in params:
                            params.append(param_num)
            
            # Build signature
            if params:
                max_param = max(params)
                param_list = ' '.join(f'$1' if j == 1 else f'${{{j}}}' for j in range(1, max_param + 1))
                signature = f"({param_list})"
            else:
                signature = "()"
            
            # Extract function body for call analysis
            func_body_lines = []
            brace_count = 0
            in_func_body = False
            for j in range(i+1, len(lines)):
                line_content = lines[j]
                if '{' in line_content:
                    brace_count += line_content.count('{')
                    in_func_body = True
                if in_func_body:
                    func_body_lines.append(line_content)
                if '}' in line_content:
                    brace_count -= line_content.count('}')
                    if brace_count <= 0:
                        break
            
            func_info = {}
            if func_body_lines:
                func_body = '\n'.join(func_body_lines)
                calls = extract_function_calls_shell(func_body, all_function_names)
                if calls:
                    func_info['calls'] = calls
            
            if doc:
                func_info['doc'] = doc
            
            if func_info:
                func_info['signature'] = signature
                result['functions'][func_name] = func_info
            else:
                result['functions'][func_name] = signature
            continue
            
        # Check for function definition (style 2)
        match = re.match(func_pattern2, stripped)
        if match:
            func_name = match.group(1)
            # Extract documentation comment if present
            doc = None
            if i > 0 and lines[i-1].strip().startswith('#'):
                doc = lines[i-1].strip()[1:].strip()
            
            # Try to find parameters from the function body
            params = []
            brace_count = 0
            in_func_body = False
            
            # Look for $1, $2, etc. usage in the function body only
            for j in range(i+1, min(i+20, len(lines))):
                line_content = lines[j].strip()
                
                # Track braces to know when we're in the function
                if '{' in line_content:
                    brace_count += line_content.count('{')
                    in_func_body = True
                if '}' in line_content:
                    brace_count -= line_content.count('}')
                    if brace_count <= 0:
                        break  # End of function
                
                # Only look for parameters inside the function body
                if in_func_body:
                    param_matches = re.findall(r'\$(\d+)', lines[j])
                    for p in param_matches:
                        param_num = int(p)
                        if param_num > 0 and param_num not in params:
                            params.append(param_num)
            
            # Build signature
            if params:
                max_param = max(params)
                param_list = ' '.join(f'$1' if j == 1 else f'${{{j}}}' for j in range(1, max_param + 1))
                signature = f"({param_list})"
            else:
                signature = "()"
            
            # Extract function body for call analysis
            func_body_lines = []
            brace_count = 0
            in_func_body = False
            for j in range(i+1, len(lines)):
                line_content = lines[j]
                if '{' in line_content:
                    brace_count += line_content.count('{')
                    in_func_body = True
                if in_func_body:
                    func_body_lines.append(line_content)
                if '}' in line_content:
                    brace_count -= line_content.count('}')
                    if brace_count <= 0:
                        break
            
            func_info = {}
            if func_body_lines:
                func_body = '\n'.join(func_body_lines)
                calls = extract_function_calls_shell(func_body, all_function_names)
                if calls:
                    func_info['calls'] = calls
            
            if doc:
                func_info['doc'] = doc
            
            if func_info:
                func_info['signature'] = signature
                result['functions'][func_name] = func_info
            else:
                result['functions'][func_name] = signature
            continue
        
        # Check for exports
        match = re.match(export_pattern, stripped)
        if match:
            var_name = match.group(1)
            var_value = match.group(3) if match.group(3) else None
            if var_value:
                # Determine type
                if var_value.startswith(("'", '"')):
                    var_type = 'str'
                elif var_value.isdigit():
                    var_type = 'number'
                else:
                    var_type = 'value'
                result['exports'][var_name] = var_type
            continue
        
        # Check for regular variables (uppercase)
        match = re.match(var_pattern, stripped)
        if match:
            var_name = match.group(1)
            # Only track if not already in exports
            if var_name not in result['exports'] and var_name not in result['variables']:
                result['variables'].append(var_name)
            continue
        
        # Check for source/dot includes
        for source_pattern in source_patterns:
            match = re.match(source_pattern, stripped)
            if match:
                # Extract the file path based on which pattern matched
                if len(match.groups()) == 2:  # Quoted pattern
                    sourced_file = match.group(2)
                else:  # Unquoted or command substitution
                    sourced_file = match.group(1)
                
                sourced_file = sourced_file.strip()
                if sourced_file and sourced_file not in result['sources']:
                    result['sources'].append(sourced_file)
                break  # Found a match, no need to try other patterns
    
    # Clean up empty collections
    if not result['variables']:
        del result['variables']
    if not result['exports']:
        del result['exports']
    if not result['sources']:
        del result['sources']
    
    return result


def extract_markdown_structure(file_path: Path) -> Dict[str, List[str]]:
    """Extract headers and architectural hints from markdown files."""
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
    except:
        return {'sections': [], 'architecture_hints': []}
    
    # Extract headers (up to level 3)
    headers = re.findall(r'^#{1,3}\s+(.+)$', content[:5000], re.MULTILINE)  # Only scan first 5KB
    
    # Look for architectural hints
    arch_patterns = [
        r'(?:located?|found?|stored?)\s+in\s+`?([\w\-\./]+)`?',
        r'`?([\w\-\./]+)`?\s+(?:contains?|houses?|holds?)',
        r'(?:see|check|look)\s+(?:in\s+)?`?([\w\-\./]+)`?\s+for',
        r'(?:file|module|component)\s+`?([\w\-\./]+)`?',
    ]
    
    hints = set()
    for pattern in arch_patterns:
        matches = re.findall(pattern, content[:5000], re.IGNORECASE)
        for match in matches:
            if '/' in match and not match.startswith('http'):
                hints.add(match)
    
    return {
        'sections': headers[:10],  # Limit to prevent bloat
        'architecture_hints': list(hints)[:5]
    }


def infer_file_purpose(file_path: Path) -> Optional[str]:
    """Infer the purpose of a file from its name and location."""
    name = file_path.stem.lower()
    
    # Common file purposes
    if name in ['index', 'main', 'app']:
        return 'Application entry point'
    elif 'test' in name or 'spec' in name:
        return 'Test file'
    elif 'config' in name or 'settings' in name:
        return 'Configuration'
    elif 'route' in name:
        return 'Route definitions'
    elif 'model' in name:
        return 'Data model'
    elif 'util' in name or 'helper' in name:
        return 'Utility functions'
    elif 'middleware' in name:
        return 'Middleware'
    
    return None


def infer_directory_purpose(path: Path, files_within: List[str]) -> Optional[str]:
    """Infer directory purpose from naming patterns and contents."""
    dir_name = path.name.lower()
    
    # Check exact matches first
    if dir_name in DIRECTORY_PURPOSES:
        return DIRECTORY_PURPOSES[dir_name]
    
    # Check if directory name contains key patterns
    for pattern, purpose in DIRECTORY_PURPOSES.items():
        if pattern in dir_name:
            return purpose
    
    # Infer from contents
    if files_within:
        # Check for test files
        if any('test' in f.lower() or 'spec' in f.lower() for f in files_within):
            return 'Test files and test utilities'
        
        # Check for specific file patterns
        if any('model' in f.lower() for f in files_within):
            return 'Data models and schemas'
        elif any('route' in f.lower() or 'endpoint' in f.lower() for f in files_within):
            return 'API routes and endpoints'
        elif any('component' in f.lower() for f in files_within):
            return 'UI components'
    
    return None


def get_language_name(extension: str) -> str:
    """Get readable language name from extension."""
    if extension in PARSEABLE_LANGUAGES:
        return PARSEABLE_LANGUAGES[extension]
    return extension[1:] if extension else 'unknown'


# ---------- External Engines: ast-grep + ripgrep (fallback for Solidity) ----------

# Map file extensions to ast-grep language aliases
ASTGREP_LANG_BY_EXT: Dict[str, str] = {
    '.py': 'python',
    '.js': 'javascript',
    '.jsx': 'javascript',
    '.ts': 'typescript',
    '.tsx': 'tsx',
    '.go': 'go',
    '.rs': 'rust',
    '.java': 'java',
    '.cs': 'csharp',
    '.c': 'c',
    '.h': 'c',
    '.cc': 'cpp',
    '.cpp': 'cpp',
    '.cxx': 'cpp',
    '.hpp': 'cpp',
}


def _which(cmd: str) -> Optional[str]:
    try:
        out = subprocess.run(['bash', '-lc', f'command -v {cmd}'], capture_output=True, text=True)
        path = out.stdout.strip()
        return path or None
    except Exception:
        return None


def sg_cli() -> Optional[str]:
    """Return ast-grep CLI name (sg or ast-grep) if available."""
    return _which('sg') or _which('ast-grep')


def rg_cli() -> Optional[str]:
    """Return ripgrep CLI path if available."""
    return _which('rg') or _which('ripgrep')


def _astgrep_run(pattern: str, lang: str, file_path: Path, selector: Optional[str] = None) -> List[Dict]:
    cli = sg_cli()
    if not cli:
        return []
    try:
        # Use stream JSON for efficiency
        cmd = [cli, 'run', '-p', pattern, '-l', lang, '--json=stream', str(file_path)]
        if selector:
            cmd = [cli, 'run', '-p', pattern, '-l', lang, '--selector', selector, '--json=stream', str(file_path)]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        matches = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                matches.append(json.loads(line))
            except Exception:
                continue
        return matches
    except Exception:
        return []


def _extract_name_sig_from_text(ext: str, kind: str, text: str) -> Optional[Tuple[str, str]]:
    """Extract name and signature string from matched text.
    kind: 'function' | 'class'
    Returns (name, signature)
    """
    t = text.strip()
    if ext == '.py':
        if kind == 'function':
            m = re.match(r'^def\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*:', t)
            if m:
                name, params = m.groups()
                return name, f'({params})'
        elif kind == 'class':
            m = re.match(r'^class\s+([A-Za-z_]\w*)(?:\s*\(([^)]*)\))?\s*:', t)
            if m:
                name, bases = m.groups()
                sig = f'({bases})' if bases else ''
                return name, sig
    elif ext in ('.js', '.jsx', '.ts', '.tsx'):
        if kind == 'function':
            # function decl
            m = re.match(r'^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)', t)
            if m:
                name, params = m.groups()
                return name, f'({params})'
            # arrow function const name = (...) =>
            m = re.match(r'^(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>', t)
            if m:
                name, params = m.groups()
                return name, f'({params})'
        elif kind == 'class':
            m = re.match(r'^(?:export\s+)?class\s+([A-Za-z_$][\w$]*)', t)
            if m:
                name = m.group(1)
                return name, ''
    elif ext == '.go':
        if kind == 'function':
            # func Name(params) [returns] {
            m = re.match(r'^func\s+(?:\([^)]+\)\s*)?([A-Za-z_]\w*)\s*\(([^)]*)\)\s*([^\{]*)\{', t)
            if m:
                name, params, ret = m.groups()
                sig = f'({params})'
                ret = ret.strip()
                if ret:
                    sig += f' -> {ret.strip()}'
                return name, sig
    elif ext == '.rs':
        if kind == 'function':
            m = re.match(r'^fn\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?:->\s*([^\{]+))?\s*\{', t)
            if m:
                name, params, ret = m.groups()
                sig = f'({params})'
                if ret:
                    sig += f' -> {ret.strip()}'
                return name, sig
    elif ext in ('.java', '.cs'):
        if kind == 'function':
            # modifiers/annotations + return + name(params) { ... }
            m = re.search(r'([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{', t)
            if m:
                name, params = m.groups()
                return name, f'({params})'
        elif kind == 'class':
            m = re.search(r'\bclass\s+([A-Za-z_$][\w$]*)', t)
            if m:
                return m.group(1), ''
    elif ext in ('.c', '.h', '.cc', '.cpp', '.cxx', '.hpp'):
        if kind == 'function':
            m = re.search(r'([A-Za-z_~][\w$]*)\s*\(([^)]*)\)\s*\{', t)
            if m:
                name, params = m.groups()
                return name, f'({params})'
        elif ext in ('.cc', '.cpp', '.cxx', '.hpp') and kind == 'class':
            m = re.search(r'\b(class|struct)\s+([A-Za-z_][\w$]*)', t)
            if m:
                return m.group(2), ''
    return None


def extract_with_astgrep(file_path: Path, content: str) -> Dict[str, Dict]:
    """Use ast-grep to extract functions/classes for supported languages.
    Returns structure like {'functions': {...}, 'classes': {...}} or empty dict if not applicable.
    """
    ext = file_path.suffix
    lang = ASTGREP_LANG_BY_EXT.get(ext)
    if not lang or not sg_cli():
        return {}
    functions: Dict[str, Dict] = {}
    classes: Dict[str, Dict] = {}

    # Python
    if ext == '.py':
        func_matches = _astgrep_run('def $FN($$$ARGS): $$$', 'python', file_path)
        for m in func_matches:
            text = m.get('text', '')
            parsed = _extract_name_sig_from_text(ext, 'function', text)
            if parsed:
                name, sig = parsed
                if name not in functions:
                    functions[name] = {'signature': sig}
        class_matches = _astgrep_run('class $C($$BASES): $$$', 'python', file_path) + \
                        _astgrep_run('class $C: $$$', 'python', file_path)
        for m in class_matches:
            text = m.get('text', '')
            parsed = _extract_name_sig_from_text(ext, 'class', text)
            if parsed:
                name, sig = parsed
                if name not in classes:
                    classes[name] = {'methods': {}}
    # JS/TS/JSX/TSX
    elif ext in ('.js', '.jsx', '.ts', '.tsx'):
        func_matches = []
        func_matches += _astgrep_run('function $FN($$$ARGS) { $$$ }', lang, file_path)
        func_matches += _astgrep_run('function $FN($$$ARGS): $RET { $$$ }', lang, file_path)
        func_matches += _astgrep_run('const $FN = ($$$ARGS) => { $$$ }', lang, file_path)
        func_matches += _astgrep_run('const $FN = ($$$ARGS): $RET => { $$$ }', lang, file_path)
        for m in func_matches:
            text = m.get('text', '')
            parsed = _extract_name_sig_from_text(ext, 'function', text)
            if parsed:
                name, sig = parsed
                if name not in functions:
                    functions[name] = {'signature': sig}
        class_matches = _astgrep_run('class $C { $$$ }', lang, file_path)
        for m in class_matches:
            text = m.get('text', '')
            parsed = _extract_name_sig_from_text(ext, 'class', text)
            if parsed:
                name, sig = parsed
                if name not in classes:
                    classes[name] = {'methods': {}}
    elif ext == '.go':
        # functions and methods
        func_matches = []
        func_matches += _astgrep_run('func $FN($$$ARGS) { $$$ }', 'go', file_path)
        func_matches += _astgrep_run('func $FN($$$ARGS) $RET { $$$ }', 'go', file_path)
        # methods with receiver
        func_matches += _astgrep_run('func ($REC $T) $FN($$$ARGS) { $$$ }', 'go', file_path)
        func_matches += _astgrep_run('func ($REC $T) $FN($$$ARGS) $RET { $$$ }', 'go', file_path)
        for m in func_matches:
            text = m.get('text', '')
            parsed = _extract_name_sig_from_text(ext, 'function', text)
            if parsed:
                name, sig = parsed
                if name not in functions:
                    functions[name] = {'signature': sig}
        result: Dict[str, Dict] = {'functions': functions, 'classes': classes}
        if not functions:
            result.pop('functions', None)
        if not classes:
            result.pop('classes', None)
        return result
    elif ext == '.rs':
        func_matches = []
        func_matches += _astgrep_run('fn $FN($$$ARGS) { $$$ }', 'rust', file_path)
        func_matches += _astgrep_run('fn $FN($$$ARGS) -> $RET { $$$ }', 'rust', file_path)
        # methods inside impl
        func_matches += _astgrep_run('impl $T { fn $FN($$$ARGS) { $$$ } }', 'rust', file_path)
        func_matches += _astgrep_run('impl $T { fn $FN($$$ARGS) -> $RET { $$$ } }', 'rust', file_path)
        for m in func_matches:
            text = m.get('text', '')
            parsed = _extract_name_sig_from_text(ext, 'function', text)
            if parsed:
                name, sig = parsed
                if name not in functions:
                    functions[name] = {'signature': sig}
        result: Dict[str, Dict] = {'functions': functions, 'classes': classes}
        if not functions:
            result.pop('functions', None)
        if not classes:
            result.pop('classes', None)
        return result
    elif ext == '.java':
        # Classes with ranges
        class_matches = _astgrep_run('class $C { $$$ }', 'java', file_path)
        class_ranges: List[Tuple[str, int, int]] = []
        for m in class_matches:
            text = m.get('text', '')
            parsed = _extract_name_sig_from_text(ext, 'class', text)
            if parsed:
                name, _ = parsed
                r = m.get('range', {})
                s = r.get('start', {}).get('line', 0)
                e = r.get('end', {}).get('line', 0)
                class_ranges.append((name, s, e))
                classes.setdefault(name, {'methods': {}})
        # Methods inside classes using selector
        method_matches = _astgrep_run('class $C { $$$ }', 'java', file_path, selector='method_declaration')
        for m in method_matches:
            text = m.get('text', '')
            parsed = _extract_name_sig_from_text(ext, 'function', text)
            if not parsed:
                continue
            mname, sig = parsed
            r = m.get('range', {})
            sline = r.get('start', {}).get('line', 0)
            eline = r.get('end', {}).get('line', 0)
            # Find enclosing class by range
            owner = None
            for cname, cs, ce in class_ranges:
                if cs <= sline <= ce:
                    owner = cname
            if owner:
                classes.setdefault(owner, {'methods': {}})
                if mname not in classes[owner]['methods']:
                    classes[owner]['methods'][mname] = {'signature': sig}
            else:
                functions.setdefault(mname, {'signature': sig})
        result: Dict[str, Dict] = {'functions': functions, 'classes': classes}
        if not functions:
            result.pop('functions', None)
        if not classes:
            result.pop('classes', None)
        return result
    elif ext == '.cs':
        class_matches = _astgrep_run('class $C { $$$ }', 'csharp', file_path)
        class_ranges: List[Tuple[str, int, int]] = []
        for m in class_matches:
            text = m.get('text', '')
            parsed = _extract_name_sig_from_text(ext, 'class', text)
            if parsed:
                name, _ = parsed
                r = m.get('range', {})
                s = r.get('start', {}).get('line', 0)
                e = r.get('end', {}).get('line', 0)
                class_ranges.append((name, s, e))
                classes.setdefault(name, {'methods': {}})
        method_matches = _astgrep_run('class $C { $$$ }', 'csharp', file_path, selector='method_declaration')
        for m in method_matches:
            text = m.get('text', '')
            parsed = _extract_name_sig_from_text(ext, 'function', text)
            if not parsed:
                continue
            mname, sig = parsed
            r = m.get('range', {})
            sline = r.get('start', {}).get('line', 0)
            eline = r.get('end', {}).get('line', 0)
            owner = None
            for cname, cs, ce in class_ranges:
                if cs <= sline <= ce:
                    owner = cname
            if owner:
                classes.setdefault(owner, {'methods': {}})
                if mname not in classes[owner]['methods']:
                    classes[owner]['methods'][mname] = {'signature': sig}
            else:
                functions.setdefault(mname, {'signature': sig})
        result: Dict[str, Dict] = {'functions': functions, 'classes': classes}
        if not functions:
            result.pop('functions', None)
        if not classes:
            result.pop('classes', None)
        return result
    elif ext in ('.c', '.h'):
        func_matches = _astgrep_run('$_RET $FN($$$ARGS) { $$$ }', 'c', file_path)
        for m in func_matches:
            text = m.get('text', '')
            parsed = _extract_name_sig_from_text(ext, 'function', text)
            if parsed:
                name, sig = parsed
                functions.setdefault(name, {'signature': sig})
        result: Dict[str, Dict] = {'functions': functions}
        if not functions:
            result.pop('functions', None)
        return result
    elif ext in ('.cc', '.cpp', '.cxx', '.hpp'):
        class_matches = []
        class_matches += _astgrep_run('class $C { $$$ }', 'cpp', file_path)
        class_matches += _astgrep_run('struct $C { $$$ }', 'cpp', file_path)
        class_ranges: List[Tuple[str, int, int]] = []
        for m in class_matches:
            text = m.get('text', '')
            parsed = _extract_name_sig_from_text(ext, 'class', text)
            if parsed:
                name, _ = parsed
                r = m.get('range', {})
                s = r.get('start', {}).get('line', 0)
                e = r.get('end', {}).get('line', 0)
                class_ranges.append((name, s, e))
                classes.setdefault(name, {'methods': {}})
        # Methods inside class bodies using selector
        method_matches = _astgrep_run('class $C { $$$ }', 'cpp', file_path, selector='function_definition')
        # Also for struct
        method_matches += _astgrep_run('struct $C { $$$ }', 'cpp', file_path, selector='function_definition')
        for m in method_matches:
            text = m.get('text', '')
            parsed = _extract_name_sig_from_text(ext, 'function', text)
            if not parsed:
                continue
            mname, sig = parsed
            r = m.get('range', {})
            sline = r.get('start', {}).get('line', 0)
            owner = None
            for cname, cs, ce in class_ranges:
                if cs <= sline <= ce:
                    owner = cname
            if owner:
                classes.setdefault(owner, {'methods': {}})
                if mname not in classes[owner]['methods']:
                    classes[owner]['methods'][mname] = {'signature': sig}
            else:
                functions.setdefault(mname, {'signature': sig})
        result: Dict[str, Dict] = {'functions': functions, 'classes': classes}
        if not functions:
            result.pop('functions', None)
        if not classes:
            result.pop('classes', None)
        return result
    else:
        return {}

    result: Dict[str, Dict] = {'functions': functions, 'classes': classes}
    # Clean empties
    if not functions:
        result.pop('functions', None)
    if not classes:
        result.pop('classes', None)
    return result


def extract_solidity_with_rg(file_path: Path) -> Dict[str, Dict]:
    """Extract Solidity contracts and functions using ripgrep as fallback."""
    rg = rg_cli()
    if not rg:
        return {}
    functions: Dict[str, Dict] = {}
    classes: Dict[str, Dict] = {}
    try:
        # Contracts/interfaces/libraries
        proc_c = subprocess.run(
            [rg, '-nU', '-e', r'^\s*(?:contract|interface|library)\s+([A-Za-z_]\w*)', str(file_path)],
            capture_output=True, text=True
        )
        for line in proc_c.stdout.splitlines():
            m = re.search(r'(?:contract|interface|library)\s+([A-Za-z_]\w*)', line)
            if m:
                name = m.group(1)
                classes.setdefault(name, {'methods': {}})
        # Functions/constructors
        proc_f = subprocess.run(
            [rg, '-nU', '-P', '-e', r'^\s*(?:function|constructor)\s*([A-Za-z_]\w*)?\s*\(([^)]*)\)\s*(?:[a-z\s]*)?(?:returns\s*\(([^)]*)\))?', str(file_path)],
            capture_output=True, text=True
        )
        for line in proc_f.stdout.splitlines():
            m = re.search(r'(?:function|constructor)\s*([A-Za-z_]\w*)?\s*\(([^)]*)\)\s*(?:[a-z\s]*)?(?:returns\s*\(([^)]*)\))?', line)
            if m:
                name = m.group(1) or 'constructor'
                params = m.group(2) or ''
                ret = m.group(3)
                sig = f'({params})'
                if ret:
                    sig += f' returns ({ret})'
                if name not in functions:
                    functions[name] = {'signature': sig}
    except Exception:
        pass
    result: Dict[str, Dict] = {'functions': functions, 'classes': classes}
    if not functions:
        result.pop('functions', None)
    if not classes:
        result.pop('classes', None)
    return result


def extract_signatures_auto(file_path: Path, content: str) -> Dict[str, Dict]:
    """Primary: ast-grep (sg/ast-grep); Solidity falls back to ripgrep;
    Otherwise fallback to built-in extractors.
    """
    ext = file_path.suffix
    # Solidity
    if ext == '.sol':
        via_rg = extract_solidity_with_rg(file_path)
        if via_rg:
            return via_rg
        return {}
    # ast-grep if available and supported
    via_sg = extract_with_astgrep(file_path, content)
    if via_sg:
        return via_sg
    # Built-in fallback
    if ext == '.py':
        return extract_python_signatures(content)
    if ext in {'.js', '.ts', '.jsx', '.tsx'}:
        return extract_javascript_signatures(content)
    if ext in {'.sh', '.bash'}:
        return extract_shell_signatures(content)
    return {}


# Global cache for gitignore patterns
_gitignore_cache = {}


def git_root(path: Path) -> Optional[Path]:
    """Return Git repository root for path, or None if not in a repo."""
    try:
        out = subprocess.run(
            ['git', '-C', str(path), 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            check=True
        )
        p = Path(out.stdout.strip())
        return p if p.exists() else None
    except Exception:
        return None


def git_ls_unignored_files(root: Path, scope: Optional[Path] = None) -> Optional[List[Path]]:
    """List non-ignored files using Git. Returns paths relative to root.

    - root: Git repo root (output of git_root)
    - scope: subdirectory to limit results; when provided, filters to files under scope
    """
    if git_root(root) is None:
        return None
    try:
        # Use exclude-standard (includes .gitignore, .git/info/exclude, global excludes)
        # -c (cached/tracked) + -o (others/untracked) → all non-ignored
        cmd = ['git', '-C', str(root), 'ls-files', '-co', '--exclude-standard', '-z']
        out = subprocess.run(cmd, capture_output=True, check=True)
        raw = out.stdout
        items = [x for x in raw.split(b'\x00') if x]
        paths = [Path(x.decode('utf-8')) for x in items]
        if scope is not None:
            scope = scope.resolve()
            # Keep only files under scope
            scoped = []
            for p in paths:
                full = (root / p).resolve()
                if str(full).startswith(str(scope) + str(Path('/')) ) or full == scope or scope in full.parents:
                    # Return relative to scope
                    try:
                        scoped.append(full.relative_to(scope))
                    except Exception:
                        continue
            return scoped
        return paths
    except Exception:
        return None


def parse_gitignore(gitignore_path: Path) -> List[str]:
    """Parse a .gitignore file and return list of patterns."""
    if not gitignore_path.exists():
        return []
    
    patterns = []
    try:
        with open(gitignore_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                patterns.append(line)
    except:
        pass
    
    return patterns


def load_gitignore_patterns(root_path: Path) -> Set[str]:
    """Load all gitignore patterns from project root and merge with defaults."""
    # Use cached patterns if available
    cache_key = str(root_path)
    if cache_key in _gitignore_cache:
        return _gitignore_cache[cache_key]
    
    # Start with conservative defaults only; Git will be primary filter
    patterns = set(IGNORE_DIRS)
    
    # Add patterns from .gitignore in project root
    gitignore_path = root_path / '.gitignore'
    if gitignore_path.exists():
        for pattern in parse_gitignore(gitignore_path):
            # Handle negations (!) later if needed
            if not pattern.startswith('!'):
                patterns.add(pattern)
    
    # Cache the patterns
    _gitignore_cache[cache_key] = patterns
    return patterns


def matches_gitignore_pattern(path: Path, patterns: Set[str], root_path: Path) -> bool:
    """Check if a path matches any gitignore pattern."""
    # Get relative path from root
    try:
        rel_path = path.relative_to(root_path)
    except ValueError:
        # Path is not relative to root
        return False
    
    # Convert to string for pattern matching
    path_str = str(rel_path)
    path_parts = rel_path.parts
    
    for pattern in patterns:
        # Check if any parent directory matches the pattern
        # Strip trailing slash for directory patterns
        clean_pattern = pattern.rstrip('/')
        for part in path_parts:
            if part == clean_pattern or fnmatch.fnmatch(part, clean_pattern):
                return True
        
        # Check full path patterns
        if '/' in pattern:
            # Pattern includes directory separator
            if fnmatch.fnmatch(path_str, pattern):
                return True
            # Also check without leading slash
            if pattern.startswith('/') and fnmatch.fnmatch(path_str, pattern[1:]):
                return True
        else:
            # Pattern is just a filename/directory name
            # Check if the filename matches
            if fnmatch.fnmatch(path.name, pattern):
                return True
            # Check if it matches the full relative path
            if fnmatch.fnmatch(path_str, pattern):
                return True
            # Check with wildcards
            if fnmatch.fnmatch(path_str, f'**/{pattern}'):
                return True
    
    return False


def should_index_file(path: Path, root_path: Path = None) -> bool:
    """Check if we should index this file."""
    # Must be a code or markdown file
    if not (path.suffix in CODE_EXTENSIONS or path.suffix in MARKDOWN_EXTENSIONS):
        return False
    
    # If inside Git repo and path is ignored by Git, skip
    if root_path:
        repo = git_root(root_path)
        if repo is not None:
            # Use git check-ignore for precise evaluation
            try:
                rel = str((root_path / path).resolve().relative_to(repo)) if root_path else str(path)
            except Exception:
                rel = str(path)
            try:
                res = subprocess.run(
                    ['git', '-C', str(repo), 'check-ignore', '-q', '--', rel],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                if res.returncode == 0:
                    return False
            except Exception:
                # Fall through to .gitignore patterns
                pass
    
    # Skip if in basic ignored directory (fallback when not in Git)
    for part in path.parts:
        if part in IGNORE_DIRS:
            return False
    
    # If root_path provided, check .gitignore patterns (fallback)
    if root_path:
        patterns = load_gitignore_patterns(root_path)
        if matches_gitignore_pattern(path, patterns, root_path):
            return False
    
    return True
