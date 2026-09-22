# -*- coding: utf-8 -*-

"""
Alcalay - Google Drive Registry
===============================

Registers the complete Alcalay Google Drive hierarchy in PostgreSQL.

Drive hierarchy:

    LEVEL 1
    Alcalay
        |
        +-- LEVEL 2
            +-- Gmail
            |     |
            |     +-- LEVEL 3
            |           +-- frank.avner@gmail.com
            |                 |
            |                 +-- LEVEL 4
            |                       +-- attachments
            |                       +-- copy_audit
            |                       +-- messages
            |
            +-- Documents
            |
            +-- Database
            |
            +-- Backups

The registry stores the complete folder hierarchy using:

    drive_folders.parent_drive_file_id

Files are stored in:

    drive_files.parent_drive_file_id

This module performs METADATA REGISTRATION ONLY.

It does NOT:

    - Download files.
    - Upload files.
    - Delete files.
    - Move files.
    - Rename files.
    - Apply keyword filtering.
    - Detect duplicates.
    - Select canonical versions.
    - Modify files in Google Drive.
    - Index document contents.

Workflow:

    Google Drive
        |
        v
    DriveConnection
        |
        v
    DriveRepository
        |
        v
    DriveScanner
        |
        v
    DriveRegistry
        |
        v
    PostgreSQL
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from src.database.connection import DatabaseConnection
from src.drive.drive_connection import DriveConnection
from src.drive.drive_repository import DriveRepository
from src.drive.drive_scanner import DriveItem, DriveScanner


REPOSITORY_KEY = "alcalay"

SYNC_TYPE = "DRIVE_METADATA_SCAN"

SYNC_STATUS_RUNNING = "RUNNING"
SYNC_STATUS_COMPLETED = "COMPLETED"
SYNC_STATUS_FAILED = "FAILED"

ITEM_STATUS_COMPLETED = "COMPLETED"

ACTION_REGISTER = "REGISTER"
ACTION_UPDATE = "UPDATE"


@dataclass
class RegistryStatistics:
    """
    Statistics for one registry run.
    """

    scanned_count: int = 0
    folders_count: int = 0
    files_count: int = 0
    new_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    error_count: int = 0


class DriveRegistry:
    """
    Registers the complete Google Drive hierarchy in PostgreSQL.

    The registry is deliberately separated from:

        - Drive authentication
        - Drive scanning
        - keyword filtering
        - duplicate handling
        - file downloading

    This class only reads Drive metadata and stores it in PostgreSQL.
    """

    def __init__(
        self,
        drive_connection: DriveConnection | None = None,
        database_connection: DatabaseConnection | None = None,
        account_email: str = "",
    ) -> None:

        self.drive_connection = (
            drive_connection
            if drive_connection is not None
            else DriveConnection(
                account_email=account_email
            )
        )

        self.database_connection = (
            database_connection
            if database_connection is not None
            else DatabaseConnection()
        )

        self.repository: DriveRepository | None = None
        self.scanner: DriveScanner | None = None

    # ------------------------------------------------------------------
    # Connection / initialization
    # ------------------------------------------------------------------

    def connect(
        self,
        account_email: str = "",
    ) -> str:
        """
        Connect to Google Drive and initialize:

            DriveRepository
            DriveScanner

        Returns:
            Connected Google account email.
        """

        email = self.drive_connection.connect(
            account_email or None
        )

        self.repository = DriveRepository(
            self.drive_connection
        )

        self.scanner = DriveScanner(
            self.drive_connection,
            self.repository,
        )

        return email

    def _require_initialized(self) -> None:
        """
        Ensure DriveRepository and DriveScanner exist.
        """

        if self.repository is None:
            raise RuntimeError(
                "DriveRepository לא אותחל. "
                "יש לקרוא ל-connect() לפני הסריקה."
            )

        if self.scanner is None:
            raise RuntimeError(
                "DriveScanner לא אותחל. "
                "יש לקרוא ל-connect() לפני הסריקה."
            )

    # ------------------------------------------------------------------
    # PostgreSQL repository
    # ------------------------------------------------------------------

    def _get_repository_id(
        self,
        connection,
    ) -> int:
        """
        Return the PostgreSQL repository ID for Alcalay.
        """

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT id
                FROM drive_repositories
                WHERE repository_key = %s
                  AND enabled = TRUE
                """,
                (
                    REPOSITORY_KEY,
                ),
            )

            row = cursor.fetchone()

        if row is None:
            raise RuntimeError(
                "לא נמצא repository פעיל ב-PostgreSQL עבור "
                f"repository_key='{REPOSITORY_KEY}'."
            )

        return int(row[0])

    # ------------------------------------------------------------------
    # Sync run
    # ------------------------------------------------------------------

    def _create_sync_run(
        self,
        connection,
        repository_id: int,
    ) -> int:
        """
        Create a RUNNING synchronization record.
        """

        with connection.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO drive_sync_runs
                (
                    repository_id,
                    sync_type,
                    status,
                    started_at
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    NOW()
                )
                RETURNING id
                """,
                (
                    repository_id,
                    SYNC_TYPE,
                    SYNC_STATUS_RUNNING,
                ),
            )

            row = cursor.fetchone()

        if row is None:
            raise RuntimeError(
                "לא ניתן ליצור drive_sync_runs."
            )

        return int(row[0])

    def _finish_sync_run(
        self,
        connection,
        sync_run_id: int,
        statistics: RegistryStatistics,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """
        Finish a synchronization run.
        """

        with connection.cursor() as cursor:

            cursor.execute(
                """
                UPDATE drive_sync_runs
                SET
                    finished_at = NOW(),
                    status = %s,
                    scanned_count = %s,
                    folders_count = %s,
                    files_count = %s,
                    relevant_count = %s,
                    skipped_count = %s,
                    downloaded_count = %s,
                    updated_count = %s,
                    duplicate_count = %s,
                    error_count = %s,
                    error_message = %s
                WHERE id = %s
                """,
                (
                    status,
                    statistics.scanned_count,
                    statistics.folders_count,
                    statistics.files_count,
                    0,
                    statistics.unchanged_count,
                    0,
                    statistics.updated_count,
                    0,
                    statistics.error_count,
                    error_message,
                    sync_run_id,
                ),
            )

    # ------------------------------------------------------------------
    # Folder registration
    # ------------------------------------------------------------------

    def _upsert_folder(
        self,
        connection,
        repository_id: int,
        item: DriveItem,
    ) -> str:
        """
        Insert or update one Drive folder.

        Returns:

            NEW
            UPDATED
            UNCHANGED
        """

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    name,
                    parent_drive_file_id,
                    mime_type,
                    web_view_link,
                    created_time,
                    modified_time,
                    trashed
                FROM drive_folders
                WHERE repository_id = %s
                  AND drive_file_id = %s
                """,
                (
                    repository_id,
                    item.file_id,
                ),
            )

            existing = cursor.fetchone()

            if existing is None:

                cursor.execute(
                    """
                    INSERT INTO drive_folders
                    (
                        repository_id,
                        drive_file_id,
                        parent_drive_file_id,
                        name,
                        mime_type,
                        web_view_link,
                        created_time,
                        modified_time,
                        trashed,
                        first_seen_at,
                        last_seen_at
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        NOW(),
                        NOW()
                    )
                    """,
                    (
                        repository_id,
                        item.file_id,
                        item.parent_id,
                        item.name,
                        item.mime_type,
                        item.web_view_link,
                        item.created_time,
                        item.modified_time,
                        item.trashed,
                    ),
                )

                return "NEW"

            (
                existing_id,
                existing_name,
                existing_parent_id,
                existing_mime_type,
                existing_web_view_link,
                existing_created_time,
                existing_modified_time,
                existing_trashed,
            ) = existing

            changed = (
                existing_name != item.name
                or existing_parent_id != item.parent_id
                or existing_mime_type != item.mime_type
                or existing_web_view_link != item.web_view_link
                or existing_created_time != item.created_time
                or existing_modified_time != item.modified_time
                or existing_trashed != item.trashed
            )

            cursor.execute(
                """
                UPDATE drive_folders
                SET
                    parent_drive_file_id = %s,
                    name = %s,
                    mime_type = %s,
                    web_view_link = %s,
                    created_time = %s,
                    modified_time = %s,
                    trashed = %s,
                    last_seen_at = NOW()
                WHERE repository_id = %s
                  AND drive_file_id = %s
                """,
                (
                    item.parent_id,
                    item.name,
                    item.mime_type,
                    item.web_view_link,
                    item.created_time,
                    item.modified_time,
                    item.trashed,
                    repository_id,
                    item.file_id,
                ),
            )

            return (
                "UPDATED"
                if changed
                else "UNCHANGED"
            )

    # ------------------------------------------------------------------
    # File registration
    # ------------------------------------------------------------------

    def _upsert_file(
        self,
        connection,
        repository_id: int,
        item: DriveItem,
    ) -> tuple[int, str]:
        """
        Insert or update one Drive file.

        Returns:

            (
                PostgreSQL drive_files.id,
                NEW / UPDATED / UNCHANGED
            )
        """

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    parent_drive_file_id,
                    name,
                    mime_type,
                    size_bytes,
                    created_time,
                    modified_time,
                    md5_checksum,
                    web_view_link,
                    is_trashed
                FROM drive_files
                WHERE repository_id = %s
                  AND drive_file_id = %s
                """,
                (
                    repository_id,
                    item.file_id,
                ),
            )

            existing = cursor.fetchone()

            if existing is None:

                cursor.execute(
                    """
                    INSERT INTO drive_files
                    (
                        repository_id,
                        drive_file_id,
                        parent_drive_file_id,
                        name,
                        mime_type,
                        size_bytes,
                        created_time,
                        modified_time,
                        md5_checksum,
                        web_view_link,
                        is_trashed,
                        first_seen_at,
                        last_seen_at,
                        last_checked_at
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        NOW(),
                        NOW(),
                        NOW()
                    )
                    RETURNING id
                    """,
                    (
                        repository_id,
                        item.file_id,
                        item.parent_id,
                        item.name,
                        item.mime_type,
                        item.size,
                        item.created_time,
                        item.modified_time,
                        item.md5_checksum,
                        item.web_view_link,
                        item.trashed,
                    ),
                )

                row = cursor.fetchone()

                if row is None:
                    raise RuntimeError(
                        "לא ניתן לקבל ID לאחר הכנסת "
                        f"Drive file: {item.file_id}"
                    )

                return int(row[0]), "NEW"

            (
                existing_id,
                existing_parent_id,
                existing_name,
                existing_mime_type,
                existing_size,
                existing_created_time,
                existing_modified_time,
                existing_md5,
                existing_web_view_link,
                existing_trashed,
            ) = existing

            changed = (
                existing_parent_id != item.parent_id
                or existing_name != item.name
                or existing_mime_type != item.mime_type
                or existing_size != item.size
                or existing_created_time != item.created_time
                or existing_modified_time != item.modified_time
                or existing_md5 != item.md5_checksum
                or existing_web_view_link != item.web_view_link
                or existing_trashed != item.trashed
            )

            cursor.execute(
                """
                UPDATE drive_files
                SET
                    parent_drive_file_id = %s,
                    name = %s,
                    mime_type = %s,
                    size_bytes = %s,
                    created_time = %s,
                    modified_time = %s,
                    md5_checksum = %s,
                    web_view_link = %s,
                    is_trashed = %s,
                    last_seen_at = NOW(),
                    last_checked_at = NOW()
                WHERE id = %s
                """,
                (
                    item.parent_id,
                    item.name,
                    item.mime_type,
                    item.size,
                    item.created_time,
                    item.modified_time,
                    item.md5_checksum,
                    item.web_view_link,
                    item.trashed,
                    existing_id,
                ),
            )

            return (
                int(existing_id),
                "UPDATED"
                if changed
                else "UNCHANGED",
            )

    # ------------------------------------------------------------------
    # Sync item registration
    # ------------------------------------------------------------------

    def _create_sync_item(
        self,
        connection,
        sync_run_id: int,
        drive_file_db_id: int,
        action: str,
        reason: str,
    ) -> None:
        """
        Register a FILE in drive_sync_items.

        Folders are intentionally not registered here because
        drive_sync_items.drive_file_id_fk references drive_files.id.
        """

        with connection.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO drive_sync_items
                (
                    sync_run_id,
                    drive_file_id_fk,
                    action,
                    status,
                    reason,
                    started_at,
                    finished_at
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    NOW(),
                    NOW()
                )
                """,
                (
                    sync_run_id,
                    drive_file_db_id,
                    action,
                    ITEM_STATUS_COMPLETED,
                    reason,
                ),
            )

    # ------------------------------------------------------------------
    # Root folder
    # ------------------------------------------------------------------

    def _get_root_item(self) -> DriveItem:
        """
        Retrieve the Level 1 Alcalay root folder metadata.

        DriveRepository already contains the configured root folder ID.
        DriveConnection.verify_folder() gives us its metadata.
        """

        self._require_initialized()

        assert self.repository is not None

        root_folder = self.repository.get_root_folder()

        metadata = self.drive_connection.verify_folder(
            root_folder.folder_id
        )

        return DriveItem(
            file_id=str(
                metadata.get(
                    "id",
                    root_folder.folder_id,
                )
            ),
            name=str(
                metadata.get(
                    "name",
                    root_folder.display_name,
                )
            ),
            mime_type=str(
                metadata.get(
                    "mimeType",
                    "application/vnd.google-apps.folder",
                )
            ),
            size=None,
            modified_time=None,
            created_time=None,
            md5_checksum=None,
            web_view_link=metadata.get(
                "webViewLink"
            ),
            parent_id=None,
            is_folder=True,
            trashed=bool(
                metadata.get(
                    "trashed",
                    False,
                )
            ),
        )

    # ------------------------------------------------------------------
    # Level 2 folders
    # ------------------------------------------------------------------

    def _get_level_two_items(self) -> list[DriveItem]:
        """
        Return the four configured Level 2 folders:

            Gmail
            Documents
            Database
            Backups

        They are explicitly registered because they are part of the
        repository hierarchy itself, not merely scan results.
        """

        self._require_initialized()

        assert self.repository is not None

        result: list[DriveItem] = []

        folders = (
            self.repository.get_documents_folder(),
            self.repository.get_gmail_folder(),
            self.repository.get_database_folder(),
            self.repository.get_backups_folder(),
        )

        root_folder = self.repository.get_root_folder()

        for folder in folders:

            metadata = self.drive_connection.verify_folder(
                folder.folder_id
            )

            result.append(
                DriveItem(
                    file_id=str(
                        metadata.get(
                            "id",
                            folder.folder_id,
                        )
                    ),
                    name=str(
                        metadata.get(
                            "name",
                            folder.display_name,
                        )
                    ),
                    mime_type=str(
                        metadata.get(
                            "mimeType",
                            "application/vnd.google-apps.folder",
                        )
                    ),
                    size=None,
                    modified_time=None,
                    created_time=None,
                    md5_checksum=None,
                    web_view_link=metadata.get(
                        "webViewLink"
                    ),
                    parent_id=root_folder.folder_id,
                    is_folder=True,
                    trashed=bool(
                        metadata.get(
                            "trashed",
                            False,
                        )
                    ),
                )
            )

        return result

    # ------------------------------------------------------------------
    # Recursive scan
    # ------------------------------------------------------------------

    def _scan_all_content(
        self,
    ) -> list[DriveItem]:
        """
        Scan all four Level 2 content folders recursively.

        Returned items include:

            Level 3 folders
            Level 4 folders
            deeper folders
            files

        Level 1 and Level 2 are handled separately so the complete
        repository tree is registered.
        """

        self._require_initialized()

        assert self.scanner is not None

        all_items: list[DriveItem] = []

        scan_methods = (
            (
                "Documents",
                self.scanner.scan_documents,
            ),
            (
                "Gmail",
                self.scanner.scan_gmail,
            ),
            (
                "Database",
                self.scanner.scan_database,
            ),
            (
                "Backups",
                self.scanner.scan_backups,
            ),
        )

        for display_name, scan_method in scan_methods:

            print(
                f"[SCAN] {display_name}"
            )

            items = scan_method(
                recursive=True
            )

            print(
                f"[SCAN] {display_name}: "
                f"{len(items)} items"
            )

            all_items.extend(items)

        return all_items

    # ------------------------------------------------------------------
    # Main registry operation
    # ------------------------------------------------------------------

    def run(self) -> RegistryStatistics:
        """
        Execute one complete metadata registry run.

        The complete hierarchy is registered:

            Level 1
            Level 2
            Level 3+
            Files
        """

        self._require_initialized()

        statistics = RegistryStatistics()

        connection = self.database_connection.connect()

        sync_run_id: int | None = None

        try:

            repository_id = self._get_repository_id(
                connection
            )

            sync_run_id = self._create_sync_run(
                connection,
                repository_id,
            )

            connection.commit()

            print()
            print("=" * 72)
            print(
                "STARTING GOOGLE DRIVE METADATA REGISTRY"
            )
            print("=" * 72)
            print(
                f"[REPOSITORY] {REPOSITORY_KEY}"
            )
            print(
                f"[SYNC RUN] {sync_run_id}"
            )
            print()
            print(
                "[STRUCTURE] "
                "Level 1 -> Level 2 -> Level 3+ -> Files"
            )
            print()

            # ----------------------------------------------------------
            # LEVEL 1 - Alcalay
            # ----------------------------------------------------------

            root_item = self._get_root_item()

            print(
                f"[REGISTER] LEVEL 1: "
                f"{root_item.name}"
            )

            result = self._upsert_folder(
                connection,
                repository_id,
                root_item,
            )

            statistics.scanned_count += 1
            statistics.folders_count += 1

            if result == "NEW":
                statistics.new_count += 1
            elif result == "UPDATED":
                statistics.updated_count += 1
            else:
                statistics.unchanged_count += 1

            connection.commit()

            # ----------------------------------------------------------
            # LEVEL 2 - Documents/Gmail/Database/Backups
            # ----------------------------------------------------------

            level_two_items = (
                self._get_level_two_items()
            )

            for item in level_two_items:

                print(
                    f"[REGISTER] LEVEL 2: "
                    f"{item.name}"
                )

                result = self._upsert_folder(
                    connection,
                    repository_id,
                    item,
                )

                statistics.scanned_count += 1
                statistics.folders_count += 1

                if result == "NEW":
                    statistics.new_count += 1
                elif result == "UPDATED":
                    statistics.updated_count += 1
                else:
                    statistics.unchanged_count += 1

                connection.commit()

            # ----------------------------------------------------------
            # LEVEL 3+ and FILES
            # ----------------------------------------------------------

            items = self._scan_all_content()

            statistics.scanned_count += len(items)

            for index, item in enumerate(
                items,
                start=1,
            ):

                print(
                    f"[REGISTER] "
                    f"{index}/{len(items)} "
                    f"{item.name}"
                )

                try:

                    if item.is_folder:

                        result = self._upsert_folder(
                            connection,
                            repository_id,
                            item,
                        )

                        statistics.folders_count += 1

                    else:

                        drive_file_db_id, result = (
                            self._upsert_file(
                                connection,
                                repository_id,
                                item,
                            )
                        )

                        statistics.files_count += 1

                        if result == "NEW":

                            self._create_sync_item(
                                connection,
                                sync_run_id,
                                drive_file_db_id,
                                ACTION_REGISTER,
                                "New Drive metadata registered",
                            )

                        elif result == "UPDATED":

                            self._create_sync_item(
                                connection,
                                sync_run_id,
                                drive_file_db_id,
                                ACTION_UPDATE,
                                "Existing Drive metadata updated",
                            )

                        else:

                            self._create_sync_item(
                                connection,
                                sync_run_id,
                                drive_file_db_id,
                                ACTION_UPDATE,
                                "Drive metadata checked; no metadata change",
                            )

                    if result == "NEW":
                        statistics.new_count += 1

                    elif result == "UPDATED":
                        statistics.updated_count += 1

                    else:
                        statistics.unchanged_count += 1

                    connection.commit()

                except Exception as exc:

                    connection.rollback()

                    statistics.error_count += 1

                    print(
                        "[ERROR] "
                        f"{item.file_id}: "
                        f"{exc}"
                    )

                    continue

            self._finish_sync_run(
                connection,
                sync_run_id,
                statistics,
                SYNC_STATUS_COMPLETED,
                None,
            )

            connection.commit()

            print()
            print("=" * 72)
            print(
                "GOOGLE DRIVE METADATA REGISTRY COMPLETED"
            )
            print("=" * 72)
            print(
                f"[SYNC RUN]       {sync_run_id}"
            )
            print(
                f"[SCANNED]        {statistics.scanned_count}"
            )
            print(
                f"[FOLDERS]        {statistics.folders_count}"
            )
            print(
                f"[FILES]          {statistics.files_count}"
            )
            print(
                f"[NEW]            {statistics.new_count}"
            )
            print(
                f"[UPDATED]        {statistics.updated_count}"
            )
            print(
                f"[UNCHANGED]      {statistics.unchanged_count}"
            )
            print(
                f"[ERRORS]         {statistics.error_count}"
            )
            print("=" * 72)

            return statistics

        except Exception as exc:

            if sync_run_id is not None:

                try:

                    connection.rollback()

                    self._finish_sync_run(
                        connection,
                        sync_run_id,
                        statistics,
                        SYNC_STATUS_FAILED,
                        str(exc),
                    )

                    connection.commit()

                except Exception:

                    connection.rollback()

            raise

        finally:

            connection.close()

    # ------------------------------------------------------------------
    # Convenience method
    # ------------------------------------------------------------------

    def connect_and_run(
        self,
        account_email: str = "",
    ) -> RegistryStatistics:
        """
        Connect to Google Drive and immediately run the registry.
        """

        email = self.connect(
            account_email
        )

        print(
            f"[GOOGLE ACCOUNT] {email}"
        )

        return self.run()


# ----------------------------------------------------------------------
# Command-line entry point
# ----------------------------------------------------------------------

def main() -> int:
    """
    Command-line entry point.

    Usage:

        python -m src.drive.drive_registry

    Optional:

        python -m src.drive.drive_registry user@example.com
    """

    account_email = ""

    if len(sys.argv) > 1:
        account_email = sys.argv[1].strip()

    try:

        registry = DriveRegistry()

        registry.connect_and_run(
            account_email=account_email
        )

        return 0

    except KeyboardInterrupt:

        print()
        print(
            "[STOPPED] המשתמש עצר את הסריקה."
        )

        return 130

    except Exception as exc:

        print()
        print("=" * 72)
        print("DRIVE REGISTRY FAILED")
        print("=" * 72)
        print(
            f"[ERROR] {exc}"
        )
        print("=" * 72)

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )