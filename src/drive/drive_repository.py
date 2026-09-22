# -*- coding: utf-8 -*-

"""
Alcalay - Google Drive Repository
=================================

Logical representation of the Alcalay Google Drive repository.

Repository structure:

    Alcalay
    ├── Documents
    ├── Gmail
    ├── Database
    └── Backups

Responsibilities:
    - Load the configured repository from Alcalay configuration.
    - Provide named access to repository folders.
    - Verify repository folders through DriveConnection.
    - Expose folder IDs and metadata.

This module does NOT:
    - Upload files.
    - Download files.
    - Delete files.
    - Move files.
    - Rename files.
    - Synchronize files.
    - Modify PostgreSQL.
    - Index documents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.drive.drive_connection import DriveConnection


@dataclass(frozen=True)
class DriveFolder:
    """
    Represents one configured Google Drive folder.
    """

    key: str
    display_name: str
    folder_id: str


class DriveRepository:
    """
    Represents the configured Alcalay Google Drive repository.

    The repository currently contains five configured folders:

        root
        documents
        gmail
        database
        backups
    """

    FOLDER_DEFINITIONS = (
        ("root_folder_id", "root", "Alcalay"),
        ("documents_folder_id", "documents", "Documents"),
        ("gmail_folder_id", "gmail", "Gmail"),
        ("database_folder_id", "database", "Database"),
        ("backups_folder_id", "backups", "Backups"),
    )

    def __init__(
        self,
        connection: DriveConnection,
    ) -> None:

        if not isinstance(
            connection,
            DriveConnection,
        ):
            raise TypeError(
                "connection חייב להיות מופע של DriveConnection."
            )

        self.connection = connection

        self._folders: dict[str, DriveFolder] = {}

        repository_ids = (
            self.connection.get_repository_folder_ids()
        )

        for config_key, key, display_name in (
            self.FOLDER_DEFINITIONS
        ):

            folder_id = repository_ids.get(
                config_key
            )

            if not folder_id:
                raise ValueError(
                    "חסר Folder ID עבור repository folder: "
                    f"{config_key}"
                )

            self._folders[key] = DriveFolder(
                key=key,
                display_name=display_name,
                folder_id=folder_id,
            )

    def get_folder(
        self,
        key: str,
    ) -> DriveFolder:

        normalized_key = key.strip().lower()

        if normalized_key not in self._folders:
            raise KeyError(
                "לא נמצאה תיקיית repository בשם: "
                f"{key}"
            )

        return self._folders[
            normalized_key
        ]

    def get_root_folder(self) -> DriveFolder:

        return self.get_folder("root")

    def get_documents_folder(self) -> DriveFolder:

        return self.get_folder("documents")

    def get_gmail_folder(self) -> DriveFolder:

        return self.get_folder("gmail")

    def get_database_folder(self) -> DriveFolder:

        return self.get_folder("database")

    def get_backups_folder(self) -> DriveFolder:

        return self.get_folder("backups")

    def get_all_folders(
        self,
    ) -> dict[str, DriveFolder]:

        return dict(self._folders)

    def get_folder_ids(
        self,
    ) -> dict[str, str]:

        return {
            key: folder.folder_id
            for key, folder in self._folders.items()
        }

    def verify(
        self,
    ) -> dict[str, dict[str, Any]]:

        if self.connection.service is None:
            raise RuntimeError(
                "Google Drive עדיין לא מחובר. "
                "יש לבצע connection.connect() לפני verify()."
            )

        results: dict[str, dict[str, Any]] = {}

        for key, folder in self._folders.items():

            metadata = (
                self.connection.verify_folder(
                    folder.folder_id
                )
            )

            results[key] = metadata

        return results

    def verify_structure(
        self,
    ) -> bool:

        results = self.verify()

        expected_names = {
            "root": "alcalay",
            "documents": "documents",
            "gmail": "gmail",
            "database": "database",
            "backups": "backups",
        }

        for key, expected_name in (
            expected_names.items()
        ):

            metadata = results[key]

            actual_name = (
                str(
                    metadata.get(
                        "name",
                        "",
                    )
                )
                .strip()
                .lower()
            )

            if actual_name != expected_name:
                return False

            if metadata.get(
                "trashed",
                False,
            ):
                return False

            if metadata.get(
                "mimeType"
            ) != "application/vnd.google-apps.folder":
                return False

        return True

    def describe(
        self,
    ) -> list[dict[str, str]]:

        result: list[dict[str, str]] = []

        for key, folder in self._folders.items():

            result.append(
                {
                    "key": key,
                    "name": folder.display_name,
                    "folder_id": folder.folder_id,
                }
            )

        return result