from __future__ import annotations

import os
import shutil
import socket
from dataclasses import dataclass
from typing import Any


@dataclass
class DatabaseResult:
    success: bool
    message: str
    database_exists: bool = False
    user_exists: bool = False
    connection_ok: bool = False
    psql_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "database_exists": self.database_exists,
            "user_exists": self.user_exists,
            "connection_ok": self.connection_ok,
            "psql_available": self.psql_available,
        }


def find_psql() -> str | None:
    """
    Locate the PostgreSQL command-line client.
    """

    return shutil.which("psql")


def postgres_port_open(
    host: str,
    port: int,
    timeout: float = 2.0,
) -> bool:
    """
    Check whether PostgreSQL's TCP endpoint is reachable.

    This does not authenticate and does not modify PostgreSQL.
    """

    try:
        with socket.create_connection(
            (host, port),
            timeout=timeout,
        ):
            return True

    except OSError:
        return False


def get_environment_password() -> str:
    """
    Read the PostgreSQL password from the environment.

    The password is never stored in the Alcalay configuration.
    """

    return os.environ.get(
        "ALCALAY_POSTGRES_PASSWORD",
        "",
    )


def check_postgresql(
    configuration: dict[str, Any],
) -> DatabaseResult:
    """
    Check the PostgreSQL environment.

    Checks:
        - psql availability
        - PostgreSQL TCP connectivity

    Does NOT:
        - create a database
        - create a user
        - modify permissions
        - execute schema migrations
        - store passwords
    """

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
                5432,
            )
        )

    except (TypeError, ValueError):
        return DatabaseResult(
            success=False,
            message="Invalid PostgreSQL port.",
            psql_available=(
                find_psql() is not None
            ),
        )

    psql = find_psql()

    if psql is None:
        return DatabaseResult(
            success=False,
            message=(
                "PostgreSQL command-line tool "
                "'psql' was not found."
            ),
            psql_available=False,
        )

    port_ok = postgres_port_open(
        host,
        port,
    )

    if not port_ok:
        return DatabaseResult(
            success=False,
            message=(
                f"PostgreSQL is not reachable "
                f"at {host}:{port}."
            ),
            psql_available=True,
            connection_ok=False,
        )

    return DatabaseResult(
        success=True,
        message=(
            f"PostgreSQL endpoint is reachable "
            f"at {host}:{port}."
        ),
        psql_available=True,
        connection_ok=True,
    )


def check_postgresql_dict(
    configuration: dict[str, Any],
) -> dict[str, Any]:
    """
    Convenience function for the setup UI.
    """

    return check_postgresql(
        configuration
    ).to_dict()


if __name__ == "__main__":
    print("Alcalay PostgreSQL Setup Check")
    print("=" * 60)

    psql = find_psql()

    if psql:
        print(f"psql: {psql}")
    else:
        print("psql: NOT FOUND")

    host = "localhost"
    port = 5432

    reachable = postgres_port_open(
        host,
        port,
    )

    print(
        f"PostgreSQL endpoint "
        f"{host}:{port}: "
        f"{'REACHABLE' if reachable else 'NOT REACHABLE'}"
    )

    print()
    print(
        "No database or user was created."
    )
    print(
        "No PostgreSQL configuration was modified."
    )