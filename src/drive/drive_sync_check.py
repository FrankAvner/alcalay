# -*- coding: utf-8 -*-

"""
Alcalay - Google Drive Sync Pre-Check

READ ONLY.

This program checks the local storage against PostgreSQL and Google Drive
before the actual LOCAL_TO_DRIVE synchronization.

IMPORTANT:
- Does NOT upload files.
- Does NOT download files.
- Does NOT create Drive folders.
- Does NOT modify PostgreSQL.
- Does NOT modify local files.
- Uses DriveConnection.service for the Google Drive API.
  DriveConnection.connect() returns the account email string.

Current local -> Drive structure:

Alcalay/
    Documents/
        ... non-Gmail storage files ...

    gmail/
        frank.avner@gmail.com/
            attachments/
            copy_audit/
            messages/

The checker validates:
1. Local files.
2. PostgreSQL mappings.
3. Expected Google Drive hierarchy.
4. Existing Drive files.
5. SHA256 checksums.
6. Duplicate / update / create / skip classification.

Reports are written to:

storage/drive_sync_check/
"""

from __future__ import annotations

import hashlib
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ============================================================================
# PROJECT ROOT
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# PROJECT IMPORTS
# ============================================================================

from src.database.connection import DatabaseConnection
from src.database.database_manager import DatabaseManager
from src.drive.drive_connection import DriveConnection


# ============================================================================
# CONFIGURATION
# ============================================================================

LOCAL_STORAGE = PROJECT_ROOT / "storage"

REPORT_DIR = (
    LOCAL_STORAGE
    / "drive_sync_check"
)

REPOSITORY_KEY = "alcalay"

DRIVE_ROOT_NAME = "Alcalay"

DOCUMENTS_DRIVE_FOLDER = "Documents"

GMAIL_ACCOUNT = "frank.avner@gmail.com"

GMAIL_LOCAL_ROOT = (
    Path("gmail")
    / GMAIL_ACCOUNT
)


# ============================================================================
# FILE FILTERS
# ============================================================================

IGNORED_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
}

IGNORED_SUFFIXES = {
    ".tmp",
    ".part",
    ".crdownload",
}

