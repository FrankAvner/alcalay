from __future__ import annotations

import json
import os
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


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

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


def tcp_test(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    """
    Test whether a TCP endpoint can be reached.

    This does NOT authenticate to PostgreSQL.
    It only verifies TCP connectivity.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"TCP connection successful: {host}:{port}"
    except socket.timeout:
        return False, f"Connection timeout: {host}:{port}"
    except OSError as exc:
        return False, f"Connection failed: {exc}"


# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

def default_server_root(server_os: str | None = None) -> Path:
    """
    Return a sensible default server root for the selected server OS.

    The path is only a configuration default. It is not automatically used
    to perform remote operations on another machine.
    """
    selected_os = (server_os or platform.system()).strip().lower()

    if selected_os in {"windows", "win32", "win"}:
        return Path(r"C:\AlcalayServer")

    return Path.home() / "AlcalayServer"


# ---------------------------------------------------------------------------
# Configuration construction
# ---------------------------------------------------------------------------

def build_configuration(ui_state: dict[str, Any]) -> dict[str, Any]:
    """
    Convert the flat UI state into the canonical Alcalay configuration.

    The UI is intentionally not responsible for the final configuration
    structure. This function is the central mapping point.
    """

    server = ui_state.get("server", {})
    paths = ui_state.get("paths", {})
    postgres = ui_state.get("postgresql", {})
    google_drive = ui_state.get("google_drive", {})
    gmail = ui_state.get("gmail", {})
    processing = ui_state.get("processing", {})
    ocr = ui_state.get("ocr", {})
    ai_ml = ui_state.get("ai_ml", {})
    search = ui_state.get("search", {})
    security = ui_state.get("security", {})

    server_os = server.get("server_os") or platform.system()
    app_root = normalize_path(
        paths.get("server_root")
        or default_server_root(server_os)
    )

    documents_root = normalize_path(
        paths.get("documents")
        or Path(app_root) / "documents"
    )

    index_root = normalize_path(
        paths.get("index")
        or Path(app_root) / "search_index"
    )

    backups_root = normalize_path(
        paths.get("backups")
        or Path(app_root) / "backups"
    )

    logs_root = normalize_path(
        paths.get("logs")
        or Path(app_root) / "logs"
    )

    config_root = normalize_path(
        paths.get("config")
        or Path(app_root) / "config"
    )

    data_root = normalize_path(
        paths.get("data")
        or Path(app_root) / "data"
    )

    runtime_root = normalize_path(
        paths.get("runtime")
        or Path(app_root) / "runtime"
    )

    selected_labels = gmail.get("selected_labels", [])

    if not isinstance(selected_labels, list):
        selected_labels = list(selected_labels or [])

    account_id = gmail.get("account_id") or "gmail_001"

    gmail_account = {
        "account_id": account_id,
        "email": gmail.get("email", "").strip(),
        "enabled": bool(gmail.get("enabled", False)),
        "selected_labels": selected_labels,
        "selected_labels_only": True,
        "download_attachments": bool(
            gmail.get("download_attachments", True)
        ),
        "index_message_body": bool(
            gmail.get("index_message_body", True)
        ),
        "incremental_sync": bool(
            gmail.get("incremental_sync", True)
        ),
        "last_successful_sync": gmail.get("last_successful_sync"),
        "history_id": gmail.get("history_id"),
        "status": gmail.get("status", "not_connected"),
    }

    configuration = {
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
            "name": server.get("server_name", "").strip(),
            "host": server.get("host", "0.0.0.0").strip(),
            "api_port": int(
                server.get("api_port", DEFAULT_API_PORT)
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
            "host": postgres.get("host", "localhost").strip(),
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
            "password_env": "ALCALAY_POSTGRES_PASSWORD",
            "connection_tested": bool(
                postgres.get("connection_tested", False)
            ),
        },

        "sources": {
            "local_server": {
                "enabled": True,
                "root": documents_root,
            },

            "google_drive": {
                "enabled": bool(
                    google_drive.get("enabled", False)
                ),
                "root": google_drive.get(
                    "root",
                    "",
                ).strip(),
                "sync_mode": google_drive.get(
                    "sync_mode",
                    "index_source",
                ),
                "oauth_status": google_drive.get(
                    "oauth_status",
                    "not_connected",
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
                "accounts": [gmail_account],
            },
        },

        "processing": {
            "extract_text": bool(
                processing.get("extract_text", True)
            ),
            "extract_metadata": bool(
                processing.get("extract_metadata", True)
            ),
            "classification": bool(
                processing.get("classification", True)
            ),
            "keywords": bool(
                processing.get("keywords", True)
            ),
            "thesaurus": bool(
                processing.get("thesaurus", True)
            ),
        },

        "ocr": {
            "enabled": bool(
                ocr.get("enabled", True)
            ),
            "language": ocr.get(
                "language",
                "heb+eng",
            ),
            "automatic": bool(
                ocr.get("automatic", True)
            ),
        },

        "ai_ml": {
            "enabled": bool(
                ai_ml.get("enabled", True)
            ),
            "semantic_understanding": bool(
                ai_ml.get(
                    "semantic_understanding",
                    True,
                )
            ),
            "classification": bool(
                ai_ml.get("classification", True)
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
                search.get("full_text", True)
            ),
            "metadata": bool(
                search.get("metadata", True)
            ),
            "semantic": bool(
                search.get("semantic", True)
            ),
            "boolean": bool(
                search.get("boolean", True)
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
            "api_secret_env": "ALCALAY_API_SECRET",
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

    return configuration


# ---------------------------------------------------------------------------
# Filesystem operations
# ---------------------------------------------------------------------------

def create_server_directories(
    configuration: dict[str, Any],
) -> list[Path]:
    """
    Create all directories required by the Alcalay server configuration.

    Returns a list of directories that were created/verified.
    """

    paths = configuration.get("paths", {})
    app_root = Path(paths["app_root"])

    directories = [
        app_root,
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
        result.append(create_directory(directory))

    return result


# ---------------------------------------------------------------------------
# Configuration files
# ---------------------------------------------------------------------------

def write_configuration(
    configuration: dict[str, Any],
) -> tuple[Path, Path]:
    """
    Write the canonical JSON configuration and .env.example.

    Returns:
        (configuration_path, env_example_path)
    """

    paths = configuration.get("paths", {})

    config_directory = create_directory(
        paths["config"]
    )

    configuration_path = (
        config_directory / CONFIG_FILENAME
    )

    env_example_path = (
        config_directory / ENV_EXAMPLE_FILENAME
    )

    configuration_path.write_text(
        json.dumps(
            configuration,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    env_content = """# Alcalay environment variables
# Copy this file to a secure environment configuration.
# DO NOT commit real secrets to Git.

ALCALAY_POSTGRES_PASSWORD=
ALCALAY_API_SECRET=
"""

    env_example_path.write_text(
        env_content,
        encoding="utf-8",
    )

    return configuration_path, env_example_path


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
        path.read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_configuration(
    configuration: dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Validate the canonical configuration.

    This validates configuration and filesystem state only.
    It does not pretend that PostgreSQL, Gmail or Google Drive
    are connected unless they were actually tested.
    """

    errors: list[str] = []

    application = configuration.get("application", {})
    server = configuration.get("server", {})
    paths = configuration.get("paths", {})
    postgres = configuration.get("postgresql", {})
    security = configuration.get("security", {})
    gmail = (
        configuration
        .get("sources", {})
        .get("gmail", {})
    )

    if application.get("name") != APP_NAME:
        errors.append(
            "Application name is invalid."
        )

    server_name = server.get("name", "").strip()
    if not server_name:
        errors.append(
            "Server name is required."
        )

    if not is_valid_port(
        server.get("api_port")
    ):
        errors.append(
            "API port is invalid."
        )

    if not paths.get("app_root"):
        errors.append(
            "Application root is missing."
        )

    for key in (
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

    if security.get("tls_required") is not True:
        errors.append(
            "TLS must be required."
        )

    gmail_policy = gmail.get(
        "global_policy",
        {},
    )

    if gmail_policy.get(
        "sync_entire_mailbox"
    ):
        errors.append(
            "Entire Gmail mailbox synchronization "
            "must remain disabled."
        )

    if not gmail_policy.get(
        "sync_selected_labels_only"
    ):
        errors.append(
            "Gmail selected-label policy is required."
        )

    if not gmail_policy.get(
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


# ---------------------------------------------------------------------------
# Compatibility / terminal entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Terminal entry point.

    The graphical UI does not call this function.
    It exists so the engine can still be used independently
    from a terminal if required.
    """

    print(f"{APP_NAME} Server Setup")
    print("=" * 60)
    print()
    print(
        "The graphical setup UI should be used for interactive setup:"
    )
    print()
    print("    python init_files/setup_ui.py")
    print()
    print(
        "The setup engine is exposed through reusable functions "
        "for the graphical UI."
    )


if __name__ == "__main__":
    main()