from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alcalay_server_setup import (
    create_server_directories,
    validate_configuration,
    write_configuration,
)


@dataclass
class InstallResult:
    success: bool
    message: str
    directories_created: bool = False
    configuration_written: bool = False
    validation_passed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "directories_created": self.directories_created,
            "configuration_written": self.configuration_written,
            "validation_passed": self.validation_passed,
        }


def prepare_server(
    configuration: dict[str, Any],
) -> InstallResult:
    """
    Prepare the Alcalay server filesystem and configuration.

    This function:
        1. Validates the basic configuration.
        2. Creates the required server directories.
        3. Writes alcalay_config.json.
        4. Writes .env.example.

    This function does NOT:
        - install Python
        - install PostgreSQL
        - create PostgreSQL databases
        - create PostgreSQL users
        - configure OAuth
        - synchronize Gmail
        - synchronize Google Drive
        - start the Alcalay API
        - start operating-system services
    """

    # ---------------------------------------------------------
    # Step 1: Basic configuration validation
    # ---------------------------------------------------------

    validation = validate_configuration(
        configuration
    )

    if not validation.get("valid", False):
        failed_items = [
            item
            for item in validation.get(
                "results",
                [],
            )
            if not item.get("success", False)
        ]

        messages = [
            item.get(
                "message",
                "Unknown validation error.",
            )
            for item in failed_items
        ]

        return InstallResult(
            success=False,
            message=(
                "Configuration validation failed: "
                + " | ".join(messages)
            ),
            directories_created=False,
            configuration_written=False,
            validation_passed=False,
        )

    # ---------------------------------------------------------
    # Step 2: Create server directories
    # ---------------------------------------------------------

    try:
        create_server_directories(
            configuration
        )

        directories_created = True

    except Exception as exc:
        return InstallResult(
            success=False,
            message=(
                "Failed to create server directories: "
                f"{exc}"
            ),
            directories_created=False,
            configuration_written=False,
            validation_passed=True,
        )

    # ---------------------------------------------------------
    # Step 3: Write configuration
    # ---------------------------------------------------------

    try:
        config_path = write_configuration(
            configuration
        )

        configuration_written = True

    except Exception as exc:
        return InstallResult(
            success=False,
            message=(
                "Server directories were created, "
                "but configuration could not be written: "
                f"{exc}"
            ),
            directories_created=directories_created,
            configuration_written=False,
            validation_passed=True,
        )

    # ---------------------------------------------------------
    # Step 4: Success
    # ---------------------------------------------------------

    return InstallResult(
        success=True,
        message=(
            "Alcalay server preparation completed. "
            f"Configuration written to: {config_path}"
        ),
        directories_created=directories_created,
        configuration_written=configuration_written,
        validation_passed=True,
    )


def prepare_server_dict(
    configuration: dict[str, Any],
) -> dict[str, Any]:
    """
    Convenience function for the graphical setup UI.
    """

    result = prepare_server(
        configuration
    )

    return result.to_dict()


def configuration_file_path(
    configuration: dict[str, Any],
) -> Path:
    """
    Return the expected Alcalay configuration path.

    This does not create the directory or file.
    """

    paths = configuration.get(
        "paths",
        {},
    )

    config_root = paths.get(
        "config_root"
    )

    if not config_root:
        raise ValueError(
            "Configuration path is missing: "
            "paths.config_root"
        )

    return (
        Path(config_root)
        / "alcalay_config.json"
    )


if __name__ == "__main__":
    print(
        "Alcalay Setup Installer"
    )
    print("=" * 60)
    print(
        "This module is used by the setup UI."
    )
    print(
        "It prepares the filesystem and writes "
        "the Alcalay configuration."
    )