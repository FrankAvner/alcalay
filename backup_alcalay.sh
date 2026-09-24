#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$HOME/alcalay"
BACKUP_ROOT="$PROJECT_ROOT/backups"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

BACKUP_NAME="alcalay_${TIMESTAMP}"
TEMP_DIR="$BACKUP_ROOT/.${BACKUP_NAME}_tmp"
BACKUP_DIR="$BACKUP_ROOT/$BACKUP_NAME"
ZIP_FILE="$BACKUP_ROOT/${BACKUP_NAME}.zip"

DB_NAME="alcalay"
DB_HOST="127.0.0.1"
DB_PORT="5432"

echo
echo "============================================================"
echo "ALCALAY FULL BACKUP"
echo "============================================================"
echo
echo "Project : $PROJECT_ROOT"
echo "Database: $DB_NAME"
echo "Backup  : $BACKUP_NAME"
echo

# ------------------------------------------------------------
# Basic checks
# ------------------------------------------------------------

if [ ! -d "$PROJECT_ROOT" ]; then
    echo "[ERROR] Project directory does not exist:"
    echo "$PROJECT_ROOT"
    exit 1
fi

if [ ! -d "$PROJECT_ROOT/.git" ]; then
    echo "[WARNING] .git directory was not found."
    echo "Git history will not be included."
    echo
fi

if ! command -v rsync >/dev/null 2>&1; then
    echo "[ERROR] rsync was not found."
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo "[ERROR] git was not found."
    exit 1
fi

if ! command -v pg_dump >/dev/null 2>&1; then
    echo "[ERROR] pg_dump was not found."
    echo "Make sure PostgreSQL client tools are installed."
    exit 1
fi

if ! command -v pg_dumpall >/dev/null 2>&1; then
    echo "[ERROR] pg_dumpall was not found."
    exit 1
fi

if ! command -v ditto >/dev/null 2>&1; then
    echo "[ERROR] ditto was not found."
    exit 1
fi

# ------------------------------------------------------------
# Prepare backup directories
# ------------------------------------------------------------

mkdir -p "$BACKUP_ROOT"

if [ -e "$TEMP_DIR" ]; then
    echo "[WARNING] Temporary backup directory already exists."
    echo "Removing:"
    echo "$TEMP_DIR"
    rm -rf "$TEMP_DIR"
fi

if [ -e "$BACKUP_DIR" ]; then
    echo "[ERROR] Backup directory already exists:"
    echo "$BACKUP_DIR"
    echo
    echo "This script NEVER overwrites an existing backup."
    echo "Aborting for safety."
    exit 1
fi

if [ -e "$ZIP_FILE" ]; then
    echo "[ERROR] Backup ZIP already exists:"
    echo "$ZIP_FILE"
    echo
    echo "This script NEVER overwrites an existing backup."
    echo "Aborting for safety."
    exit 1
fi

mkdir -p "$TEMP_DIR"

BACKUP_STARTED_AT=$(date "+%Y-%m-%d %H:%M:%S")

# ------------------------------------------------------------
# 1. Copy complete project
# ------------------------------------------------------------

echo "[1/8] Copying complete Alcalay project..."

mkdir -p "$TEMP_DIR/project"

rsync -a \
    --exclude=".venv/" \
    --exclude="venv/" \
    --exclude="env/" \
    --exclude="__pycache__/" \
    --exclude="*.pyc" \
    --exclude="*.pyo" \
    --exclude=".DS_Store" \
    --exclude="Thumbs.db" \
    --exclude="desktop.ini" \
    --exclude="backups/" \
    "$PROJECT_ROOT/" \
    "$TEMP_DIR/project/"

echo "[OK] Complete project copied."

echo
echo "Included:"
echo "  - src/"
echo "  - storage/"
echo "  - results/"
echo "  - config/"
echo "  - credentials/"
echo "  - database/"
echo "  - sql/"
echo "  - init_files/"
echo "  - uri_source/"
echo "  - scripts"
echo "  - .git/"
echo "  - all other project files"
echo
echo "Excluded:"
echo "  - .venv/"
echo "  - Python cache"
echo "  - .DS_Store"
echo "  - backups/"
echo

# ------------------------------------------------------------
# 2. Git information
# ------------------------------------------------------------

echo "[2/8] Saving Git information..."

cd "$PROJECT_ROOT"

git status --short > "$TEMP_DIR/git_status.txt" 2>&1 || true
git branch --show-current > "$TEMP_DIR/git_branch.txt" 2>&1 || true
git log -20 --oneline --decorate > "$TEMP_DIR/git_recent_commits.txt" 2>&1 || true
git rev-parse HEAD > "$TEMP_DIR/git_head.txt" 2>&1 || true

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git status --porcelain=v1 -uall > "$TEMP_DIR/git_status_full.txt" 2>&1 || true
fi

echo "[OK] Git information saved."

# ------------------------------------------------------------
# 3. PostgreSQL password
# ------------------------------------------------------------

echo "[3/8] Preparing PostgreSQL authentication..."

if [ -z "${PGPASSWORD:-}" ]; then
    echo
    echo "PostgreSQL password is required if authentication"
    echo "is not already configured through .pgpass."
    echo

    read -r -s -p "PostgreSQL password: " PGPASSWORD
    echo

    export PGPASSWORD
fi

echo "[OK] PostgreSQL authentication prepared."

# ------------------------------------------------------------
# 4. PostgreSQL database dump
# ------------------------------------------------------------

echo "[4/8] PostgreSQL database backup..."

mkdir -p "$TEMP_DIR/postgresql"

pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$USER" \
    -d "$DB_NAME" \
    --format=custom \
    --blobs \
    --verbose \
    --file="$TEMP_DIR/postgresql/alcalay.dump"

echo "[OK] PostgreSQL database dumped."

# ------------------------------------------------------------
# 5. PostgreSQL globals
# ------------------------------------------------------------

echo "[5/8] PostgreSQL roles and global objects..."

pg_dumpall \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$USER" \
    --globals-only \
    > "$TEMP_DIR/postgresql/postgresql_globals.sql"

echo "[OK] PostgreSQL globals saved."

unset PGPASSWORD

# ------------------------------------------------------------
# 6. Backup information
# ------------------------------------------------------------

echo "[6/8] Saving backup information..."

BACKUP_COMPLETED_AT=$(date "+%Y-%m-%d %H:%M:%S")

cat > "$TEMP_DIR/BACKUP_INFO.txt" <<EOF
ALCALAY FULL BACKUP
============================================================

Backup name:
$BACKUP_NAME

Backup started:
$BACKUP_STARTED_AT

Backup completed:
$BACKUP_COMPLETED_AT

Project:
$PROJECT_ROOT

Database:
$DB_NAME

PostgreSQL host:
$DB_HOST

PostgreSQL port:
$DB_PORT

------------------------------------------------------------
CONTENTS
------------------------------------------------------------

1. project/

   Complete Alcalay project files.

   Includes:
   - source code
   - storage
   - results
   - configuration
   - credentials
   - database files
   - SQL files
   - initialization files
   - URI source files
   - scripts
   - Git repository (.git)
   - all other project files

2. postgresql/alcalay.dump

   Complete PostgreSQL database dump.

3. postgresql/postgresql_globals.sql

   PostgreSQL roles and global objects.

4. git_status.txt

   Git status at backup time.

5. git_status_full.txt

   Full Git status including untracked files.

6. git_branch.txt

   Current Git branch.

7. git_head.txt

   Current Git HEAD commit.

8. git_recent_commits.txt

   Recent Git commits.

------------------------------------------------------------
EXCLUDED
------------------------------------------------------------

- .venv/
- venv/
- env/
- __pycache__/
- *.pyc
- *.pyo
- .DS_Store
- Thumbs.db
- desktop.ini
- backups/

The backups directory is excluded to prevent recursive backups.

------------------------------------------------------------
IMPORTANT
------------------------------------------------------------

