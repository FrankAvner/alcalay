# -*- coding: utf-8 -*-

"""
Alcalay - Google Drive <-> Local Synchronization

Supports:
    DRIVE_TO_LOCAL
    LOCAL_TO_DRIVE

LOCAL_TO_DRIVE:
    storage/office
    storage/pdf
    storage/media
    storage/gmail
    storage/drive

The local-to-drive process:
    1. Scans physical local files.
    2. Calculates SHA-256.
    3. Checks PostgreSQL for an existing local mapping.
    4. Checks Google Drive for an existing file.
    5. Creates a new Drive file when necessary.
    6. Updates an existing Drive file when the local file is newer.
    7. Records the operation in PostgreSQL.
    8. Stops immediately on insufficient Drive permissions.

Important:
    Google Drive OAuth must have write permission for LOCAL_TO_DRIVE.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.database.connection import DatabaseConnection
from src.drive.drive_connection import DriveConnection
from src.drive.drive_downloader import DriveDownloader


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPOSITORY_KEY = "alcalay"

DIRECTION_DRIVE_TO_LOCAL = "DRIVE_TO_LOCAL"
DIRECTION_LOCAL_TO_DRIVE = "LOCAL_TO_DRIVE"

GOOGLE_NATIVE_PREFIX = "application/vnd.google-apps."

STOP_WORDS = {
    "STOP",
    "QUIT",
    "EXIT",
    "עצור",
}

AUTH_ERROR_MESSAGE = "אין הרשאות - נא להתחבר עם יוזר מורשה"

LOCAL_STORAGE_ROOT = PROJECT_ROOT / "storage"

LOCAL_SOURCE_DIRS = (
    "office",
    "pdf",
    "media",
    "gmail",
    "drive",
)

IGNORED_NAMES = {
    ".DS_Store",
    "Thumbs.db",
}

IGNORED_SUFFIXES = {
    ".syncing",
    ".part",
    ".tmp",
}

CHUNK_SIZE = 1024 * 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()

    return str(value)


def parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    text = str(value).strip()

    if not text:
        return None

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class DriveSync:
    def __init__(self, direction: str = DIRECTION_DRIVE_TO_LOCAL):
        self.direction = direction.upper().strip()

        self.db = DatabaseConnection()
        self.connection = None

        self.drive_connection: Optional[DriveConnection] = None
        self.drive = None

        self.repository_id: Optional[int] = None
        self.repository_root_folder_id: Optional[str] = None

        self.stop_event = threading.Event()
        self.stop_listener_started = False

        self.downloader = DriveDownloader()

        self.summary = {
            "scanned": 0,
            "folders": 0,
            "files": 0,
            "relevant": 0,
            "skipped": 0,
            "downloaded": 0,
            "updated": 0,
            "duplicates": 0,
            "errors": 0,
        }

        self.by_type: Dict[str, int] = {}

        self.auth_error = False
        self.auth_error_message = AUTH_ERROR_MESSAGE

        self.sync_run_id: Optional[int] = None

    # -----------------------------------------------------------------------
    # Events
    # -----------------------------------------------------------------------

    def emit(self, event: str, **payload: Any) -> None:
        data = {
            "event": event,
            **payload,
        }

        print(
            f"[SYNC_EVENT] {json.dumps(data, ensure_ascii=False, default=str)}",
            flush=True,
        )

    # -----------------------------------------------------------------------
    # STOP listener
    # -----------------------------------------------------------------------

    def start_stop_listener(self) -> None:
        if self.stop_listener_started:
            return

        self.stop_listener_started = True

        def listener() -> None:
            while not self.stop_event.is_set():
                try:
                    line = sys.stdin.readline()

                    if not line:
                        break

                    command = line.strip().upper()

                    if command in STOP_WORDS:
                        self.stop_event.set()

                        self.emit(
                            "STOP_REQUESTED",
                            message="התקבלה בקשת עצירה מהמשתמש",
                        )

                        break

                except Exception as exc:
                    self.emit(
                        "STOP_LISTENER_ERROR",
                        error=str(exc),
                    )
                    break

        thread = threading.Thread(
            target=listener,
            name="alcalay-drive-sync-stop-listener",
            daemon=True,
        )

        thread.start()

    # -----------------------------------------------------------------------
    # Authorization
    # -----------------------------------------------------------------------

    def is_insufficient_scope_error(self, exc: Exception) -> bool:
        text_parts = [
            str(exc),
            repr(exc),
        ]

        if isinstance(exc, HttpError):
            try:
                content = exc.content

                if isinstance(content, bytes):
                    content = content.decode(
                        "utf-8",
                        errors="replace",
                    )

                text_parts.append(str(content))
            except Exception:
                pass

        text = " ".join(text_parts).lower()

        indicators = (
            "insufficient authentication scopes",
            "insufficientpermissions",
            "insufficient permissions",
            "insufficient scope",
            "insufficient authentication",
            "forbidden",
            "permission denied",
            "403",
        )

        return any(item in text for item in indicators)

    def handle_auth_error(self, exc: Exception) -> None:
        self.auth_error = True
        self.stop_event.set()

        self.emit(
            "AUTH_ERROR",
            message=AUTH_ERROR_MESSAGE,
            error=str(exc),
        )

    def _verify_drive_service(self) -> None:
        """
        Verify that Google Drive is reachable.

        Note:
            The Drive API does not provide a simple 'write scope' endpoint.
            Therefore:
                - account access is checked here;
                - actual CREATE/UPDATE operations are protected by
                  is_insufficient_scope_error().
        """

        if self.drive is None:
            raise RuntimeError("Google Drive service is not available")

        try:
            response = (
                self.drive.about()
                .get(fields="user(emailAddress)")
                .execute()
            )

            email = (
                response.get("user", {}).get("emailAddress")
                if response
                else None
            )

            self.emit(
                "DRIVE_CONNECTED",
                email=email or "",
            )

        except Exception as exc:
            if self.is_insufficient_scope_error(exc):
                self.handle_auth_error(exc)

                raise RuntimeError(
                    AUTH_ERROR_MESSAGE
                ) from exc

            raise

    # -----------------------------------------------------------------------
    # Connection
    # -----------------------------------------------------------------------

    def connect(self) -> None:
        self.connection = self.db.connect()

        self.get_repository()

        self.ensure_drive_connection()

        try:
            self.downloader.connection = self.connection
        except Exception:
            pass

        try:
            self.downloader.drive = self.drive
        except Exception:
            pass

    def get_repository(self) -> None:
        if self.connection is None:
            raise RuntimeError("Database connection is not available")

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                root_folder_id
            FROM drive_repositories
            WHERE repository_key = %s
              AND enabled = TRUE
            LIMIT 1
            """,
            (REPOSITORY_KEY,),
        )

        row = cursor.fetchone()
        cursor.close()

        if not row:
            raise RuntimeError(
                f"Google Drive repository '{REPOSITORY_KEY}' was not found"
            )

        self.repository_id = int(row[0])
        self.repository_root_folder_id = str(row[1])

        self.emit(
            "REPOSITORY",
            repository_id=self.repository_id,
            root_folder_id=self.repository_root_folder_id,
        )

    def ensure_drive_connection(self) -> None:
        self.drive_connection = DriveConnection(
            account_email="frank.avner@gmail.com"
        )

        try:
            self.drive_connection.connect()
            self.drive = self.drive_connection.service
        except Exception as exc:
            if self.is_insufficient_scope_error(exc):
                self.handle_auth_error(exc)

                raise RuntimeError(
                    AUTH_ERROR_MESSAGE
                ) from exc

            raise

        if self.drive is None:
            raise RuntimeError(
                "Google Drive service was not created"
            )

        self._verify_drive_service()

    # -----------------------------------------------------------------------
    # Drive folder handling
    # -----------------------------------------------------------------------

    @staticmethod
    def escape_drive_query(value: str) -> str:
        return (
            str(value)
            .replace("\\", "\\\\")
            .replace("'", "\\'")
        )

    def find_child_folder(
        self,
        parent_id: str,
        folder_name: str,
    ) -> Optional[Dict[str, Any]]:
        if not self.drive:
            return None

        safe_name = self.escape_drive_query(folder_name)

        query = (
            "trashed = false "
            "and mimeType = 'application/vnd.google-apps.folder' "
            f"and name = '{safe_name}' "
            f"and '{parent_id}' in parents"
        )

        try:
            result = (
                self.drive.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="files(id,name,mimeType,parents)",
                    pageSize=20,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )

            files = result.get("files", [])

            if files:
                return files[0]

            return None

        except Exception as exc:
            if self.is_insufficient_scope_error(exc):
                self.handle_auth_error(exc)

            raise

    def resolve_local_parent_folder(
        self,
        source_folder: str,
    ) -> str:
        """
        Map local storage folders into the Alcalay Drive repository.

        Gmail:
            storage/gmail -> Drive/Gmail

        Everything else:
            storage/<folder> -> Drive/Documents

        If the target child folder does not exist, the repository root
        is used as fallback.
        """

        if not self.repository_root_folder_id:
            raise RuntimeError(
                "Repository root folder ID is not available"
            )

        target_name = (
            "Gmail"
            if source_folder.lower() == "gmail"
            else "Documents"
        )

        folder = self.find_child_folder(
            self.repository_root_folder_id,
            target_name,
        )

        if folder:
            return folder["id"]

        self.emit(
            "FOLDER_FALLBACK",
            source_folder=source_folder,
            target_folder=target_name,
            parent=self.repository_root_folder_id,
        )

        return self.repository_root_folder_id

    # -----------------------------------------------------------------------
    # PostgreSQL - candidates
    # -----------------------------------------------------------------------

    def get_drive_candidates(self) -> List[Dict[str, Any]]:
        if self.connection is None:
            raise RuntimeError("Database connection is not available")

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT
                df.id,
                df.drive_file_id,
                df.name,
                df.mime_type,
                df.size_bytes,
                df.modified_time,
                df.md5_checksum,
                df.local_path,
                df.local_checksum,
                df.local_size_bytes,
                df.parent_drive_file_id,
                df.is_trashed,
                df.is_relevant,
                df.local_status,
                df.last_seen_at,
                df.last_checked_at,
                v.version_number,
                v.drive_modified_time,
                v.size_bytes,
                v.md5_checksum,
                v.local_path,
                v.local_checksum,
                v.status
            FROM drive_files df
            LEFT JOIN LATERAL (
                SELECT
                    version_number,
                    drive_modified_time,
                    size_bytes,
                    md5_checksum,
                    local_path,
                    local_checksum,
                    status
                FROM drive_file_versions
                WHERE drive_file_id_fk = df.id
                ORDER BY version_number DESC
                LIMIT 1
            ) v ON TRUE
            WHERE df.repository_id = %s
              AND COALESCE(df.is_trashed, FALSE) = FALSE
              AND COALESCE(df.is_relevant, TRUE) = TRUE
            ORDER BY df.id
            """,
            (self.repository_id,),
        )

        rows = cursor.fetchall()
        cursor.close()

        result: List[Dict[str, Any]] = []

        for row in rows:
            result.append(
                {
                    "id": row[0],
                    "drive_file_id": row[1],
                    "name": row[2],
                    "mime_type": row[3],
                    "size_bytes": row[4],
                    "modified_time": row[5],
                    "md5_checksum": row[6],
                    "local_path": row[7],
                    "local_checksum": row[8],
                    "local_size_bytes": row[9],
                    "parent_drive_file_id": row[10],
                    "is_trashed": row[11],
                    "is_relevant": row[12],
                    "local_status": row[13],
                    "last_seen_at": row[14],
                    "last_checked_at": row[15],
                    "version_number": row[16],
                    "version_drive_modified_time": row[17],
                    "version_size_bytes": row[18],
                    "version_md5_checksum": row[19],
                    "version_local_path": row[20],
                    "version_local_checksum": row[21],
                    "version_status": row[22],
                }
            )

        return result

    # -----------------------------------------------------------------------
    # Local file scanning
    # -----------------------------------------------------------------------

    def get_local_candidates(self) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        seen_paths = set()

        for source_name in LOCAL_SOURCE_DIRS:
            root = LOCAL_STORAGE_ROOT / source_name

            if not root.exists():
                self.emit(
                    "LOCAL_FOLDER_MISSING",
                    folder=str(root),
                )
                continue

            if not root.is_dir():
                continue

            for path in root.rglob("*"):
                if self.stop_event.is_set():
                    break

                try:
                    if not path.is_file():
                        continue

                    if path.is_symlink():
                        continue

                    if path.name in IGNORED_NAMES:
                        continue

                    if path.suffix.lower() in IGNORED_SUFFIXES:
                        continue

                    absolute_path = path.resolve()

                    key = str(absolute_path)

                    if key in seen_paths:
                        continue

                    seen_paths.add(key)

                    stat = path.stat()

                    mime_type, _ = mimetypes.guess_type(
                        str(path)
                    )

                    if not mime_type:
                        mime_type = (
                            "application/octet-stream"
                        )

                    result.append(
                        {
                            "local_path": str(absolute_path),
                            "name": path.name,
                            "mime_type": mime_type,
                            "size_bytes": stat.st_size,
                            "modified_time": datetime.fromtimestamp(
                                stat.st_mtime,
                                tz=timezone.utc,
                            ),
                            "source_folder": source_name,
                            "relative_path": str(
                                path.relative_to(root)
                            ),
                        }
                    )

                except OSError as exc:
                    self.emit(
                        "LOCAL_SCAN_ERROR",
                        path=str(path),
                        error=str(exc),
                    )

            if self.stop_event.is_set():
                break

        return result

    # -----------------------------------------------------------------------
    # Hash
    # -----------------------------------------------------------------------

    def sha256(self, path: str) -> str:
        digest = hashlib.sha256()

        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(CHUNK_SIZE)

                if not chunk:
                    break

                digest.update(chunk)

        return digest.hexdigest()

    # -----------------------------------------------------------------------
    # Classification
    # -----------------------------------------------------------------------

    def classify(
        self,
        mime_type: Optional[str],
        name: Optional[str],
    ) -> str:
        mime = (mime_type or "").lower()
        filename = (name or "").lower()

        if mime.startswith("application/vnd.google-apps."):
            return "GOOGLE"

        if mime == "application/pdf" or filename.endswith(".pdf"):
            return "PDF"

        if (
            "word" in mime
            or filename.endswith(".doc")
            or filename.endswith(".docx")
            or filename.endswith(".rtf")
        ):
            return "WORD / OFFICE"

        if (
            "excel" in mime
            or "spreadsheet" in mime
            or filename.endswith(".xls")
            or filename.endswith(".xlsx")
            or filename.endswith(".csv")
        ):
            return "EXCEL"

        if (
            "powerpoint" in mime
            or "presentation" in mime
            or filename.endswith(".ppt")
            or filename.endswith(".pptx")
        ):
            return "POWERPOINT"

        if mime.startswith("image/"):
            return "IMAGES"

        if mime.startswith("video/"):
            return "VIDEO"

        if mime.startswith("audio/"):
            return "AUDIO"

        if "message" in mime or filename.endswith(".eml"):
            return "GMAIL"

        return "OTHER"

    def type_stats(self, record: Dict[str, Any]) -> None:
        category = self.classify(
            record.get("mime_type"),
            record.get("name"),
        )

        self.by_type[category] = (
            self.by_type.get(category, 0) + 1
        )

    # -----------------------------------------------------------------------
    # Google Drive metadata
    # -----------------------------------------------------------------------

    def current_drive_metadata(
        self,
        drive_file_id: str,
    ) -> Dict[str, Any]:
        try:
            return (
                self.drive.files()
                .get(
                    fileId=drive_file_id,
                    fields=(
                        "id,name,mimeType,size,createdTime,"
                        "modifiedTime,md5Checksum,webViewLink,"
                        "parents,trashed"
                    ),
                    supportsAllDrives=True,
                )
                .execute()
            )

        except Exception as exc:
            if self.is_insufficient_scope_error(exc):
                self.handle_auth_error(exc)

            raise

    def search_drive_file(
        self,
        name: str,
        parent_id: str,
    ) -> Optional[Dict[str, Any]]:
        safe_name = self.escape_drive_query(name)

        query = (
            "trashed = false "
            f"and name = '{safe_name}' "
            f"and '{parent_id}' in parents"
        )

        try:
            response = (
                self.drive.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields=(
                        "files(id,name,mimeType,size,createdTime,"
                        "modifiedTime,md5Checksum,webViewLink,"
                        "parents,trashed)"
                    ),
                    orderBy="modifiedTime desc",
                    pageSize=20,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )

            files = response.get("files", [])

            if not files:
                return None

            return files[0]

        except Exception as exc:
            if self.is_insufficient_scope_error(exc):
                self.handle_auth_error(exc)

            raise

    # -----------------------------------------------------------------------
    # PostgreSQL - drive_files
    # -----------------------------------------------------------------------

    def find_drive_file_by_local_path(
        self,
        local_path: str,
    ) -> Optional[Dict[str, Any]]:
        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
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
                is_relevant,
                local_status,
                local_path,
                local_checksum,
                local_size_bytes,
                last_seen_at,
                last_checked_at,
                last_downloaded_at,
                last_error
            FROM drive_files
            WHERE repository_id = %s
              AND local_path = %s
            LIMIT 1
            """,
            (
                self.repository_id,
                local_path,
            ),
        )

        row = cursor.fetchone()
        cursor.close()

        if not row:
            return None

        return {
            "id": row[0],
            "repository_id": row[1],
            "drive_file_id": row[2],
            "parent_drive_file_id": row[3],
            "name": row[4],
            "mime_type": row[5],
            "size_bytes": row[6],
            "created_time": row[7],
            "modified_time": row[8],
            "md5_checksum": row[9],
            "web_view_link": row[10],
            "is_trashed": row[11],
            "is_relevant": row[12],
            "local_status": row[13],
            "local_path": row[14],
            "local_checksum": row[15],
            "local_size_bytes": row[16],
            "last_seen_at": row[17],
            "last_checked_at": row[18],
            "last_downloaded_at": row[19],
            "last_error": row[20],
        }

    def create_drive_file_record(
        self,
        metadata: Dict[str, Any],
        local_path: str,
        local_checksum: str,
        local_size: int,
    ) -> int:
        cursor = self.connection.cursor()

        created_time = parse_dt(
            metadata.get("createdTime")
        )

        modified_time = parse_dt(
            metadata.get("modifiedTime")
        )

        cursor.execute(
            """
            INSERT INTO drive_files (
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
                is_relevant,
                local_status,
                local_path,
                local_checksum,
                local_size_bytes,
                first_seen_at,
                last_seen_at,
                last_checked_at,
                last_error
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                NOW(), NOW(), NOW(), NULL
            )
            ON CONFLICT (repository_id, drive_file_id)
            DO UPDATE SET
                parent_drive_file_id = EXCLUDED.parent_drive_file_id,
                name = EXCLUDED.name,
                mime_type = EXCLUDED.mime_type,
                size_bytes = EXCLUDED.size_bytes,
                created_time = EXCLUDED.created_time,
                modified_time = EXCLUDED.modified_time,
                md5_checksum = EXCLUDED.md5_checksum,
                web_view_link = EXCLUDED.web_view_link,
                is_trashed = EXCLUDED.is_trashed,
                is_relevant = EXCLUDED.is_relevant,
                local_status = EXCLUDED.local_status,
                local_path = EXCLUDED.local_path,
                local_checksum = EXCLUDED.local_checksum,
                local_size_bytes = EXCLUDED.local_size_bytes,
                last_seen_at = NOW(),
                last_checked_at = NOW(),
                last_error = NULL
            RETURNING id
            """,
            (
                self.repository_id,
                metadata["id"],
                (
                    metadata.get("parents", [None])[0]
                    if metadata.get("parents")
                    else None
                ),
                metadata.get("name") or "",
                metadata.get("mimeType")
                or "application/octet-stream",
                int(metadata.get("size") or local_size),
                created_time,
                modified_time,
                metadata.get("md5Checksum"),
                metadata.get("webViewLink"),
                bool(metadata.get("trashed", False)),
                True,
                "DOWNLOADED",
                local_path,
                local_checksum,
                local_size,
            ),
        )

        row = cursor.fetchone()

        if not row:
            self.connection.rollback()
            cursor.close()

            raise RuntimeError(
                "Failed to create/update drive_files record"
            )

        drive_file_db_id = int(row[0])

        self.connection.commit()
        cursor.close()

        return drive_file_db_id

    def update_drive_file_record(
        self,
        db_id: int,
        metadata: Dict[str, Any],
        local_path: str,
        local_checksum: str,
        local_size: int,
    ) -> None:
        cursor = self.connection.cursor()

        modified_time = parse_dt(
            metadata.get("modifiedTime")
        )

        cursor.execute(
            """
            UPDATE drive_files
            SET
                parent_drive_file_id = %s,
                name = %s,
                mime_type = %s,
                size_bytes = %s,
                modified_time = %s,
                md5_checksum = %s,
                web_view_link = %s,
                is_trashed = %s,
                is_relevant = TRUE,
                local_status = 'DOWNLOADED',
                local_path = %s,
                local_checksum = %s,
                local_size_bytes = %s,
                last_seen_at = NOW(),
                last_checked_at = NOW(),
                last_error = NULL
            WHERE id = %s
            """,
            (
                (
                    metadata.get("parents", [None])[0]
                    if metadata.get("parents")
                    else None
                ),
                metadata.get("name") or "",
                metadata.get("mimeType")
                or "application/octet-stream",
                int(metadata.get("size") or local_size),
                modified_time,
                metadata.get("md5Checksum"),
                metadata.get("webViewLink"),
                bool(metadata.get("trashed", False)),
                local_path,
                local_checksum,
                local_size,
                db_id,
            ),
        )

        self.connection.commit()
        cursor.close()

    # -----------------------------------------------------------------------
    # PostgreSQL - versions
    # -----------------------------------------------------------------------

    def latest_version(
        self,
        drive_file_db_id: int,
    ) -> Optional[Dict[str, Any]]:
        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
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
            LIMIT 1
            """,
            (drive_file_db_id,),
        )

        row = cursor.fetchone()
        cursor.close()

        if not row:
            return None

        return {
            "id": row[0],
            "version_number": row[1],
            "drive_modified_time": row[2],
            "size_bytes": row[3],
            "md5_checksum": row[4],
            "discovered_at": row[5],
            "downloaded": row[6],
            "local_path": row[7],
            "local_checksum": row[8],
            "downloaded_at": row[9],
            "status": row[10],
            "error_message": row[11],
        }

    def create_version(
        self,
        drive_file_db_id: int,
        metadata: Dict[str, Any],
        local_path: Optional[str],
        local_checksum: Optional[str],
        status: str = "DISCOVERED",
        downloaded: bool = False,
    ) -> int:
        latest = self.latest_version(
            drive_file_db_id
        )

        if latest:
            version_number = (
                int(latest["version_number"]) + 1
            )
        else:
            version_number = 1

        modified_time = parse_dt(
            metadata.get("modifiedTime")
        )

        size_bytes = metadata.get("size")

        if size_bytes is not None:
            size_bytes = int(size_bytes)

        md5_checksum = metadata.get(
            "md5Checksum"
        )

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO drive_file_versions (
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
            )
            VALUES (
                %s, %s, %s, %s, %s,
                NOW(), %s, %s, %s,
                %s, %s, NULL
            )
            ON CONFLICT (
                drive_file_id_fk,
                version_number
            )
            DO UPDATE SET
                drive_modified_time = EXCLUDED.drive_modified_time,
                size_bytes = EXCLUDED.size_bytes,
                md5_checksum = EXCLUDED.md5_checksum,
                downloaded = EXCLUDED.downloaded,
                local_path = EXCLUDED.local_path,
                local_checksum = EXCLUDED.local_checksum,
                downloaded_at = EXCLUDED.downloaded_at,
                status = EXCLUDED.status
            RETURNING id
            """,
            (
                drive_file_db_id,
                version_number,
                modified_time,
                size_bytes,
                md5_checksum,
                downloaded,
                local_path,
                local_checksum,
                utc_now() if downloaded else None,
                status,
            ),
        )

        row = cursor.fetchone()

        if not row:
            self.connection.rollback()
            cursor.close()

            raise RuntimeError(
                "Failed to create drive_file_versions record"
            )

        version_id = int(row[0])

        self.connection.commit()
        cursor.close()

        return version_id

    # -----------------------------------------------------------------------
    # PostgreSQL - local mapping
    # -----------------------------------------------------------------------

    def link_local_file(
        self,
        drive_file_db_id: int,
        version_id: Optional[int],
        local_path: str,
        file_name: str,
        size_bytes: int,
        checksum: str,
    ) -> None:
        cursor = self.connection.cursor()

        cursor.execute(
            """
            UPDATE drive_local_files
            SET
                is_current = FALSE,
                last_verified_at = NOW()
            WHERE local_path = %s
              AND drive_file_id_fk <> %s
            """,
            (
                local_path,
                drive_file_db_id,
            ),
        )

        cursor.execute(
            """
            INSERT INTO drive_local_files (
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
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                'SHA256', NOW(), NOW(), TRUE
            )
            ON CONFLICT (local_path)
            DO UPDATE SET
                drive_file_id_fk = EXCLUDED.drive_file_id_fk,
                drive_file_version_id =
                    EXCLUDED.drive_file_version_id,
                file_name = EXCLUDED.file_name,
                size_bytes = EXCLUDED.size_bytes,
                checksum = EXCLUDED.checksum,
                checksum_type = 'SHA256',
                last_verified_at = NOW(),
                is_current = TRUE
            """,
            (
                drive_file_db_id,
                version_id,
                local_path,
                file_name,
                size_bytes,
                checksum,
            ),
        )

        self.connection.commit()
        cursor.close()

    # -----------------------------------------------------------------------
    # PostgreSQL - sync runs
    # -----------------------------------------------------------------------

    def create_run(
        self,
        scanned_count: int,
    ) -> int:
        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO drive_sync_runs (
                repository_id,
                sync_type,
                started_at,
                status,
                scanned_count,
                folders_count,
                files_count,
                relevant_count,
                skipped_count,
                downloaded_count,
                updated_count,
                duplicate_count,
                error_count
            )
            VALUES (
                %s, %s, NOW(), 'RUNNING',
                %s, 0, 0, 0, 0, 0, 0, 0, 0
            )
            RETURNING id
            """,
            (
                self.repository_id,
                self.direction,
                scanned_count,
            ),
        )

        row = cursor.fetchone()

        if not row:
            self.connection.rollback()
            cursor.close()

            raise RuntimeError(
                "Failed to create drive_sync_runs record"
            )

        run_id = int(row[0])

        self.connection.commit()
        cursor.close()

        self.sync_run_id = run_id

        return run_id

    def finish_run(
        self,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        if not self.sync_run_id:
            return

        cursor = self.connection.cursor()

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
                self.summary["scanned"],
                self.summary["folders"],
                self.summary["files"],
                self.summary["relevant"],
                self.summary["skipped"],
                self.summary["downloaded"],
                self.summary["updated"],
                self.summary["duplicates"],
                self.summary["errors"],
                error_message,
                self.sync_run_id,
            ),
        )

        self.connection.commit()
        cursor.close()

    # -----------------------------------------------------------------------
    # PostgreSQL - sync items
    # -----------------------------------------------------------------------

    def item_start(
        self,
        drive_file_db_id: Optional[int],
        action: str,
        reason: Optional[str],
    ) -> Optional[int]:
        if not self.sync_run_id:
            return None

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO drive_sync_items (
                sync_run_id,
                drive_file_id_fk,
                action,
                status,
                reason,
                started_at
            )
            VALUES (
                %s, %s, %s, 'RUNNING', %s, NOW()
            )
            RETURNING id
            """,
            (
                self.sync_run_id,
                drive_file_db_id,
                action,
                reason,
            ),
        )

        row = cursor.fetchone()

        if not row:
            self.connection.rollback()
            cursor.close()

            raise RuntimeError(
                "Failed to create drive_sync_items record"
            )

        item_id = int(row[0])

        self.connection.commit()
        cursor.close()

        return item_id

    def item_finish(
        self,
        item_id: Optional[int],
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        if not item_id:
            return

        cursor = self.connection.cursor()

        cursor.execute(
            """
            UPDATE drive_sync_items
            SET
                status = %s,
                finished_at = NOW(),
                error_message = %s
            WHERE id = %s
            """,
            (
                status,
                error_message,
                item_id,
            ),
        )

        self.connection.commit()
        cursor.close()

    # -----------------------------------------------------------------------
    # DRIVE_TO_LOCAL
    # -----------------------------------------------------------------------

    def same_drive_state(
        self,
        metadata: Dict[str, Any],
        version: Optional[Dict[str, Any]],
    ) -> bool:
        if not version:
            return False

        drive_size = metadata.get("size")

        if drive_size is not None:
            try:
                drive_size = int(drive_size)
            except Exception:
                pass

        if (
            version.get("size_bytes") is not None
            and drive_size is not None
            and int(version["size_bytes"]) != int(drive_size)
        ):
            return False

        drive_md5 = metadata.get("md5Checksum")

        if (
            version.get("md5_checksum")
            and drive_md5
            and version["md5_checksum"] != drive_md5
        ):
            return False

        drive_modified = parse_dt(
            metadata.get("modifiedTime")
        )

        version_modified = parse_dt(
            version.get("drive_modified_time")
        )

        if drive_modified and version_modified:
            if abs(
                (
                    drive_modified - version_modified
                ).total_seconds()
            ) > 2:
                return False

        return True

    def sync_drive_to_local(
        self,
        record: Dict[str, Any],
    ) -> str:
        if self.stop_event.is_set():
            return "STOPPED"

        drive_db_id = record["id"]
        drive_id = record["drive_file_id"]

        metadata = self.current_drive_metadata(
            drive_id
        )

        if metadata.get("trashed"):
            self.summary["skipped"] += 1
            return "TRASHED"

        self.summary["files"] += 1

        local_path = record.get("local_path")

        if not local_path:
            self.summary["skipped"] += 1
            return "NO_LOCAL_PATH"

        version = self.latest_version(
            drive_db_id
        )

        if self.same_drive_state(
            metadata,
            version,
        ):
            self.summary["skipped"] += 1
            return "NO_CHANGE"

        item_id = self.item_start(
            drive_db_id,
            "DOWNLOAD",
            "Drive version changed",
        )

        try:
            result = self.downloader.download_file(
                metadata,
                local_path,
            )

            if result is False:
                raise RuntimeError(
                    "DriveDownloader reported failure"
                )

            local_checksum = self.sha256(
                local_path
            )

            local_size = Path(
                local_path
            ).stat().st_size

            version_id = self.create_version(
                drive_db_id,
                metadata,
                local_path,
                local_checksum,
                status="DOWNLOADED",
                downloaded=True,
            )

            self.update_drive_file_record(
                drive_db_id,
                metadata,
                local_path,
                local_checksum,
                local_size,
            )

            self.link_local_file(
                drive_db_id,
                version_id,
                local_path,
                metadata.get("name") or record["name"],
                local_size,
                local_checksum,
            )

            self.summary["downloaded"] += 1

            self.item_finish(
                item_id,
                "COMPLETED",
            )

            return "DOWNLOADED"

        except Exception as exc:
            self.summary["errors"] += 1

            self.item_finish(
                item_id,
                "ERROR",
                str(exc),
            )

            if self.is_insufficient_scope_error(exc):
                self.handle_auth_error(exc)

            raise

    # -----------------------------------------------------------------------
    # LOCAL_TO_DRIVE - upload
    # -----------------------------------------------------------------------

    def upload_new_local_file(
        self,
        record: Dict[str, Any],
        parent_folder_id: str,
        local_checksum: str,
    ) -> Dict[str, Any]:
        local_path = record["local_path"]

        media = MediaFileUpload(
            local_path,
            mimetype=record["mime_type"],
            resumable=True,
        )

        body = {
            "name": record["name"],
            "parents": [parent_folder_id],
        }

        try:
            metadata = (
                self.drive.files()
                .create(
                    body=body,
                    media_body=media,
                    fields=(
                        "id,name,mimeType,size,createdTime,"
                        "modifiedTime,md5Checksum,webViewLink,"
                        "parents,trashed"
                    ),
                    supportsAllDrives=True,
                )
                .execute()
            )

            return metadata

        except Exception as exc:
            if self.is_insufficient_scope_error(exc):
                self.handle_auth_error(exc)

                raise RuntimeError(
                    AUTH_ERROR_MESSAGE
                ) from exc

            raise

    def update_existing_drive_file(
        self,
        drive_file_id: str,
        record: Dict[str, Any],
    ) -> Dict[str, Any]:
        media = MediaFileUpload(
            record["local_path"],
            mimetype=record["mime_type"],
            resumable=True,
        )

        try:
            metadata = (
                self.drive.files()
                .update(
                    fileId=drive_file_id,
                    media_body=media,
                    fields=(
                        "id,name,mimeType,size,createdTime,"
                        "modifiedTime,md5Checksum,webViewLink,"
                        "parents,trashed"
                    ),
                    supportsAllDrives=True,
                )
                .execute()
            )

            return metadata

        except Exception as exc:
            if self.is_insufficient_scope_error(exc):
                self.handle_auth_error(exc)

                raise RuntimeError(
                    AUTH_ERROR_MESSAGE
                ) from exc

            raise

    # -----------------------------------------------------------------------
    # LOCAL_TO_DRIVE
    # -----------------------------------------------------------------------

    def sync_local_to_drive(
        self,
        record: Dict[str, Any],
    ) -> str:
        if self.stop_event.is_set():
            return "STOPPED"

        local_path = record["local_path"]

        path = Path(local_path)

        if not path.exists() or not path.is_file():
            self.summary["skipped"] += 1
            return "LOCAL_FILE_MISSING"

        self.summary["files"] += 1
        self.type_stats(record)

        local_size = path.stat().st_size
        local_checksum = self.sha256(
            local_path
        )

        # ---------------------------------------------------------------
        # Existing PostgreSQL mapping
        # ---------------------------------------------------------------

        existing = self.find_drive_file_by_local_path(
            local_path
        )

        if existing:
            drive_db_id = existing["id"]
            drive_id = existing["drive_file_id"]

            previous_checksum = existing.get(
                "local_checksum"
            )

            if (
                previous_checksum
                and previous_checksum == local_checksum
                and existing.get("local_size_bytes") == local_size
            ):
                self.summary["skipped"] += 1

                item_id = self.item_start(
                    drive_db_id,
                    "LOCAL_TO_DRIVE",
                    "Local file unchanged",
                )

                self.item_finish(
                    item_id,
                    "NO_CHANGE",
                )

                return "NO_CHANGE"

            metadata = self.current_drive_metadata(
                drive_id
            )

            if metadata.get("trashed"):
                metadata = None
            else:
                drive_modified = parse_dt(
                    metadata.get("modifiedTime")
                )

                local_modified = record[
                    "modified_time"
                ]

                if (
                    drive_modified
                    and local_modified
                    and local_modified <= drive_modified
                ):
                    self.summary["duplicates"] += 1

                    version_id = self.create_version(
                        drive_db_id,
                        metadata,
                        local_path,
                        local_checksum,
                        status="DUPLICATE",
                        downloaded=False,
                    )

                    self.link_local_file(
                        drive_db_id,
                        version_id,
                        local_path,
                        record["name"],
                        local_size,
                        local_checksum,
                    )

                    item_id = self.item_start(
                        drive_db_id,
                        "LOCAL_TO_DRIVE",
                        "Drive version is current or newer",
                    )

                    self.item_finish(
                        item_id,
                        "DUPLICATE",
                    )

                    return "DUPLICATE"

            if metadata is None:
                parent_id = self.resolve_local_parent_folder(
                    record["source_folder"]
                )

                metadata = self.search_drive_file(
                    record["name"],
                    parent_id,
                )

            if metadata:
                item_id = self.item_start(
                    drive_db_id,
                    "UPDATE",
                    "Local file changed",
                )

                try:
                    updated = self.update_existing_drive_file(
                        drive_id,
                        record,
                    )

                    version_id = self.create_version(
                        drive_db_id,
                        updated,
                        local_path,
                        local_checksum,
                        status="UPDATED",
                        downloaded=False,
                    )

                    self.update_drive_file_record(
                        drive_db_id,
                        updated,
                        local_path,
                        local_checksum,
                        local_size,
                    )

                    self.link_local_file(
                        drive_db_id,
                        version_id,
                        local_path,
                        record["name"],
                        local_size,
                        local_checksum,
                    )

                    self.summary["updated"] += 1

                    self.item_finish(
                        item_id,
                        "COMPLETED",
                    )

                    return "UPDATED"

                except Exception as exc:
                    self.summary["errors"] += 1

                    self.item_finish(
                        item_id,
                        "ERROR",
                        str(exc),
                    )

                    raise

        # ---------------------------------------------------------------
        # New local file
        # ---------------------------------------------------------------

        parent_folder_id = (
            self.resolve_local_parent_folder(
                record["source_folder"]
            )
        )

        existing_drive = self.search_drive_file(
            record["name"],
            parent_folder_id,
        )

        # ---------------------------------------------------------------
        # Same filename already exists in Drive
        # ---------------------------------------------------------------

        if existing_drive:
            drive_db_id = self.create_drive_file_record(
                existing_drive,
                local_path,
                local_checksum,
                local_size,
            )

            item_id = self.item_start(
                drive_db_id,
                "LOCAL_TO_DRIVE",
                "Matching file already exists in Drive",
            )

            drive_size = existing_drive.get("size")

            try:
                if drive_size is not None:
                    drive_size = int(drive_size)

                same_size = (
                    drive_size == local_size
                )

                drive_modified = parse_dt(
                    existing_drive.get("modifiedTime")
                )

                local_modified = record[
                    "modified_time"
                ]

                if (
                    same_size
                    and drive_modified
                    and local_modified <= drive_modified
                ):
                    version_id = self.create_version(
                        drive_db_id,
                        existing_drive,
                        local_path,
                        local_checksum,
                        status="DUPLICATE",
                        downloaded=False,
                    )

                    self.link_local_file(
                        drive_db_id,
                        version_id,
                        local_path,
                        record["name"],
                        local_size,
                        local_checksum,
                    )

                    self.summary["duplicates"] += 1

                    self.item_finish(
                        item_id,
                        "DUPLICATE",
                    )

                    return "DUPLICATE"

                # Local is newer or size differs:
                # update the existing Drive file.
                updated = self.update_existing_drive_file(
                    existing_drive["id"],
                    record,
                )

                version_id = self.create_version(
                    drive_db_id,
                    updated,
                    local_path,
                    local_checksum,
                    status="UPDATED",
                    downloaded=False,
                )

                self.update_drive_file_record(
                    drive_db_id,
                    updated,
                    local_path,
                    local_checksum,
                    local_size,
                )

                self.link_local_file(
                    drive_db_id,
                    version_id,
                    local_path,
                    record["name"],
                    local_size,
                    local_checksum,
                )

                self.summary["updated"] += 1

                self.item_finish(
                    item_id,
                    "COMPLETED",
                )

                return "UPDATED"

            except Exception as exc:
                self.summary["errors"] += 1

                self.item_finish(
                    item_id,
                    "ERROR",
                    str(exc),
                )

                raise

        # ---------------------------------------------------------------
        # Completely new file
        # ---------------------------------------------------------------

        self.emit(
            "UPLOAD_START",
            name=record["name"],
            local_path=local_path,
            source_folder=record["source_folder"],
        )

        try:
            uploaded = self.upload_new_local_file(
                record,
                parent_folder_id,
                local_checksum,
            )

        except Exception as exc:
            self.summary["errors"] += 1

            if self.is_insufficient_scope_error(exc):
                self.handle_auth_error(exc)

                self.emit(
                    "AUTH_ERROR",
                    message=AUTH_ERROR_MESSAGE,
                )

            raise

        drive_db_id = self.create_drive_file_record(
            uploaded,
            local_path,
            local_checksum,
            local_size,
        )

        item_id = self.item_start(
            drive_db_id,
            "CREATE",
            "New local file uploaded to Drive",
        )

        try:
            version_id = self.create_version(
                drive_db_id,
                uploaded,
                local_path,
                local_checksum,
                status="UPLOADED",
                downloaded=False,
            )

            self.link_local_file(
                drive_db_id,
                version_id,
                local_path,
                record["name"],
                local_size,
                local_checksum,
            )

            self.summary["updated"] += 1

            self.item_finish(
                item_id,
                "COMPLETED",
            )

            self.emit(
                "UPLOAD_COMPLETE",
                name=record["name"],
                drive_file_id=uploaded["id"],
                local_path=local_path,
            )

            return "UPLOADED"

        except Exception as exc:
            self.summary["errors"] += 1

            self.item_finish(
                item_id,
                "ERROR",
                str(exc),
            )

            raise

    # -----------------------------------------------------------------------
    # Process one Drive record
    # -----------------------------------------------------------------------

    def process_drive_record(
        self,
        record: Dict[str, Any],
    ) -> str:
        if self.stop_event.is_set():
            return "STOPPED"

        self.summary["scanned"] += 1
        self.summary["relevant"] += 1

        self.emit(
            "ITEM_START",
            name=record.get("name"),
            action=self.direction,
            drive_file_id=record.get("drive_file_id"),
        )

        try:
            result = self.sync_drive_to_local(
                record
            )

            self.emit(
                "ITEM_FINISH",
                name=record.get("name"),
                result=result,
            )

            return result

        except Exception as exc:
            self.summary["errors"] += 1

            self.emit(
                "ITEM_ERROR",
                name=record.get("name"),
                error=str(exc),
            )

            if self.is_insufficient_scope_error(exc):
                self.handle_auth_error(exc)

            return "ERROR"

    # -----------------------------------------------------------------------
    # Process one local record
    # -----------------------------------------------------------------------

    def process_local_record(
        self,
        record: Dict[str, Any],
    ) -> str:
        if self.stop_event.is_set():
            return "STOPPED"

        self.summary["scanned"] += 1
        self.summary["relevant"] += 1

        self.emit(
            "ITEM_START",
            name=record.get("name"),
            action=self.direction,
            local_path=record.get("local_path"),
        )

        try:
            result = self.sync_local_to_drive(
                record
            )

            self.emit(
                "ITEM_FINISH",
                name=record.get("name"),
                result=result,
            )

            return result

        except Exception as exc:
            if self.is_insufficient_scope_error(exc):
                self.handle_auth_error(exc)

                self.emit(
                    "AUTH_ERROR",
                    message=AUTH_ERROR_MESSAGE,
                )

                return "AUTH_ERROR"

            self.summary["errors"] += 1

            self.emit(
                "ITEM_ERROR",
                name=record.get("name"),
                error=str(exc),
            )

            return "ERROR"

    # -----------------------------------------------------------------------
    # Main run
    # -----------------------------------------------------------------------

    def run(self) -> int:
        self.emit(
            "RUN_START",
            direction=self.direction,
            message=(
                "Local → Drive"
                if self.direction == DIRECTION_LOCAL_TO_DRIVE
                else "Drive → Local"
            ),
        )

        try:
            self.start_stop_listener()

            self.connect()

            if self.auth_error:
                self.finish_run(
                    "AUTH_ERROR",
                    AUTH_ERROR_MESSAGE,
                )

                return 2

            # ---------------------------------------------------------------
            # Local -> Drive
            # ---------------------------------------------------------------

            if self.direction == DIRECTION_LOCAL_TO_DRIVE:
                candidates = self.get_local_candidates()

            # ---------------------------------------------------------------
            # Drive -> Local
            # ---------------------------------------------------------------

            else:
                candidates = self.get_drive_candidates()

            self.summary["scanned"] = 0

            self.sync_run_id = self.create_run(
                len(candidates)
            )

            self.emit(
                "CANDIDATES",
                count=len(candidates),
                direction=self.direction,
            )

            for record in candidates:
                if self.stop_event.is_set():
                    break

                if self.auth_error:
                    break

                if self.direction == DIRECTION_LOCAL_TO_DRIVE:
                    result = self.process_local_record(
                        record
                    )
                else:
                    result = self.process_drive_record(
                        record
                    )

                if result == "AUTH_ERROR":
                    break

            # ---------------------------------------------------------------
            # Final status
            # ---------------------------------------------------------------

            if self.auth_error:
                self.finish_run(
                    "AUTH_ERROR",
                    AUTH_ERROR_MESSAGE,
                )

                self.emit(
                    "AUTH_ERROR",
                    message=AUTH_ERROR_MESSAGE,
                )

                return 2

            if self.stop_event.is_set():
                self.finish_run(
                    "STOPPED"
                )

                self.emit(
                    "RUN_STOPPED",
                    exit_code=1,
                )

                return 1

            self.finish_run(
                "COMPLETED"
            )

            self.emit(
                "RUN_FINISHED",
                status="COMPLETED",
                summary=self.summary,
                by_type=self.by_type,
            )

            return 0

        except Exception as exc:
            self.summary["errors"] += 1

            if self.is_insufficient_scope_error(exc):
                self.handle_auth_error(exc)

                try:
                    self.finish_run(
                        "AUTH_ERROR",
                        AUTH_ERROR_MESSAGE,
                    )
                except Exception:
                    pass

                self.emit(
                    "AUTH_ERROR",
                    message=AUTH_ERROR_MESSAGE,
                )

                return 2

            try:
                self.finish_run(
                    "ERROR",
                    str(exc),
                )
            except Exception:
                pass

            self.emit(
                "RUN_ERROR",
                error=str(exc),
                summary=self.summary,
            )

            return 3

        finally:
            try:
                if self.connection:
                    self.connection.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    direction = os.environ.get(
        "ALCALAY_SYNC_DIRECTION",
        DIRECTION_DRIVE_TO_LOCAL,
    ).strip().upper()

    if direction not in {
        DIRECTION_DRIVE_TO_LOCAL,
        DIRECTION_LOCAL_TO_DRIVE,
    }:
        print(
            f"Invalid ALCALAY_SYNC_DIRECTION: {direction}",
            file=sys.stderr,
        )

        return 2

    sync = DriveSync(
        direction=direction
    )

    return sync.run()


if __name__ == "__main__":
    raise SystemExit(main())