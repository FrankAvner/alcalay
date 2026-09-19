# -*- coding: utf-8 -*-

"""
Alcalay - Gmail Connection
==========================

Gmail OAuth connection module.

This module is responsible only for:
    - Connecting to a specific Gmail account
    - Refreshing an OAuth token
    - Reading the connected Gmail account address
    - Providing the authenticated Gmail API service

It does NOT contain:
    - Gmail search
    - Gmail labels management
    - Message downloading
    - Attachments
    - Synchronization

Each Gmail account has its own OAuth token.
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
#         └── tokens/
#             ├── frank.avner@gmail.com.json
#             └── another@gmail.com.json
#

PROJECT_ROOT = CURRENT_FILE.parents[2]

GMAIL_DIR = PROJECT_ROOT / "config" / "gmail"

CREDENTIALS_FILE = GMAIL_DIR / "credentials.json"

TOKENS_DIR = GMAIL_DIR / "tokens"


# ----------------------------------------------------------------------
# Gmail OAuth scope
# ----------------------------------------------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]


# ======================================================================
# Helper functions
# ======================================================================

def _normalize_email(email: str) -> str:
    """
    Normalize a Gmail address for internal use.
    """

    return email.strip().lower()


def _token_file_for_email(email: str) -> Path:
    """
    Return the OAuth token file for a specific Gmail account.

    Example:
        frank.avner@gmail.com
        ->
        config/gmail/tokens/frank.avner@gmail.com.json
    """

    normalized_email = _normalize_email(email)

    return TOKENS_DIR / f"{normalized_email}.json"


# ======================================================================
# Gmail Connection
# ======================================================================

class GmailConnection:
    """
    Handles authentication and connection to one Gmail account.

    One GmailConnection instance represents one currently connected
    Gmail account.
    """

    def __init__(self, account_email: str = ""):

        self.service = None
        self.credentials = None

        self.account_email = _normalize_email(
            account_email
        )

    # ------------------------------------------------------------------
    # Connect
    # ------------------------------------------------------------------

    def connect(
        self,
        account_email: str | None = None,
    ) -> str:
        """
        Connect to a specific Gmail account.

        Args:
            account_email:
                Optional Gmail address.

                If supplied, it is used as the preferred account
                during OAuth.

                If omitted and no account was previously supplied,
                OAuth account selection is used.

        Returns:
            The connected Gmail account email address.

        Raises:
            FileNotFoundError:
                If credentials.json does not exist.

            Exception:
                If authentication or Gmail connection fails.
        """

        # --------------------------------------------------------------
        # Update requested account
        # --------------------------------------------------------------

        if account_email:

            self.account_email = _normalize_email(
                account_email
            )

        # --------------------------------------------------------------
        # Verify credentials.json
        # --------------------------------------------------------------

        if not CREDENTIALS_FILE.exists():

            raise FileNotFoundError(
                "לא נמצא credentials.json:\n\n"
                f"{CREDENTIALS_FILE}"
            )

        GMAIL_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        TOKENS_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        credentials = None

        # --------------------------------------------------------------
        # Try existing token for the requested account
        # --------------------------------------------------------------

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
        # Verify connection and obtain actual account email
        # --------------------------------------------------------------

        profile = (
            self.service.users()
            .getProfile(
                userId="me"
            )
            .execute()
        )

        connected_email = profile.get(
            "emailAddress",
            ""
        )

        if not connected_email:

            self.service = None
            self.credentials = None

            raise RuntimeError(
                "החיבור ל-Gmail הצליח, "
                "אך לא התקבלה כתובת חשבון."
            )

        connected_email = _normalize_email(
            connected_email
        )

        # --------------------------------------------------------------
        # If the requested account was different from the actual
        # connected account, use the actual account.
        # --------------------------------------------------------------

        self.account_email = connected_email

        # --------------------------------------------------------------
        # Save token under the actual Gmail account.
        # --------------------------------------------------------------

        token_file = _token_file_for_email(
            self.account_email
        )

        with open(
            token_file,
            "w",
            encoding="utf-8"
        ) as file:

            file.write(
                credentials.to_json()
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

        The OAuth token is intentionally NOT deleted.
        """

        self.service = None
        self.credentials = None
        self.account_email = ""


# ======================================================================
# Standalone test
# ======================================================================

def main() -> int:

    print()
    print("=" * 60)
    print("Alcalay - Gmail Connection Test")
    print("=" * 60)
    print()

    print("Credentials:")
    print(CREDENTIALS_FILE)

    print()

    print("Tokens directory:")
    print(TOKENS_DIR)

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

        print(
            f"Token: {_token_file_for_email(email)}"
        )

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