This backup is independent from previous backups.

Existing backups are NOT deleted or overwritten.

Backup name:
$BACKUP_NAME

EOF

echo "[OK] Backup information saved."

# ------------------------------------------------------------
# 7. Verify backup contents
# ------------------------------------------------------------

echo "[7/8] Verifying backup..."

if [ ! -d "$TEMP_DIR/project" ]; then
    echo "[ERROR] Project backup directory was not created."
    rm -rf "$TEMP_DIR"
    exit 1
fi

if [ ! -d "$TEMP_DIR/project/src" ]; then
    echo "[ERROR] src/ was not copied."
    rm -rf "$TEMP_DIR"
    exit 1
fi

if [ ! -d "$TEMP_DIR/project/storage" ]; then
    echo "[ERROR] storage/ was not copied."
    rm -rf "$TEMP_DIR"
    exit 1
fi

if [ ! -f "$TEMP_DIR/postgresql/alcalay.dump" ]; then
    echo "[ERROR] PostgreSQL dump was not created."
    rm -rf "$TEMP_DIR"
    exit 1
fi

if [ ! -f "$TEMP_DIR/postgresql/postgresql_globals.sql" ]; then
    echo "[ERROR] PostgreSQL globals dump was not created."
    rm -rf "$TEMP_DIR"
    exit 1
fi

if [ ! -f "$TEMP_DIR/BACKUP_INFO.txt" ]; then
    echo "[ERROR] BACKUP_INFO.txt was not created."
    rm -rf "$TEMP_DIR"
    exit 1
fi

if [ -d "$PROJECT_ROOT/.git" ]; then
    if [ ! -d "$TEMP_DIR/project/.git" ]; then
        echo "[ERROR] Git repository was expected but .git was not copied."
        rm -rf "$TEMP_DIR"
        exit 1
    fi
fi

echo "[OK] Backup contents verified."

# ------------------------------------------------------------
# 8. Create unique archive
# ------------------------------------------------------------

echo "[8/8] Creating unique backup archive..."

mv "$TEMP_DIR" "$BACKUP_DIR"

ditto -c -k \
    --sequesterRsrc \
    --keepParent \
    "$BACKUP_DIR" \
    "$ZIP_FILE"

if [ ! -f "$ZIP_FILE" ]; then
    echo "[ERROR] ZIP archive was not created."
    exit 1
fi

# ------------------------------------------------------------
# Final verification
# ------------------------------------------------------------

echo
echo "------------------------------------------------------------"
echo "FINAL BACKUP VERIFICATION"
echo "------------------------------------------------------------"

BACKUP_SIZE=$(du -sh "$BACKUP_DIR" | awk '{print $1}')
ZIP_SIZE=$(du -h "$ZIP_FILE" | awk '{print $1}')

PROJECT_FILE_COUNT=$(find "$BACKUP_DIR/project" -type f 2>/dev/null | wc -l | tr -d ' ')
PROJECT_DIR_COUNT=$(find "$BACKUP_DIR/project" -type d 2>/dev/null | wc -l | tr -d ' ')

echo "Project files : $PROJECT_FILE_COUNT"
echo "Project dirs  : $PROJECT_DIR_COUNT"
echo "Folder size   : $BACKUP_SIZE"
echo "ZIP size      : $ZIP_SIZE"

echo
echo "============================================================"
echo "BACKUP COMPLETED SUCCESSFULLY"
echo "============================================================"
echo

echo "Backup name:"
echo "$BACKUP_NAME"

echo
echo "Backup folder:"
echo "$BACKUP_DIR"

echo
echo "Backup ZIP:"
echo "$ZIP_FILE"

echo
echo "Previous backups were NOT modified."
echo

ls -lh "$ZIP_FILE"

echo
echo "All backup files currently available:"
echo

find "$BACKUP_ROOT" \
    -maxdepth 1 \
    -type f \
    -name "alcalay_*.zip" \
    -print \
    | sort

echo
echo "============================================================"
echo
