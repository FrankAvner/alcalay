#!/bin/bash

set -e

PROJECT_ROOT="$HOME/alcalay"
BACKUP_ROOT="$PROJECT_ROOT/backups"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

TEMP_DIR="$BACKUP_ROOT/.backup_tmp_$TIMESTAMP"
BACKUP_DIR="$BACKUP_ROOT/alcalay_latest"
ZIP_FILE="$BACKUP_ROOT/alcalay_latest.zip"

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
echo

if [ ! -d "$PROJECT_ROOT" ]; then
    echo "[ERROR] Project directory does not exist:"
    echo "$PROJECT_ROOT"
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

mkdir -p "$BACKUP_ROOT"

echo "[1/7] Preparing temporary backup directory..."

rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

echo "[2/7] Copying Alcalay project code..."

mkdir -p "$TEMP_DIR/project"

rsync -a \
    --exclude=".git/" \
    --exclude=".venv/" \
    --exclude="venv/" \
    --exclude="env/" \
    --exclude="__pycache__/" \
    --exclude="*.pyc" \
    --exclude="*.pyo" \
    --exclude=".DS_Store" \
    --exclude="data/" \
    --exclude="documents/" \
    --exclude="backups/" \
    --exclude="logs/" \
    --exclude="search_index/" \
    --exclude="indexes/" \
    --exclude="models/" \
    --exclude="*.db" \
    --exclude="*.sqlite" \
    --exclude="*.sqlite3" \
    --exclude="config/alcalay_config.json" \
    --exclude="config/*.json" \
    "$PROJECT_ROOT/" \
    "$TEMP_DIR/project/"

echo "[OK] Project code copied."

echo
echo "[3/7] Saving Git information..."

cd "$PROJECT_ROOT"

git status --short > "$TEMP_DIR/git_status.txt" 2>&1 || true
git branch --show-current > "$TEMP_DIR/git_branch.txt" 2>&1 || true
git log -10 --oneline > "$TEMP_DIR/git_recent_commits.txt" 2>&1 || true
git rev-parse HEAD > "$TEMP_DIR/git_head.txt" 2>&1 || true

echo "[OK] Git information saved."

echo
echo "[4/7] PostgreSQL database backup..."

mkdir -p "$TEMP_DIR/postgresql"

echo
echo "PostgreSQL password is required if your PostgreSQL setup does not"
echo "already provide authentication through .pgpass."
echo

if [ -z "$PGPASSWORD" ]; then
    read -s -p "PostgreSQL password: " PGPASSWORD
    echo
    export PGPASSWORD
fi

pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$USER" \
    -d "$DB_NAME" \
    --format=custom \
    --file="$TEMP_DIR/postgresql/alcalay.dump"

echo "[OK] PostgreSQL database dumped."

echo
echo "[5/7] PostgreSQL roles and global objects..."

pg_dumpall \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$USER" \
    --globals-only \
    > "$TEMP_DIR/postgresql/postgresql_globals.sql"

echo "[OK] PostgreSQL globals saved."

unset PGPASSWORD

echo
echo "[6/7] Saving backup information..."

cat > "$TEMP_DIR/BACKUP_INFO.txt" <<EOF
ALCALAY FULL BACKUP

Backup timestamp:
$TIMESTAMP

Project:
$PROJECT_ROOT

PostgreSQL database:
$DB_NAME

PostgreSQL host:
$DB_HOST

PostgreSQL port:
$DB_PORT

Contents:

1. project/
   Alcalay source code and project files.

2. postgresql/alcalay.dump
   Complete PostgreSQL dump of the Alcalay database.

3. postgresql/postgresql_globals.sql
   PostgreSQL roles and global objects.

4. git_status.txt
   Git working tree status at backup time.

5. git_branch.txt
   Current Git branch.

6. git_head.txt
   Current Git commit.

7. git_recent_commits.txt
   Last 10 Git commits.

Excluded from this backup:

- .git/
- .venv/
- Python cache files
- runtime data/
- documents/
- logs/
- search_index/
- indexes/
- models/
- existing backups/
- local JSON configuration containing secrets
- SQLite runtime databases
EOF

echo "[OK] Backup information saved."

echo
echo "[7/7] Creating new backup archive..."

rm -rf "$BACKUP_DIR"
rm -f "$ZIP_FILE"

mv "$TEMP_DIR" "$BACKUP_DIR"

cd "$BACKUP_ROOT"

ditto -c -k --sequesterRsrc --keepParent \
    "$BACKUP_DIR" \
    "$BACKUP_ROOT/alcalay_latest.zip"

echo "[OK] New backup archive created."

echo
echo "============================================================"
echo "BACKUP COMPLETED SUCCESSFULLY"
echo "============================================================"
echo
echo "Folder:"
echo "$BACKUP_DIR"
echo
echo "ZIP:"
echo "$ZIP_FILE"
echo
echo "The previous backup has been replaced."
echo
ls -lh "$ZIP_FILE"
echo
