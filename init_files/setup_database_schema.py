from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

CURRENT_FILE = Path(__file__).resolve()

# init_files/setup_database_schema.py
# parents[0] = init_files
# parents[1] = alcalay project root
PROJECT_ROOT = CURRENT_FILE.parents[1]

MIGRATIONS_ROOT = PROJECT_ROOT / "database" / "migrations"


# ---------------------------------------------------------------------------
# Result object
# ---------------------------------------------------------------------------

@dataclass
class SchemaResult:
    success: bool
    message: str
    migration_count: int = 0
    migrations_applied: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "migration_count": self.migration_count,
            "migrations_applied": self.migrations_applied,
        }


# ---------------------------------------------------------------------------
# Migration location
# ---------------------------------------------------------------------------

def find_migrations_root(
    configuration: dict[str, Any],
) -> Path:
    """
    Locate the Alcalay database migrations directory.

    Migrations are part of the Alcalay source repository and therefore
    live under:

        <project_root>/database/migrations

    They are intentionally NOT stored under AlcalayServer, which is
    reserved for runtime data and configuration.

    The configuration argument is retained for compatibility with the
    setup orchestrator and existing callers.
    """

    return MIGRATIONS_ROOT


# ---------------------------------------------------------------------------
# Migration discovery
# ---------------------------------------------------------------------------

def discover_migrations(
    configuration: dict[str, Any],
) -> list[Path]:
    """
    Discover SQL migration files.

    Migration files are sorted by filename so they can later be applied
    in deterministic order.

    This function only discovers files.
    It does NOT execute SQL.
    """

    migrations_root = find_migrations_root(
        configuration
    )

    if not migrations_root.exists():
        return []

    if not migrations_root.is_dir():
        return []

    return sorted(
        (
            path
            for path in migrations_root.iterdir()
            if path.is_file()
            and path.suffix.lower() == ".sql"
        ),
        key=lambda path: path.name,
    )


# ---------------------------------------------------------------------------
# Migration filename validation
# ---------------------------------------------------------------------------

def validate_migration_names(
    migrations: list[Path],
) -> SchemaResult:
    """
    Validate migration filenames.

    Every migration must have a non-empty filename stem.

    Duplicate filenames are not possible within one directory, but the
    list is still checked explicitly so the validation remains clear
    and deterministic.
    """

    seen_names: set[str] = set()

    for migration in migrations:
        if not migration.stem.strip():
            return SchemaResult(
                success=False,
                message=(
                    f"Invalid migration filename: "
                    f"{migration.name}"
                ),
                migration_count=len(migrations),
            )

        filename = migration.name

        if filename in seen_names:
            return SchemaResult(
                success=False,
                message=(
                    f"Duplicate migration filename: "
                    f"{filename}"
                ),
                migration_count=len(migrations),
            )

        seen_names.add(filename)

    return SchemaResult(
        success=True,
        message=(
            f"Found {len(migrations)} database migration(s)."
        ),
        migration_count=len(migrations),
    )


# ---------------------------------------------------------------------------
# Schema structure check
# ---------------------------------------------------------------------------

def check_schema(
    configuration: dict[str, Any],
) -> SchemaResult:
    """
    Check the Alcalay migration structure.

    This function does NOT connect to PostgreSQL.
    This function does NOT execute SQL.

    It only verifies that the migration directory can be located and
    that its SQL migration files have valid filenames.
    """

    try:
        migrations_root = find_migrations_root(
            configuration
        )

        migrations = discover_migrations(
            configuration
        )

    except Exception as exc:
        return SchemaResult(
            success=False,
            message=(
                f"Could not locate migrations: {exc}"
            ),
        )

    if not migrations:
        return SchemaResult(
            success=True,
            message=(
                "No database migrations exist yet. "
                f"Expected directory: {migrations_root}"
            ),
            migration_count=0,
            migrations_applied=0,
        )

    validation = validate_migration_names(
        migrations
    )

    if not validation.success:
        return validation

    return SchemaResult(
        success=True,
        message=(
            "Database migration structure is valid. "
            f"Found {len(migrations)} migration(s) in "
            f"{migrations_root}."
        ),
        migration_count=len(migrations),
        migrations_applied=0,
    )


# ---------------------------------------------------------------------------
# Dictionary convenience function
# ---------------------------------------------------------------------------

def check_schema_dict(
    configuration: dict[str, Any],
) -> dict[str, Any]:
    """
    Convenience function for the setup UI.
    """

    return check_schema(
        configuration
    ).to_dict()


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Alcalay Database Schema Check")
    print("=" * 60)

    print(
        f"Project root: {PROJECT_ROOT}"
    )

    print(
        f"Migrations root: {MIGRATIONS_ROOT}"
    )

    print()

    print(
        "This module checks migration files only."
    )

    print(
        "No SQL is executed."
    )

    print()

    result = check_schema({})

    print(
        f"Success: {result.success}"
    )

    print(
        f"Message: {result.message}"
    )

    print(
        f"Migrations found: {result.migration_count}"
    )