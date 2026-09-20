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

if [ ! -d ".git" ]; then
    echo "ERROR: This directory is not a Git repository:"
    echo "$PROJECT_ROOT"
    exit 1
fi

CURRENT_BRANCH=$(git branch --show-current)

echo "[1/10] Checking Git branch..."
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

echo "[2/10] Activating Python virtual environment..."

if [ ! -f "$VENV/bin/activate" ]; then
    echo "ERROR: Python virtual environment not found:"
    echo "$VENV"
    exit 1
fi

source "$VENV/bin/activate"

echo "Python:"
python --version
echo ""

echo "[3/10] Checking Python files..."

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

echo "[4/10] Checking PostgreSQL project files..."

POSTGRES_FILES=(
    "database/migrations/001_initial_schema.sql"
    "init_files/setup_database.py"
    "init_files/setup_database_schema.py"
    "src/database/__init__.py"
    "src/database/connection.py"
    "src/database/database_manager.py"
)

POSTGRES_ERROR=0

for FILE in "${POSTGRES_FILES[@]}"; do

    if [ ! -f "$PROJECT_ROOT/$FILE" ]; then
        echo "ERROR: Required PostgreSQL file is missing:"
        echo "  $FILE"
        POSTGRES_ERROR=1
    fi

done

if [ "$POSTGRES_ERROR" -ne 0 ]; then
    echo ""
    echo "ERROR: PostgreSQL project file check failed."
    echo "Git update aborted."
    exit 1
fi

echo "PostgreSQL project files: OK"
echo ""

echo "PostgreSQL files:"
for FILE in "${POSTGRES_FILES[@]}"; do
    echo "  $FILE"
done

echo ""

echo "[5/10] Checking PostgreSQL configuration protection..."

if git check-ignore -q "config/alcalay_config.json"; then
    echo "Local database configuration is ignored by Git: OK"
else
    echo "WARNING: config/alcalay_config.json is NOT ignored by Git."
    echo "This file may contain local database configuration."
    echo ""
fi

echo "PostgreSQL configuration protection check completed."
echo ""

echo "[6/10] Current Git status..."

echo ""
git status --short
echo ""

echo "[7/10] Checking nested repositories..."

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

echo "[8/10] Adding all Alcalay changes..."

git add -A

echo ""
echo "Files staged:"
git diff --cached --name-status
echo ""

echo "Checking PostgreSQL files in Git..."

POSTGRES_GIT_ERROR=0

for FILE in "${POSTGRES_FILES[@]}"; do

    if ! git ls-files --error-unmatch "$FILE" >/dev/null 2>&1; then

        echo "ERROR: PostgreSQL file is NOT tracked by Git:"
        echo "  $FILE"

        POSTGRES_GIT_ERROR=1

    fi

done

if [ "$POSTGRES_GIT_ERROR" -ne 0 ]; then

    echo ""
    echo "ERROR: PostgreSQL Git verification failed."
    echo "Git update aborted."
    exit 1

fi

echo "All PostgreSQL project files are tracked by Git: OK"
echo ""

echo "[9/10] Creating Git commit..."

if git diff --cached --quiet; then

    echo "No new Alcalay changes to commit."

else

    COMMIT_MESSAGE="Update Alcalay project"

    git commit -m "$COMMIT_MESSAGE"

    echo ""
    echo "Commit created:"
    git log -1 --oneline

fi

echo ""

echo "Updating GitHub main..."

echo "Remote:"
git remote get-url origin

echo ""

echo "Pushing:"
echo "  local  main"
echo "  remote main"

echo ""

git push -u origin main

echo ""

echo "[10/10] Final verification..."

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

echo "PostgreSQL files tracked by Git:"
for FILE in "${POSTGRES_FILES[@]}"; do
    echo "  $FILE"
done

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