IGNORED_PREFIXES = (
    "~$",
)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO format."""

    return datetime.now(
        timezone.utc
    ).isoformat()


def json_default(value: Any) -> str:
    """JSON serializer fallback."""

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    return str(value)


def sha256_file(
    path: Path,
    chunk_size: int = 8 * 1024 * 1024,
) -> str:
    """
    Calculate SHA256 without loading the entire file into memory.
    """

    digest = hashlib.sha256()

    with path.open("rb") as file_handle:

        while True:

            data = file_handle.read(
                chunk_size
            )

            if not data:
                break

            digest.update(data)

    return digest.hexdigest()


def is_ignored_file(
    path: Path,
) -> bool:
    """
    Return True when a file should not be included.
    """

    if path.name in IGNORED_NAMES:
        return True

    if path.name.startswith(
        IGNORED_PREFIXES
    ):
        return True

    if path.suffix.lower() in IGNORED_SUFFIXES:
        return True

    return False


def relative_local_path(
    path: Path,
) -> str:
    """
    Return local path relative to storage,
    using forward slashes.
    """

    return path.relative_to(
        LOCAL_STORAGE
    ).as_posix()


def detect_source_type(
    relative_path: str,
) -> str:
    """
    Determine source type from local storage hierarchy.
    """

    parts = Path(
        relative_path
    ).parts

    if not parts:
        return "OTHER"

    first = parts[0].lower()

    if first == "gmail":
        return "GMAIL"

    if first == "office":
        return "OFFICE"

    if first == "pdf":
        return "PDF"

    if first == "media":
        return "MEDIA"

    if first == "drive":
        return "DRIVE"

    return "OTHER"


# ============================================================================
# MAIN CHECKER
# ============================================================================

class DriveSyncChecker:
    """
    Read-only local storage -> Google Drive pre-check.
    """

    def __init__(self) -> None:

        self.db_connection = DatabaseConnection()

        self.db = DatabaseManager()

        self.drive_connection = DriveConnection()

        # DriveConnection.connect() returns account email.
        self.drive_account: Optional[str] = None

        # Actual Google Drive API service.
        self.drive_service = None

        self.repository_id: Optional[int] = None

        self.drive_root_id: Optional[str] = None

        self.results: list[
            dict[str, Any]
        ] = []

        self.summary: dict[str, int] = {
            "total_local_files": 0,
            "gmail_files": 0,
            "non_gmail_files": 0,
            "already_in_postgresql": 0,
            "not_in_postgresql": 0,
            "already_in_drive": 0,
            "not_in_drive": 0,
            "create": 0,
            "update": 0,
            "skip": 0,
            "duplicate": 0,
            "warning": 0,
            "error": 0,
        }


    # ========================================================================
    # GOOGLE DRIVE CONNECTION
    # ========================================================================

    def connect_drive(self) -> None:
        """
        Connect to Google Drive.

        DriveConnection.connect() returns the account email.

        The actual Google Drive API service is stored in:
            DriveConnection.service
        """

        print(
            "[Google Drive] Connecting..."
        )

        self.drive_account = (
            self.drive_connection.connect()
        )

        if not self.drive_account:
            raise RuntimeError(
                "Google Drive connection returned "
                "an empty account value."
            )

        self.drive_service = getattr(
            self.drive_connection,
            "service",
            None,
        )

        if self.drive_service is None:
            raise RuntimeError(
                "DriveConnection.connect() succeeded, "
                "but DriveConnection.service is not available."
            )

        files_method = getattr(
            self.drive_service,
            "files",
            None,
        )

        if not callable(files_method):
            raise RuntimeError(
                "DriveConnection.service does not expose files()."
            )

        print(
            "OK: Google Drive connection"
        )

        print(
            f"Drive account: "
            f"{self.drive_account}"
        )


    # ========================================================================
    # POSTGRESQL REPOSITORY
    # ========================================================================

    def load_repository(self) -> None:
        """
        Load Alcalay Drive repository information.

        Actual schema:

        drive_repositories
        ------------------
        id
        repository_key
        display_name
        root_folder_id
        enabled
        created_at
        updated_at
        """

        row = self.db.fetch_one(
            """
            SELECT
                id,
                repository_key,
                display_name,
                root_folder_id,
                enabled
            FROM drive_repositories
            WHERE repository_key = %s
            LIMIT 1
            """,
            (
                REPOSITORY_KEY,
            ),
        )

        if not row:

            raise RuntimeError(
                f"Drive repository "
                f"'{REPOSITORY_KEY}' "
                f"was not found in "
                f"drive_repositories."
            )

        self.repository_id = row.get(
            "id"
        )

        self.drive_root_id = row.get(
            "root_folder_id"
        )

        if not self.drive_root_id:

            raise RuntimeError(
                f"Drive repository "
                f"'{REPOSITORY_KEY}' "
                f"has no root_folder_id."
            )

        if row.get("enabled") is False:

            raise RuntimeError(
                f"Drive repository "
                f"'{REPOSITORY_KEY}' "
                f"is disabled."
            )

        print(
            "OK: Alcalay repository"
        )

        print(
            f"Repository: "
            f"{row.get('display_name')}"
        )

        print(
            f"Drive root folder ID: "
            f"{self.drive_root_id}"
        )


    # ========================================================================
    # LOCAL STORAGE SCAN
    # ========================================================================

    def scan_local_files(
        self,
    ) -> list[Path]:
        """
        Scan all files under storage.
        """

        print()
        print(
            "Scanning local storage..."
        )
        print()

        print(
            f"Storage: "
            f"{LOCAL_STORAGE}"
        )

        if not LOCAL_STORAGE.exists():

            raise RuntimeError(
                f"Local storage does not exist: "
                f"{LOCAL_STORAGE}"
            )

        files: list[Path] = []

        for path in LOCAL_STORAGE.rglob("*"):

            if not path.is_file():
                continue

            if is_ignored_file(path):
                continue

            # Do not treat generated reports as source files.
            try:

                path.relative_to(
                    REPORT_DIR
                )

                continue

            except ValueError:
                pass

            files.append(path)

        files.sort(
            key=lambda p:
            relative_local_path(
                p
            ).casefold()
        )

        self.summary[
            "total_local_files"
        ] = len(files)

        gmail_count = 0

        for path in files:

            rel = relative_local_path(
                path
            )

            if (
                detect_source_type(rel)
                == "GMAIL"
            ):
                gmail_count += 1

        self.summary[
            "gmail_files"
        ] = gmail_count

        self.summary[
            "non_gmail_files"
        ] = (
            len(files)
            - gmail_count
        )

        print()
        print(
            f"Found "
            f"{len(files):,} files."
        )

        print(
            f"Gmail files: "
            f"{gmail_count:,}"
        )

        print(
            f"Other files: "
            f"{len(files) - gmail_count:,}"
        )

        return files


    # ========================================================================
    # POSTGRESQL FILE MAPPING
    # ========================================================================

    def find_postgresql_mapping(
        self,
        local_path: str,
    ) -> Optional[
        dict[str, Any]
    ]:
        """
        Find an existing local -> Drive mapping.

        First checks drive_local_files.

        Then checks drive_files.

        READ ONLY.
        """

        try:

            row = self.db.fetch_one(
                """
                SELECT *
                FROM drive_local_files
                WHERE local_path = %s
                LIMIT 1
                """,
                (
                    local_path,
                ),
            )

            if row:
                return row

        except Exception:
            pass

        try:

            row = self.db.fetch_one(
                """
                SELECT *
                FROM drive_files
                WHERE local_path = %s
                LIMIT 1
                """,
                (
                    local_path,
                ),
            )

            if row:
                return row

        except Exception:
            pass

        return None


    # ========================================================================
    # EXPECTED DRIVE PATH
    # ========================================================================

    def expected_drive_segments(
        self,
        relative_path: str,
    ) -> list[str]:
        """
        Return expected Drive folders.

        Gmail example:

        storage/gmail/frank.avner@gmail.com/messages/a.eml

        becomes:

        Alcalay/
            gmail/
                frank.avner@gmail.com/
                    messages/
                        a.eml

        Non-Gmail example:

        storage/office/a.docx

        becomes:

        Alcalay/
            Documents/
                a.docx
        """

        rel = Path(
            relative_path
        )

        parts = rel.parts

        if not parts:
            return []

        source_type = detect_source_type(
            relative_path
        )

        if source_type == "GMAIL":

            # gmail /
            # frank.avner@gmail.com /
            # messages

            return list(
                parts[:-1]
            )

        return [
            DOCUMENTS_DRIVE_FOLDER
        ]


    # ========================================================================
    # FIND DRIVE FOLDER
    # ========================================================================

    def find_drive_folder(
        self,
        parent_id: str,
        folder_name: str,
    ) -> Optional[
        dict[str, Any]
    ]:
        """
        Find an existing folder directly
        under parent_id.
        """

        if self.drive_service is None:

            raise RuntimeError(
                "Google Drive service "
                "is not connected."
            )

        query = (
            "trashed = false "
            "and mimeType = "
            "'application/vnd.google-apps.folder' "
            f"and name = "
            f"{json.dumps(folder_name)} "
            f"and {json.dumps(parent_id)} "
            "in parents"
        )

        response = (
            self.drive_service
            .files()
            .list(
                q=query,
                spaces="drive",
                fields=(
                    "files("
                    "id,"
                    "name,"
                    "mimeType,"
                    "parents"
                    ")"
                ),
                pageSize=100,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
            .execute()
        )

        folders = response.get(
            "files",
            []
        )

        if not folders:
            return None

        return folders[0]


    # ========================================================================
    # RESOLVE DRIVE PARENT
    # ========================================================================

    def resolve_existing_drive_parent(
        self,
        folder_segments: list[str],
    ) -> tuple[
        Optional[str],
        bool,
        list[str],
    ]:
        """
        Walk the Drive hierarchy without
        creating anything.

        Returns:

            parent_id
            complete
            missing_segments

        If any segment is missing,
        parent_id is None.
        """

        if not self.drive_root_id:

            raise RuntimeError(
                "Drive root folder ID "
                "is not loaded."
            )

        current_id = (
            self.drive_root_id
        )

        missing: list[str] = []

        for segment in folder_segments:

            folder = (
                self.find_drive_folder(
                    current_id,
                    segment,
                )
            )

            if not folder:

                missing.append(
                    segment
                )

                return (
                    None,
                    False,
                    missing,
                )

            current_id = folder[
                "id"
            ]

        return (
            current_id,
            True,
            missing,
        )


    # ========================================================================
    # FIND DRIVE FILE
    # ========================================================================

    def find_drive_file(
        self,
        parent_id: str,
        file_name: str,
    ) -> Optional[
        dict[str, Any]
    ]:
        """
        Find a file directly under
        a Drive folder.
        """

        if self.drive_service is None:

            raise RuntimeError(
                "Google Drive service "
                "is not connected."
            )

        query = (
            "trashed = false "
            "and mimeType != "
            "'application/vnd.google-apps.folder' "
            f"and name = "
            f"{json.dumps(file_name)} "
            f"and {json.dumps(parent_id)} "
            "in parents"
        )

        response = (
            self.drive_service
            .files()
            .list(
                q=query,
                spaces="drive",
                fields=(
                    "files("
                    "id,"
                    "name,"
                    "mimeType,"
                    "size,"
                    "modifiedTime,"
                    "md5Checksum,"
                    "parents,"
                    "webViewLink"
                    ")"
                ),
                pageSize=100,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
            .execute()
        )

        files = response.get(
            "files",
            []
        )

        if not files:
            return None

        return files[0]


    # ========================================================================
    # DRIVE PATH CHECK
    # ========================================================================

    def check_drive_path(
        self,
        relative_path: str,
    ) -> dict[str, Any]:
        """
        Check whether the expected Drive
        folder tree and file exist.

        Does NOT create anything.
        """

        rel = Path(
            relative_path
        )

        if not rel.parts:

            raise RuntimeError(
                f"Invalid local relative path: "
                f"{relative_path}"
            )

        file_name = rel.name

        folder_segments = (
            self.expected_drive_segments(
                relative_path
            )
        )

        (
            parent_id,
            complete,
            missing_segments,
        ) = (
            self.resolve_existing_drive_parent(
                folder_segments
            )
        )

        result: dict[str, Any] = {

            "drive_root_id":
                self.drive_root_id,

            "expected_folder_segments":
                folder_segments,

            "missing_folder_segments":
                missing_segments,

            "folder_tree_exists":
                complete,

            "drive_parent_id":
                parent_id,

            "drive_file":
                None,
        }

        # If folder tree is missing,
        # the file cannot exist at
        # the expected location.
        if (
            not complete
            or not parent_id
        ):

            result[
                "file_exists"
            ] = False

            return result

        drive_file = (
            self.find_drive_file(
                parent_id,
                file_name,
            )
        )

        result[
            "drive_file"
        ] = drive_file

        result[
            "file_exists"
        ] = (
            drive_file is not None
        )

        return result


    # ========================================================================
    # CLASSIFICATION
    # ========================================================================

    def classify_file(
        self,
        path: Path,
        local_sha256: str,
        pg_mapping: Optional[
            dict[str, Any]
        ],
        drive_info: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Classify one local file.

        Possible actions:

        CREATE
        UPDATE
        SKIP
        DUPLICATE
        """

        relative_path = (
            relative_local_path(
                path
            )
        )

        drive_file = (
            drive_info.get(
                "drive_file"
            )
        )

        folder_tree_exists = (
            drive_info.get(
                "folder_tree_exists",
                False,
            )
        )

        stat = path.stat()

        result: dict[str, Any] = {

            "status": "OK",

            "action": None,

            "source_type":
                detect_source_type(
                    relative_path
                ),

            "local_path":
                str(path),

            "relative_path":
                relative_path,

            "local_size":
                stat.st_size,

            "local_mtime":
                datetime.fromtimestamp(
                    stat.st_mtime,
                    tz=timezone.utc,
                ).isoformat(),

            "sha256":
                local_sha256,

            "postgresql_mapping":
                bool(pg_mapping),

            "drive_folder_tree_exists":
                folder_tree_exists,

            "drive_file_id":
                None,

            "drive_file_name":
                None,

            "drive_file_modified_time":
                None,

            "drive_md5":
                None,

            "missing_drive_folders":
                drive_info.get(
                    "missing_folder_segments",
                    [],
                ),
        }

        if drive_file:

            result[
                "drive_file_id"
            ] = drive_file.get(
                "id"
            )

            result[
                "drive_file_name"
            ] = drive_file.get(
                "name"
            )

            result[
                "drive_file_modified_time"
            ] = drive_file.get(
                "modifiedTime"
            )

            result[
                "drive_md5"
            ] = drive_file.get(
                "md5Checksum"
            )

        # ----------------------------------------------------------------
        # PostgreSQL + Drive
        # ----------------------------------------------------------------

        if (
            pg_mapping
            and drive_file
        ):

            result[
                "action"
            ] = "SKIP"

            self.summary[
                "skip"
            ] += 1

            self.summary[
                "already_in_postgresql"
            ] += 1

            self.summary[
                "already_in_drive"
            ] += 1

            return result

        # ----------------------------------------------------------------
        # PostgreSQL but not Drive
        # ----------------------------------------------------------------

        if (
            pg_mapping
            and not drive_file
        ):

            result[
                "action"
            ] = "CREATE"

            self.summary[
                "already_in_postgresql"
            ] += 1

            self.summary[
                "not_in_drive"
            ] += 1

            self.summary[
                "create"
            ] += 1

            return result

        # ----------------------------------------------------------------
        # Drive but not PostgreSQL
        # ----------------------------------------------------------------

        if (
            not pg_mapping
            and drive_file
        ):

            result[
                "action"
            ] = "DUPLICATE"

            self.summary[
                "not_in_postgresql"
            ] += 1

            self.summary[
                "already_in_drive"
            ] += 1

            self.summary[
                "duplicate"
            ] += 1

            return result

        # ----------------------------------------------------------------
        # Neither PostgreSQL nor Drive
        # ----------------------------------------------------------------

        result[
            "action"
        ] = "CREATE"

        self.summary[
            "not_in_postgresql"
        ] += 1

        self.summary[
            "not_in_drive"
        ] += 1

        self.summary[
            "create"
        ] += 1

        return result


    # ========================================================================
    # CHECK ONE FILE
    # ========================================================================

    def check_one_file(
        self,
        path: Path,
        index: int,
        total: int,
    ) -> dict[str, Any]:
        """
        Perform all checks for one file.
        """

        relative_path = (
            relative_local_path(
                path
            )
        )

        try:

            local_sha256 = (
                sha256_file(
                    path
                )
            )

            pg_mapping = (
                self.find_postgresql_mapping(
                    relative_path
                )
            )

            drive_info = (
                self.check_drive_path(
                    relative_path
                )
            )

            result = (
                self.classify_file(
                    path=path,
                    local_sha256=local_sha256,
                    pg_mapping=pg_mapping,
                    drive_info=drive_info,
                )
            )

            result[
                "status"
            ] = "OK"

            return result

        except Exception as exc:

            self.summary[
                "error"
            ] += 1

            return {
                "status": "ERROR",

                "source_type":
                    detect_source_type(
                        relative_path
                    ),

                "local_path":
                    str(path),

                "relative_path":
                    relative_path,

                "error":
                    str(exc),
            }


    # ========================================================================
    # RUN
    # ========================================================================

    def run(self) -> None:
        """
        Execute complete read-only pre-check.
        """

        print("=" * 80)

        print(
            "ALCALAY DRIVE SYNC PRE-CHECK"
        )

        print("=" * 80)

        print()

        print(
            "MODE: READ ONLY"
        )

        print(
            "לא יתבצעו העלאות, הורדות, "
            "יצירת תיקיות או שינויים "
            "ב-PostgreSQL."
        )

        print()

        # Google Drive.
        self.connect_drive()

        # PostgreSQL repository.
        self.load_repository()

        # Local storage.
        files = (
            self.scan_local_files()
        )

        print()

        print(
            "Checking files..."
        )

        print()

        total = len(files)

        for index, path in enumerate(
            files,
            1,
        ):

            result = (
                self.check_one_file(
                    path,
                    index,
                    total,
                )
            )

            self.results.append(
                result
            )

            if (
                index % 100 == 0
                or index == total
            ):

                print(
                    f"Checked "
                    f"{index:,}/"
                    f"{total:,}"
                )

        self.write_reports()

        self.print_summary()


    # ========================================================================
    # BUILD JSON REPORT
    # ========================================================================

    def build_report(
        self,
    ) -> dict[str, Any]:
        """
        Build complete JSON report.
        """

        return {

            "created_at":
                utc_now_iso(),

            "mode":
                "READ_ONLY",

            "repository": {

                "repository_key":
                    REPOSITORY_KEY,

                "repository_id":
                    self.repository_id,

                "root_folder_id":
                    self.drive_root_id,

                "drive_account":
                    self.drive_account,
            },

            "local_storage":
                str(LOCAL_STORAGE),

            "summary":
                self.summary,

            "results":
                self.results,
        }


    # ========================================================================
    # WRITE REPORTS
    # ========================================================================

    def write_reports(
        self,
    ) -> None:
        """
        Write JSON and TXT reports.
        """

        REPORT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        timestamp = (
            datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )
        )

        json_path = (
            REPORT_DIR
            / f"pre_sync_{timestamp}.json"
        )

        txt_path = (
            REPORT_DIR
            / f"pre_sync_{timestamp}.txt"
        )

        report = (
            self.build_report()
        )

        with json_path.open(
            "w",
            encoding="utf-8",
        ) as file_handle:

            json.dump(
                report,
                file_handle,
                ensure_ascii=False,
                indent=2,
                default=json_default,
            )

        self.write_text_report(
            txt_path,
            report,
        )

        print()

        print(
            "Report written to:"
        )

        print(
            json_path
        )

        print(
            txt_path
        )


    # ========================================================================
    # WRITE TEXT REPORT
    # ========================================================================

    def write_text_report(
        self,
        path: Path,
        report: dict[str, Any],
    ) -> None:
        """
        Write human-readable report.
        """

        summary = (
            report["summary"]
        )

        with path.open(
            "w",
            encoding="utf-8",
        ) as file_handle:

            file_handle.write(
                "=" * 80
                + "\n"
            )

            file_handle.write(
                "ALCALAY DRIVE SYNC PRE-CHECK\n"
            )

            file_handle.write(
                "=" * 80
                + "\n\n"
            )

            file_handle.write(
                f"Created: "
                f"{report['created_at']}\n"
            )

            file_handle.write(
                f"Mode: "
                f"{report['mode']}\n"
            )

            file_handle.write(
                f"Repository: "
                f"{REPOSITORY_KEY}\n"
            )

            file_handle.write(
                f"Drive account: "
                f"{report['repository'].get('drive_account')}\n"
            )

            file_handle.write(
                f"Drive root: "
                f"{report['repository'].get('root_folder_id')}\n"
            )

            file_handle.write(
                "\n"
            )

            file_handle.write(
                "SUMMARY\n"
            )

            file_handle.write(
                "=" * 80
                + "\n"
            )

            ordered_keys = [
                "total_local_files",
                "gmail_files",
                "non_gmail_files",
                "already_in_postgresql",
                "not_in_postgresql",
                "already_in_drive",
                "not_in_drive",
                "create",
                "update",
                "skip",
                "duplicate",
                "warning",
                "error",
            ]

            for key in ordered_keys:

                file_handle.write(
                    f"{key:24}: "
                    f"{summary.get(key, 0):,}\n"
                )

            file_handle.write(
                "\n"
            )

            file_handle.write(
                "ERRORS\n"
            )

            file_handle.write(
                "=" * 80
                + "\n"
            )

            errors = [
                result
                for result in report[
                    "results"
                ]
                if result.get(
                    "status"
                ) == "ERROR"
            ]

            if not errors:

                file_handle.write(
                    "No errors.\n"
                )

            else:

                for error in errors:

                    file_handle.write(
                        "\nPath: "
                        f"{error.get('local_path')}\n"
                    )

                    file_handle.write(
                        "Error: "
                        f"{error.get('error')}\n"
                    )

            file_handle.write(
                "\n"
            )

            file_handle.write(
                "CLASSIFICATION\n"
            )

            file_handle.write(
                "=" * 80
                + "\n"
            )

            actions: dict[
                str,
                int
            ] = {}

            for result in report[
                "results"
            ]:

                action = result.get(
                    "action",
                    "NO_ACTION",
                )

                actions[action] = (
                    actions.get(
                        action,
                        0,
                    )
                    + 1
                )

            for action, count in sorted(
                actions.items()
            ):

                file_handle.write(
                    f"{action:24}: "
                    f"{count:,}\n"
                )


    # ========================================================================
    # PRINT SUMMARY
    # ========================================================================

    def print_summary(
        self,
    ) -> None:
        """
        Print final console summary.
        """

        print()

        print("=" * 80)

        print(
            "PRE-CHECK SUMMARY"
        )

        print("=" * 80)

        print(
            f"Total local files     : "
            f"{self.summary['total_local_files']:,}"
        )

        print(
            f"Gmail files           : "
            f"{self.summary['gmail_files']:,}"
        )

        print(
            f"Other files           : "
            f"{self.summary['non_gmail_files']:,}"
        )

        print(
            f"PostgreSQL already    : "
            f"{self.summary['already_in_postgresql']:,}"
        )

        print(
            f"PostgreSQL missing    : "
            f"{self.summary['not_in_postgresql']:,}"
        )

        print(
            f"Already in Drive      : "
            f"{self.summary['already_in_drive']:,}"
        )

        print(
            f"Not in Drive          : "
            f"{self.summary['not_in_drive']:,}"
        )

        print(
            f"CREATE                : "
            f"{self.summary['create']:,}"
        )

        print(
            f"UPDATE                : "
            f"{self.summary['update']:,}"
        )

        print(
            f"SKIP                  : "
            f"{self.summary['skip']:,}"
        )

        print(
            f"DUPLICATE             : "
            f"{self.summary['duplicate']:,}"
        )

        print(
            f"WARNINGS              : "
            f"{self.summary['warning']:,}"
        )

        print(
            f"ERRORS                : "
            f"{self.summary['error']:,}"
        )

        # ------------------------------------------------------------
        # Gmail path validation
        # ------------------------------------------------------------

        gmail_results = [
            result
            for result in self.results
            if result.get(
                "source_type"
            ) == "GMAIL"
        ]

        gmail_path_errors = 0

        for result in gmail_results:

            if result.get(
                "status"
            ) == "ERROR":

                gmail_path_errors += 1

        print(
            f"Gmail path checks     : "
            f"{len(gmail_results):,}"
        )

        print(
            f"Gmail path errors     : "
            f"{gmail_path_errors:,}"
        )

        print(
            "=" * 80
        )


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:

    checker = (
        DriveSyncChecker()
    )

    try:

        checker.run()

        return 0

    except KeyboardInterrupt:

        print()

        print(
            "PRE-CHECK INTERRUPTED."
        )

        return 130

    except Exception as exc:

        print()

        print("=" * 80)

        print(
            "PRE-CHECK FAILED"
        )

        print("=" * 80)

        print()

        print(
            str(exc)
        )

        print()

        traceback.print_exc()

        return 1


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )