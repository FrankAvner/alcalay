# -*- coding: utf-8 -*-

"""
Alcalay - Google Drive Connection Test
======================================

Read-only verification of the Alcalay Google Drive repository.

This test:
    - Connects to Google Drive.
    - Performs OAuth if required.
    - Identifies the connected Google account.
    - Verifies the five configured Alcalay folders.

This test does NOT:
    - Upload files.
    - Download files.
    - Delete files.
    - Move files.
    - Rename files.
    - Modify PostgreSQL.
"""

from __future__ import annotations

import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.drive.drive_connection import DriveConnection


def main() -> int:

    print()
    print("=" * 72)
    print("ALCALAY - GOOGLE DRIVE CONNECTION TEST")
    print("=" * 72)
    print()

    try:

        connection = DriveConnection()

        print("[1/2] Connecting to Google Drive...")
        print()

        email = connection.connect()

        print(f"[OK] Connected account: {email}")
        print()

        print("[2/2] Verifying Alcalay repository folders...")
        print()

        results = connection.verify_alcalay_repository()

        all_ok = True

        for folder_name, metadata in results.items():

            folder_id = metadata.get("id", "")
            actual_name = metadata.get("name", "")
            mime_type = metadata.get("mimeType", "")
            trashed = metadata.get("trashed", False)

            if trashed:
                all_ok = False

            print(
                f"[{'OK' if not trashed else 'ERROR'}] "
                f"{folder_name}"
            )

            print(
                f"     Name:      {actual_name}"
            )

            print(
                f"     ID:        {folder_id}"
            )

            print(
                f"     MIME type: {mime_type}"
            )

            print(
                f"     Trashed:   {trashed}"
            )

            print()

        print("=" * 72)

        if all_ok:

            print("RESULT: Google Drive connection is OK.")
            print("RESULT: Alcalay repository is accessible.")
            print()

            return 0

        print(
            "RESULT: One or more configured folders "
            "are not accessible."
        )
        print()

        return 1

    except Exception as exc:

        print()
        print("=" * 72)
        print("ERROR")
        print("=" * 72)
        print()
        print(str(exc))
        print()

        return 1


if __name__ == "__main__":
    raise SystemExit(main())