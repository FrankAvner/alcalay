#!/bin/zsh

set -e

PROJECT_ROOT="$HOME/alcalay"
VENV="$PROJECT_ROOT/.venv"

cd "$PROJECT_ROOT"

echo ""
echo "=========================================="
echo " Alcalay - Git Update"
echo "=========================================="
echo ""

# --------------------------------------------------
# 1. Check Git repository
# --------------------------------------------------

if [ ! -d ".git" ]; then
    echo "ERROR: This directory is not a Git repository:"
    echo "$PROJECT_ROOT"
    exit 1
fi

# --------------------------------------------------
# 2. Activate virtual environment
# --------------------------------------------------

if [ ! -f "$VENV/bin/activate" ]; then
    echo "ERROR: Python virtual environment not found:"
    echo "$VENV"
    exit 1
fi

echo "[1/6] Activating Python virtual environment..."

source "$VENV/bin/activate"

echo "Python:"
python --version

# --------------------------------------------------
# 3. Python syntax check
# --------------------------------------------------

echo ""
echo "[2/6] Checking Python files..."

python -m py_compile init_files/*.py

echo "Python syntax check: OK"

# --------------------------------------------------
# 4. Git status
# --------------------------------------------------

echo ""
echo "[3/6] Current Git status..."
echo ""

git status --short

# --------------------------------------------------
# 5. Add changes
# --------------------------------------------------

echo ""
echo "[4/6] Adding changes..."

git add .

echo ""
echo "Files staged:"
git status --short

# --------------------------------------------------
# 6. Commit
# --------------------------------------------------

echo ""
echo "[5/6] Creating Git commit..."

COMMIT_MESSAGE="Update Alcalay setup UI and setup integration"

git commit -m "$COMMIT_MESSAGE" || {
    echo ""
    echo "No commit was created."
    echo "There may be no new changes to commit."
}

echo ""
echo "[6/6] Final Git status..."
echo ""

git status

echo ""
echo "=========================================="
echo " Git update completed"
echo "=========================================="
echo ""
echo "No push was performed."
echo ""
