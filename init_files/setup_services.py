from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Any


@dataclass
class ServiceResult:
    success: bool
    service: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "service": self.service,
            "message": self.message,
        }


def check_api_port(
    host: str,
    port: int,
    timeout: float = 1.0,
) -> ServiceResult:
    """
    Check whether the Alcalay API is already reachable.

    This function does not start or stop anything.
    """

    try:
        port = int(port)
    except (TypeError, ValueError):
        return ServiceResult(
            success=False,
            service="api",
            message="API port is invalid.",
        )

    try:
        with socket.create_connection(
            (host, port),
            timeout=timeout,
        ):
            return ServiceResult(
                success=True,
                service="api",
                message=(
                    f"Alcalay API is reachable "
                    f"at {host}:{port}."
                ),
            )

    except OSError:
        return ServiceResult(
            success=False,
            service="api",
            message=(
                f"Alcalay API is not reachable "
                f"at {host}:{port}."
            ),
        )


def check_api_configuration(
    configuration: dict[str, Any],
) -> ServiceResult:
    """
    Validate the basic API server configuration.

    This does not start the API.
    """

    server = configuration.get(
        "server",
        {},
    )

    host = server.get(
        "host",
        "0.0.0.0",
    )

    port = server.get(
        "api_port",
        8443,
    )

    if not host:
        return ServiceResult(
            success=False,
            service="api",
            message="API host is missing.",
        )

    try:
        port = int(port)
    except (TypeError, ValueError):
        return ServiceResult(
            success=False,
            service="api",
            message="API port is invalid.",
        )

    if not 1 <= port <= 65535:
        return ServiceResult(
            success=False,
            service="api",
            message=(
                f"API port is outside the valid range: {port}"
            ),
        )

    return ServiceResult(
        success=True,
        service="api",
        message=(
            f"API configuration valid: "
            f"{host}:{port}"
        ),
    )


def check_api_binding(
    host: str,
    port: int,
) -> ServiceResult:
    """
    Check whether the configured API port appears to be
    available for binding.

    True means that no service currently appears to be
    listening on the endpoint.

    This function does not bind or reserve the port.
    """

    try:
        port = int(port)
    except (TypeError, ValueError):
        return ServiceResult(
            success=False,
            service="api",
            message="API port is invalid.",
        )

    if not 1 <= port <= 65535:
        return ServiceResult(
            success=False,
            service="api",
            message=(
                f"API port is outside the valid range: {port}"
            ),
        )

    try:
        with socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        ) as sock:

            sock.settimeout(0.5)

            result = sock.connect_ex(
                (host, port)
            )

            if result != 0:
                return ServiceResult(
                    success=True,
                    service="api",
                    message=(
                        f"API port {port} appears "
                        f"to be available on {host}."
                    ),
                )

            return ServiceResult(
                success=False,
                service="api",
                message=(
                    f"API port {port} is already "
                    f"in use on {host}."
                ),
            )

    except OSError as exc:
        return ServiceResult(
            success=False,
            service="api",
            message=(
                f"Could not check API port "
                f"{host}:{port}: {exc}"
            ),
        )


def check_services(
    configuration: dict[str, Any],
) -> list[ServiceResult]:
    """
    Run all currently available service checks.

    At this stage the setup system only validates
    configuration and connectivity.

    Service start/stop/restart will be added later,
    once the actual Alcalay API service exists.
    """

    results: list[ServiceResult] = []

    api_config = check_api_configuration(
        configuration
    )

    results.append(api_config)

    if api_config.success:
        server = configuration.get(
            "server",
            {},
        )

        host = server.get(
            "host",
            "0.0.0.0",
        )

        port = server.get(
            "api_port",
            8443,
        )

        results.append(
            check_api_binding(
                host,
                port,
            )
        )

    return results


def check_services_dict(
    configuration: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Convenience function for the graphical setup UI.
    """

    return [
        result.to_dict()
        for result in check_services(
            configuration
        )
    ]


if __name__ == "__main__":
    print("Alcalay Services Setup Check")
    print("=" * 60)

    configuration = {
        "server": {
            "host": "0.0.0.0",
            "api_port": 8443,
        }
    }

    results = check_services(
        configuration
    )

    for result in results:
        status = (
            "OK"
            if result.success
            else "NOT READY"
        )

        print(
            f"[{status}] "
            f"{result.service}: "
            f"{result.message}"
        )