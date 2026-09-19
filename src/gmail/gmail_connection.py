# -*- coding: utf-8 -*-

"""
Alcalay - Gmail Connection
==========================

Gmail OAuth connection module.

This module is intentionally limited to:
    - Connecting to a Gmail account
    - Refreshing an existing OAuth token
    - Reading the connected Gmail account address
    - Providing the authenticated Gmail API service

It does NOT contain:
    - Gmail search
    - Gmail labels
    - Message downloading
    - Attachments
    - Synchronization
"""

from __future__ import annotations

from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------

CURRENT_FILE = Path(__file__).resolve()

# Expected structure:
#
# Alcalay/
# ├── src/
# │   └── gmail/
# │       └── gmail_connection.py
# └── config/
#     └── gmail/
#         ├── credentials.json
#         └── token.json
#
PROJECT_ROOT = CURRENT_FILE.parents[2]

GMAIL_DIR = PROJECT_ROOT / "config" / "gmail"

CREDENTIALS_FILE = GMAIL_DIR / "credentials.json"
TOKEN_FILE = GMAIL_DIR / "token.json"


# ----------------------------------------------------------------------
# Gmail OAuth scope
# ----------------------------------------------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]


# ----------------------------------------------------------------------
# Gmail Connection
# ----------------------------------------------------------------------

class GmailConnection:
    """
    Handles authentication and connection to Gmail.

    This class intentionally contains only the Gmail connection layer.
    """

    def __init__(self):
        self.service = None
        self.credentials = None
        self.account_email = ""

    # ------------------------------------------------------------------
    # Connect
    # ------------------------------------------------------------------

    def connect(self) -> str:
        """
        Connect to Gmail.

        Returns:
            The connected Gmail account email address.

        Raises:
            FileNotFoundError:
                If credentials.json does not exist.

            Exception:
                If authentication or Gmail connection fails.
        """

        if not CREDENTIALS_FILE.exists():
            raise FileNotFoundError(
                "לא נמצא credentials.json:\n\n"
                f"{CREDENTIALS_FILE}"
            )

        GMAIL_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        credentials = None

        # --------------------------------------------------------------
        # Try existing token
        # --------------------------------------------------------------

        if TOKEN_FILE.exists():

            try:

                credentials = (
                    Credentials
                    .from_authorized_user_file(
                        str(TOKEN_FILE),
                        SCOPES
                    )
                )

            except Exception:

                credentials = None

        # --------------------------------------------------------------
        # Refresh existing credentials
        # --------------------------------------------------------------

        if (
            credentials
            and credentials.expired
            and credentials.refresh_token
        ):

            credentials.refresh(
                Request()
            )

        # --------------------------------------------------------------
        # Start OAuth if necessary
        # --------------------------------------------------------------

        if (
            not credentials
            or not credentials.valid
        ):

            flow = (
                InstalledAppFlow
                .from_client_secrets_file(
                    str(CREDENTIALS_FILE),
                    SCOPES
                )
            )

            credentials = (
                flow.run_local_server(
                    port=0,
                    access_type="offline",
                    prompt="select_account"
                )
            )

            # ----------------------------------------------------------
            # Save token
            # ----------------------------------------------------------

            with open(
                TOKEN_FILE,
                "w",
                encoding="utf-8"
            ) as file:

                file.write(
                    credentials.to_json()
                )

        # --------------------------------------------------------------
        # Build Gmail API service
        # --------------------------------------------------------------

        self.credentials = credentials

        self.service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False
        )

        # --------------------------------------------------------------
        # Verify connection and obtain account email
        # --------------------------------------------------------------

        profile = (
            self.service.users()
            .getProfile(
                userId="me"
            )
            .execute()
        )

        self.account_email = profile.get(
            "emailAddress",
            ""
        )

        if not self.account_email:
            raise RuntimeError(
                "החיבור ל-Gmail הצליח, "
                "אך לא התקבלה כתובת חשבון."
            )

        return self.account_email

    # ------------------------------------------------------------------
    # Connection status
    # ------------------------------------------------------------------

    def is_connected(self) -> bool:
        """
        Return True if a Gmail service is currently connected.
        """

        return self.service is not None

    # ------------------------------------------------------------------
    # Account email
    # ------------------------------------------------------------------

    def get_account_email(self) -> str:
        """
        Return the currently connected Gmail address.
        """

        return self.account_email

    # ------------------------------------------------------------------
    # Gmail API service
    # ------------------------------------------------------------------

    def get_service(self):
        """
        Return the authenticated Gmail API service.

        Raises:
            RuntimeError:
                If there is currently no Gmail connection.
        """

        if self.service is None:
            raise RuntimeError(
                "אין חיבור פעיל ל-Gmail."
            )

        return self.service

    # ------------------------------------------------------------------
    # Disconnect
    # ------------------------------------------------------------------

    def disconnect(self):
        """
        Disconnect the current Gmail service from the application.

        This does NOT delete token.json.
        """

        self.service = None
        self.credentials = None
        self.account_email = ""


# ----------------------------------------------------------------------
# Standalone test
# ----------------------------------------------------------------------

def main() -> int:

    print()
    print("=" * 60)
    print("Alcalay - Gmail Connection Test")
    print("=" * 60)
    print()

    print("Credentials:")
    print(CREDENTIALS_FILE)

    print()

    print("Token:")
    print(TOKEN_FILE)

    print()

    connection = GmailConnection()

    try:

        print("מתחבר ל-Gmail...")
        print()

        email = connection.connect()

        print("=" * 60)
        print("החיבור הצליח")
        print("=" * 60)
        print()
        print(f"חשבון Gmail: {email}")
        print()
        print("Gmail API service: OK")
        print()

        return 0

    except Exception as exc:

        print("=" * 60)
        print("החיבור נכשל")
        print("=" * 60)
        print()
        print(str(exc))
        print()

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )