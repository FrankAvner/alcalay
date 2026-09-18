#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Alcalay Server - Initial Setup
==============================

Initial installation/setup wizard for the Alcalay server.

Suggested location:
    alcalay/init_files/alcalay_server_setup.py

This script creates the initial server configuration.

Supported server operating systems:
    - Windows
    - macOS

Configured components:
    - Alcalay server
    - PostgreSQL
    - Local document storage
    - Search index
    - Backups
    - Google Drive
    - Gmail
    - OCR
    - AI
    - ML
    - Authentication
    - Incremental synchronization

IMPORTANT:
    Gmail is configured to synchronize SELECTED LABELS ONLY.
    The entire Gmail mailbox is NOT synchronized.

The actual Gmail OAuth connection, label selection UI,
synchronization engine, indexing engine and runtime API
will be implemented in later stages.
"""

from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path


# ============================================================================
# CONSTANTS
# ============================================================================

APP_NAME = "Alcalay"
CONFIG_VERSION = "1.0"

DEFAULT_API_PORT = 8443
DEFAULT_POSTGRES_PORT = 5432


# ============================================================================
# GENERAL HELPERS
# ============================================================================

def now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ask(
    prompt: str,
    default: str | None = None,
    required: bool = False,
) -> str:
    """Ask the user for a text value."""

    while True:
        suffix = f" [{default}]" if default else ""

        value = input(f"{prompt}{suffix}: ").strip()

        if not value and default is not None:
            value = default

        if required and not value:
            print("ערך זה חובה.")
            continue

        return value


def ask_int(
    prompt: str,
    default: int,
) -> int:
    """Ask the user for a valid TCP port."""

    while True:
        value = ask(prompt, str(default))

        try:
            number = int(value)

            if 1 <= number <= 65535:
                return number

        except ValueError:
            pass

        print("נא להזין מספר בין 1 ל-65535.")


def ask_yes_no(
    prompt: str,
    default: bool = True,
) -> bool:
    """Ask a yes/no question."""

    default_text = "Y/n" if default else "y/N"

    while True:

        value = input(
            f"{prompt} [{default_text}]: "
        ).strip().lower()

        if not value:
            return default

        if value in ("y", "yes", "כן"):
            return True

        if value in ("n", "no", "לא"):
            return False

        print("נא להזין Y/N.")


def normalize_path(value: str) -> str:
    """Normalize a user supplied filesystem path."""

    return str(
        Path(value).expanduser()
    )


def create_directory(path: str) -> None:
    """Create a directory if it does not exist."""

    Path(path).expanduser().mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================================
# SERVER OS
# ============================================================================

def choose_server_os() -> str:
    """
    Ask which operating system will be used by the Alcalay server.

    The user can explicitly choose Windows or macOS even when running
    the setup script from another operating system.
    """

    detected = platform.system().lower()

    if detected == "windows":
        detected_name = "Windows"

    elif detected == "darwin":
        detected_name = "macOS"

    else:
        detected_name = "Other"

    print()
    print("--- מערכת ההפעלה של שרת Alcalay ---")
    print()
    print("1. Windows")
    print("2. macOS")
    print()
    print(
        f"מערכת ההפעלה הנוכחית שזוהתה: {detected_name}"
    )
    print()

    while True:

        choice = input(
            "בחר 1 או 2: "
        ).strip()

        if choice == "1":
            return "windows"

        if choice == "2":
            return "macos"

        print("בחירה לא תקינה.")


def default_server_root(
    server_os: str,
) -> str:
    """Return a sensible default root directory."""

    if server_os == "windows":

        return r"C:\AlcalayServer"

    return str(
        Path.home() / "AlcalayServer"
    )


# ============================================================================
# HEADER
# ============================================================================

def print_header() -> None:

    print()
    print("=" * 78)
    print("ALCALAY SERVER - INITIAL SETUP")
    print("=" * 78)
    print()
    print("אשף הקמת שרת Alcalay")
    print()
    print(
        "שלב זה יוצר את תצורת השרת הראשונית."
    )
    print(
        "הוא אינו מפעיל עדיין OAuth, סנכרון Gmail או מנוע החיפוש."
    )
    print()


# ============================================================================
# MAIN SETUP
# ============================================================================

def main() -> None:

    print_header()

    # ========================================================================
    # 1. SERVER
    # ========================================================================

    server_os = choose_server_os()

    print()
    print("--- הגדרות שרת ---")
    print()

    server_name = ask(
        "שם השרת",
        "ALCALAY-SERVER",
    )

    server_host = ask(
        "כתובת / DNS של השרת",
        "0.0.0.0",
    )

    server_port = ask_int(
        "פורט API",
        DEFAULT_API_PORT,
    )

    # ========================================================================
    # 2. PATHS
    # ========================================================================

    print()
    print("--- תיקיות שרת ---")
    print()

    print(
        "ניתן לשנות את כל הנתיבים."
    )

    app_root = normalize_path(
        ask(
            "תיקיית הבסיס של Alcalay",
            default_server_root(server_os),
        )
    )

    documents_root = normalize_path(
        ask(
            "תיקיית המסמכים המקומית",
            str(
                Path(app_root) /
                "documents"
            ),
        )
    )

    index_root = normalize_path(
        ask(
            "תיקיית אינדקס החיפוש",
            str(
                Path(app_root) /
                "index"
            ),
        )
    )

    backup_root = normalize_path(
        ask(
            "תיקיית גיבויים",
            str(
                Path(app_root) /
                "backups"
            ),
        )
    )

    logs_root = normalize_path(
        ask(
            "תיקיית לוגים",
            str(
                Path(app_root) /
                "logs"
            ),
        )
    )

    # ========================================================================
    # 3. POSTGRESQL
    # ========================================================================

    print()
    print("--- PostgreSQL ---")
    print()

    print(
        "PostgreSQL אמור לרוץ על שרת המשרד."
    )

    pg_host = ask(
        "PostgreSQL host",
        "127.0.0.1",
    )

    pg_port = ask_int(
        "PostgreSQL port",
        DEFAULT_POSTGRES_PORT,
    )

    pg_database = ask(
        "שם בסיס הנתונים",
        "alcalay",
    )

    pg_user = ask(
        "משתמש PostgreSQL",
        "alcalay",
    )

    print()
    print(
        "סיסמת PostgreSQL לא תישמר בקובץ התצורה."
    )
    print(
        "היא תוגדר באמצעות:"
    )
    print(
        "ALCALAY_POSTGRES_PASSWORD"
    )

    # ========================================================================
    # 4. GOOGLE DRIVE
    # ========================================================================

    print()
    print("--- Google Drive ---")
    print()

    drive_enabled = ask_yes_no(
        "האם Google Drive יהיה מקור נתונים?",
        True,
    )

    drive_root = ""
    drive_sync_mode = "disabled"

    if drive_enabled:

        drive_root = ask(
            "Google Drive root / folder ID / path",
            "",
        )

        drive_sync_mode = (
            "configured_source"
        )

    # ========================================================================
    # 5. GMAIL
    # ========================================================================

    print()
    print("--- Gmail ---")
    print()

    print(
        "בשלב הראשון מוגדר חשבון Gmail אחד בלבד."
    )

    print(
        "בעתיד ניתן יהיה להוסיף חשבונות Gmail נוספים."
    )

    print()
    print("מדיניות Gmail:")
    print(
        "  1. לא מסנכרנים את כל תיבת הדואר."
    )
    print(
        "  2. מסנכרנים רק Labels שתבחר."
    )
    print(
        "  3. רשימת ה-Labels מתחילה ריקה."
    )
    print(
        "  4. ניתן יהיה להוריד Attachments לשרת."
    )
    print(
        "  5. הסנכרון יהיה Incremental."
    )
    print(
        "  6. יישמר Gmail History ID."
    )

    gmail_enabled = ask_yes_no(
        "האם להפעיל Gmail כמקור נתונים?",
        True,
    )

    gmail_accounts = []

    if gmail_enabled:

        print()

        gmail_address = ask(
            "כתובת Gmail הראשונה",
            "",
            required=True,
        )

        gmail_accounts.append(
            {
                "account_id": "gmail_001",

                "email": gmail_address,

                "enabled": True,

                # IMPORTANT:
                # The list remains empty during setup.
                # Labels will be selected later through the Gmail
                # connection/configuration component.
                "selected_labels": [],

                "sync_mode": (
                    "selected_labels_only"
                ),

                # Incremental synchronization state.
                "last_successful_refresh_at": None,

                "last_history_id": None,

                "last_sync_status": (
                    "not_started"
                ),

                "last_sync_error": None,
            }
        )

    # ========================================================================
    # 6. DOCUMENT PROCESSING
    # ========================================================================

    print()
    print("--- OCR / AI / ML ---")
    print()

    ocr_enabled = ask_yes_no(
        "להפעיל OCR?",
        True,
    )

    ai_enabled = ask_yes_no(
        "להפעיל AI להבנת תוכן?",
        True,
    )

    ml_enabled = ask_yes_no(
        "להפעיל ML לסיווג והבנת תוכן?",
        True,
    )

    # ========================================================================
    # 7. SECURITY
    # ========================================================================

    print()
    print("--- אבטחה ---")
    print()

    authentication_enabled = ask_yes_no(
        "להפעיל אימות משתמשים?",
        True,
    )

    # ========================================================================
    # 8. CREATE DIRECTORIES
    # ========================================================================

    print()
    print("--- יצירת תיקיות ---")
    print()

    folders = [

        app_root,

        documents_root,

        index_root,

        backup_root,

        logs_root,

        str(
            Path(app_root) /
            "config"
        ),

        str(
            Path(app_root) /
            "data"
        ),

        str(
            Path(app_root) /
            "runtime"
        ),
    ]

    for folder in folders:

        create_directory(folder)

    config_dir = (
        Path(app_root) /
        "config"
    )

    # ========================================================================
    # 9. CONFIGURATION
    # ========================================================================

    config = {

        "application": {

            "name": APP_NAME,

            "config_version": (
                CONFIG_VERSION
            ),

            "created_at": now_iso(),

            "setup_phase": True,

            "runtime_phase_ready": False,
        },

        "server": {

            "name": server_name,

            "os": server_os,

            "host": server_host,

            "port": server_port,

            "protocol": "https",
        },

        "paths": {

            "app_root": app_root,

            "documents_root": (
                documents_root
            ),

            "index_root": (
                index_root
            ),

            "backup_root": (
                backup_root
            ),

            "logs_root": (
                logs_root
            ),
        },

        "postgresql": {

            "host": pg_host,

            "port": pg_port,

            "database": pg_database,

            "user": pg_user,

            "password_env": (
                "ALCALAY_POSTGRES_PASSWORD"
            ),
        },

        "sources": {

            "local_server": {

                "enabled": True,

                "root": documents_root,

                "sync_mode": (
                    "configured_folders"
                ),
            },

            "google_drive": {

                "enabled": (
                    drive_enabled
                ),

                "root": drive_root,

                "sync_mode": (
                    drive_sync_mode
                ),
            },

            "gmail": {

                "enabled": (
                    gmail_enabled
                ),

                "global_policy": {

                    # CRITICAL:
                    # Never synchronize the entire mailbox.
                    "sync_entire_mailbox": False,

                    "sync_selected_labels_only": True,

                    # Email processing.
                    "index_email_body": True,

                    "download_attachments": True,

                    "index_attachments": True,

                    # Incremental synchronization.
                    "incremental_sync": True,

                    "use_history_id": True,

                    # Deduplication.
                    "deduplicate_by_message_id": True,

                    "deduplicate_by_content_hash": True,

                    # Full synchronization is an explicit
                    # administrative operation only.
                    "allow_manual_full_sync": True,

                    "full_sync_requires_explicit_action": True,
                },

                "accounts": (
                    gmail_accounts
                ),
            },
        },

        "processing": {

            "ocr_enabled": (
                ocr_enabled
            ),

            "ai_enabled": (
                ai_enabled
            ),

            "ml_enabled": (
                ml_enabled
            ),

            "extract_text": True,

            "extract_metadata": True,

            "classify_documents": True,

            "extract_keywords": True,

            "thesaurus_enabled": True,

            "semantic_search_enabled": True,

            "index_new_content": True,

            "reprocess_changed_content": True,
        },

        "security": {

            "authentication_enabled": (
                authentication_enabled
            ),

            "api_secret_env": (
                "ALCALAY_API_SECRET"
            ),

            "tls_required": True,

            "secrets_in_config": False,
        },

        "sync": {

            "incremental_sync": True,

            "deduplicate_by_source_id": True,

            "deduplicate_by_hash": True,

            "store_sync_state_in_postgresql": True,
        },

        "git_policy": {

            "commit_setup_code": True,

            "commit_config_template": True,

            "commit_real_data": False,

            "commit_documents": False,

            "commit_database": False,

            "commit_secrets": False,

            "commit_oauth_tokens": False,

            "commit_search_indexes": False,
        },
    }

    # ========================================================================
    # 10. WRITE CONFIGURATION
    # ========================================================================

    config_path = (
        config_dir /
        "alcalay_config.json"
    )

    env_example_path = (
        config_dir /
        ".env.example"
    )

    config_path.write_text(
        json.dumps(
            config,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    env_example = """# Alcalay environment variables
# DO NOT commit the real .env file to Git.

ALCALAY_POSTGRES_PASSWORD=
ALCALAY_API_SECRET=

# Gmail OAuth credentials will be configured by
# the Gmail integration/runtime component.
"""

    env_example_path.write_text(
        env_example,
        encoding="utf-8",
    )

    # ========================================================================
    # 11. SUMMARY
    # ========================================================================

    print()
    print("=" * 78)
    print(
        "ההקמה הראשונית של Alcalay הסתיימה בהצלחה"
    )
    print("=" * 78)

    print()
    print(
        f"שרת:                  {server_os}"
    )

    print(
        f"שם שרת:               {server_name}"
    )

    print(
        f"API:                   "
        f"{server_host}:{server_port}"
    )

    print(
        f"Alcalay root:          "
        f"{app_root}"
    )

    print(
        f"מסמכים:                "
        f"{documents_root}"
    )

    print(
        f"אינדקס:                "
        f"{index_root}"
    )

    print(
        f"גיבויים:               "
        f"{backup_root}"
    )

    print(
        f"PostgreSQL:             "
        f"{pg_host}:{pg_port}/{pg_database}"
    )

    print(
        f"Google Drive:           "
        f"{'מופעל' if drive_enabled else 'כבוי'}"
    )

    print(
        f"Gmail:                  "
        f"{'מופעל' if gmail_enabled else 'כבוי'}"
    )

    if gmail_enabled:

        account = gmail_accounts[0]

        print()

        print(
            f"חשבון Gmail ראשון:     "
            f"{account['email']}"
        )

        print(
            "סנכרון Gmail:          "
            "Labels נבחרים בלבד"
        )

        print(
            "כל תיבת Gmail:         לא"
        )

        print(
            "גוף הודעה:             כן"
        )

        print(
            "Attachments:            כן"
        )

        print(
            "Incremental sync:      כן"
        )

        print(
            "Gmail History ID:      כן"
        )

    print()

    print(
        "קובץ תצורה:"
    )

    print(
        config_path
    )

    print()

    print(
        "קובץ משתני סביבה לדוגמה:"
    )

    print(
        env_example_path
    )

    print()
    print("--- השלבים הבאים ---")
    print()

    print(
        "1. התקנת PostgreSQL."
    )

    print(
        "2. יצירת בסיס הנתונים והמשתמש."
    )

    print(
        "3. הגדרת ALCALAY_POSTGRES_PASSWORD."
    )

    print(
        "4. הגדרת ALCALAY_API_SECRET."
    )

    print(
        "5. חיבור OAuth ל-Gmail."
    )

    print(
        "6. הצגת Labels של החשבון."
    )

    print(
        "7. בחירת ה-Labels שיסונכרנו."
    )

    print(
        "8. הקמת מנגנון הסנכרון והאינדקס."
    )

    print()

    print(
        "אין להכניס סיסמאות, OAuth tokens, "
        "מסמכים, DB או אינדקסים ל-Git."
    )


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    main()