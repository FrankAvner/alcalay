from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SourceResult:
    success: bool
    source: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "source": self.source,
            "message": self.message,
        }


def validate_local_source(
    configuration: dict[str, Any],
) -> SourceResult:
    sources = configuration.get("sources", {})
    local = sources.get("local_server", {})

    enabled = bool(
        local.get("enabled", True)
    )

    root = local.get("root")

    if not enabled:
        return SourceResult(
            success=True,
            source="local_server",
            message="Local server source is disabled.",
        )

    if not root:
        return SourceResult(
            success=False,
            source="local_server",
            message="Local server source root is missing.",
        )

    return SourceResult(
        success=True,
        source="local_server",
        message=f"Local server source configured: {root}",
    )


def validate_google_drive_source(
    configuration: dict[str, Any],
) -> SourceResult:
    sources = configuration.get("sources", {})
    drive = sources.get("google_drive", {})

    enabled = bool(
        drive.get("enabled", False)
    )

    if not enabled:
        return SourceResult(
            success=True,
            source="google_drive",
            message="Google Drive source is disabled.",
        )

    root = drive.get("root")

    if not root:
        return SourceResult(
            success=False,
            source="google_drive",
            message="Google Drive root is missing.",
        )

    return SourceResult(
        success=True,
        source="google_drive",
        message=f"Google Drive source configured: {root}",
    )


def validate_gmail_source(
    configuration: dict[str, Any],
) -> list[SourceResult]:
    results: list[SourceResult] = []

    sources = configuration.get("sources", {})
    gmail = sources.get("gmail", {})

    enabled = bool(
        gmail.get("enabled", False)
    )

    if not enabled:
        results.append(
            SourceResult(
                success=True,
                source="gmail",
                message="Gmail source is disabled.",
            )
        )
        return results

    accounts = gmail.get(
        "accounts",
        [],
    )

    if not isinstance(accounts, list):
        results.append(
            SourceResult(
                success=False,
                source="gmail",
                message="Gmail accounts must be a list.",
            )
        )
        return results

    if not accounts:
        results.append(
            SourceResult(
                success=True,
                source="gmail",
                message=(
                    "Gmail is enabled but no accounts "
                    "are connected yet."
                ),
            )
        )
        return results

    for index, account in enumerate(accounts, start=1):
        if not isinstance(account, dict):
            results.append(
                SourceResult(
                    success=False,
                    source=f"gmail_account_{index}",
                    message=(
                        "Gmail account configuration "
                        "must be an object."
                    ),
                )
            )
            continue

        account_id = account.get(
            "account_id",
            f"gmail_{index:03d}",
        )

        email = account.get(
            "email",
            "",
        )

        labels = account.get(
            "labels",
            [],
        )

        if not email:
            results.append(
                SourceResult(
                    success=False,
                    source=str(account_id),
                    message="Gmail account email is missing.",
                )
            )
            continue

        if not isinstance(labels, list):
            results.append(
                SourceResult(
                    success=False,
                    source=str(account_id),
                    message="Gmail labels must be a list.",
                )
            )
            continue

        results.append(
            SourceResult(
                success=True,
                source=str(account_id),
                message=(
                    f"Gmail account configured: {email}; "
                    f"{len(labels)} selected label(s)."
                ),
            )
        )

    return results


def validate_gmail_policy(
    configuration: dict[str, Any],
) -> SourceResult:
    sources = configuration.get("sources", {})
    gmail = sources.get("gmail", {})

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

    if sync_entire_mailbox:
        return SourceResult(
            success=False,
            source="gmail_policy",
            message=(
                "Full Gmail mailbox synchronization "
                "must remain disabled."
            ),
        )

    if not selected_labels_only:
        return SourceResult(
            success=False,
            source="gmail_policy",
            message=(
                "Gmail must use selected-label synchronization."
            ),
        )

    if not incremental:
        return SourceResult(
            success=False,
            source="gmail_policy",
            message=(
                "Incremental Gmail synchronization "
                "must remain enabled."
            ),
        )

    if not history_id_enabled:
        return SourceResult(
            success=False,
            source="gmail_policy",
            message=(
                "Gmail historyId tracking must remain enabled."
            ),
        )

    return SourceResult(
        success=True,
        source="gmail_policy",
        message=(
            "Gmail synchronization policy is valid: "
            "selected labels + incremental sync + historyId."
        ),
    )


def validate_sources(
    configuration: dict[str, Any],
) -> list[SourceResult]:
    """
    Validate all Alcalay information sources.

    This module does NOT:
        - perform OAuth
        - connect to Google
        - download Gmail messages
        - download Drive files
        - copy documents
        - modify source systems
    """

    results: list[SourceResult] = []

    results.append(
        validate_local_source(
            configuration
        )
    )

    results.append(
        validate_google_drive_source(
            configuration
        )
    )

    results.extend(
        validate_gmail_source(
            configuration
        )
    )

    results.append(
        validate_gmail_policy(
            configuration
        )
    )

    return results


def validate_sources_dict(
    configuration: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        result.to_dict()
        for result in validate_sources(
            configuration
        )
    ]


if __name__ == "__main__":
    print("Alcalay Sources Setup Check")
    print("=" * 60)
    print(
        "This module validates source configuration only."
    )
    print(
        "No Google OAuth or synchronization is performed."
    )