from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alcalay_server_setup import (
    DEFAULT_API_PORT,
    DEFAULT_POSTGRES_PORT,
    is_valid_port,
    tcp_test,
)


@dataclass
class ValidationItem:
    name: str
    success: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "success": self.success,
            "message": self.message,
        }


def validate_paths(
    configuration: dict[str, Any],
) -> list[ValidationItem]:
    results: list[ValidationItem] = []

    paths = configuration.get("paths", {})

    required_paths = {
        "app_root": "Application root",
        "data_root": "Data root",
        "documents_root": "Documents root",
        "search_index_root": "Search index root",
        "backups_root": "Backups root",
        "logs_root": "Logs root",
        "config_root": "Configuration root",
    }

    for key, description in required_paths.items():
        value = paths.get(key)

        if not value:
            results.append(
                ValidationItem(
                    name=key,
                    success=False,
                    message=f"{description} is not configured.",
                )
            )
            continue

        path = Path(value).expanduser()

        if path.exists():
            results.append(
                ValidationItem(
                    name=key,
                    success=True,
                    message=f"{description}: {path}",
                )
            )
        else:
            results.append(
                ValidationItem(
                    name=key,
                    success=True,
                    message=(
                        f"{description} does not exist yet "
                        f"but is configured: {path}"
                    ),
                )
            )

    return results


def validate_ports(
    configuration: dict[str, Any],
) -> list[ValidationItem]:
    results: list[ValidationItem] = []

    server = configuration.get("server", {})
    postgres = configuration.get("postgresql", {})

    api_port = server.get(
        "api_port",
        DEFAULT_API_PORT,
    )

    postgres_port = postgres.get(
        "port",
        DEFAULT_POSTGRES_PORT,
    )

    try:
        api_port = int(api_port)

        results.append(
            ValidationItem(
                name="api_port",
                success=is_valid_port(api_port),
                message=f"API port: {api_port}",
            )
        )

    except (TypeError, ValueError):
        results.append(
            ValidationItem(
                name="api_port",
                success=False,
                message="API port is not a valid number.",
            )
        )

    try:
        postgres_port = int(postgres_port)

        results.append(
            ValidationItem(
                name="postgres_port",
                success=is_valid_port(postgres_port),
                message=f"PostgreSQL port: {postgres_port}",
            )
        )

    except (TypeError, ValueError):
        results.append(
            ValidationItem(
                name="postgres_port",
                success=False,
                message="PostgreSQL port is not a valid number.",
            )
        )

    return results


def validate_postgresql(
    configuration: dict[str, Any],
) -> list[ValidationItem]:
    results: list[ValidationItem] = []

    postgres = configuration.get(
        "postgresql",
        {},
    )

    host = postgres.get(
        "host",
        "localhost",
    )

    try:
        port = int(
            postgres.get(
                "port",
                DEFAULT_POSTGRES_PORT,
            )
        )
    except (TypeError, ValueError):
        results.append(
            ValidationItem(
                name="postgresql_connection",
                success=False,
                message="Invalid PostgreSQL port.",
            )
        )
        return results

    reachable, message = tcp_test(
        host,
        port,
    )

    results.append(
        ValidationItem(
            name="postgresql_connection",
            success=reachable,
            message=(
                f"PostgreSQL {host}:{port} "
                f"{'is reachable' if reachable else 'is not reachable'}."
            ),
        )
    )

    if not reachable:
        results.append(
            ValidationItem(
                name="postgresql_note",
                success=True,
                message=(
                    "PostgreSQL is not reachable. "
                    "This is acceptable during initial setup "
                    "if PostgreSQL has not been installed or started yet."
                ),
            )
        )

    return results


def validate_git() -> ValidationItem:
    import shutil

    git_path = shutil.which("git")

    if git_path:
        return ValidationItem(
            name="git",
            success=True,
            message=f"Git found: {git_path}",
        )

    return ValidationItem(
        name="git",
        success=False,
        message="Git executable was not found.",
    )


def validate_security(
    configuration: dict[str, Any],
) -> list[ValidationItem]:
    results: list[ValidationItem] = []

    security = configuration.get(
        "security",
        {},
    )

    authentication_required = bool(
        security.get(
            "authentication_required",
            True,
        )
    )

    tls_required = bool(
        security.get(
            "tls_required",
            True,
        )
    )

    results.append(
        ValidationItem(
            name="authentication",
            success=authentication_required,
            message=(
                "Authentication is required."
                if authentication_required
                else "Authentication requirement is disabled."
            ),
        )
    )

    results.append(
        ValidationItem(
            name="tls",
            success=tls_required,
            message=(
                "TLS is required."
                if tls_required
                else "TLS requirement is disabled."
            ),
        )
    )

    return results


