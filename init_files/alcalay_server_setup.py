from __future__ import annotations

import json
import platform
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


APP_NAME = "Alcalay"
CONFIG_VERSION = "1.0"

DEFAULT_API_PORT = 8443
DEFAULT_POSTGRES_PORT = 5432

CONFIG_FILENAME = "alcalay_config.json"
ENV_EXAMPLE_FILENAME = ".env.example"


# ============================================================================
# GENERAL
# ============================================================================

def now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def normalize_path(value: str | Path) -> str:
    """Normalize a path without requiring it to exist."""
    return str(Path(value).expanduser())


def create_directory(path: str | Path) -> Path:
    """Create a directory if it does not exist."""
    directory = Path(path).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def is_valid_port(value: Any) -> bool:
    try:
        port = int(value)
        return 1 <= port <= 65535
    except (TypeError, ValueError):
        return False


def tcp_test(
    host: str,
    port: int,
    timeout: float = 3.0,
) -> tuple[bool, str]:
    """
    Test TCP connectivity.

    This does NOT authenticate to PostgreSQL.
    """

    try:
        with socket.create_connection(
            (host, port),
            timeout=timeout,
        ):
            return True, (
                f"TCP connection successful: "
                f"{host}:{port}"
            )

    except socket.timeout:
        return False, (
            f"Connection timeout: "
            f"{host}:{port}"
        )

    except OSError as exc:
        return False, (
            f"Connection failed: {exc}"
        )


# ============================================================================
# DEFAULT SERVER PATHS
# ============================================================================

def default_server_root(
    server_os: str | None = None,
) -> Path:
    """
    Return a platform-appropriate server root.
    """

    selected_os = (
        server_os or platform.system()
    ).strip().lower()

    if selected_os in {
        "windows",
        "win32",
        "win",
    }:
        return Path(r"C:\AlcalayServer")

    return Path.home() / "AlcalayServer"


def build_default_paths(
    server_os: str | None = None,
) -> dict[str, str]:
    """
    Build all default Alcalay server paths.
    """

    root = default_server_root(server_os)

    return {
        "app_root": normalize_path(root),
        "documents": normalize_path(
            root / "documents"
        ),
        "search_index": normalize_path(
            root / "search_index"
        ),
        "backups": normalize_path(
            root / "backups"
        ),
        "logs": normalize_path(
            root / "logs"
        ),
        "config": normalize_path(
            root / "config"
        ),
        "data": normalize_path(
            root / "data"
        ),
        "runtime": normalize_path(
            root / "runtime"
        ),
    }


# ============================================================================
# CONFIGURATION
# ============================================================================

