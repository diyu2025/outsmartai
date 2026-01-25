#!/bin/bash
# Wrapper script to ensure correct Python environment is used

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="/Users/yud/repo/outsmartai/.venv/bin/python"

# Check if venv Python exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ ERROR: Virtual environment not found at $VENV_PYTHON"
    echo "Please create/activate the virtual environment first"
    exit 1
fi

# Check if formalgeo is installed
if ! $VENV_PYTHON -c "import formalgeo" 2>/dev/null; then
    echo "❌ ERROR: formalgeo not installed in virtual environment"
    echo "Run: $VENV_PYTHON -m pip install formalgeo"
    exit 1
fi

# Run the E2E test with correct Python
echo "Using Python: $VENV_PYTHON"
echo "FormalGeo version:"
$VENV_PYTHON -c "import formalgeo; print(f'  {formalgeo.__version__}')"
echo ""

exec $VENV_PYTHON "$SCRIPT_DIR/run_e2e.py" "$@"
