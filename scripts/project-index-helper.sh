#!/bin/bash
set -eo pipefail

# Claude Code PROJECT_INDEX Helper Script
# Wraps the Python indexer with error handling and user feedback

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/project_index.py"

# Check if Python script exists
if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    echo "❌ Error: PROJECT_INDEX not properly installed"
    echo "   Missing: $PYTHON_SCRIPT"
    echo ""
    echo "To reinstall, run:"
    echo "   curl -fsSL https://raw.githubusercontent.com/roderik/claude-code-project-index/main/install.sh | bash"
    exit 1
fi

# Determine Python command to use
# The .python_cmd file is in the parent directory
INSTALL_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON_CMD_FILE="$INSTALL_DIR/.python_cmd"
if [[ -f "$PYTHON_CMD_FILE" ]]; then
    PYTHON_CMD=$(cat "$PYTHON_CMD_FILE")
elif [[ -f "$SCRIPT_DIR/find_python.sh" ]]; then
    PYTHON_CMD=$(bash "$SCRIPT_DIR/find_python.sh" 2>/dev/null)
    if [[ -z "$PYTHON_CMD" ]]; then
        exit 1
    fi
else
    # Fallback to basic check
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        echo "❌ Error: Python 3.8+ is required but not installed"
        echo "Please install Python 3.8+ and try again"
        exit 1
    fi
fi

# Run the indexer
echo "🚀 Creating PROJECT_INDEX.json for current project..."
echo ""

# Execute the Python script
if $PYTHON_CMD "$PYTHON_SCRIPT" "$@"; then
    echo ""
    echo "✨ PROJECT_INDEX.json created successfully!"
    echo ""
    echo "📌 Usage tips:"
    echo "   • Reference with @PROJECT_INDEX.json when you need architectural awareness"
    echo "   • The index updates automatically when you edit files"
    echo "   • Re-run /index anytime to rebuild from scratch"
else
    exit_code=$?
    echo ""
    echo "❌ Error creating index (exit code: $exit_code)"
    echo ""
    echo "Common issues:"
    echo "   • Wrong directory - run from your project root"
    echo "   • No supported files - check if project has .py, .js, .ts files"
    echo "   • Permission issues - check file permissions"
    echo ""
    echo "For help, see: $INSTALL_DIR/README.md"
    exit $exit_code
fi