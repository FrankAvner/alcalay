
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
# 2. Verify main branch
# --------------------------------------------------

CURRENT_BRANCH=$(git branch --show-current)

echo "[1/8] Checking Git branch..."
echo "Current branch: $CURRENT_BRANCH"
echo ""

if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "ERROR: Alcalay project must be updated from the main branch."
    echo ""
    echo "Current branch:"
    echo "  $CURRENT_BRANCH"
    echo ""
    echo "Expected:"
    echo "  main"
    echo ""
    echo "Switch to main with:"
    echo "  git switch main"
    echo ""
    exit 1
fi

echo "Git branch: OK"
echo ""

# --------------------------------------------------
# 3. Activate Python virtual environment
# --------------------------------------------------

echo "[2/8] Activating Python virtual environment..."

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
# 4. Check Python files
# --------------------------------------------------

echo "[3/8] Checking Python files..."

PYTHON_ERROR=0

find src init_files -type f -name "*.py" \
    -not -path "*/__pycache__/*" \
    -exec python -m py_compile {} \; || PYTHON_ERROR=1

if [ "$PYTHON_ERROR" -ne 0 ]; then
    echo ""
    echo "ERROR: Python syntax check failed."
    echo "Git update aborted."
    exit 1
fi

echo "Python syntax check: OK"
echo ""

# --------------------------------------------------
# 5. Show current status
# --------------------------------------------------

echo "[4/8] Current Git status..."
echo ""

git status --short

echo ""

# --------------------------------------------------
# 6. Check nested repository / uri_source
# --------------------------------------------------

echo "[5/8] Checking nested repositories..."

if [ -d "$PROJECT_ROOT/uri_source/.git" ] || [ -f "$PROJECT_ROOT/uri_source/.git" ]; then

    echo ""
    echo "WARNING: uri_source is a separate Git repository."
    echo "Its internal files are NOT part of the Alcalay Git repository."
    echo ""

    (
        cd "$PROJECT_ROOT/uri_source"

        if [ -n "$(git status --porcelain)" ]; then
            echo "uri_source has uncommitted changes:"
            echo ""
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
# 7. Add and commit ALL Alcalay changes
# --------------------------------------------------

echo "[6/8] Adding all Alcalay changes..."

git add -A

echo ""
echo "Files staged:"
git diff --cached --name-status
echo ""

if git diff --cached --quiet; then
    echo "No new Alcalay changes to commit."
else
    echo "Creating Git commit..."

    COMMIT_MESSAGE="Update Alcalay project"

    git commit -m "$COMMIT_MESSAGE"

    echo ""
    echo "Commit created:"
    git log -1 --oneline
fi

echo ""

# --------------------------------------------------
# 8. Push ONLY main
# --------------------------------------------------

echo "[7/8] Updating GitHub main..."

echo "Remote:"
git remote get-url origin

echo ""
echo "Pushing:"
echo "  local  main"
echo "  remote main"
echo ""

git push -u origin main

echo ""

# --------------------------------------------------
# Final verification
# --------------------------------------------------

echo "[8/8] Final verification..."
echo ""

echo "=========================================="
echo " Git update completed successfully"
echo "=========================================="
echo ""

echo "Branch:"
git branch --show-current

echo ""

echo "Latest commit:"
git log -1 --oneline

echo ""

echo "Git status:"
git status --short

echo ""

echo "Remote:"
git remote -v

echo ""

echo "=========================================="
echo " Alcalay Git is synchronized with GitHub"
echo "=========================================="
echo ""


