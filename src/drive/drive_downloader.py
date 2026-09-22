# -*- coding: utf-8 -*-

"""
Alcalay - Google Drive Downloader / Exporter
============================================

Downloads / exports only files that were previously marked
READY_FOR_DOWNLOAD by drive_duplicate_checker.py.

Workflow:

    drive_files
        ↓
    READY_FOR_DOWNLOAD
        ↓
    Google Drive download/export
        ↓
    local file
        ↓
    SHA-256 checksum
        ↓
    PostgreSQL
        ↓
    drive_file_versions
    drive_local_files
    drive_files

Important:

- This module does NOT search Google Drive.
- This module does NOT select keywords.
- This module does NOT decide relevance.
- This module does NOT decide which version is newer.
- It trusts the previous duplicate/version check.
- It never downloads an already downloaded version.
- Google Workspace native files are exported.
- Binary files are downloaded directly.
- Google Drive is read-only.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Any

from googleapiclient.http import MediaIoBaseDownload


# ----------------------------------------------------------------------
# Project root
# ----------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ----------------------------------------------------------------------
# Alcalay imports
# ----------------------------------------------------------------------

from src.database.connection import DatabaseConnection
from src.drive.drive_connection import DriveConnection


# ----------------------------------------------------------------------
# Local storage
# ----------------------------------------------------------------------

LOCAL_ROOT = PROJECT_ROOT / "storage" / "drive"


# ----------------------------------------------------------------------
# Google Workspace MIME types
# ----------------------------------------------------------------------

GOOGLE_EXPORT_TYPES = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
    "application/vnd.google-apps.drawing": (
        "image/png",
        ".png",
    ),
}


# ----------------------------------------------------------------------
# Downloader
# ----------------------------------------------------------------------


class DriveDownloader:

    def __init__(self) -> None:
        self.db = DatabaseConnection()
        self.connection = None

        # DriveConnection owns the actual Google Drive API service.
        self.drive_connection = None
        self.drive = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        self.connection = self.db.connect()

        self.drive_connection = DriveConnection(
            account_email="frank.avner@gmail.com"
        )

        # IMPORTANT:
        #
        # DriveConnection.connect() returns the connected
        # account email as a string.
        #
        # The actual Google Drive API service is stored in:
        #
        #     self.drive_connection.service
        #
        self.drive_connection.connect()

        self.drive = self.drive_connection.service

        if self.drive is None:
            raise RuntimeError(
                "Google Drive service was not created."
            )

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def get_repository_id(
        self,
        repository_key: str,
    ) -> int:

        cursor = self.connection.cursor()

        try:
            cursor.execute(
                """
                SELECT id
                FROM drive_repositories
                WHERE repository_key = %s
                  AND enabled = TRUE
                LIMIT 1
                """,
                (repository_key,),
            )

            row = cursor.fetchone()

            if row is None:
                raise RuntimeError(
                    f"Repository not found or disabled: "
                    f"{repository_key}"
                )

            return int(row[0])

        finally:
            cursor.close()

    # ------------------------------------------------------------------

    def get_ready_files(
        self,
        repository_id: int,
    ) -> list[dict[str, Any]]:

        cursor = self.connection.cursor()

        try:
            cursor.execute(
                """
                SELECT
                    df.id,
                    df.drive_file_id,
                    df.parent_drive_file_id,
                    df.name,
                    df.mime_type,
                    df.size_bytes,
                    df.created_time,
                    df.modified_time,
                    df.md5_checksum,
                    df.web_view_link,
                    df.local_status,
                    df.local_path,
                    df.local_checksum,
                    df.last_downloaded_at,

                    v.id AS version_id,
                    v.version_number,
                    v.drive_modified_time,
                    v.size_bytes AS version_size_bytes,
                    v.md5_checksum AS version_md5_checksum,
                    v.downloaded,
                    v.local_path AS version_local_path,
                    v.local_checksum AS version_local_checksum,
                    v.status AS version_status

                FROM drive_files df

                JOIN drive_file_versions v
                  ON v.drive_file_id_fk = df.id

                WHERE df.repository_id = %s
                  AND df.is_trashed = FALSE
                  AND df.is_relevant = TRUE
                  AND v.status = 'DISCOVERED'
                  AND v.downloaded = FALSE

                ORDER BY
                    df.id,
                    v.version_number
                """,
                (repository_id,),
            )

            rows = cursor.fetchall()

            columns = [
                description[0]
                for description in cursor.description
            ]

            return [
                dict(zip(columns, row))
                for row in rows
            ]

        finally:
            cursor.close()

    # ------------------------------------------------------------------

    def get_existing_local_version(
        self,
        version_id: int,
    ) -> dict[str, Any] | None:

        cursor = self.connection.cursor()

        try:
            cursor.execute(
                """
                SELECT
                    id,
                    local_path,
                    local_checksum,
                    downloaded,
                    status
                FROM drive_file_versions
                WHERE id = %s
                LIMIT 1
                """,
                (version_id,),
            )

            row = cursor.fetchone()

            if row is None:
                return None

            columns = [
                description[0]
                for description in cursor.description
            ]

            return dict(zip(columns, row))

        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # File name handling
    # ------------------------------------------------------------------

    @staticmethod
    def sanitize_filename(
        name: str,
    ) -> str:

        name = name.strip()

        name = re.sub(
            r'[<>:"/\\|?*\x00-\x1f]',
            "_",
            name,
        )

        name = name.rstrip(". ")

        if not name:
            name = "unnamed"

        return name

    # ------------------------------------------------------------------

    def build_local_path(
        self,
        file_record: dict[str, Any],
    ) -> Path:

        drive_file_id = str(
            file_record["drive_file_id"]
        )

        name = self.sanitize_filename(
            str(file_record["name"])
        )

        mime_type = file_record.get(
            "mime_type"
        )

        export_info = GOOGLE_EXPORT_TYPES.get(
            mime_type
        )

        if export_info:
            export_extension = export_info[1]

            current_suffix = Path(name).suffix

            if (
                current_suffix.lower()
                != export_extension.lower()
            ):
                name = (
                    f"{Path(name).stem}"
                    f"{export_extension}"
                )

        directory = (
            LOCAL_ROOT
            / drive_file_id
        )

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        return directory / name

    # ------------------------------------------------------------------
    # SHA-256
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_sha256(
        path: Path,
    ) -> str:

        sha256 = hashlib.sha256()

        with path.open("rb") as file:

            while True:

                chunk = file.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                sha256.update(chunk)

        return sha256.hexdigest()

    # ------------------------------------------------------------------

    @staticmethod
    def calculate_size(
        path: Path,
    ) -> int:

        return path.stat().st_size

    # ------------------------------------------------------------------
    # Download regular Drive file
    # ------------------------------------------------------------------

    def download_regular_file(
        self,
        drive_file_id: str,
        destination: Path,
    ) -> None:

        if self.drive is None:
            raise RuntimeError(
                "Google Drive service is not connected."
            )

        request = (
            self.drive
            .files()
            .get(
                fileId=drive_file_id,
                alt="media",
                supportsAllDrives=True,
            )
        )

        with destination.open("wb") as file:

            downloader = MediaIoBaseDownload(
                file,
                request,
                chunksize=1024 * 1024,
            )

            done = False

            while not done:

                status, done = (
                    downloader.next_chunk()
                )

                if status is not None:

                    progress = int(
                        status.progress() * 100
                    )

                    print(
                        f"[DOWNLOAD PROGRESS] "
                        f"{progress}%"
                    )

    # ------------------------------------------------------------------
    # Export Google Workspace file
    # ------------------------------------------------------------------

    def export_google_file(
        self,
        drive_file_id: str,
        mime_type: str,
        destination: Path,
    ) -> None:

        if self.drive is None:
            raise RuntimeError(
                "Google Drive service is not connected."
            )

        export_info = GOOGLE_EXPORT_TYPES.get(
            mime_type
        )

        if export_info is None:
            raise RuntimeError(
                "Unsupported Google Workspace MIME type: "
                f"{mime_type}"
            )

        export_mime_type = export_info[0]

        request = (
            self.drive
            .files()
            .export_media(
                fileId=drive_file_id,
                mimeType=export_mime_type,
            )
        )

        with destination.open("wb") as file:

            downloader = MediaIoBaseDownload(
                file,
                request,
                chunksize=1024 * 1024,
            )

            done = False

            while not done:

                status, done = (
                    downloader.next_chunk()
                )

                if status is not None:

                    progress = int(
                        status.progress() * 100
                    )

                    print(
                        f"[EXPORT PROGRESS] "
                        f"{progress}%"
                    )

    # ------------------------------------------------------------------
    # Download / export dispatcher
    # ------------------------------------------------------------------

    def download_file(
        self,
        file_record: dict[str, Any],
        destination: Path,
    ) -> str:

        drive_file_id = str(
            file_record["drive_file_id"]
        )

        mime_type = str(
            file_record["mime_type"]
        )

        if mime_type.startswith(
            "application/vnd.google-apps."
        ):

            print(
                "[ACTION] "
                "EXPORT GOOGLE WORKSPACE FILE"
            )

            self.export_google_file(
                drive_file_id=drive_file_id,
                mime_type=mime_type,
                destination=destination,
            )

            return "EXPORTED"

        print(
            "[ACTION] DOWNLOAD REGULAR FILE"
        )

        self.download_regular_file(
            drive_file_id=drive_file_id,
            destination=destination,
        )

        return "DOWNLOADED"

    # ------------------------------------------------------------------
    # Mark version downloaded
    # ------------------------------------------------------------------

    def mark_version_downloaded(
        self,
        version_id: int,
        local_path: str,
        local_checksum: str,
    ) -> None:

        cursor = self.connection.cursor()

        try:

            cursor.execute(
                """
                UPDATE drive_file_versions
                SET
                    downloaded = TRUE,
                    local_path = %s,
                    local_checksum = %s,
                    downloaded_at = NOW(),
                    status = 'DOWNLOADED',
                    error_message = NULL
                WHERE id = %s
                """,
                (
                    local_path,
                    local_checksum,
                    version_id,
                ),
            )

        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # Update drive_files
    # ------------------------------------------------------------------

    def update_drive_file(
        self,
        file_id: int,
        local_path: str,
        local_checksum: str,
        local_size: int,
    ) -> None:

        cursor = self.connection.cursor()

        try:

            cursor.execute(
                """
                UPDATE drive_files
                SET
                    local_status = 'DOWNLOADED',
                    local_path = %s,
                    local_checksum = %s,
                    local_size_bytes = %s,
                    last_downloaded_at = NOW(),
                    last_checked_at = NOW(),
                    last_error = NULL
                WHERE id = %s
                """,
                (
                    local_path,
                    local_checksum,
                    local_size,
                    file_id,
                ),
            )

        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # Register local file
    # ------------------------------------------------------------------

    def register_local_file(
        self,
        file_id: int,
        version_id: int,
        local_path: str,
        file_name: str,
        size_bytes: int,
        checksum: str,
    ) -> None:

        cursor = self.connection.cursor()

        try:

            cursor.execute(
                """
                UPDATE drive_local_files
                SET
                    is_current = FALSE
                WHERE drive_file_id_fk = %s
                """,
                (file_id,),
            )

            cursor.execute(
                """
                INSERT INTO drive_local_files
                (
                    drive_file_id_fk,
                    drive_file_version_id,
                    local_path,
                    file_name,
                    size_bytes,
                    checksum,
                    checksum_type,
                    last_verified_at,
                    is_current
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'SHA-256',
                    NOW(),
                    TRUE
                )
                ON CONFLICT (local_path)
                DO UPDATE SET
                    drive_file_id_fk =
                        EXCLUDED.drive_file_id_fk,
                    drive_file_version_id =
                        EXCLUDED.drive_file_version_id,
                    file_name =
                        EXCLUDED.file_name,
                    size_bytes =
                        EXCLUDED.size_bytes,
                    checksum =
                        EXCLUDED.checksum,
                    checksum_type =
                        EXCLUDED.checksum_type,
                    last_verified_at =
                        NOW(),
                    is_current = TRUE
                """,
                (
                    file_id,
                    version_id,
                    local_path,
                    file_name,
                    size_bytes,
                    checksum,
                ),
            )

        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def mark_error(
        self,
        file_id: int,
        version_id: int,
        error_message: str,
    ) -> None:

        cursor = self.connection.cursor()

        try:

            cursor.execute(
                """
                UPDATE drive_file_versions
                SET
                    status = 'ERROR',
                    error_message = %s
                WHERE id = %s
                """,
                (
                    error_message[:4000],
                    version_id,
                ),
            )

            cursor.execute(
                """
                UPDATE drive_files
                SET
                    local_status = 'ERROR',
                    last_error = %s,
                    last_checked_at = NOW()
                WHERE id = %s
                """,
                (
                    error_message[:4000],
                    file_id,
                ),
            )

        finally:
            cursor.close()

    # ------------------------------------------------------------------
    # Process one file
    # ------------------------------------------------------------------

    def process_file(
        self,
        file_record: dict[str, Any],
        index: int,
        total: int,
    ) -> str:

        file_id = int(
            file_record["id"]
        )

        version_id = int(
            file_record["version_id"]
        )

        version_number = int(
            file_record["version_number"]
        )

        drive_file_id = str(
            file_record["drive_file_id"]
        )

        name = str(
            file_record["name"]
        )

        mime_type = str(
            file_record["mime_type"]
        )

        print()
        print("-" * 72)
        print(
            f"[FILE] {index}/{total}"
        )
        print(
            f"[NAME] {name}"
        )
        print(
            f"[DRIVE FILE ID] "
            f"{drive_file_id}"
        )
        print(
            f"[MIME] {mime_type}"
        )
        print(
            f"[VERSION] "
            f"{version_number}"
        )

        # --------------------------------------------------------------
        # Safety check BEFORE Google Drive download/export
        # --------------------------------------------------------------

        existing = (
            self.get_existing_local_version(
                version_id
            )
        )

        if existing is not None:

            if (
                existing["downloaded"] is True
                and existing["local_path"]
                and existing["local_checksum"]
            ):

                existing_path = Path(
                    existing["local_path"]
                )

                if existing_path.exists():

                    print(
                        "[RESULT] "
                        "ALREADY_DOWNLOADED"
                    )

                    print(
                        "[REASON] "
                        "Local copy already exists "
                        "for this exact database version."
                    )

                    return "ALREADY_DOWNLOADED"

        # --------------------------------------------------------------
        # Final destination
        # --------------------------------------------------------------

        destination = (
            self.build_local_path(
                file_record=file_record
            )
        )

        print(
            f"[LOCAL PATH] "
            f"{destination}"
        )

        # --------------------------------------------------------------
        # Check existing destination BEFORE download
        # --------------------------------------------------------------

        if destination.exists():

            existing_checksum = (
                self.calculate_sha256(
                    destination
                )
            )

            print(
                "[LOCAL FILE] Existing file found."
            )

            cursor = (
                self.connection.cursor()
            )

            try:

                cursor.execute(
                    """
                    SELECT local_checksum
                    FROM drive_file_versions
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (version_id,),
                )

                row = cursor.fetchone()

            finally:
                cursor.close()

            database_checksum = (
                row[0]
                if row
                else None
            )

            if (
                database_checksum
                and database_checksum
                == existing_checksum
            ):

                size_bytes = (
                    self.calculate_size(
                        destination
                    )
                )

                self.mark_version_downloaded(
                    version_id=version_id,
                    local_path=str(
                        destination
                    ),
                    local_checksum=(
                        existing_checksum
                    ),
                )

                self.update_drive_file(
                    file_id=file_id,
                    local_path=str(
                        destination
                    ),
                    local_checksum=(
                        existing_checksum
                    ),
                    local_size=size_bytes,
                )

                self.register_local_file(
                    file_id=file_id,
                    version_id=version_id,
                    local_path=str(
                        destination
                    ),
                    file_name=(
                        destination.name
                    ),
                    size_bytes=size_bytes,
                    checksum=(
                        existing_checksum
                    ),
                )

                self.connection.commit()

                print(
                    "[RESULT] "
                    "ALREADY_DOWNLOADED"
                )

                print(
                    "[REASON] "
                    "Existing local file matches "
                    "the recorded checksum."
                )

                return "ALREADY_DOWNLOADED"

        # --------------------------------------------------------------
        # Temporary file
        # --------------------------------------------------------------

        temporary = destination.with_name(
            destination.name
            + ".downloading"
        )

        if temporary.exists():
            temporary.unlink()

        try:

            # ----------------------------------------------------------
            # Download / export
            # ----------------------------------------------------------

            action = self.download_file(
                file_record=file_record,
                destination=temporary,
            )

            if not temporary.exists():
                raise RuntimeError(
                    "Google Drive download/export "
                    "completed but temporary file "
                    "was not created."
                )

            # ----------------------------------------------------------
            # Validate file
            # ----------------------------------------------------------

            size_bytes = (
                self.calculate_size(
                    temporary
                )
            )

            if size_bytes == 0:
                raise RuntimeError(
                    "Downloaded/exported file "
                    "is empty."
                )

            checksum = (
                self.calculate_sha256(
                    temporary
                )
            )

            print(
                f"[ACTION RESULT] "
                f"{action}"
            )

            print(
                f"[SIZE] "
                f"{size_bytes}"
            )

            print(
                f"[SHA-256] "
                f"{checksum}"
            )

            # ----------------------------------------------------------
            # Move completed file to final location
            # ----------------------------------------------------------

            temporary.replace(
                destination
            )

            # ----------------------------------------------------------
            # Update version
            # ----------------------------------------------------------

            self.mark_version_downloaded(
                version_id=version_id,
                local_path=str(
                    destination
                ),
                local_checksum=checksum,
            )

            # ----------------------------------------------------------
            # Update drive_files
            # ----------------------------------------------------------

            self.update_drive_file(
                file_id=file_id,
                local_path=str(
                    destination
                ),
                local_checksum=checksum,
                local_size=size_bytes,
            )

            # ----------------------------------------------------------
            # Register local file
            # ----------------------------------------------------------

            self.register_local_file(
                file_id=file_id,
                version_id=version_id,
                local_path=str(
                    destination
                ),
                file_name=destination.name,
                size_bytes=size_bytes,
                checksum=checksum,
            )

            self.connection.commit()

            print(
                "[RESULT] DOWNLOADED"
            )

            print(
                "[DATABASE] UPDATED"
            )

            return "DOWNLOADED"

        except Exception as exc:

            if temporary.exists():
                temporary.unlink()

            self.connection.rollback()

            message = str(exc)

            self.mark_error(
                file_id=file_id,
                version_id=version_id,
                error_message=message,
            )

            self.connection.commit()

            print(
                f"[ERROR] {message}"
            )

            return "ERROR"

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(
        self,
        repository_key: str = "alcalay",
    ) -> dict[str, int]:

        summary = {
            "candidates": 0,
            "downloaded": 0,
            "already_downloaded": 0,
            "errors": 0,
        }

        try:

            self.connect()

            repository_id = (
                self.get_repository_id(
                    repository_key
                )
            )

            files = (
                self.get_ready_files(
                    repository_id
                )
            )

            summary["candidates"] = len(
                files
            )

            print()
            print("=" * 72)
            print(
                "STARTING GOOGLE DRIVE "
                "DOWNLOAD / EXPORT"
            )
            print("=" * 72)
            print()
            print(
                "[DATABASE] PostgreSQL"
            )
            print(
                "[DOWNLOAD] YES"
            )
            print(
                "[DRIVE WRITE] NO"
            )
            print()
            print(
                f"[REPOSITORY] "
                f"{repository_key}"
            )
            print(
                f"[REPOSITORY ID] "
                f"{repository_id}"
            )
            print(
                f"[READY FOR DOWNLOAD] "
                f"{len(files)}"
            )

            if not files:

                print()
                print(
                    "[INFO] No files are "
                    "ready for download."
                )

            for index, file_record in enumerate(
                files,
                start=1,
            ):

                result = (
                    self.process_file(
                        file_record=file_record,
                        index=index,
                        total=len(files),
                    )
                )

                if result == "DOWNLOADED":

                    summary[
                        "downloaded"
                    ] += 1

                elif (
                    result
                    == "ALREADY_DOWNLOADED"
                ):

                    summary[
                        "already_downloaded"
                    ] += 1

                elif result == "ERROR":

                    summary[
                        "errors"
                    ] += 1

            print()
            print("=" * 72)
            print(
                "GOOGLE DRIVE "
                "DOWNLOAD / EXPORT COMPLETED"
            )
            print("=" * 72)
            print()
            print(
                f"[REPOSITORY] "
                f"{repository_key}"
            )
            print(
                f"[CANDIDATES] "
                f"{summary['candidates']}"
            )
            print(
                f"[DOWNLOADED] "
                f"{summary['downloaded']}"
            )
            print(
                f"[ALREADY DOWNLOADED] "
                f"{summary['already_downloaded']}"
            )
            print(
                f"[ERRORS] "
                f"{summary['errors']}"
            )
            print()
            print(
                "[DRIVE WRITE] NO"
            )

            return summary

        finally:

            if self.connection is not None:

                self.connection.close()

                self.connection = None


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------


def main() -> None:

    downloader = DriveDownloader()

    summary = downloader.run(
        repository_key="alcalay"
    )

    if summary["errors"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()