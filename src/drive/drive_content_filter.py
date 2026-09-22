# -*- coding: utf-8 -*-

"""
Alcalay - Google Drive Content Keyword Filter
==============================================

Searches the indexed content of Google Drive files for the
configured Alcalay keyword rules.

Workflow:

    PostgreSQL drive_files
            |
            v
    Files registered in repository "alcalay"
            |
            v
    Skip files already marked relevant
            |
            v
    Google Drive fullText search
            |
            v
    Match Google Drive file IDs against PostgreSQL
            |
            v
    drive_file_keyword_matches
            |
            v
    drive_files.is_relevant = TRUE

Important:

    - No file download.
    - No Google Drive export.
    - No Google Drive write.
    - No duplicate detection.
    - No version selection.
    - Content keyword detection only.

Filename/path filtering is performed by:
    src/drive/drive_keyword_filter.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ============================================================================
# PROJECT ROOT
# ============================================================================

CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# DATABASE
# ============================================================================

def create_database_connection():
    from src.database.connection import DatabaseConnection

    database = DatabaseConnection()

    return database.connect()


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass(frozen=True)
class KeywordRule:
    id: int
    keyword: str
    enabled: bool
    case_sensitive: bool
    search_filename: bool
    search_description: bool
    search_path: bool
    search_metadata: bool


@dataclass(frozen=True)
class DriveFileRecord:
    id: int
    drive_file_id: str
    name: str
    mime_type: str
    is_relevant: bool | None


# ============================================================================
# CONTENT FILTER
# ============================================================================

class DriveContentKeywordFilter:

    REPOSITORY_KEY = "alcalay"

    PAGE_SIZE = 1000

    FILE_FIELDS = (
        "nextPageToken,"
        "files("
        "id,"
        "name,"
        "mimeType,"
        "modifiedTime,"
        "trashed"
        ")"
    )

    def __init__(self, connection) -> None:

        self.connection = connection
        self.service = connection.service

        if self.service is None:
            raise RuntimeError(
                "Google Drive עדיין לא מחובר."
            )

    # ========================================================================
    # POSTGRESQL
    # ========================================================================

    def _get_repository_id(self, cursor) -> int:

        cursor.execute(
            """
            SELECT id
            FROM drive_repositories
            WHERE repository_key = %s
            """,
            (self.REPOSITORY_KEY,),
        )

        row = cursor.fetchone()

        if row is None:
            raise RuntimeError(
                "לא נמצא repository בשם "
                f"'{self.REPOSITORY_KEY}' ב-drive_repositories."
            )

        return int(row[0])

    def _get_enabled_rule_set(
        self,
        cursor,
    ) -> tuple[int, str]:

        cursor.execute(
            """
            SELECT id, name
            FROM drive_keyword_rule_sets
            WHERE enabled = TRUE
            ORDER BY id
            LIMIT 1
            """
        )

        row = cursor.fetchone()

        if row is None:
            raise RuntimeError(
                "לא נמצא enabled keyword rule set."
            )

        return int(row[0]), str(row[1])

    def _load_keyword_rules(
        self,
        cursor,
        rule_set_id: int,
    ) -> list[KeywordRule]:

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
              AND enabled = TRUE
            ORDER BY id
            """,
            (rule_set_id,),
        )

        rules: list[KeywordRule] = []

        for row in cursor.fetchall():

            rules.append(
                KeywordRule(
                    id=int(row[0]),
                    keyword=str(row[1]),
                    enabled=bool(row[2]),
                    case_sensitive=bool(row[3]),
                    search_filename=bool(row[4]),
                    search_description=bool(row[5]),
                    search_path=bool(row[6]),
                    search_metadata=bool(row[7]),
                )
            )

        return rules

    def _load_candidate_files(
        self,
        cursor,
        repository_id: int,
    ) -> list[DriveFileRecord]:

        cursor.execute(
            """
            SELECT
                id,
                drive_file_id,
                name,
                mime_type,
                is_relevant
            FROM drive_files
            WHERE repository_id = %s
              AND is_trashed = FALSE
              AND is_relevant IS DISTINCT FROM TRUE
            ORDER BY id
            """,
            (repository_id,),
        )

        files: list[DriveFileRecord] = []

        for row in cursor.fetchall():

            files.append(
                DriveFileRecord(
                    id=int(row[0]),
                    drive_file_id=str(row[1]),
                    name=str(row[2]),
                    mime_type=str(row[3]),
                    is_relevant=(
                        None
                        if row[4] is None
                        else bool(row[4])
                    ),
                )
            )

        return files

    # ========================================================================
    # GOOGLE DRIVE QUERY
    # ========================================================================

    @staticmethod
    def _escape_drive_query_value(
        value: str,
    ) -> str:

        value = value.replace(
            "\\",
            "\\\\",
        )

        value = value.replace(
            "'",
            "\\'",
        )

        return value

    @classmethod
    def _build_full_text_query(
        cls,
        keyword: str,
    ) -> str:

        keyword = keyword.strip()

        if not keyword:
            raise ValueError(
                "Keyword ריק."
            )

        escaped = cls._escape_drive_query_value(
            keyword
        )

        if " " in keyword:

            return (
                "fullText contains "
                f"'\"{escaped}\"' "
                "and trashed = false"
            )

        return (
            "fullText contains "
            f"'{escaped}' "
            "and trashed = false"
        )

    def _search_google_drive(
        self,
        keyword: str,
    ) -> set[str]:

        query = self._build_full_text_query(
            keyword
        )

        matched_ids: set[str] = set()

        page_token: str | None = None

        while True:

            # IMPORTANT:
            # Do NOT use orderBy together with fullText.
            #
            # Google Drive returns:
            # "Sorting is not supported for queries with fullText terms."

            request = (
                self.service
                .files()
                .list(
                    q=query,
                    spaces="drive",
                    fields=self.FILE_FIELDS,
                    pageSize=self.PAGE_SIZE,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
            )

            response = request.execute()

            files = response.get(
                "files",
                [],
            )

            for metadata in files:

                if not isinstance(
                    metadata,
                    dict,
                ):
                    continue

                file_id = metadata.get(
                    "id"
                )

                if not file_id:
                    continue

                if metadata.get(
                    "trashed",
                    False,
                ):
                    continue

                matched_ids.add(
                    str(file_id)
                )

            page_token = response.get(
                "nextPageToken"
            )

            if not page_token:
                break

        return matched_ids

    # ========================================================================
    # POSTGRESQL UPDATES
    # ========================================================================

    def _insert_content_match(
        self,
        cursor,
        drive_file: DriveFileRecord,
        rule: KeywordRule,
    ) -> bool:

        cursor.execute(
            """
            INSERT INTO drive_file_keyword_matches
            (
                drive_file_id_fk,
                keyword_rule_id,
                matched_text,
                matched_in
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s
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
            RETURNING id
            """,
            (
                drive_file.id,
                rule.id,
                rule.keyword,
                "content",
            ),
        )

        row = cursor.fetchone()

        return row is not None

    def _mark_file_relevant(
        self,
        cursor,
        drive_file: DriveFileRecord,
        keyword: str,
    ) -> None:

        cursor.execute(
            """
            UPDATE drive_files
            SET
                is_relevant = TRUE,
                relevance_reason = %s,
                keyword_checked_at = NOW(),
                last_checked_at = NOW()
            WHERE id = %s
            """,
            (
                f"CONTENT_KEYWORD:{keyword}",
                drive_file.id,
            ),
        )

    def _mark_file_checked_not_relevant(
        self,
        cursor,
        drive_file: DriveFileRecord,
    ) -> None:

        cursor.execute(
            """
            UPDATE drive_files
            SET
                is_relevant = FALSE,
                relevance_reason = COALESCE(
                    relevance_reason,
                    'CONTENT_SEARCH_NO_MATCH'
                ),
                keyword_checked_at = NOW(),
                last_checked_at = NOW()
            WHERE id = %s
              AND is_relevant IS DISTINCT FROM TRUE
            """,
            (
                drive_file.id,
            ),
        )

    # ========================================================================
    # MAIN PROCESSING
    # ========================================================================

    def run(self) -> dict[str, Any]:

        summary: dict[str, Any] = {
            "repository": self.REPOSITORY_KEY,
            "rule_set": "",
            "rules": 0,
            "candidate_files": 0,
            "google_matches": 0,
            "relevant_files": 0,
            "content_matches": 0,
            "not_relevant": 0,
            "errors": 0,
            "errors_detail": [],
        }

        database_connection = create_database_connection()

        try:

            with database_connection.cursor() as cursor:

                repository_id = self._get_repository_id(
                    cursor
                )

                rule_set_id, rule_set_name = (
                    self._get_enabled_rule_set(
                        cursor
                    )
                )

                summary["rule_set"] = rule_set_name

                rules = self._load_keyword_rules(
                    cursor,
                    rule_set_id,
                )

                summary["rules"] = len(rules)

                candidates = self._load_candidate_files(
                    cursor,
                    repository_id,
                )

                summary["candidate_files"] = len(
                    candidates
                )

                if not candidates:

                    database_connection.commit()

                    return summary

                candidate_by_drive_id = {
                    item.drive_file_id: item
                    for item in candidates
                }

                candidate_drive_ids = set(
                    candidate_by_drive_id.keys()
                )

                matched_file_ids_by_keyword: dict[
                    int,
                    set[str],
                ] = {}

                for rule in rules:

                    try:

                        print(
                            "[CONTENT SEARCH] "
                            f"{rule.keyword}"
                        )

                        google_ids = (
                            self._search_google_drive(
                                rule.keyword
                            )
                        )

                        matched_file_ids_by_keyword[
                            rule.id
                        ] = google_ids

                        relevant_ids = (
                            google_ids
                            & candidate_drive_ids
                        )

                        print(
                            "[CONTENT RESULT] "
                            f"{rule.keyword}: "
                            f"{len(google_ids)} Google matches, "
                            f"{len(relevant_ids)} Alcalay candidates"
                        )

                        summary[
                            "google_matches"
                        ] += len(relevant_ids)

                        for drive_id in relevant_ids:

                            drive_file = (
                                candidate_by_drive_id[
                                    drive_id
                                ]
                            )

                            self._insert_content_match(
                                cursor,
                                drive_file,
                                rule,
                            )

                            self._mark_file_relevant(
                                cursor,
                                drive_file,
                                rule.keyword,
                            )

                            summary[
                                "content_matches"
                            ] += 1

                    except Exception as exc:

                        summary[
                            "errors"
                        ] += 1

                        detail = (
                            f"keyword={rule.keyword}: "
                            f"{type(exc).__name__}: {exc}"
                        )

                        summary[
                            "errors_detail"
                        ].append(
                            detail
                        )

                        print(
                            "[ERROR] "
                            f"{detail}"
                        )

                # ------------------------------------------------------------
                # Determine files with no content match.
                # ------------------------------------------------------------

                relevant_drive_ids: set[str] = set()

                for rule in rules:

                    google_ids = (
                        matched_file_ids_by_keyword.get(
                            rule.id,
                            set(),
                        )
                    )

                    relevant_drive_ids.update(
                        google_ids
                        & candidate_drive_ids
                    )

                for drive_file in candidates:

                    if (
                        drive_file.drive_file_id
                        in relevant_drive_ids
                    ):
                        continue

                    self._mark_file_checked_not_relevant(
                        cursor,
                        drive_file,
                    )

                    summary[
                        "not_relevant"
                    ] += 1

                database_connection.commit()

                summary[
                    "relevant_files"
                ] = len(
                    relevant_drive_ids
                )

                return summary

        except Exception:

            database_connection.rollback()

            raise

        finally:

            database_connection.close()

    # ========================================================================
    # SUMMARY
    # ========================================================================

    @staticmethod
    def print_summary(
        summary: dict[str, Any],
    ) -> None:

        print()
        print("=" * 72)
        print(
            "GOOGLE DRIVE CONTENT KEYWORD FILTER COMPLETED"
        )
        print("=" * 72)

        print(
            f"[REPOSITORY]       "
            f"{summary.get('repository', '')}"
        )

        print(
            f"[RULE SET]         "
            f"{summary.get('rule_set', '')}"
        )

        print(
            f"[RULES]            "
            f"{summary.get('rules', 0)}"
        )

        print(
            f"[CANDIDATES]       "
            f"{summary.get('candidate_files', 0)}"
        )

        print(
            f"[GOOGLE MATCHES]   "
            f"{summary.get('google_matches', 0)}"
        )

        print(
            f"[RELEVANT FILES]   "
            f"{summary.get('relevant_files', 0)}"
        )

        print(
            f"[CONTENT MATCHES]  "
            f"{summary.get('content_matches', 0)}"
        )

        print(
            f"[NOT RELEVANT]     "
            f"{summary.get('not_relevant', 0)}"
        )

        print(
            f"[ERRORS]           "
            f"{summary.get('errors', 0)}"
        )

        print(
            "[DOWNLOAD]         NO"
        )

        print(
            "[DRIVE WRITE]      NO"
        )

        print("=" * 72)

        errors_detail = summary.get(
            "errors_detail",
            [],
        )

        if errors_detail:

            print()
            print(
                "ERROR DETAILS"
            )
            print("-" * 72)

            for detail in errors_detail:

                print(
                    f"[ERROR] {detail}"
                )


# ============================================================================
# CLI
# ============================================================================

def main() -> int:

    print()
    print("=" * 72)
    print(
        "STARTING GOOGLE DRIVE CONTENT KEYWORD FILTER"
    )
    print("=" * 72)

    try:

        from src.drive.drive_connection import (
            DriveConnection,
        )

        connection = DriveConnection(
            "frank.avner@gmail.com"
        )

        email = connection.connect()

        print(
            f"[GOOGLE ACCOUNT] {email}"
        )

        print(
            "[SEARCH]         Google Drive fullText"
        )

        print(
            "[DOWNLOAD]       NO"
        )

        print(
            "[DRIVE WRITE]    NO"
        )

        print()

        content_filter = (
            DriveContentKeywordFilter(
                connection
            )
        )

        summary = content_filter.run()

        content_filter.print_summary(
            summary
        )

        if summary.get(
            "errors",
            0,
        ):
            return 1

        return 0

    except Exception as exc:

        print()
        print(
            "GOOGLE DRIVE CONTENT KEYWORD FILTER FAILED"
        )

        print(
            f"[ERROR] {type(exc).__name__}: {exc}"
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )