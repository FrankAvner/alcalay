# -*- coding: utf-8 -*-

"""
Alcalay - Google Drive Scanner
==============================

Read-only scanner for the Alcalay Google Drive repository.

Responsibilities:
    - Scan files and folders inside a configured repository folder.
    - Scan recursively through subfolders.
    - Return Google Drive metadata only.
    - Preserve metadata required for duplicate detection.
    - Preserve metadata required for version/change detection.

This module does NOT:
    - Download files.
    - Upload files.
    - Delete files.
    - Move files.
    - Rename files.
    - Modify files.
    - Synchronize files.
    - Modify PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.drive.drive_connection import DriveConnection
from src.drive.drive_repository import DriveRepository


FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


@dataclass(frozen=True)
class DriveItem:
    """
    Metadata representation of one Google Drive item.

    No file content is downloaded by this class.
    """

    file_id: str
    name: str
    mime_type: str

    size: int | None

    modified_time: str | None
    created_time: str | None

    md5_checksum: str | None

    web_view_link: str | None

    parent_id: str | None

    is_folder: bool
    trashed: bool


class DriveScanner:
    """
    Read-only recursive scanner for Google Drive.

    The scanner retrieves metadata only.

    It does not download or modify any Drive content.
    """

    PAGE_SIZE = 1000

    FILE_FIELDS = (
        "nextPageToken,"
        "files("
        "id,"
        "name,"
        "mimeType,"
        "size,"
        "createdTime,"
        "modifiedTime,"
        "md5Checksum,"
        "webViewLink,"
        "parents,"
        "trashed"
        ")"
    )

    def __init__(
        self,
        connection: DriveConnection,
        repository: DriveRepository,
    ) -> None:

        if not isinstance(
            connection,
            DriveConnection,
        ):
            raise TypeError(
                "connection חייב להיות מופע של DriveConnection."
            )

        if not isinstance(
            repository,
            DriveRepository,
        ):
            raise TypeError(
                "repository חייב להיות מופע של DriveRepository."
            )

        self.connection = connection
        self.repository = repository

    def _require_connection(self) -> None:
        """
        Ensure that the Google Drive service is connected.
        """

        if self.connection.service is None:
            raise RuntimeError(
                "Google Drive עדיין לא מחובר."
            )

    def _list_children(
        self,
        parent_id: str,
    ) -> list[dict[str, Any]]:
        """
        Return direct children of one Google Drive folder.

        This method retrieves metadata only.
        """

        self._require_connection()

        if not parent_id:
            raise ValueError(
                "parent_id אינו יכול להיות ריק."
            )

        files: list[dict[str, Any]] = []

        page_token: str | None = None

        while True:

            request = (
                self.connection.service
                .files()
                .list(
                    q=(
                        f"'{parent_id}' in parents "
                        "and trashed = false"
                    ),
                    spaces="drive",
                    fields=self.FILE_FIELDS,
                    pageSize=self.PAGE_SIZE,
                    pageToken=page_token,
                    orderBy="folder,name",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
            )

            response = request.execute()

            page_files = response.get(
                "files",
                [],
            )

            if isinstance(
                page_files,
                list,
            ):
                files.extend(page_files)

            page_token = response.get(
                "nextPageToken"
            )

            if not page_token:
                break

        return files

    @staticmethod
    def _safe_optional_string(
        value: Any,
    ) -> str | None:
        """
        Convert a metadata value to a clean optional string.
        """

        if value is None:
            return None

        value_string = str(value).strip()

        if not value_string:
            return None

        return value_string

    @staticmethod
    def _safe_optional_int(
        value: Any,
    ) -> int | None:
        """
        Convert a metadata value to an optional integer.
        """

        if value is None:
            return None

        try:
            return int(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @classmethod
    def _to_drive_item(
        cls,
        metadata: dict[str, Any],
        parent_id: str | None,
    ) -> DriveItem:
        """
        Convert raw Google Drive metadata into DriveItem.
        """

        mime_type = str(
            metadata.get(
                "mimeType",
                "",
            )
        ).strip()

        size = cls._safe_optional_int(
            metadata.get(
                "size"
            )
        )

        parents = metadata.get(
            "parents"
        )

        actual_parent_id = parent_id

        if (
            isinstance(
                parents,
                list,
            )
            and parents
        ):

            first_parent = parents[0]

            if first_parent is not None:

                actual_parent_id = str(
                    first_parent
                ).strip()

        file_id = cls._safe_optional_string(
            metadata.get(
                "id"
            )
        )

        if not file_id:
            raise ValueError(
                "Google Drive item ללא file_id."
            )

        name = str(
            metadata.get(
                "name",
                "",
            )
        ).strip()

        return DriveItem(
            file_id=file_id,
            name=name,

            mime_type=mime_type,

            size=size,

            modified_time=cls._safe_optional_string(
                metadata.get(
                    "modifiedTime"
                )
            ),

            created_time=cls._safe_optional_string(
                metadata.get(
                    "createdTime"
                )
            ),

            md5_checksum=cls._safe_optional_string(
                metadata.get(
                    "md5Checksum"
                )
            ),

            web_view_link=cls._safe_optional_string(
                metadata.get(
                    "webViewLink"
                )
            ),

            parent_id=actual_parent_id,

            is_folder=(
                mime_type == FOLDER_MIME_TYPE
            ),

            trashed=bool(
                metadata.get(
                    "trashed",
                    False,
                )
            ),
        )

    def scan_folder(
        self,
        folder_id: str,
        recursive: bool = True,
    ) -> list[DriveItem]:
        """
        Scan a Google Drive folder.

        When recursive=True, all descendant folders are scanned.

        Returns metadata only.
        """

        self._require_connection()

        if not folder_id:
            raise ValueError(
                "folder_id אינו יכול להיות ריק."
            )

        results: list[DriveItem] = []

        children = self._list_children(
            folder_id
        )

        for metadata in children:

            item = self._to_drive_item(
                metadata,
                folder_id,
            )

            results.append(
                item
            )

            if (
                recursive
                and item.is_folder
            ):

                results.extend(
                    self.scan_folder(
                        item.file_id,
                        recursive=True,
                    )
                )

        return results

    def scan_documents(
        self,
        recursive: bool = True,
    ) -> list[DriveItem]:
        """
        Scan the configured Documents repository folder.
        """

        documents_folder = (
            self.repository
            .get_documents_folder()
        )

        return self.scan_folder(
            documents_folder.folder_id,
            recursive=recursive,
        )

    def scan_gmail(
        self,
        recursive: bool = True,
    ) -> list[DriveItem]:
        """
        Scan the configured Gmail repository folder.
        """

        gmail_folder = (
            self.repository
            .get_gmail_folder()
        )

        return self.scan_folder(
            gmail_folder.folder_id,
            recursive=recursive,
        )

    def scan_database(
        self,
        recursive: bool = True,
    ) -> list[DriveItem]:
        """
        Scan the configured Database repository folder.
        """

        database_folder = (
            self.repository
            .get_database_folder()
        )

        return self.scan_folder(
            database_folder.folder_id,
            recursive=recursive,
        )

    def scan_backups(
        self,
        recursive: bool = True,
    ) -> list[DriveItem]:
        """
        Scan the configured Backups repository folder.
        """

        backups_folder = (
            self.repository
            .get_backups_folder()
        )

        return self.scan_folder(
            backups_folder.folder_id,
            recursive=recursive,
        )