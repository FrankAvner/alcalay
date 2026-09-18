from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SetupCheck:
    category: str
    name: str
    success: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "name": self.name,
            "success": self.success,
            "message": self.message,
        }


@dataclass
class SetupReport:
    success: bool
    total_checks: int
    successful_checks: int
    failed_checks: int
    checks: list[SetupCheck]

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "total_checks": self.total_checks,
            "successful_checks": self.successful_checks,
            "failed_checks": self.failed_checks,
            "checks": [
                check.to_dict()
                for check in self.checks
            ],
        }


def _add_check_results(
    checks: list[SetupCheck],
    category: str,
    results: list[Any],
) -> None:
    """
    Convert result objects returned by setup modules
    into unified SetupCheck objects.
    """

    for result in results:
        if isinstance(
            result,
            dict,
        ):
            name = str(
                result.get(
                    "name",
                    result.get(
                        "component",
                        result.get(
                            "service",
                            "unknown",
                        ),
                    ),
                )
            )

            success = bool(
                result.get(
                    "success",
                    False,
                )
            )

            message = str(
                result.get(
                    "message",
                    "",
                )
            )

        else:
            name = str(
                getattr(
                    result,
                    "name",
                    getattr(
                        result,
                        "component",
                        getattr(
                            result,
                            "service",
                            "unknown",
                        ),
                    ),
                )
            )

            success = bool(
                getattr(
                    result,
                    "success",
                    False,
                )
            )

            message = str(
                getattr(
                    result,
                    "message",
                    "",
                )
            )

        checks.append(
            SetupCheck(
                category=category,
                name=name,
                success=success,
                message=message,
            )
        )


def build_setup_report(
    *,
    detector_results: list[Any] | None = None,
    validation_results: list[Any] | None = None,
    database_results: list[Any] | None = None,
    schema_results: list[Any] | None = None,
    service_results: list[Any] | None = None,
    auth_results: list[Any] | None = None,
    source_results: list[Any] | None = None,
    processing_results: list[Any] | None = None,
    sync_results: list[Any] | None = None,
) -> SetupReport:
    """
    Build one unified setup report from all setup modules.

    This function only aggregates results.
    It does not execute setup actions.
    """

    checks: list[SetupCheck] = []

    _add_check_results(
        checks,
        "detector",
        detector_results or [],
    )

    _add_check_results(
        checks,
        "configuration",
        validation_results or [],
    )

    _add_check_results(
        checks,
        "database",
        database_results or [],
    )

    _add_check_results(
        checks,
        "database_schema",
        schema_results or [],
    )

    _add_check_results(
        checks,
        "services",
        service_results or [],
    )

    _add_check_results(
        checks,
        "security",
        auth_results or [],
    )

    _add_check_results(
        checks,
        "sources",
        source_results or [],
    )

    _add_check_results(
        checks,
        "processing",
        processing_results or [],
    )

    _add_check_results(
        checks,
        "sync",
        sync_results or [],
    )

    total = len(checks)

    successful = sum(
        1
        for check in checks
        if check.success
    )

    failed = total - successful

    return SetupReport(
        success=(
            failed == 0
        ),
        total_checks=total,
        successful_checks=successful,
        failed_checks=failed,
        checks=checks,
    )


def report_summary(
    report: SetupReport,
) -> str:
    """
    Create a human-readable setup summary.
    """

    lines = [
        "Alcalay Setup Report",
        "=" * 60,
        (
            f"Status: "
            f"{'READY' if report.success else 'NOT READY'}"
        ),
        f"Total checks: {report.total_checks}",
        f"Successful: {report.successful_checks}",
        f"Failed: {report.failed_checks}",
        "",
    ]

    for check in report.checks:
        status = (
            "OK"
            if check.success
            else "FAILED"
        )

        lines.append(
            f"[{status}] "
            f"{check.category} / "
            f"{check.name}: "
            f"{check.message}"
        )

    return "\n".join(
        lines
    )


def report_dict(
    report: SetupReport,
) -> dict[str, Any]:
    """
    Convenience function for the UI.
    """

    return report.to_dict()


if __name__ == "__main__":
    report = build_setup_report(
        validation_results=[
            {
                "name": "configuration",
                "success": True,
                "message": "Configuration is valid.",
            }
        ],
        database_results=[
            {
                "component": "postgresql",
                "success": True,
                "message": "PostgreSQL endpoint is reachable.",
            }
        ],
        service_results=[
            {
                "service": "api",
                "success": True,
                "message": "API configuration is valid.",
            }
        ],
    )

    print(
        report_summary(report)
    )