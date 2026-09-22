# -*- coding: utf-8 -*-

"""
Alcalay - Google Drive Duplicate / Version Checker
===================================================

Pre-download duplicate and version detection.

This module performs PostgreSQL metadata checks only.

It does NOT:
    - download files
    - export Google Workspace files
    - modify Google Drive
    - delete files
    - move files
    - rename files

Workflow:

    drive_files
        |
        v
    Duplicate / Version Check
        |
        +--> already downloaded and unchanged
        |
        +--> existing unchanged version
        |
        +--> new version
        |
        +--> duplicate by known checksum
        |
        +--> ready for download

Important:

Google Workspace files such as Google Docs normally do not have
md5Checksum in Drive metadata.

Therefore this module does NOT claim that content equality has
been established for such files.

Exact content duplicate detection for Google Workspace documents
requires a later deterministic export/download and checksum stage.
That stage is intentionally NOT performed here.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


# ----------------------------------------------------------------------
# Project root
# ----------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ----------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------

from src.database.connection import DatabaseConnection


# ----------------------------------------------------------------------
# Status constants
# ----------------------------------------------------------------------

STATUS_ALREADY_DOWNLOADED = "ALREADY_DOWNLOADED"
STATUS_NO_DOWNLOAD_NEEDED = "NO_DOWNLOAD_NEEDED"
STATUS_NEW_VERSION = "NEW_VERSION"
STATUS_READY_FOR_DOWNLOAD = "READY_FOR_DOWNLOAD"
STATUS_DUPLICATE_BY_CHECKSUM = "DUPLICATE_BY_CHECKSUM"
STATUS_ERROR = "ERROR"


# ----------------------------------------------------------------------
# Result object
# ----------------------------------------------------------------------

@dataclass
class DuplicateCheckResult:
    drive_file_db_id: int
    drive_file_id: str
    name: str
    mime_type: str

    status: str

    existing_version_id: int | None = None
    existing_version_number: int | None = None

    new_version_number: int | None = None

    duplicate_group_id: int | None = None
    canonical_drive_file_db_id: int | None = None

    reason: str = ""


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------

def parse_timestamp(value: Any) -> datetime | None:
    """
    Convert PostgreSQL timestamp or ISO string to datetime.
    """

    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):

        value = value.strip()

        if not value:
            return None

        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    return None


def normalize_checksum(value: Any) -> str | None:
    """
    Normalize checksum for comparison.
    """

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value.lower()


# ----------------------------------------------------------------------
# Main checker
# ----------------------------------------------------------------------

class DriveDuplicateChecker:
    """
    Pre-download duplicate/version checker.

    Uses the existing Alcalay DatabaseConnection class and its
    psycopg connection.

    No Google Drive download/export is performed.
    """

    def __init__(self) -> None:

        self.db = DatabaseConnection()

        self.connection = None

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(
        self,
        repository_key: str = "alcalay",
    ) -> dict[str, Any]:

        print("=" * 72)
        print("STARTING GOOGLE DRIVE DUPLICATE / VERSION CHECK")
        print("=" * 72)
        print()
        print("[DATABASE] PostgreSQL")
        print("[DOWNLOAD] NO")
        print("[DRIVE WRITE] NO")
        print()

        summary: dict[str, Any] = {
            "repository": repository_key,
            "candidates": 0,
            "already_downloaded": 0,
            "no_download_needed": 0,
            "new_versions": 0,
            "ready_for_download": 0,
            "duplicates_by_checksum": 0,
            "errors": 0,
        }

        try:

            # ----------------------------------------------------------
            # Open PostgreSQL connection.
            # ----------------------------------------------------------

            self.connection = self.db.connect()

            # ----------------------------------------------------------
            # Find repository by repository_key.
            # ----------------------------------------------------------

            repository_id = self.get_repository_id(
                repository_key
            )

            if repository_id is None:

                print(
                    f"[ERROR] Repository not found: "
                    f"{repository_key}"
                )

                summary["errors"] += 1

                return summary

            # ----------------------------------------------------------
            # Load relevant files.
            # ----------------------------------------------------------

            files = self.get_relevant_files(
                repository_id
            )

            summary["candidates"] = len(files)

            print(
                f"[REPOSITORY] "
                f"{repository_key}"
            )

            print(
                f"[REPOSITORY ID] "
                f"{repository_id}"
            )

            print(
                f"[RELEVANT FILES] "
                f"{len(files)}"
            )

            print()

            if not files:

                print(
                    "[INFO] No relevant files require "
                    "duplicate/version checking."
                )

                return summary

            # ----------------------------------------------------------
            # Process files.
            # ----------------------------------------------------------

            for index, file_row in enumerate(
                files,
                start=1,
            ):

                print("-" * 72)

                print(
                    f"[FILE] "
                    f"{index}/{len(files)}"
                )

                print(
                    f"[NAME] "
                    f"{file_row['name']}"
                )

                print(
                    f"[DRIVE FILE ID] "
                    f"{file_row['drive_file_id']}"
                )

                print(
                    f"[MIME] "
                    f"{file_row['mime_type']}"
                )

                try:

                    result = self.check_file(
                        file_row
                    )

                    self.print_result(
                        result
                    )

                    if result.status == STATUS_ALREADY_DOWNLOADED:

                        summary[
                            "already_downloaded"
                        ] += 1

                    elif result.status == STATUS_NO_DOWNLOAD_NEEDED:

                        summary[
                            "no_download_needed"
                        ] += 1

                    elif result.status == STATUS_NEW_VERSION:

                        summary[
                            "new_versions"
                        ] += 1

                    elif result.status == STATUS_READY_FOR_DOWNLOAD:

                        summary[
                            "ready_for_download"
                        ] += 1

                    elif result.status == STATUS_DUPLICATE_BY_CHECKSUM:

                        summary[
                            "duplicates_by_checksum"
                        ] += 1

                    else:

                        summary[
                            "errors"
                        ] += 1

                    self.connection.commit()

                except Exception as exc:

                    summary["errors"] += 1

                    print(
                        f"[ERROR] {exc}"
                    )

                    try:
                        self.connection.rollback()
                    except Exception:
                        pass

                    try:

                        self.set_file_error(
                            int(file_row["id"]),
                            str(exc),
                        )

                        self.connection.commit()

                    except Exception:

                        try:
                            self.connection.rollback()
                        except Exception:
                            pass

                print()

            return summary

        except Exception as exc:

            summary["errors"] += 1

            print(
                f"[FATAL ERROR] "
                f"{exc}"
            )

            if self.connection is not None:

                try:
                    self.connection.rollback()
                except Exception:
                    pass

            return summary

        finally:

            if self.connection is not None:

                try:
                    self.connection.close()
                except Exception:
                    pass

                self.connection = None

    # ------------------------------------------------------------------
    # Repository
    # ------------------------------------------------------------------

    def get_repository_id(
        self,
        repository_key: str,
    ) -> int | None:

        """
        Get repository ID using drive_repositories.repository_key.

        The database schema does NOT contain a 'name' column.
        """

        sql = """
            SELECT id
            FROM drive_repositories
            WHERE repository_key = %s
              AND enabled = TRUE
            LIMIT 1
        """

        with self.connection.cursor() as cursor:

            cursor.execute(
                sql,
                (repository_key,),
            )

            row = cursor.fetchone()

        if row is None:
            return None

        return int(row[0])

    # ------------------------------------------------------------------
    # Relevant files
    # ------------------------------------------------------------------

    def get_relevant_files(
        self,
        repository_id: int,
    ) -> list[dict[str, Any]]:

        sql = """
            SELECT
                id,
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
                is_relevant,
                local_status,
                local_path,
                local_checksum,
                local_size_bytes,
                last_downloaded_at
            FROM drive_files
            WHERE repository_id = %s
              AND is_trashed = FALSE
              AND is_relevant = TRUE
            ORDER BY id
        """

        columns = [
            "id",
            "drive_file_id",
            "parent_drive_file_id",
            "name",
            "mime_type",
            "size_bytes",
            "created_time",
            "modified_time",
            "md5_checksum",
            "web_view_link",
            "is_trashed",
            "is_relevant",
            "local_status",
            "local_path",
            "local_checksum",
            "local_size_bytes",
            "last_downloaded_at",
        ]

        with self.connection.cursor() as cursor:

            cursor.execute(
                sql,
                (repository_id,),
            )

            rows = cursor.fetchall()

        return [
            dict(
                zip(
                    columns,
                    row,
                )
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Check one file
    # ------------------------------------------------------------------

    def check_file(
        self,
        file_row: dict[str, Any],
    ) -> DuplicateCheckResult:

        drive_file_db_id = int(
            file_row["id"]
        )

        drive_file_id = str(
            file_row["drive_file_id"]
        )

        name = str(
            file_row["name"]
        )

        mime_type = str(
            file_row["mime_type"]
        )

        current_modified = parse_timestamp(
            file_row.get("modified_time")
        )

        current_size = file_row.get(
            "size_bytes"
        )

        current_checksum = normalize_checksum(
            file_row.get("md5_checksum")
        )

        local_status = (
            str(
                file_row.get(
                    "local_status"
                )
                or ""
            )
            .strip()
            .upper()
        )

        local_path = file_row.get(
            "local_path"
        )

        # --------------------------------------------------------------
        # Existing versions.
        # --------------------------------------------------------------

        versions = self.get_versions(
            drive_file_db_id
        )

        latest_version = (
            versions[0]
            if versions
            else None
        )

        # --------------------------------------------------------------
        # Existing current local file.
        # --------------------------------------------------------------

        local_file = self.get_current_local_file(
            drive_file_db_id
        )

        if local_file:

            local_version_id = local_file.get(
                "drive_file_version_id"
            )

            if local_version_id is not None:

                local_version = self.get_version_by_id(
                    int(local_version_id)
                )

                if local_version:

                    if self.version_matches_current_file(
                        local_version,
                        current_modified,
                        current_size,
                        current_checksum,
                    ):

                        return DuplicateCheckResult(
                            drive_file_db_id=drive_file_db_id,
                            drive_file_id=drive_file_id,
                            name=name,
                            mime_type=mime_type,
                            status=STATUS_ALREADY_DOWNLOADED,
                            existing_version_id=int(
                                local_version["id"]
                            ),
                            existing_version_number=int(
                                local_version[
                                    "version_number"
                                ]
                            ),
                            reason=(
                                "Current local file already "
                                "represents the current "
                                "Drive version."
                            ),
                        )

        # --------------------------------------------------------------
        # Existing downloaded state.
        # --------------------------------------------------------------

        if (
            local_status == "DOWNLOADED"
            and local_path
            and latest_version
        ):

            if self.version_matches_current_file(
                latest_version,
                current_modified,
                current_size,
                current_checksum,
            ):

                return DuplicateCheckResult(
                    drive_file_db_id=drive_file_db_id,
                    drive_file_id=drive_file_id,
                    name=name,
                    mime_type=mime_type,
                    status=STATUS_ALREADY_DOWNLOADED,
                    existing_version_id=int(
                        latest_version["id"]
                    ),
                    existing_version_number=int(
                        latest_version[
                            "version_number"
                        ]
                    ),
                    reason=(
                        "drive_files reports the file "
                        "as downloaded and the current "
                        "Drive metadata matches the "
                        "latest registered version."
                    ),
                )

        # --------------------------------------------------------------
        # Known checksum duplicate.
        # --------------------------------------------------------------

        if current_checksum:

            duplicate = self.find_checksum_duplicate(
                drive_file_db_id,
                current_checksum,
            )

            if duplicate:

                duplicate_group_id = int(
                    duplicate[
                        "duplicate_group_id"
                    ]
                )

                canonical_id = (
                    int(
                        duplicate[
                            "canonical_drive_file_id"
                        ]
                    )
                    if duplicate[
                        "canonical_drive_file_id"
                    ] is not None
                    else None
                )

                self.ensure_duplicate_member(
                    duplicate_group_id,
                    drive_file_db_id,
                    canonical_id == drive_file_db_id,
                )

                return DuplicateCheckResult(
                    drive_file_db_id=drive_file_db_id,
                    drive_file_id=drive_file_id,
                    name=name,
                    mime_type=mime_type,
                    status=STATUS_DUPLICATE_BY_CHECKSUM,
                    duplicate_group_id=duplicate_group_id,
                    canonical_drive_file_db_id=canonical_id,
                    reason=(
                        "Another registered Drive file "
                        "already has the same checksum."
                    ),
                )

        # --------------------------------------------------------------
        # Existing version.
        # --------------------------------------------------------------

        if latest_version:

            if self.version_matches_current_file(
                latest_version,
                current_modified,
                current_size,
                current_checksum,
            ):

                return DuplicateCheckResult(
                    drive_file_db_id=drive_file_db_id,
                    drive_file_id=drive_file_id,
                    name=name,
                    mime_type=mime_type,
                    status=STATUS_NO_DOWNLOAD_NEEDED,
                    existing_version_id=int(
                        latest_version["id"]
                    ),
                    existing_version_number=int(
                        latest_version[
                            "version_number"
                        ]
                    ),
                    reason=(
                        "Current Drive metadata matches "
                        "the latest discovered version."
                    ),
                )

            # ----------------------------------------------------------
            # Metadata changed.
            # ----------------------------------------------------------

            new_version_number = (
                int(
                    latest_version[
                        "version_number"
                    ]
                )
                + 1
            )

            self.create_version(
                drive_file_db_id=drive_file_db_id,
                version_number=new_version_number,
                modified_time=current_modified,
                size_bytes=current_size,
                md5_checksum=current_checksum,
            )

            return DuplicateCheckResult(
                drive_file_db_id=drive_file_db_id,
                drive_file_id=drive_file_id,
                name=name,
                mime_type=mime_type,
                status=STATUS_NEW_VERSION,
                existing_version_id=int(
                    latest_version["id"]
                ),
                existing_version_number=int(
                    latest_version[
                        "version_number"
                    ]
                ),
                new_version_number=new_version_number,
                reason=(
                    "Drive metadata changed compared "
                    "with the latest registered version."
                ),
            )

        # --------------------------------------------------------------
        # First discovery.
        # --------------------------------------------------------------

        version_number = 1

        self.create_version(
            drive_file_db_id=drive_file_db_id,
            version_number=version_number,
            modified_time=current_modified,
            size_bytes=current_size,
            md5_checksum=current_checksum,
        )

        return DuplicateCheckResult(
            drive_file_db_id=drive_file_db_id,
            drive_file_id=drive_file_id,
            name=name,
            mime_type=mime_type,
            status=STATUS_READY_FOR_DOWNLOAD,
            new_version_number=version_number,
            reason=(
                "No previous version or local copy exists. "
                "The file is ready for the download/export stage."
            ),
        )

    # ------------------------------------------------------------------
    # Get versions
    # ------------------------------------------------------------------

    def get_versions(
        self,
        drive_file_db_id: int,
    ) -> list[dict[str, Any]]:

        sql = """
            SELECT
                id,
                drive_file_id_fk,
                version_number,
                drive_modified_time,
                size_bytes,
                md5_checksum,
                discovered_at,
                downloaded,
                local_path,
                local_checksum,
                downloaded_at,
                status,
                error_message
            FROM drive_file_versions
            WHERE drive_file_id_fk = %s
            ORDER BY version_number DESC
        """

        columns = [
            "id",
            "drive_file_id_fk",
            "version_number",
            "drive_modified_time",
            "size_bytes",
            "md5_checksum",
            "discovered_at",
            "downloaded",
            "local_path",
            "local_checksum",
            "downloaded_at",
            "status",
            "error_message",
        ]

        with self.connection.cursor() as cursor:

            cursor.execute(
                sql,
                (drive_file_db_id,),
            )

            rows = cursor.fetchall()

        return [
            dict(
                zip(
                    columns,
                    row,
                )
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Get version by ID
    # ------------------------------------------------------------------

    def get_version_by_id(
        self,
        version_id: int,
    ) -> dict[str, Any] | None:

        sql = """
            SELECT
                id,
                drive_file_id_fk,
                version_number,
                drive_modified_time,
                size_bytes,
                md5_checksum,
                discovered_at,
                downloaded,
                local_path,
                local_checksum,
                downloaded_at,
                status,
                error_message
            FROM drive_file_versions
            WHERE id = %s
            LIMIT 1
        """

        columns = [
            "id",
            "drive_file_id_fk",
            "version_number",
            "drive_modified_time",
            "size_bytes",
            "md5_checksum",
            "discovered_at",
            "downloaded",
            "local_path",
            "local_checksum",
            "downloaded_at",
            "status",
            "error_message",
        ]

        with self.connection.cursor() as cursor:

            cursor.execute(
                sql,
                (version_id,),
            )

            row = cursor.fetchone()

        if row is None:
            return None

        return dict(
            zip(
                columns,
                row,
            )
        )

    # ------------------------------------------------------------------
    # Get current local file
    # ------------------------------------------------------------------

    def get_current_local_file(
        self,
        drive_file_db_id: int,
    ) -> dict[str, Any] | None:

        sql = """
            SELECT
                id,
                drive_file_id_fk,
                drive_file_version_id,
                local_path,
                file_name,
                size_bytes,
                checksum,
                checksum_type,
                created_at,
                last_verified_at,
                is_current
            FROM drive_local_files
            WHERE drive_file_id_fk = %s
              AND is_current = TRUE
            ORDER BY id DESC
            LIMIT 1
        """

        columns = [
            "id",
            "drive_file_id_fk",
            "drive_file_version_id",
            "local_path",
            "file_name",
            "size_bytes",
            "checksum",
            "checksum_type",
            "created_at",
            "last_verified_at",
            "is_current",
        ]

        with self.connection.cursor() as cursor:

            cursor.execute(
                sql,
                (drive_file_db_id,),
            )

            row = cursor.fetchone()

        if row is None:
            return None

        return dict(
            zip(
                columns,
                row,
            )
        )

    # ------------------------------------------------------------------
    # Compare version with current Drive metadata
    # ------------------------------------------------------------------

    def version_matches_current_file(
        self,
        version: dict[str, Any],
        current_modified: datetime | None,
        current_size: Any,
        current_checksum: str | None,
    ) -> bool:

        version_modified = parse_timestamp(
            version.get(
                "drive_modified_time"
            )
        )

        version_size = version.get(
            "size_bytes"
        )

        version_checksum = normalize_checksum(
            version.get(
                "md5_checksum"
            )
        )

        # --------------------------------------------------------------
        # Checksum comparison.
        # --------------------------------------------------------------

        if (
            current_checksum
            and version_checksum
        ):

            return (
                current_checksum
                == version_checksum
            )

        # --------------------------------------------------------------
        # Modified time comparison.
        # --------------------------------------------------------------

        if (
            current_modified
            and version_modified
        ):

            if current_modified != version_modified:
                return False

        elif (
            current_modified
            or version_modified
        ):

            return False

        # --------------------------------------------------------------
        # Size comparison.
        # --------------------------------------------------------------

        if (
            current_size is not None
            and version_size is not None
        ):

            try:

                if int(current_size) != int(
                    version_size
                ):
                    return False

            except (
                TypeError,
                ValueError,
            ):

                return False

        elif (
            current_size is not None
            or version_size is not None
        ):

            return False

        return True

    # ------------------------------------------------------------------
    # Create version
    # ------------------------------------------------------------------

    def create_version(
        self,
        drive_file_db_id: int,
        version_number: int,
        modified_time: datetime | None,
        size_bytes: Any,
        md5_checksum: str | None,
    ) -> int:

        sql = """
            INSERT INTO drive_file_versions (
                drive_file_id_fk,
                version_number,
                drive_modified_time,
                size_bytes,
                md5_checksum,
                status,
                downloaded
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                'DISCOVERED',
                FALSE
            )
            ON CONFLICT (
                drive_file_id_fk,
                version_number
            )
            DO UPDATE SET
                drive_modified_time =
                    EXCLUDED.drive_modified_time,
                size_bytes =
                    EXCLUDED.size_bytes,
                md5_checksum =
                    EXCLUDED.md5_checksum
            RETURNING id
        """

        with self.connection.cursor() as cursor:

            cursor.execute(
                sql,
                (
                    drive_file_db_id,
                    version_number,
                    modified_time,
                    size_bytes,
                    md5_checksum,
                ),
            )

            row = cursor.fetchone()

        return int(row[0])

    # ------------------------------------------------------------------
    # Find duplicate by known checksum
    # ------------------------------------------------------------------

    def find_checksum_duplicate(
        self,
        drive_file_db_id: int,
        checksum: str,
    ) -> dict[str, Any] | None:

        sql = """
            SELECT
                dd.id AS duplicate_group_id,
                dd.canonical_drive_file_id
            FROM drive_duplicates dd
            JOIN drive_duplicate_members dm
                ON dm.duplicate_group_id =
                   dd.id
            WHERE lower(dd.checksum) =
                  lower(%s)
              AND dd.checksum_type = 'MD5'
              AND dm.drive_file_id_fk <> %s
            ORDER BY dd.id
            LIMIT 1
        """

        with self.connection.cursor() as cursor:

            cursor.execute(
                sql,
                (
                    checksum,
                    drive_file_db_id,
                ),
            )

            row = cursor.fetchone()

        if row is None:
            return None

        return {
            "duplicate_group_id": row[0],
            "canonical_drive_file_id": row[1],
        }

    # ------------------------------------------------------------------
    # Ensure duplicate member
    # ------------------------------------------------------------------

    def ensure_duplicate_member(
        self,
        duplicate_group_id: int,
        drive_file_db_id: int,
        is_canonical: bool,
    ) -> None:

        sql = """
            INSERT INTO drive_duplicate_members (
                duplicate_group_id,
                drive_file_id_fk,
                is_canonical
            )
            VALUES (
                %s,
                %s,
                %s
            )
            ON CONFLICT (
                duplicate_group_id,
                drive_file_id_fk
            )
            DO UPDATE SET
                is_canonical =
                    EXCLUDED.is_canonical
        """

        with self.connection.cursor() as cursor:

            cursor.execute(
                sql,
                (
                    duplicate_group_id,
                    drive_file_db_id,
                    is_canonical,
                )
            )

    # ------------------------------------------------------------------
    # Save error
    # ------------------------------------------------------------------

    def set_file_error(
        self,
        drive_file_db_id: int,
        error_message: str,
    ) -> None:

        sql = """
            UPDATE drive_files
            SET
                last_error = %s,
                last_checked_at = NOW()
            WHERE id = %s
        """

        with self.connection.cursor() as cursor:

            cursor.execute(
                sql,
                (
                    error_message,
                    drive_file_db_id,
                )
            )

    # ------------------------------------------------------------------
    # Print result
    # ------------------------------------------------------------------

    def print_result(
        self,
        result: DuplicateCheckResult,
    ) -> None:

        print(
            f"[RESULT] "
            f"{result.status}"
        )

        if result.existing_version_number is not None:

            print(
                f"[EXISTING VERSION] "
                f"{result.existing_version_number}"
            )

        if result.new_version_number is not None:

            print(
                f"[NEW VERSION] "
                f"{result.new_version_number}"
            )

        if result.duplicate_group_id is not None:

            print(
                f"[DUPLICATE GROUP] "
                f"{result.duplicate_group_id}"
            )

        if result.canonical_drive_file_db_id is not None:

            print(
                f"[CANONICAL FILE DB ID] "
                f"{result.canonical_drive_file_db_id}"
            )

        print(
            f"[REASON] "
            f"{result.reason}"
        )


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main() -> int:

    checker = DriveDuplicateChecker()

    summary = checker.run(
        repository_key="alcalay"
    )

    print("=" * 72)
    print(
        "GOOGLE DRIVE DUPLICATE / VERSION CHECK COMPLETED"
    )
    print("=" * 72)

    print(
        f"[REPOSITORY] "
        f"{summary['repository']}"
    )

    print(
        f"[CANDIDATES] "
        f"{summary['candidates']}"
    )

    print(
        f"[ALREADY DOWNLOADED] "
        f"{summary['already_downloaded']}"
    )

    print(
        f"[NO DOWNLOAD NEEDED] "
        f"{summary['no_download_needed']}"
    )

    print(
        f"[NEW VERSIONS] "
        f"{summary['new_versions']}"
    )

    print(
        f"[READY FOR DOWNLOAD] "
        f"{summary['ready_for_download']}"
    )

    print(
        f"[DUPLICATES BY CHECKSUM] "
        f"{summary['duplicates_by_checksum']}"
    )

    print(
        f"[ERRORS] "
        f"{summary['errors']}"
    )

    print("[DOWNLOAD] NO")
    print("[DRIVE WRITE] NO")
    print()

    if summary["errors"] > 0:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())