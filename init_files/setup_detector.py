from __future__ import annotations

import platform
import shutil
import socket
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from alcalay_server_setup import (
    DEFAULT_API_PORT,
    DEFAULT_POSTGRES_PORT,
    default_server_root,
    is_valid_port,
    tcp_test,
)


@dataclass
class DetectionResult:
    operating_system: str
    operating_system_version: str
    machine_name: str

    python_version: str
    python_executable: str

    server_root: str

    api_port: int
    api_port_available: bool

    postgres_host: str
    postgres_port: int
    postgres_tcp_available: bool

    home_directory: str
    disk_free_gb: float

    git_available: bool
    postgres_command_available: bool

    write_test: bool
    write_test_message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def port_available(
    host: str,
    port: int,
) -> bool:
    """
    Check whether a TCP port appears to be available.

    True means that nothing appears to be listening
    on the specified endpoint.
    """

    if not is_valid_port(port):
        return False

    try:
        with socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        ) as sock:

            sock.settimeout(0.5)

            result = sock.connect_ex(
                (host, port)
            )

            return result != 0

    except OSError:
        return False


def test_write_access(
    directory: Path,
) -> tuple[bool, str]:
    """
    Verify that the specified directory can be created
    and that the current user can write to it.
    """

    try:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        test_file = (
            directory
            / ".alcalay_write_test"
        )

        test_file.write_text(
            "Alcalay write test",
            encoding="utf-8",
        )

        test_file.unlink(
            missing_ok=True
        )

        return (
            True,
            f"Write access OK: {directory}",
        )

    except Exception as exc:
        return (
            False,
            f"Write access failed: "
            f"{directory}: {exc}",
        )


def detect_server(
    server_os: str | None = None,
    server_root: str | Path | None = None,
    api_port: int = DEFAULT_API_PORT,
    postgres_host: str = "localhost",
    postgres_port: int = DEFAULT_POSTGRES_PORT,
) -> DetectionResult:
    """
    Detect the local Alcalay server environment.

    This function only detects the environment.

    It does NOT:
        - install software
        - modify PostgreSQL
        - create databases
        - create users
        - start services
        - connect Gmail
        - connect Google Drive
    """

    selected_os = (
        server_os
        or platform.system()
    )

    root = Path(
        server_root
        or default_server_root(
            selected_os
        )
    ).expanduser()

    write_ok, write_message = (
        test_write_access(root)
    )

    postgres_ok, _ = tcp_test(
        postgres_host,
        postgres_port,
    )

    disk = shutil.disk_usage(
        Path.home()
    )

    return DetectionResult(
        operating_system=selected_os,

        operating_system_version=(
            platform.version()
        ),

        machine_name=(
            socket.gethostname()
        ),

        python_version=(
            platform.python_version()
        ),

        python_executable=(
            sys.executable
        ),

        server_root=str(root),

        api_port=int(api_port),

        api_port_available=port_available(
            "0.0.0.0",
            int(api_port),
        ),

        postgres_host=postgres_host,

        postgres_port=int(
            postgres_port
        ),

        postgres_tcp_available=(
            postgres_ok
        ),

        home_directory=str(
            Path.home()
        ),

        disk_free_gb=round(
            disk.free / (1024 ** 3),
            2,
        ),

        git_available=(
            shutil.which("git")
            is not None
        ),

        postgres_command_available=(
            shutil.which("psql")
            is not None
        ),

        write_test=write_ok,

        write_test_message=(
            write_message
        ),
    )


def detect_server_dict(
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Convenience function for the graphical UI.
    """

    return detect_server(
        **kwargs
    ).to_dict()


if __name__ == "__main__":
    result = detect_server()

    print("Alcalay Server Detection")
    print("=" * 60)

    for key, value in result.to_dict().items():
        print(
            f"{key}: {value}"
        )