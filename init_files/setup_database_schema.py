from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


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


def find_migrations_root(
    configuration: dict[str, Any],
) -> Path:
    """
    Locate the Alcalay database migrations directory.

    The directory is expected to be:

        <app_root>/database/migrations
    """

    paths = configuration.get(
        "paths",
        {},
    )

    app_root = paths.get(
        "app_root"
    )

    if not app_root:
        raise ValueError(
            "Missing paths.app_root in configuration."
        )

    return (
        Path(app_root)
        / "database"
        / "migrations"
    )


def discover_migrations(
    configuration: dict[str, Any],
) -> list[Path]:
    """
    Discover SQL migration files.

    Migration files are sorted by filename so they can
    later be applied in deterministic order.
    """

    migrations_root = find_migrations_root(
        configuration
    )

    if not migrations_root.exists():
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


def validate_migration_names(
    migrations: list[Path],
) -> SchemaResult:
    """
    Validate migration filenames.

    Duplicate filenames are impossible within one directory,
    but this function also verifies that every migration has
    a non-empty filename.
    """

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

    return SchemaResult(
        success=True,
        message=(
            f"Found {len(migrations)} database migration(s)."
        ),
        migration_count=len(migrations),
    )


def check_schema(
    configuration: dict[str, Any],
) -> SchemaResult:
    """
    Check the Alcalay migration structure.

    This function does NOT execute SQL.
    """

    try:
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
        migrations_root = find_migrations_root(
            configuration
        )

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
            f"Database migration structure is valid. "
            f"Found {len(migrations)} migration(s)."
        ),
        migration_count=len(migrations),
        migrations_applied=0,
    )


def check_schema_dict(
    configuration: dict[str, Any],
) -> dict[str, Any]:
    """
    Convenience function for the setup UI.
    """

    return check_schema(
        configuration
    ).to_dict()


if __name__ == "__main__":
    print("Alcalay Database Schema Check")
    print("=" * 60)
    print(
        "This module checks migration files only."
    )
    print(
        "No SQL is executed."
    )