from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SyncResult:
    success: bool
    component: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "component": self.component,
            "message": self.message,
        }


def validate_sync_policy(
    configuration: dict[str, Any],
) -> list[SyncResult]:
    results: list[SyncResult] = []

    sync = configuration.get(
        "sync",
        {},
    )

    incremental = bool(
        sync.get(
            "incremental",
            True,
        )
    )

    deduplication = bool(
        sync.get(
            "deduplication",
            True,
        )
    )

    changed_only = bool(
        sync.get(
            "changed_documents_only",
            True,
        )
    )

    manual_full_sync = bool(
        sync.get(
            "manual_full_sync_only",
            True,
        )
    )

    results.append(
        SyncResult(
            success=incremental,
            component="incremental",
            message=(
                "Incremental synchronization is "
                "enabled."
                if incremental
                else
                "Incremental synchronization is disabled."
            ),
        )
    )

    results.append(
        SyncResult(
            success=deduplication,
            component="deduplication",
            message=(
                "Deduplication is enabled."
                if deduplication
                else
                "Deduplication is disabled."
            ),
        )
    )

    results.append(
        SyncResult(
            success=changed_only,
            component="changed_only",
            message=(
                "Only changed/new documents are "
                "processed."
                if changed_only
                else
                "Changed-only processing is disabled."
            ),
        )
    )

    results.append(
        SyncResult(
            success=manual_full_sync,
            component="manual_full_sync",
            message=(
                "Full synchronization requires "
                "explicit manual execution."
                if manual_full_sync
                else
                "Full synchronization may run automatically."
            ),
        )
    )

    return results


def validate_gmail_sync(
    configuration: dict[str, Any],
) -> list[SyncResult]:
    results: list[SyncResult] = []

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

    deduplication = policy.get(
        "deduplication",
        [],
    )

    results.append(
        SyncResult(
            success=incremental,
            component="gmail.incremental",
            message=(
                "Gmail incremental synchronization "
                "is enabled."
                if incremental
                else
                "Gmail incremental synchronization "
                "is disabled."
            ),
        )
    )

    results.append(
        SyncResult(
            success=history_id_enabled,
            component="gmail.history_id",
            message=(
                "Gmail historyId tracking is enabled."
                if history_id_enabled
                else
                "Gmail historyId tracking is disabled."
            ),
        )
    )

    if not isinstance(
        deduplication,
        list,
    ):
        results.append(
            SyncResult(
                success=False,
                component="gmail.deduplication",
                message=(
                    "Gmail deduplication configuration "
                    "must be a list."
                ),
            )
        )

    elif not deduplication:
        results.append(
            SyncResult(
                success=False,
                component="gmail.deduplication",
                message=(
                    "At least one Gmail deduplication "
                    "method must be configured."
                ),
            )
        )

    else:
        results.append(
            SyncResult(
                success=True,
                component="gmail.deduplication",
                message=(
                    "Gmail deduplication methods: "
                    + ", ".join(
                        str(item)
                        for item in deduplication
                    )
                ),
            )
        )

    accounts = gmail.get(
        "accounts",
        [],
    )

    if not isinstance(
        accounts,
        list,
    ):
        results.append(
            SyncResult(
                success=False,
                component="gmail.accounts",
                message=(
                    "Gmail accounts must be configured "
                    "as a list."
                ),
            )
        )
        return results

    for index, account in enumerate(
        accounts,
        start=1,
    ):
        if not isinstance(
            account,
            dict,
        ):
            results.append(
                SyncResult(
                    success=False,
                    component=f"gmail.account.{index}",
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

        results.append(
            SyncResult(
                success=True,
                component=f"gmail.account.{account_id}",
                message=(
                    "Gmail synchronization state is "
                    "maintained independently for this account."
                ),
            )
        )

    return results


def validate_sync_timestamps(
    configuration: dict[str, Any],
) -> SyncResult:
    """
    Validate that timestamp-based incremental synchronization
    is enabled.

    Runtime synchronization state itself is stored outside
    the static configuration.
    """

    sync = configuration.get(
        "sync",
        {},
    )

    timestamp_tracking = bool(
        sync.get(
            "timestamp_tracking",
            True,
        )
    )

    return SyncResult(
        success=timestamp_tracking,
        component="timestamp_tracking",
        message=(
            "Last successful synchronization timestamp "
            "tracking is enabled."
            if timestamp_tracking
            else
            "Timestamp tracking is disabled."
        ),
    )


def validate_sync(
    configuration: dict[str, Any],
) -> list[SyncResult]:
    """
    Validate Alcalay synchronization policy.

    This module does NOT:
        - connect to Gmail
        - connect to Google Drive
        - download documents
        - download email
        - modify source systems
        - perform synchronization
    """

    results: list[SyncResult] = []

    results.extend(
        validate_sync_policy(
            configuration
        )
    )

    results.append(
        validate_sync_timestamps(
            configuration
        )
    )

    results.extend(
        validate_gmail_sync(
            configuration
        )
    )

    return results


def validate_sync_dict(
    configuration: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        result.to_dict()
        for result in validate_sync(
            configuration
        )
    ]


if __name__ == "__main__":
    print("Alcalay Synchronization Setup Check")
    print("=" * 60)
    print(
        "This module validates synchronization policy only."
    )
    print(
        "No synchronization is performed."
    )