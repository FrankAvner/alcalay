# -*- coding: utf-8 -*-

"""
Alcalay - Google Drive Keyword Filter
=====================================

Phase 1:
    Metadata keyword filtering based on:

        1. File name
        2. Full Google Drive folder path

This module does NOT:

    - Download files
    - Export Google Workspace files
    - Modify Google Drive
    - Delete files
    - Move files
    - Rename files
    - Perform duplicate detection
    - Search inside document contents

Content search will be added as a separate phase.

Database tables used:

    drive_repositories
    drive_keyword_rule_sets
    drive_keyword_rules
    drive_folders
    drive_files
    drive_file_keyword_matches
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import psycopg


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass(frozen=True)
class KeywordRule:
    """
    One active keyword rule loaded from PostgreSQL.
    """

    id: int
    keyword: str
    enabled: bool
    case_sensitive: bool
    search_filename: bool
    search_description: bool
    search_path: bool
    search_metadata: bool


@dataclass
class DriveFileRecord:
    """
    Drive file information required by the metadata filter.
    """

    id: int
    repository_id: int
    drive_file_id: str
    parent_drive_file_id: Optional[str]
    name: str
    mime_type: str
    is_trashed: bool


class DriveKeywordFilter:
    """
    Metadata-only keyword filtering engine.

    Current search locations:

        1. File name
        2. Full Drive folder path

    The database already contains flags for:

        search_filename
        search_description
        search_path
        search_metadata

    However, drive_files currently has no description or general
    metadata columns, so Phase 1 searches only filename and path.

    Content search will be implemented separately.
    """

    DEFAULT_RULE_SET_NAME = "default"

    MATCHED_IN_FILENAME = "filename"
    MATCHED_IN_PATH = "path"

    def __init__(
        self,
        connection: psycopg.Connection,
        repository_key: str = "alcalay",
        rule_set_name: str = DEFAULT_RULE_SET_NAME,
    ):
        self.connection = connection
        self.repository_key = repository_key
        self.rule_set_name = rule_set_name

        self.repository_id: Optional[int] = None
        self.rule_set_id: Optional[int] = None

        self.rules: list[KeywordRule] = []

        self.folder_cache: dict[str, str] = {}
        self.folder_parent_cache: dict[
            str,
            Optional[str],
        ] = {}

    # ------------------------------------------------------------------
    # INITIALIZATION
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """
        Load repository, rule set and active keyword rules.
        """

        self.repository_id = self._load_repository_id()
        self.rule_set_id = self._load_rule_set_id()
        self.rules = self._load_keyword_rules()

        if not self.rules:
            raise RuntimeError(
                f"No enabled keyword rules found in rule set "
                f"'{self.rule_set_name}'."
            )

    def _load_repository_id(self) -> int:
        """
        Load repository ID from drive_repositories.
        """

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM drive_repositories
                WHERE repository_key = %s
                LIMIT 1
                """,
                (self.repository_key,),
            )

            row = cursor.fetchone()

        if row is None:
            raise RuntimeError(
                f"Drive repository '{self.repository_key}' "
                f"was not found."
            )

        return int(row[0])

    def _load_rule_set_id(self) -> int:
        """
        Load enabled keyword rule set.
        """

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM drive_keyword_rule_sets
                WHERE name = %s
                  AND enabled = true
                ORDER BY id
                LIMIT 1
                """,
                (self.rule_set_name,),
            )

            row = cursor.fetchone()

        if row is None:
            raise RuntimeError(
                f"Enabled keyword rule set "
                f"'{self.rule_set_name}' was not found."
            )

        return int(row[0])

    def _load_keyword_rules(self) -> list[KeywordRule]:
        """
        Load all enabled keyword rules belonging to the selected
        rule set.
        """

        if self.rule_set_id is None:
            raise RuntimeError(
                "Rule set has not been initialized."
            )

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    keyword,
                    enabled,
                    case_sensitive,
                    search_filename,
                    search_description,
                    search_path,
                    search_metadata
                FROM drive_keyword_rules
                WHERE rule_set_id = %s
                  AND enabled = true
                ORDER BY id
                """,
                (self.rule_set_id,),
            )

            rows = cursor.fetchall()

        rules: list[KeywordRule] = []

        for row in rows:
            keyword = str(row[1] or "").strip()

            if not keyword:
                continue

            rules.append(
                KeywordRule(
                    id=int(row[0]),
                    keyword=keyword,
                    enabled=bool(row[2]),
                    case_sensitive=bool(row[3]),
                    search_filename=bool(row[4]),
                    search_description=bool(row[5]),
                    search_path=bool(row[6]),
                    search_metadata=bool(row[7]),
                )
            )

        return rules

    # ------------------------------------------------------------------
    # FOLDER CACHE
    # ------------------------------------------------------------------

    def _load_folder_cache(self) -> None:
        """
        Load the complete folder hierarchy into memory.
        """

        if self.repository_id is None:
            raise RuntimeError(
                "Repository has not been initialized."
            )

        self.folder_cache.clear()
        self.folder_parent_cache.clear()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    drive_file_id,
                    parent_drive_file_id,
                    name
                FROM drive_folders
                WHERE repository_id = %s
                  AND COALESCE(trashed, false) = false
                """,
                (self.repository_id,),
            )

            rows = cursor.fetchall()

        for row in rows:
            drive_file_id = str(row[0])

            parent_drive_file_id = (
                str(row[1])
                if row[1] is not None
                else None
            )

            name = str(row[2] or "")

            self.folder_cache[drive_file_id] = name

            self.folder_parent_cache[
                drive_file_id
            ] = parent_drive_file_id

    def _build_folder_path(
        self,
        parent_drive_file_id: Optional[str],
    ) -> str:
        """
        Build the complete Drive folder path.

        Example:

            Alcalay / Documents

        or:

            Alcalay / Gmail / frank.avner@gmail.com / messages
        """

        if not parent_drive_file_id:
            return ""

        parts: list[str] = []

        current_id: Optional[str] = (
            parent_drive_file_id
        )

        visited: set[str] = set()

        max_depth = 100

        while current_id and len(parts) < max_depth:

            if current_id in visited:
                break

            visited.add(current_id)

            folder_name = self.folder_cache.get(
                current_id
            )

            if folder_name:
                parts.append(folder_name)

            current_id = self.folder_parent_cache.get(
                current_id
            )

        parts.reverse()

        return " / ".join(parts)

    # ------------------------------------------------------------------
    # FILE LOADING
    # ------------------------------------------------------------------

    def _load_files(self) -> list[DriveFileRecord]:
        """
        Load all non-trashed files belonging to the repository.
        """

        if self.repository_id is None:
            raise RuntimeError(
                "Repository has not been initialized."
            )

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    repository_id,
                    drive_file_id,
                    parent_drive_file_id,
                    name,
                    mime_type,
                    is_trashed
                FROM drive_files
                WHERE repository_id = %s
                  AND is_trashed = false
                ORDER BY id
                """,
                (self.repository_id,),
            )

            rows = cursor.fetchall()

        files: list[DriveFileRecord] = []

        for row in rows:
            files.append(
                DriveFileRecord(
                    id=int(row[0]),
                    repository_id=int(row[1]),
                    drive_file_id=str(row[2]),
                    parent_drive_file_id=(
                        str(row[3])
                        if row[3] is not None
                        else None
                    ),
                    name=str(row[4] or ""),
                    mime_type=str(row[5] or ""),
                    is_trashed=bool(row[6]),
                )
            )

        return files

    # ------------------------------------------------------------------
    # KEYWORD MATCHING
    # ------------------------------------------------------------------

    @staticmethod
    def _contains_keyword(
        value: str,
        keyword: str,
        case_sensitive: bool,
    ) -> bool:
        """
        Check whether keyword exists inside value.

        Hebrew keywords are supported.
        Case-insensitive matching uses Unicode casefold().
        """

        if not value or not keyword:
            return False

        if case_sensitive:
            return keyword in value

        return keyword.casefold() in value.casefold()

    def _match_file(
        self,
        file_record: DriveFileRecord,
        folder_path: str,
    ) -> list[tuple[KeywordRule, str, str]]:
        """
        Find all keyword matches for one file.

        Returns:

            (rule, matched_text, matched_in)

        matched_in:

            filename
            path
        """

        matches: list[
            tuple[KeywordRule, str, str]
        ] = []

        for rule in self.rules:

            if not rule.enabled:
                continue

            # ----------------------------------------------------------
            # FILE NAME
            # ----------------------------------------------------------

            if rule.search_filename:

                if self._contains_keyword(
                    file_record.name,
                    rule.keyword,
                    rule.case_sensitive,
                ):
                    matches.append(
                        (
                            rule,
                            file_record.name,
                            self.MATCHED_IN_FILENAME,
                        )
                    )

            # ----------------------------------------------------------
            # DRIVE PATH
            # ----------------------------------------------------------

            if rule.search_path and folder_path:

                if self._contains_keyword(
                    folder_path,
                    rule.keyword,
                    rule.case_sensitive,
                ):
                    matches.append(
                        (
                            rule,
                            folder_path,
                            self.MATCHED_IN_PATH,
                        )
                    )

        return matches

    # ------------------------------------------------------------------
    # DATABASE CLEANUP
    # ------------------------------------------------------------------

    def _clear_previous_matches(self) -> None:
        """
        Remove previous keyword matches for this repository.

        This makes the operation repeatable.

        Only matches belonging to files in the current repository
        are removed.
        """

        if self.repository_id is None:
            raise RuntimeError(
                "Repository has not been initialized."
            )

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM drive_file_keyword_matches
                WHERE drive_file_id_fk IN (
                    SELECT id
                    FROM drive_files
                    WHERE repository_id = %s
                )
                """,
                (self.repository_id,),
            )

    def _reset_file_keyword_state(self) -> None:
        """
        Reset previous keyword evaluation state.
        """

        if self.repository_id is None:
            raise RuntimeError(
                "Repository has not been initialized."
            )

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE drive_files
                SET
                    is_relevant = false,
                    relevance_reason = NULL,
                    keyword_checked_at = NULL
                WHERE repository_id = %s
                  AND is_trashed = false
                """,
                (self.repository_id,),
            )

    # ------------------------------------------------------------------
    # DATABASE MATCH INSERT
    # ------------------------------------------------------------------

    def _insert_match(
        self,
        file_record: DriveFileRecord,
        rule: KeywordRule,
        matched_text: str,
        matched_in: str,
    ) -> None:
        """
        Insert one keyword match.
        """

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO drive_file_keyword_matches
                (
                    drive_file_id_fk,
                    keyword_rule_id,
                    matched_text,
                    matched_in,
                    matched_at
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    NOW()
                )
                ON CONFLICT
                    (
                        drive_file_id_fk,
                        keyword_rule_id
                    )
                DO UPDATE SET
                    matched_text = EXCLUDED.matched_text,
                    matched_in = EXCLUDED.matched_in,
                    matched_at = NOW()
                """,
                (
                    file_record.id,
                    rule.id,
                    matched_text,
                    matched_in,
                ),
            )

    # ------------------------------------------------------------------
    # FILE RESULT UPDATE
    # ------------------------------------------------------------------

    def _update_file_result(
        self,
        file_record: DriveFileRecord,
        matches: list[
            tuple[KeywordRule, str, str]
        ],
    ) -> None:
        """
        Update drive_files with the keyword result.
        """

        checked_at = datetime.now(
            timezone.utc
        )

        if matches:

            keyword_names: list[str] = []
            locations: list[str] = []

            for (
                rule,
                _matched_text,
                matched_in,
            ) in matches:

                if rule.keyword not in keyword_names:
                    keyword_names.append(
                        rule.keyword
                    )

                if matched_in not in locations:
                    locations.append(
                        matched_in
                    )

            reason = (
                "Keyword match: "
                + ", ".join(keyword_names)
                + " | matched in: "
                + ", ".join(locations)
            )

            is_relevant = True

        else:

            reason = (
                "No enabled keyword matched "
                "file name or Drive path."
            )

            is_relevant = False

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE drive_files
                SET
                    is_relevant = %s,
                    relevance_reason = %s,
                    keyword_checked_at = %s,
                    last_checked_at = %s,
                    last_error = NULL
                WHERE id = %s
                """,
                (
                    is_relevant,
                    reason,
                    checked_at,
                    checked_at,
                    file_record.id,
                ),
            )

    # ------------------------------------------------------------------
    # RUN
    # ------------------------------------------------------------------

    def run(self) -> dict[str, int]:
        """
        Run the complete metadata keyword filter.
        """

        self.initialize()

        self._load_folder_cache()

        files = self._load_files()

        summary = {
            "files": len(files),
            "relevant": 0,
            "not_relevant": 0,
            "matches": 0,
            "errors": 0,
        }

        print()
        print("=" * 72)
        print(
            "STARTING GOOGLE DRIVE METADATA KEYWORD FILTER"
        )
        print("=" * 72)

        print(
            f"[REPOSITORY] {self.repository_key}"
        )

        print(
            f"[RULE SET]   {self.rule_set_name}"
        )

        print(
            f"[RULES]      {len(self.rules)}"
        )

        print(
            f"[FILES]      {len(files)}"
        )

        print()
        print(
            "[SEARCH]     filename + Drive path"
        )
        print(
            "[DOWNLOAD]   NO"
        )
        print(
            "[DRIVE WRITE] NO"
        )
        print()

        try:

            self._clear_previous_matches()

            self._reset_file_keyword_state()

            for index, file_record in enumerate(
                files,
                start=1,
            ):

                folder_path = (
                    self._build_folder_path(
                        file_record.parent_drive_file_id
                    )
                )

                matches = self._match_file(
                    file_record,
                    folder_path,
                )

                try:

                    for (
                        rule,
                        matched_text,
                        matched_in,
                    ) in matches:

                        self._insert_match(
                            file_record,
                            rule,
                            matched_text,
                            matched_in,
                        )

                    self._update_file_result(
                        file_record,
                        matches,
                    )

                    if matches:

                        summary["relevant"] += 1

                        summary["matches"] += (
                            len(matches)
                        )

                        keywords = ", ".join(
                            dict.fromkeys(
                                rule.keyword
                                for (
                                    rule,
                                    _text,
                                    _location,
                                ) in matches
                            )
                        )

                        print(
                            f"[RELEVANT] "
                            f"{index}/{len(files)} "
                            f"{file_record.name}"
                        )

                        print(
                            f"            PATH: "
                            f"{folder_path}"
                        )

                        print(
                            f"            KEYWORDS: "
                            f"{keywords}"
                        )

                    else:

                        summary[
                            "not_relevant"
                        ] += 1

                        print(
                            f"[SKIP] "
                            f"{index}/{len(files)} "
                            f"{file_record.name}"
                        )

                except Exception as exc:

                    summary["errors"] += 1

                    print(
                        f"[ERROR] "
                        f"{index}/{len(files)} "
                        f"{file_record.name}: "
                        f"{exc}"
                    )

                    raise

            self.connection.commit()

        except Exception:

            self.connection.rollback()

            raise

        print()
        print("=" * 72)
        print(
            "GOOGLE DRIVE METADATA KEYWORD FILTER COMPLETED"
        )
        print("=" * 72)

        print(
            f"[FILES]         "
            f"{summary['files']}"
        )

        print(
            f"[RELEVANT]      "
            f"{summary['relevant']}"
        )

        print(
            f"[NOT RELEVANT]  "
            f"{summary['not_relevant']}"
        )

        print(
            f"[MATCHES]       "
            f"{summary['matches']}"
        )

        print(
            f"[ERRORS]        "
            f"{summary['errors']}"
        )

        print("=" * 72)
        print()

        return summary


