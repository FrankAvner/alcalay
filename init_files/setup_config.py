from __future__ import annotations

from pathlib import Path
from typing import Any

from alcalay_server_setup import (
    build_configuration,
    load_configuration,
    write_configuration,
)


CONFIG_FILENAME = "alcalay_config.json"


def configuration_path(
    server_root: str | Path,
) -> Path:
    """
    Return the canonical Alcalay configuration path.
    """

    root = Path(
        server_root
    ).expanduser()

    return (
        root
        / "config"
        / CONFIG_FILENAME
    )


def build_setup_configuration(
    ui_state: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the canonical Alcalay configuration from
    setup UI state.

    The actual configuration structure remains owned by
    alcalay_server_setup.py.
    """

    return build_configuration(
        ui_state
    )


def save_setup_configuration(
    configuration: dict[str, Any],
) -> Path:
    """
    Save the canonical Alcalay configuration.

    Returns the actual configuration file path.
    """

    return write_configuration(
        configuration
    )


def load_setup_configuration(
    server_root: str | Path,
) -> dict[str, Any] | None:
    """
    Load an existing Alcalay configuration.

    Returns None when the configuration file does not exist.
    """

    path = configuration_path(
        server_root
    )

    if not path.exists():
        return None

    return load_configuration(
        path
    )


def configuration_exists(
    server_root: str | Path,
) -> bool:
    """
    Check whether an Alcalay configuration exists.
    """

    return configuration_path(
        server_root
    ).is_file()


def configuration_summary(
    configuration: dict[str, Any],
) -> dict[str, Any]:
    """
    Return a safe summary of the configuration.

    Secrets and passwords are intentionally excluded.
    """

    application = configuration.get(
        "application",
        {},
    )

    server = configuration.get(
        "server",
        {},
    )

    paths = configuration.get(
        "paths",
        {},
    )

    postgres = configuration.get(
        "postgresql",
        {},
    )

    sources = configuration.get(
        "sources",
        {},
    )

    gmail = sources.get(
        "gmail",
        {},
    )

    accounts = gmail.get(
        "accounts",
        [],
    )

    return {
        "application": application.get(
            "name",
            "Alcalay",
        ),
        "server_host": server.get(
            "host",
        ),
        "api_port": server.get(
            "api_port",
        ),
        "server_root": paths.get(
            "server_root",
            paths.get("app_root"),
        ),
        "config_root": paths.get(
            "config_root",
        ),
        "postgres_host": postgres.get(
            "host",
        ),
        "postgres_port": postgres.get(
            "port",
        ),
        "postgres_database": postgres.get(
            "database",
        ),
        "gmail_enabled": gmail.get(
            "enabled",
            False,
        ),
        "gmail_account_count": len(accounts)
            if isinstance(accounts, list)
            else 0,
    }


if __name__ == "__main__":
    print("Alcalay Configuration Setup")
    print("=" * 60)
    print(
        "Configuration helper module loaded successfully."
    )
    print(
        "Secrets are never included in configuration summaries."
    )