def validate_gmail_policy(
    configuration: dict[str, Any],
) -> list[ValidationItem]:
    results: list[ValidationItem] = []

    sources = configuration.get(
        "sources",
        {},
    )

    gmail = sources.get(
        "gmail",
        {},
    )

    policy = gmail.get(
        "global_policy",
        {},
    )

    sync_entire_mailbox = bool(
        policy.get(
            "sync_entire_mailbox",
            False,
        )
    )

    selected_labels_only = bool(
        policy.get(
            "sync_selected_labels_only",
            True,
        )
    )

    incremental = bool(
        policy.get(
            "incremental",
            True,
        )
    )

    history_id_enabled = bool(
        policy.get(
            "history_id_enabled",
            True,
        )
    )

    results.append(
        ValidationItem(
            name="gmail_full_mailbox",
            success=not sync_entire_mailbox,
            message=(
                "Full mailbox synchronization is disabled."
                if not sync_entire_mailbox
                else "Full mailbox synchronization is enabled."
            ),
        )
    )

    results.append(
        ValidationItem(
            name="gmail_selected_labels",
            success=selected_labels_only,
            message=(
                "Gmail synchronization uses selected labels only."
                if selected_labels_only
                else "Selected-label-only Gmail policy is disabled."
            ),
        )
    )

    results.append(
        ValidationItem(
            name="gmail_incremental",
            success=incremental,
            message=(
                "Incremental Gmail synchronization is enabled."
                if incremental
                else "Incremental Gmail synchronization is disabled."
            ),
        )
    )

    results.append(
        ValidationItem(
            name="gmail_history_id",
            success=history_id_enabled,
            message=(
                "Gmail historyId tracking is enabled."
                if history_id_enabled
                else "Gmail historyId tracking is disabled."
            ),
        )
    )

    return results


def validate_server(
    configuration: dict[str, Any],
) -> list[ValidationItem]:
    results: list[ValidationItem] = []

    application = configuration.get(
        "application",
        {},
    )

    server = configuration.get(
        "server",
        {},
    )

    if not application:
        results.append(
            ValidationItem(
                name="application",
                success=False,
                message="Application configuration is missing.",
            )
        )
    else:
        results.append(
            ValidationItem(
                name="application",
                success=True,
                message="Application configuration exists.",
            )
        )

    host = server.get("host")

    results.append(
        ValidationItem(
            name="server_host",
            success=bool(host),
            message=(
                f"Server host: {host}"
                if host
                else "Server host is missing."
            ),
        )
    )

    api_port = server.get(
        "api_port",
        DEFAULT_API_PORT,
    )

    try:
        api_port = int(api_port)

        results.append(
            ValidationItem(
                name="server_api_port",
                success=is_valid_port(api_port),
                message=f"Server API port: {api_port}",
            )
        )

    except (TypeError, ValueError):
        results.append(
            ValidationItem(
                name="server_api_port",
                success=False,
                message="Server API port is invalid.",
            )
        )

    return results


def validate_configuration(
    configuration: dict[str, Any],
) -> list[ValidationItem]:
    """
    Perform machine/environment validation of an Alcalay
    server configuration.

    This function validates configuration and environment
    readiness only.

    It does NOT:
        - install PostgreSQL
        - create PostgreSQL databases
        - create PostgreSQL users
        - perform OAuth
        - download Gmail messages
        - download Google Drive files
        - start the Alcalay API
    """

    results: list[ValidationItem] = []

    results.extend(
        validate_server(
            configuration
        )
    )

    results.extend(
        validate_paths(
            configuration
        )
    )

    results.extend(
        validate_ports(
            configuration
        )
    )

    results.extend(
        validate_postgresql(
            configuration
        )
    )

    results.append(
        validate_git()
    )

    results.extend(
        validate_security(
            configuration
        )
    )

    results.extend(
        validate_gmail_policy(
            configuration
        )
    )

    return results


def validation_summary(
    results: list[ValidationItem],
) -> dict[str, Any]:
    """
    Convert validation results into a compact summary.
    """

    total = len(results)

    successful = sum(
        1
        for result in results
        if result.success
    )

    failed = total - successful

    return {
        "valid": failed == 0,
        "total": total,
        "successful": successful,
        "failed": failed,
        "results": [
            result.to_dict()
            for result in results
        ],
    }


def validate_configuration_dict(
    configuration: dict[str, Any],
) -> dict[str, Any]:
    """
    Convenience function for the graphical UI.
    """

    results = validate_configuration(
        configuration
    )

    return validation_summary(
        results
    )


if __name__ == "__main__":
    print(
        "Alcalay Setup Validator"
    )
    print("=" * 60)
    print(
        "This module is used by the setup UI."
    )
    print(
        "It requires a configuration dictionary "
        "to perform validation."
    )