def build_configuration(
    ui_state: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert UI state into canonical Alcalay configuration.

    This function does not:
        - install software
        - connect to PostgreSQL
        - connect to Gmail
        - connect to Google Drive
        - start services

    It only builds configuration.
    """

    server = ui_state.get(
        "server",
        {},
    )

    paths = ui_state.get(
        "paths",
        {},
    )

    postgres = ui_state.get(
        "postgresql",
        {},
    )

    google_drive = ui_state.get(
        "google_drive",
        {},
    )

    gmail = ui_state.get(
        "gmail",
        {},
    )

    processing = ui_state.get(
        "processing",
        {},
    )

    ocr = ui_state.get(
        "ocr",
        {},
    )

    ai_ml = ui_state.get(
        "ai_ml",
        {},
    )

    search = ui_state.get(
        "search",
        {},
    )

    security = ui_state.get(
        "security",
        {},
    )

    server_os = (
        server.get("server_os")
        or platform.system()
    )

    defaults = build_default_paths(
        server_os
    )

    app_root = normalize_path(
        paths.get(
            "server_root",
            defaults["app_root"],
        )
        or defaults["app_root"]
    )

    documents_root = normalize_path(
        paths.get(
            "documents",
            Path(app_root) / "documents",
        )
        or Path(app_root) / "documents"
    )

    index_root = normalize_path(
        paths.get(
            "index",
            Path(app_root) / "search_index",
        )
        or Path(app_root) / "search_index"
    )

    backups_root = normalize_path(
        paths.get(
            "backups",
            Path(app_root) / "backups",
        )
        or Path(app_root) / "backups"
    )

    logs_root = normalize_path(
        paths.get(
            "logs",
            Path(app_root) / "logs",
        )
        or Path(app_root) / "logs"
    )

    config_root = normalize_path(
        paths.get(
            "config",
            Path(app_root) / "config",
        )
        or Path(app_root) / "config"
    )

    data_root = normalize_path(
        paths.get(
            "data",
            Path(app_root) / "data",
        )
        or Path(app_root) / "data"
    )

    runtime_root = normalize_path(
        paths.get(
            "runtime",
            Path(app_root) / "runtime",
        )
        or Path(app_root) / "runtime"
    )

    selected_labels = gmail.get(
        "selected_labels",
        [],
    )

    if not isinstance(
        selected_labels,
        list,
    ):
        selected_labels = list(
            selected_labels or []
        )

    gmail_account = {
        "account_id": (
            gmail.get("account_id")
            or "gmail_001"
        ),
        "email": gmail.get(
            "email",
            "",
        ).strip(),
        "enabled": bool(
            gmail.get(
                "enabled",
                False,
            )
        ),
        "selected_labels": selected_labels,
        "selected_labels_only": True,
        "download_attachments": bool(
            gmail.get(
                "download_attachments",
                True,
            )
        ),
        "index_message_body": bool(
            gmail.get(
                "index_message_body",
                True,
            )
        ),
        "incremental_sync": bool(
            gmail.get(
                "incremental_sync",
                True,
            )
        ),
        "last_successful_sync": gmail.get(
            "last_successful_sync"
        ),
        "history_id": gmail.get(
            "history_id"
        ),
        "status": gmail.get(
            "status",
            "not_connected",
        ),
    }

    return {
        "config_version": CONFIG_VERSION,
        "generated_at": now_iso(),

        "application": {
            "name": APP_NAME,
            "setup_version": ui_state.get(
                "setup_version",
                CONFIG_VERSION,
            ),
        },

        "server": {
            "os": server_os,
            "name": server.get(
                "server_name",
                "",
            ).strip(),
            "host": server.get(
                "host",
                "0.0.0.0",
            ).strip(),
            "api_port": int(
                server.get(
                    "api_port",
                    DEFAULT_API_PORT,
                )
            ),
            "public_hostname": server.get(
                "public_hostname",
                "",
            ).strip(),
        },

        "paths": {
            "app_root": app_root,
            "documents": documents_root,
            "search_index": index_root,
            "backups": backups_root,
            "logs": logs_root,
            "config": config_root,
            "data": data_root,
            "runtime": runtime_root,
        },

        "postgresql": {
            "host": postgres.get(
                "host",
                "localhost",
            ).strip(),
            "port": int(
                postgres.get(
                    "port",
                    DEFAULT_POSTGRES_PORT,
                )
            ),
            "database": postgres.get(
                "database",
                "alcalay",
            ).strip(),
            "user": postgres.get(
                "user",
                "alcalay",
            ).strip(),
            "password_env": (
                "ALCALAY_POSTGRES_PASSWORD"
            ),
            "connection_tested": bool(
                postgres.get(
                    "connection_tested",
                    False,
                )
            ),
        },

        "sources": {
            "local_server": {
                "enabled": True,
                "root": documents_root,
            },

            "google_drive": {
                "enabled": bool(
                    google_drive.get(
                        "enabled",
                        False,
                    )
                ),
                "root": google_drive.get(
                    "root",
                    "",
                ).strip(),
                "sync_mode": google_drive.get(
                    "sync_mode",
                    "index_source",
                ),
                "oauth_status": (
                    google_drive.get(
                        "oauth_status",
                        "not_connected",
                    )
                ),
            },

            "gmail": {
                "global_policy": {
                    "sync_entire_mailbox": False,
                    "sync_selected_labels_only": True,
                    "incremental": True,
                    "history_id_enabled": True,
                    "deduplicate_by_message_id": True,
                    "deduplicate_by_content_hash": True,
                    "manual_full_sync_explicit_only": True,
                },
                "accounts": [
                    gmail_account
                ],
            },
        },

        "processing": {
            "extract_text": bool(
                processing.get(
                    "extract_text",
                    True,
                )
            ),
            "extract_metadata": bool(
                processing.get(
                    "extract_metadata",
                    True,
                )
            ),
            "classification": bool(
                processing.get(
                    "classification",
                    True,
                )
            ),
            "keywords": bool(
                processing.get(
                    "keywords",
                    True,
                )
            ),
            "thesaurus": bool(
                processing.get(
                    "thesaurus",
                    True,
                )
            ),
        },

        "ocr": {
            "enabled": bool(
                ocr.get(
                    "enabled",
                    True,
                )
            ),
            "language": ocr.get(
                "language",
                "heb+eng",
            ),
            "automatic": bool(
                ocr.get(
                    "automatic",
                    True,
                )
            ),
        },

        "ai_ml": {
            "enabled": bool(
                ai_ml.get(
                    "enabled",
                    True,
                )
            ),
            "semantic_understanding": bool(
                ai_ml.get(
                    "semantic_understanding",
                    True,
                )
            ),
            "classification": bool(
                ai_ml.get(
                    "classification",
                    True,
                )
            ),
            "similar_documents": bool(
                ai_ml.get(
                    "similar_documents",
                    True,
                )
            ),
        },

        "search": {
            "full_text": bool(
                search.get(
                    "full_text",
                    True,
                )
            ),
            "metadata": bool(
                search.get(
                    "metadata",
                    True,
                )
            ),
            "semantic": bool(
                search.get(
                    "semantic",
                    True,
                )
            ),
            "boolean": bool(
                search.get(
                    "boolean",
                    True,
                )
            ),
            "reindex_changed_documents": bool(
                search.get(
                    "reindex_changed_documents",
                    True,
                )
            ),
        },

        "security": {
            "authentication_required": bool(
                security.get(
                    "authentication_required",
                    True,
                )
            ),
            "tls_required": bool(
                security.get(
                    "tls_required",
                    True,
                )
            ),
            "api_secret_env": (
                "ALCALAY_API_SECRET"
            ),
        },

        "sync": {
            "incremental": True,
            "full_sync_manual_only": True,
            "deduplication": True,
        },

        "git_policy": {
            "store_source_code": True,
            "store_schema_and_migrations": True,
            "store_config_templates": True,
            "exclude_documents": True,
            "exclude_databases": True,
            "exclude_passwords": True,
            "exclude_oauth_tokens": True,
            "exclude_indexes": True,
            "exclude_models": True,
        },
    }


# ============================================================================
# FILESYSTEM
# ============================================================================

def create_server_directories(
    configuration: dict[str, Any],
) -> list[Path]:
    """
    Create/verify all Alcalay server directories.
    """

    paths = configuration.get(
        "paths",
        {},
    )

    directories = [
        Path(paths["app_root"]),
        Path(paths["documents"]),
        Path(paths["search_index"]),
        Path(paths["backups"]),
        Path(paths["logs"]),
        Path(paths["config"]),
        Path(paths["data"]),
        Path(paths["runtime"]),
    ]

    result: list[Path] = []

    for directory in directories:
        result.append(
            create_directory(directory)
        )

    return result


# ============================================================================
# CONFIG FILES
# ============================================================================

def write_configuration(
    configuration: dict[str, Any],
) -> tuple[Path, Path]:
    """
    Write canonical configuration and .env.example.
    """

    paths = configuration["paths"]

    config_directory = create_directory(
        paths["config"]
    )

    configuration_path = (
        config_directory
        / CONFIG_FILENAME
    )

    env_example_path = (
        config_directory
        / ENV_EXAMPLE_FILENAME
    )

    configuration_path.write_text(
        json.dumps(
            configuration,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    env_example_path.write_text(
        """# Alcalay environment variables
# Copy this file to a secure environment configuration.
# DO NOT commit real secrets to Git.

ALCALAY_POSTGRES_PASSWORD=
ALCALAY_API_SECRET=
""",
        encoding="utf-8",
    )

    return (
        configuration_path,
        env_example_path,
    )


def load_configuration(
    configuration_path: str | Path,
) -> dict[str, Any]:
    """Load an existing Alcalay configuration."""

    path = Path(configuration_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {path}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


# ============================================================================
# BASIC VALIDATION
# ============================================================================

def validate_configuration(
    configuration: dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Validate configuration structure.

    Detailed machine checks are handled by setup_validator.py.
    """

    errors: list[str] = []

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

    security = configuration.get(
        "security",
        {},
    )

    gmail = (
        configuration
        .get("sources", {})
        .get("gmail", {})
    )

    if application.get("name") != APP_NAME:
        errors.append(
            "Application name is invalid."
        )

    if not server.get(
        "name",
        "",
    ).strip():
        errors.append(
            "Server name is required."
        )

    if not is_valid_port(
        server.get("api_port")
    ):
        errors.append(
            "API port is invalid."
        )

    for key in (
        "app_root",
        "documents",
        "search_index",
        "backups",
        "logs",
        "config",
        "data",
        "runtime",
    ):
        if not paths.get(key):
            errors.append(
                f"Path '{key}' is missing."
            )

    if not postgres.get("host"):
        errors.append(
            "PostgreSQL host is missing."
        )

    if not is_valid_port(
        postgres.get("port")
    ):
        errors.append(
            "PostgreSQL port is invalid."
        )

    if not postgres.get("database"):
        errors.append(
            "PostgreSQL database is missing."
        )

    if not postgres.get("user"):
        errors.append(
            "PostgreSQL user is missing."
        )

    if security.get(
        "tls_required"
    ) is not True:
        errors.append(
            "TLS must be required."
        )

    policy = gmail.get(
        "global_policy",
        {},
    )

    if policy.get(
        "sync_entire_mailbox"
    ):
        errors.append(
            "Entire Gmail mailbox synchronization "
            "must remain disabled."
        )

    if not policy.get(
        "sync_selected_labels_only"
    ):
        errors.append(
            "Gmail selected-label policy is required."
        )

    if not policy.get(
        "incremental"
    ):
        errors.append(
            "Gmail incremental synchronization "
            "must be enabled."
        )

    return (
        len(errors) == 0,
        errors,
    )


# ============================================================================
# COMPATIBILITY ENTRY POINT
# ============================================================================

def main() -> None:
    print(f"{APP_NAME} Server Setup")
    print("=" * 60)
    print()
    print(
        "Use the graphical setup UI:"
    )
    print()
    print(
        "    python init_files/setup_ui.py"
    )
    print()
    print(
        "The setup engine is reusable by the UI."
    )


if __name__ == "__main__":
    main()