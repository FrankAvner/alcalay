#!/bin/bash

# ============================================================
# Alcalay - Project Launcher
# ============================================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$PROJECT_DIR" || exit 1

echo "========================================"
echo "          ALCALAY"
echo "========================================"
echo
echo "Project directory:"
echo "$PROJECT_DIR"
echo

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
    source ".venv/bin/activate"
else
    echo "ERROR: Python virtual environment not found."
    echo
    echo "Expected:"
    echo "$PROJECT_DIR/.venv/bin/activate"
    echo
    read -r -p "Press Enter to close..."
    exit 1
fi

echo "Virtual environment activated."
echo

# Start Alcalay
python src/ui/alcalay_main.py

EXIT_CODE=$?

echo
echo "========================================"
echo "Alcalay stopped."
echo "Exit code: $EXIT_CODE"
echo "========================================"
echo

read -r -p "Press Enter to close..."

exit $EXIT_CODE