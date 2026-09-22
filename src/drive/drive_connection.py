# -*- coding: utf-8 -*-

"""
Alcalay - Google Drive Connection
=================================

Google Drive OAuth connection module.

Responsibilities:
    - Connect to Google Drive using OAuth.
    - Reuse the existing Google OAuth client credentials.
    - Keep a separate OAuth token for Drive.
    - Read the Alcalay Drive repository configuration.
    - Verify access to the configured Alcalay folders.
    - Allow read-only access to Drive file content for future
      content-based keyword searching and export.

This module does NOT:
    - Upload files.
    - Delete files.
    - Move files.
    - Rename files.
    - Synchronize files.
    - Modify PostgreSQL.
    - Index documents.
    - Decide which files are relevant.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[2]

CONFIG_FILE = PROJECT_ROOT / "config" / "alcalay_config.json"

GOOGLE_CREDENTIALS_FILE = (
    PROJECT_ROOT
    / "config"
    / "gmail"
    / "credentials.json"
)

DRIVE_DIR = PROJECT_ROOT / "config" / "drive"
DRIVE_TOKENS_DIR = DRIVE_DIR / "tokens"


# Read-only access to Google Drive.
#
# This scope is intentionally read-only.
# It allows metadata access and reading/exporting file content,
# but does not allow Drive modifications.
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly"
]


REPOSITORY_NAME = "alcalay"

REQUIRED_FOLDERS = {
    "root_folder_id": "Alcalay",
    "documents_folder_id": "Documents",
    "gmail_folder_id": "Gmail",
    "database_folder_id": "Database",
    "backups_folder_id": "Backups",
}


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _token_file_for_email(email: str) -> Path:
    normalized_email = _normalize_email(email)
    return DRIVE_TOKENS_DIR / f"{normalized_email}.json"


def _load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            "לא נמצא קובץ התצורה של Alcalay:\n\n"
            f"{CONFIG_FILE}"
        )

    try:
        with CONFIG_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:
            config = json.load(file)

    except json.JSONDecodeError as exc:
        raise ValueError(
            "קובץ config/alcalay_config.json אינו JSON תקין."
        ) from exc

    if not isinstance(config, dict):
        raise ValueError(
            "מבנה config/alcalay_config.json אינו תקין."
        )

    return config


def _load_alcalay_repository() -> dict[str, str]:
    config = _load_config()

    try:
        repository = (
            config["google_drive"]
            ["repositories"]
            [REPOSITORY_NAME]
        )

    except KeyError as exc:
        raise KeyError(
            "לא נמצאה הגדרת Google Drive repository "
            f"'{REPOSITORY_NAME}' ב־alcalay_config.json."
        ) from exc

    if not isinstance(repository, dict):
        raise ValueError(
            "הגדרת Alcalay Google Drive repository אינה תקינה."
        )

    result: dict[str, str] = {}

    for key in REQUIRED_FOLDERS:

        folder_id = repository.get(key)

        if not folder_id:
            raise ValueError(
                "חסר Folder ID בהגדרת Google Drive: "
                f"{key}"
            )

        if not isinstance(folder_id, str):
            raise ValueError(
                "Folder ID אינו טקסט עבור: "
                f"{key}"
            )

        folder_id = folder_id.strip()

        if not folder_id:
            raise ValueError(
                "Folder ID ריק עבור: "
                f"{key}"
            )

        result[key] = folder_id

    return result


class DriveConnection:
    """
    Handles authenticated access to Google Drive.

    The connection is read-only.

    The read-only Drive scope allows the application to:
        - Read file metadata.
        - Search Drive.
        - Search indexed file content.
        - Read/export file content when required.

    The connection does not provide write access to Drive.
    """

    def __init__(
        self,
        account_email: str = "",
    ) -> None:

        self.service = None
        self.credentials = None

        self.account_email = _normalize_email(
            account_email
        )

        self.repository = _load_alcalay_repository()

    def connect(
        self,
        account_email: str | None = None,
    ) -> str:

        if account_email:
            self.account_email = _normalize_email(
                account_email
            )

        if not GOOGLE_CREDENTIALS_FILE.exists():
            raise FileNotFoundError(
                "לא נמצא Google OAuth credentials.json:\n\n"
                f"{GOOGLE_CREDENTIALS_FILE}"
            )

        DRIVE_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        DRIVE_TOKENS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        credentials = None
        token_file = None

        if self.account_email:

            token_file = _token_file_for_email(
                self.account_email
            )

            if token_file.exists():

                try:
                    credentials = (
                        Credentials
                        .from_authorized_user_file(
                            str(token_file),
                            SCOPES,
                        )
                    )

                except Exception:
                    credentials = None

        if (
            credentials
            and credentials.expired
            and credentials.refresh_token
        ):

            credentials.refresh(
                Request()
            )

        if (
            not credentials
            or not credentials.valid
        ):

            flow = (
                InstalledAppFlow
                .from_client_secrets_file(
                    str(GOOGLE_CREDENTIALS_FILE),
                    SCOPES,
                )
            )

            credentials = (
                flow.run_local_server(
                    port=0,
                    access_type="offline",
                    prompt="select_account",
                )
            )

        self.credentials = credentials

        self.service = build(
            "drive",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )

        if not self.account_email:
            self.account_email = (
                self._get_connected_account_email()
            )

        token_file = _token_file_for_email(
            self.account_email
        )

        token_file.write_text(
            credentials.to_json(),
            encoding="utf-8",
        )

        return self.account_email

    def _get_connected_account_email(self) -> str:

        if self.service is None:
            raise RuntimeError(
                "Google Drive עדיין לא מחובר."
            )

        response = (
            self.service
            .about()
            .get(
                fields="user(emailAddress)",
            )
            .execute()
        )

        user = response.get(
            "user",
            {},
        )

        email = user.get(
            "emailAddress",
            "",
        )

        if not email:
            raise RuntimeError(
                "לא ניתן לזהות את חשבון Google המחובר."
            )

        return _normalize_email(email)

    def verify_folder(
        self,
        folder_id: str,
    ) -> dict[str, Any]:

        if self.service is None:
            raise RuntimeError(
                "Google Drive עדיין לא מחובר."
            )

        if not folder_id:
            raise ValueError(
                "Folder ID ריק."
            )

        response = (
            self.service
            .files()
            .get(
                fileId=folder_id,
                fields=(
                    "id,"
                    "name,"
                    "mimeType,"
                    "trashed,"
                    "webViewLink"
                ),
                supportsAllDrives=True,
            )
            .execute()
        )

        return response

    def verify_alcalay_repository(
        self,
    ) -> dict[str, dict[str, Any]]:

        if self.service is None:
            raise RuntimeError(
                "Google Drive עדיין לא מחובר."
            )

        results: dict[str, dict[str, Any]]] = {}

        for key, display_name in REQUIRED_FOLDERS.items():

            folder_id = self.repository[key]

            metadata = self.verify_folder(
                folder_id
            )

            results[display_name] = metadata

        return results

    def get_repository_folder_ids(
        self,
    ) -> dict[str, str]:

        return dict(self.repository)