from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from setup_auth import validate_auth_configuration
from setup_database import check_postgresql
from setup_database_schema import check_schema
from setup_detector import detect_server
from setup_installer import prepare_server
from setup_processing import validate_processing_configuration
from setup_report import build_setup_report
from setup_services import check_services
from setup_sources import validate_sources
from setup_sync import validate_sync
from setup_validator import validate_configuration


@dataclass
class SetupExecution:
    success: bool
    message: str
    configuration: dict[str, Any]
    report: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "configuration": self.configuration,
            "report": self.report,
        }


def run_detection(
    configuration: dict[str, Any],
) -> dict[str, Any]:
    """
    Run environment detection.

    Detection does not install software or modify PostgreSQL.
    """

    server = configuration.get(
        "server",
        {},
    )

    postgres = configuration.get(
        "postgresql",
        {},
    )

    result = detect_server(
        server_os=server.get(
            "os",
        ),
        server_root=configuration.get(
            "paths",
            {},
        ).get(
            "server_root",
        ),
        api_port=server.get(
            "api_port",
            8443,
        ),
        postgres_host=postgres.get(
            "host",
            "localhost",
        ),
        postgres_port=postgres.get(
            "port",
            5432,
        ),
    )

    return result.to_dict()


def run_setup_checks(
    configuration: dict[str, Any],
) -> SetupExecution:
    """
    Run all setup checks without installing or modifying
    external systems.
    """

    detection = run_detection(
        configuration
    )

    validation = validate_configuration(
        configuration
    )

    database = check_postgresql(
        configuration
    )

    schema = check_schema(
        configuration
    )

    services = check_services(
        configuration
    )

    auth = validate_auth_configuration(
        configuration
    )

    sources = validate_sources(
        configuration
    )

    processing = validate_processing_configuration(
        configuration
    )

    sync = validate_sync(
        configuration
    )

    report = build_setup_report(
        detector_results=[
            {
                "name": key,
                "success": True,
                "message": str(value),
            }
            for key, value in detection.items()
        ],
        validation_results=validation.get(
            "results",
            [],
        ),
        database_results=[
            database.to_dict()
        ],
        schema_results=[
            schema.to_dict()
        ],
        service_results=[
            result.to_dict()
            for result in services
        ],
        auth_results=[
            auth.to_dict()
        ],
        source_results=[
            result.to_dict()
            for result in sources
        ],
        processing_results=[
            result.to_dict()
            for result in processing
        ],
        sync_results=[
            result.to_dict()
            for result in sync
        ],
    )

    return SetupExecution(
        success=report.success,
        message=(
            "Alcalay setup checks completed."
            if report.success
            else
            "Alcalay setup checks completed with failures."
        ),
        configuration=configuration,
        report=report.to_dict(),
    )


def run_install(
    configuration: dict[str, Any],
) -> SetupExecution:
    """
    Prepare the Alcalay server filesystem and configuration.

    Installation is deliberately limited to the local
    Alcalay filesystem at this stage.
    """

    installation = prepare_server(
        configuration
    )

    checks = run_setup_checks(
        configuration
    )

    report = checks.report

    if not installation.success:
        return SetupExecution(
            success=False,
            message=installation.message,
            configuration=configuration,
            report=report,
        )

    return SetupExecution(
        success=True,
        message=(
            "Alcalay server preparation completed."
        ),
        configuration=configuration,
        report=report,
    )


def run_full_setup(
    configuration: dict[str, Any],
) -> SetupExecution:
    """
    Run the complete Alcalay setup workflow.

    Order:

        1. Environment detection
        2. Configuration validation
        3. Filesystem preparation
        4. PostgreSQL check
        5. Database schema check
        6. Authentication check
        7. Sources check
        8. Processing check
        9. Synchronization check
        10. API service check
        11. Final report

    This function does NOT yet:
        - install PostgreSQL
        - create PostgreSQL users
        - create PostgreSQL databases
        - execute migrations
        - perform Google OAuth
        - perform Gmail synchronization
        - perform Google Drive synchronization
        - start the API service
    """

    installation = prepare_server(
        configuration
    )

    if not installation.success:
        return SetupExecution(
            success=False,
            message=installation.message,
            configuration=configuration,
            report={},
        )

    return run_setup_checks(
        configuration
    )


if __name__ == "__main__":
    print(
        "Alcalay Setup Orchestrator"
    )
    print("=" * 60)
    print(
        "This module coordinates the setup workflow."
    )
    print(
        "It does not install external software "
        "or start services."
    )