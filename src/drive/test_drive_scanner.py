# -*- coding: utf-8 -*-

"""
Alcalay - Google Drive Scanner Test
===================================

Read-only test of recursive scanning of the
Alcalay Documents folder.

This test does NOT:
    - Download files.
    - Upload files.
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
from src.drive.drive_repository import DriveRepository
from src.drive.drive_scanner import DriveScanner


def main() -> int:

    print()
    print("=" * 72)
    print("ALCALAY - GOOGLE DRIVE DOCUMENTS SCANNER TEST")
    print("=" * 72)
    print()

    try:

        print("[1/4] Connecting to Google Drive...")
        print()

        connection = DriveConnection()

        email = connection.connect()

        print(
            f"[OK] Connected account: {email}"
        )
        print()

        print("[2/4] Loading Alcalay repository...")
        print()

        repository = DriveRepository(
            connection
        )

        print("[OK] Repository loaded.")
        print()

        print("[3/4] Creating Drive scanner...")
        print()

        scanner = DriveScanner(
            connection,
            repository,
        )

        print("[OK] Scanner created.")
        print()

        print(
            "[4/4] Scanning Documents recursively..."
        )
        print()

        items = scanner.scan_documents(
            recursive=True
        )

        folders = [
            item
            for item in items
            if item.is_folder
        ]

        files = [
            item
            for item in items
            if not item.is_folder
        ]

        print(
            f"[OK] Total items: {len(items)}"
        )

        print(
            f"[OK] Folders:     {len(folders)}"
        )

        print(
            f"[OK] Files:       {len(files)}"
        )

        print()

        if items:

            print("-" * 72)
            print("DOCUMENTS CONTENT")
            print("-" * 72)
            print()

            for index, item in enumerate(
                items,
                start=1,
            ):

                item_type = (
                    "FOLDER"
                    if item.is_folder
                    else "FILE"
                )

                size = (
                    str(item.size)
                    if item.size is not None
                    else "-"
                )

                modified = (
                    item.modified_time
                    if item.modified_time
                    else "-"
                )

                print(
                    f"{index}. [{item_type}] "
                    f"{item.name}"
                )

                print(
                    f"   ID:       {item.file_id}"
                )

                print(
                    f"   MIME:     {item.mime_type}"
                )

                print(
                    f"   Size:     {size}"
                )

                print(
                    f"   Modified: {modified}"
                )

                print()

        else:

            print(
                "[INFO] Documents folder is currently empty."
            )

            print()

        print("=" * 72)
        print("RESULT: Drive Documents scan completed.")
        print("=" * 72)
        print()

        return 0

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