# ----------------------------------------------------------------------
# DATABASE CONNECTION
# ----------------------------------------------------------------------

def create_database_connection():
    """
    Create PostgreSQL connection using the existing Alcalay
    DatabaseConnection implementation.

    The existing DatabaseConnection reads the password from:

        ALCALAY_DB_PASSWORD
    """

    from src.database.connection import DatabaseConnection

    database = DatabaseConnection()

    return database.connect()


# ----------------------------------------------------------------------
# COMMAND LINE
# ----------------------------------------------------------------------

def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Alcalay Google Drive metadata keyword filter"
        )
    )

    parser.add_argument(
        "--repository",
        default="alcalay",
        help=(
            "Drive repository key. "
            "Default: alcalay"
        ),
    )

    parser.add_argument(
        "--rule-set",
        default="default",
        help=(
            "Keyword rule set name. "
            "Default: default"
        ),
    )

    return parser.parse_args()


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------

def main() -> int:
    """
    Command-line entry point.
    """

    args = parse_arguments()

    connection = None

    try:

        connection = create_database_connection()

        keyword_filter = DriveKeywordFilter(
            connection=connection,
            repository_key=args.repository,
            rule_set_name=args.rule_set,
        )

        keyword_filter.run()

        return 0

    except KeyboardInterrupt:

        print()
        print(
            "[STOPPED] User interrupted the operation."
        )

        return 130

    except Exception as exc:

        print()
        print("=" * 72)
        print(
            "GOOGLE DRIVE METADATA KEYWORD FILTER FAILED"
        )
        print("=" * 72)
        print(
            f"[ERROR] {exc}"
        )
        print("=" * 72)

        return 1

    finally:

        if connection is not None:
            connection.close()


if __name__ == "__main__":
    sys.exit(main())