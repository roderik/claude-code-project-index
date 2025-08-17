## Project Awareness & Indexing

### PROJECT_INDEX.dsl Usage (QUERY, DON'T LOAD)

- FIRST ACTION: Check if exists: `ls PROJECT_INDEX.dsl 2>/dev/null`
- IF EXISTS, NEVER load full file - QUERY it with grep/rg:

#### DSL Format Key:

- `FN file::function` - Function definitions
- `C=` - Calls these functions
- `B=` - Called by these functions
- `F` - File entries
- `I` - Imports/dependencies
- `D` - Directory purposes
- `T` - Tree structure

#### Finding Functions/Classes:

```bash
# Find specific function (ripgrep is faster)
rg "::function_name" PROJECT_INDEX.dsl

# List all functions in a file
grep "^FN path/to/file.py::" PROJECT_INDEX.dsl | cut -d' ' -f2

# Find dead code (functions with no callers)
grep "^FN" PROJECT_INDEX.dsl | grep -v " B="

# Find all functions in Python files
grep "^FN.*\.py::" PROJECT_INDEX.dsl
```

#### Before Changes:

```bash
# What calls this function? (who depends on it)
rg "B=.*function_name" PROJECT_INDEX.dsl

# What does this function call?
rg "^FN.*::function_name.*C=" PROJECT_INDEX.dsl

# Find all imports of a module
rg "^I.*module_name" PROJECT_INDEX.dsl | cut -d= -f1

# Check directory purpose
grep "^D src/auth" PROJECT_INDEX.dsl
```

#### Adding Code:

```bash
# Find similar function names
rg "::.*pattern" PROJECT_INDEX.dsl

# Get all functions in a specific file
grep "^FN path/to/file.py::" PROJECT_INDEX.dsl

# See file's language and parse status
grep "^F path/to/file.py" PROJECT_INDEX.dsl
```

#### Quick Architecture Queries:

```bash
# Project stats (files, dirs, markdown)
grep "^P " PROJECT_INDEX.dsl

# View directory tree
grep "^T " PROJECT_INDEX.dsl

# All Python files
grep "^F.*lang=python" PROJECT_INDEX.dsl

# All parsed files with functions
grep "^F.*parsed=1" PROJECT_INDEX.dsl
```

- IF NOT PRESENT but project is complex (>50 files): suggest `/index` command
- ONLY load full index if absolutely necessary for complex architectural analysis
