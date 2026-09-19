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

echo "[1/7] Activating Python virtual environment..."

if [ ! -f "$VENV/bin/activate" ]; then
    echo "ERROR: Python virtual environment not found:"
    echo "$VENV"
    exit 1
fi

source "$VENV/bin/activate"

echo "Python:"
python --version
echo ""

# --------------------------------------------------
# 2. Check Python files
# --------------------------------------------------

echo "[2/7] Checking Python files..."

find src -type f -name "*.py" \
    -not -path "*/__pycache__/*" \
    -exec python -m py_compile {} \;

echo "Python syntax check: OK"
echo ""

# --------------------------------------------------
# 3. Show current status
# --------------------------------------------------

echo "[3/7] Current Git status..."
echo ""

git status --short

echo ""

# --------------------------------------------------
# 4. Check nested repository / submodule
# --------------------------------------------------

echo "[4/7] Checking nested repositories..."

if [ -d "$PROJECT_ROOT/uri_source/.git" ] || [ -f "$PROJECT_ROOT/uri_source/.git" ]; then

    echo ""
    echo "WARNING: uri_source is a separate Git repository/submodule."
    echo "Its internal changes cannot be committed by the Alcalay repository."
    echo ""

    (
        cd "$PROJECT_ROOT/uri_source"

        if [ -n "$(git status --porcelain)" ]; then
            echo "uri_source has uncommitted changes:"
            git status --short
            echo ""
            echo "These changes will NOT be included in the Alcalay commit."
        else
            echo "uri_source: clean"
        fi
    )

else
    echo "No nested Git repository detected."
fi

echo ""

# --------------------------------------------------
# 5. Add ALL changes
# --------------------------------------------------

echo "[5/7] Adding all changes..."

git add -A

echo ""
echo "Files staged:"
git diff --cached --name-status

echo ""

# --------------------------------------------------
# 6. Commit
# --------------------------------------------------

echo "[6/7] Creating Git commit..."

if git diff --cached --quiet; then

    echo "No new changes to commit."

else

    COMMIT_MESSAGE="Update Alcalay files"

    git commit -m "$COMMIT_MESSAGE"

fi

echo ""

# --------------------------------------------------
# 7. Push
# --------------------------------------------------

echo "[7/7] Pushing to GitHub..."

CURRENT_BRANCH=$(git branch --show-current)

if [ -z "$CURRENT_BRANCH" ]; then
    echo "ERROR: Could not determine current Git branch."
    exit 1
fi

echo "Current branch: $CURRENT_BRANCH"

if git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then

    UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}')

    echo "Upstream: $UPSTREAM"
    echo ""

    git push

else

    echo "No upstream branch configured."
    echo "Creating upstream for: $CURRENT_BRANCH"
    echo ""

    git push -u origin "$CURRENT_BRANCH"

fi

echo ""
echo "=========================================="
echo " Git update and push completed"
echo "=========================================="
echo ""

echo "Final Git status:"
git status --short

echo ""
echo "Branch:"
git branch --show-current

echo ""
echo "Latest commit:"
git log -1 --oneline

echo ""
