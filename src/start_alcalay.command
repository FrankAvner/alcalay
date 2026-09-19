#!/bin/zsh

PROJECT_ROOT="$HOME/alcalay"
VENV="$PROJECT_ROOT/.venv"

echo ""
echo "=========================================="
echo " Alcalay"
echo " Starting application..."
echo "=========================================="
echo ""

cd "$PROJECT_ROOT" || exit 1

# Check virtual environment
if [ ! -f "$VENV/bin/activate" ]; then
    echo "ERROR: Python virtual environment not found:"
    echo "$VENV"
    exit 1
fi

# Activate Python environment
echo "Activating Python virtual environment..."
source "$VENV/bin/activate"

echo "Python:"
python --version
echo ""

# Start Alcalay
echo "Starting Alcalay application..."
echo ""

python "$PROJECT_ROOT/src/ui/alcalay_main.py"

EXIT_CODE=$?

echo ""
echo "=========================================="
echo " Alcalay stopped"
echo " Exit code: $EXIT_CODE"
echo "=========================================="
echo ""

exit $EXIT_CODE

