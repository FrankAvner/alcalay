# -*- coding: utf-8 -*-

"""
Alcalay - Gmail Indexer
=======================

INDEX phase for Gmail messages.

Architecture:

    Gmail
      |
      v
    COPY
      |
      v
    message.eml
      |
      v
    PARSE
      |
      v
    gmail_parsed_messages
      |
      v
    INDEX
      |
      v
    gmail_search_index
      |
      v
    Future unified search / AI / ML

Important:

    - This module DOES NOT connect to Gmail.
    - This module DOES NOT download messages.
    - This module DOES NOT modify message.eml files.
    - This module works only with already parsed messages.
    - The operation is idempotent.
    - Running INDEX multiple times does not create duplicate rows.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ============================================================
# PROJECT
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from database.connection import DatabaseConnection


# ============================================================
# CONSTANTS
# ============================================================

INDEX_VERSION = "1.0"

DEFAULT_ACCOUNT = "frank.avner@gmail.com"


# ============================================================
# INDEXER
# ============================================================

class GmailIndexer:

    def __init__(
        self,
        account_email: str,
        force: bool = False,
    ):
        self.account_email = (
            account_email or DEFAULT_ACCOUNT
        ).strip()

        self.force = bool(force)

        self.gmail_account_id: int | None = None

        self.stats = {
            "messages_found": 0,
            "messages_indexed": 0,
            "messages_already_indexed": 0,
            "messages_updated": 0,
            "messages_missing": 0,
            "messages_failed": 0,
        }

    # ========================================================
    # LOGGING
    # ========================================================

    def log(
        self,
        message: str,
    ) -> None:
        print(
            message,
            flush=True,
        )

    # ========================================================
    # DATABASE
    # ========================================================

    def get_db_connection(self):
        db = DatabaseConnection()
        return db.connect()

    def load_database_context(
        self,
    ) -> None:

        conn = self.get_db_connection()

        try:

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        id
                    FROM gmail_accounts
                    WHERE LOWER(email) = LOWER(%s)
                    LIMIT 1
                    """,
                    (
                        self.account_email,
                    ),
                )

                row = cursor.fetchone()

                if not row:

                    raise RuntimeError(
                        "Gmail account was not found "
                        "in PostgreSQL: "
                        + self.account_email
                    )

                self.gmail_account_id = int(
                    row[0]
                )

        finally:

            conn.close()

    # ========================================================
    # CREATE INDEX TABLE
    # ========================================================

    def ensure_index_table(
        self,
    ) -> None:

        conn = self.get_db_connection()

        try:

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gmail_search_index (
                        id BIGSERIAL PRIMARY KEY,

                        gmail_message_id BIGINT NOT NULL,

                        gmail_message_key TEXT NOT NULL,

                        gmail_account_id BIGINT NOT NULL,

                        mime_message_id TEXT,

                        thread_id TEXT,

                        subject TEXT,

                        sender_name TEXT,

                        sender_email TEXT,

                        recipients JSONB,

                        cc_recipients JSONB,

                        bcc_recipients JSONB,

                        reply_to JSONB,

                        date_sent TIMESTAMPTZ,

                        body_text TEXT,

                        body_html TEXT,

                        search_text TEXT,

                        has_attachments BOOLEAN DEFAULT FALSE,

                        attachment_count INTEGER DEFAULT 0,

                        raw_sha256 TEXT,

                        raw_size BIGINT,

                        parser_version TEXT,

                        index_version TEXT NOT NULL,

                        indexed_at TIMESTAMPTZ NOT NULL,

                        updated_at TIMESTAMPTZ NOT NULL,

                        search_vector TSVECTOR,

                        metadata JSONB,

                        CONSTRAINT uq_gmail_search_index_message
                            UNIQUE (gmail_message_id)
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_gmail_search_index_account
                    ON gmail_search_index (
                        gmail_account_id
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_gmail_search_index_message_key
                    ON gmail_search_index (
                        gmail_message_key
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_gmail_search_index_date
                    ON gmail_search_index (
                        date_sent
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_gmail_search_index_sender
                    ON gmail_search_index (
                        sender_email
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_gmail_search_index_subject
                    ON gmail_search_index (
                        subject
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_gmail_search_index_search_vector
                    ON gmail_search_index
                    USING GIN (
                        search_vector
                    )
                    """
                )

            conn.commit()

        except Exception:

            conn.rollback()
            raise

        finally:

            conn.close()

    # ========================================================
    # MESSAGE LIST
    # ========================================================

    def get_parsed_messages(
        self,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:

        if self.gmail_account_id is None:

            raise RuntimeError(
                "Database context was not loaded."
            )

        conn = self.get_db_connection()

        try:

            with conn.cursor() as cursor:

                sql = """
                    SELECT
                        gpm.id,
                        gpm.gmail_message_id,
                        gpm.gmail_message_key,
                        gpm.mime_message_id,
                        gpm.thread_id,
                        gpm.subject,
                        gpm.sender_name,
                        gpm.sender_email,
                        gpm.recipients,
                        gpm.cc_recipients,
                        gpm.bcc_recipients,
                        gpm.reply_to,
                        gpm.date_sent,
                        gpm.body_text,
                        gpm.body_html,
                        gpm.search_text,
                        gpm.has_attachments,
                        gpm.attachment_count,
                        gpm.raw_sha256,
                        gpm.raw_size,
                        gpm.parser_version,
                        gpm.headers,
                        gpm.metadata
                    FROM gmail_parsed_messages gpm
                    JOIN gmail_messages gm
                        ON gm.id = gpm.gmail_message_id
                    WHERE gm.gmail_account_id = %s
                    ORDER BY
                        gpm.gmail_message_id
                """

                parameters: list[Any] = [
                    self.gmail_account_id
                ]

                if limit is not None:

                    sql += """
                        LIMIT %s
                    """

                    parameters.append(
                        int(limit)
                    )

                cursor.execute(
                    sql,
                    tuple(parameters),
                )

                columns = [
                    description[0]
                    for description
                    in cursor.description
                ]

                rows = cursor.fetchall()

                return [
                    dict(
                        zip(
                            columns,
                            row,
                        )
                    )
                    for row in rows
                ]

        finally:

            conn.close()

    # ========================================================
    # CHECK EXISTING INDEX
    # ========================================================

    def is_already_indexed(
        self,
        gmail_message_id: int,
    ) -> bool:

        conn = self.get_db_connection()

        try:

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        index_version
                    FROM gmail_search_index
                    WHERE gmail_message_id = %s
                    LIMIT 1
                    """,
                    (
                        gmail_message_id,
                    ),
                )

                row = cursor.fetchone()

                if not row:
                    return False

                existing_version = row[0]

                if self.force:
                    return False

                return (
                    existing_version
                    == INDEX_VERSION
                )

        finally:

            conn.close()

    # ========================================================
    # INDEX ONE MESSAGE
    # ========================================================

    def index_message(
        self,
        message: dict[str, Any],
    ) -> str:

        gmail_message_id = int(
            message["gmail_message_id"]
        )

        gmail_message_key = str(
            message.get(
                "gmail_message_key"
            )
            or ""
        )

        if self.is_already_indexed(
            gmail_message_id
        ):

            return "already"

        now = datetime.now(
            timezone.utc
        )

        conn = self.get_db_connection()

        try:

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    INSERT INTO gmail_search_index (
                        gmail_message_id,
                        gmail_message_key,
                        gmail_account_id,
                        mime_message_id,
                        thread_id,
                        subject,
                        sender_name,
                        sender_email,
                        recipients,
                        cc_recipients,
                        bcc_recipients,
                        reply_to,
                        date_sent,
                        body_text,
                        body_html,
                        search_text,
                        has_attachments,
                        attachment_count,
                        raw_sha256,
                        raw_size,
                        parser_version,
                        index_version,
                        indexed_at,
                        updated_at,
                        search_vector,
                        metadata
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        to_tsvector(
                            'simple',
                            COALESCE(%s, '')
                        ),
                        %s
                    )
                    ON CONFLICT (
                        gmail_message_id
                    )
                    DO UPDATE SET

                        gmail_message_key =
                            EXCLUDED.gmail_message_key,

                        gmail_account_id =
                            EXCLUDED.gmail_account_id,

                        mime_message_id =
                            EXCLUDED.mime_message_id,

                        thread_id =
                            EXCLUDED.thread_id,

                        subject =
                            EXCLUDED.subject,

                        sender_name =
                            EXCLUDED.sender_name,

                        sender_email =
                            EXCLUDED.sender_email,

                        recipients =
                            EXCLUDED.recipients,

                        cc_recipients =
                            EXCLUDED.cc_recipients,

                        bcc_recipients =
                            EXCLUDED.bcc_recipients,

                        reply_to =
                            EXCLUDED.reply_to,

                        date_sent =
                            EXCLUDED.date_sent,

                        body_text =
                            EXCLUDED.body_text,

                        body_html =
                            EXCLUDED.body_html,

                        search_text =
                            EXCLUDED.search_text,

                        has_attachments =
                            EXCLUDED.has_attachments,

                        attachment_count =
                            EXCLUDED.attachment_count,

                        raw_sha256 =
                            EXCLUDED.raw_sha256,

                        raw_size =
                            EXCLUDED.raw_size,

                        parser_version =
                            EXCLUDED.parser_version,

                        index_version =
                            EXCLUDED.index_version,

                        updated_at =
                            EXCLUDED.updated_at,

                        search_vector =
                            EXCLUDED.search_vector,

                        metadata =
                            EXCLUDED.metadata

                    RETURNING
                        id,
                        xmax
                    """,
                    (
                        gmail_message_id,
                        gmail_message_key,
                        self.gmail_account_id,
                        message.get(
                            "mime_message_id"
                        ),
                        message.get(
                            "thread_id"
                        ),
                        message.get(
                            "subject"
                        ),
                        message.get(
                            "sender_name"
                        ),
                        message.get(
                            "sender_email"
                        ),
                        json.dumps(
                            message.get(
                                "recipients"
                            )
                            or [],
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            message.get(
                                "cc_recipients"
                            )
                            or [],
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            message.get(
                                "bcc_recipients"
                            )
                            or [],
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            message.get(
                                "reply_to"
                            )
                            or [],
                            ensure_ascii=False,
                        ),
                        message.get(
                            "date_sent"
                        ),
                        message.get(
                            "body_text"
                        ),
                        message.get(
                            "body_html"
                        ),
                        message.get(
                            "search_text"
                        ),
                        bool(
                            message.get(
                                "has_attachments"
                            )
                        ),
                        int(
                            message.get(
                                "attachment_count"
                            )
                            or 0
                        ),
                        message.get(
                            "raw_sha256"
                        ),
                        message.get(
                            "raw_size"
                        ),
                        message.get(
                            "parser_version"
                        ),
                        INDEX_VERSION,
                        now,
                        now,
                        message.get(
                            "search_text"
                        ),
                        json.dumps(
                            message.get(
                                "metadata"
                            )
                            or {},
                            ensure_ascii=False,
                        ),
                    ),
                )

                row = cursor.fetchone()

                if not row:

                    raise RuntimeError(
                        "INDEX INSERT/UPDATE "
                        "did not return a row."
                    )

                xmax = row[1]

            conn.commit()

            if xmax == 0:

                return "indexed"

            return "updated"

        except Exception:

            conn.rollback()
            raise

        finally:

            conn.close()

    # ========================================================
    # PROCESS
    # ========================================================

    def process_message(
        self,
        message: dict[str, Any],
    ) -> None:

        message_key = str(
            message.get(
                "gmail_message_key"
            )
            or ""
        )

        self.log(
            "[MESSAGE] "
            + message_key
        )

        try:

            result = self.index_message(
                message
            )

            if result == "already":

                self.stats[
                    "messages_already_indexed"
                ] += 1

                self.log(
                    "[MESSAGE] Already indexed"
                )

                return

            if result == "indexed":

                self.stats[
                    "messages_indexed"
                ] += 1

                self.log(
                    "[MESSAGE] INDEXED"
                )

                return

            if result == "updated":

                self.stats[
                    "messages_updated"
                ] += 1

                self.log(
                    "[MESSAGE] UPDATED"
                )

                return

            raise RuntimeError(
                "Unknown INDEX result: "
                + str(result)
            )

        except Exception as exc:

            self.stats[
                "messages_failed"
            ] += 1

            self.log(
                "[ERROR] "
                + message_key
                + ": "
                + type(exc).__name__
                + ": "
                + str(exc)
            )

    # ========================================================
    # RUN
    # ========================================================

    def run(
        self,
        limit: int | None = None,
    ) -> dict[str, Any]:

        self.log("")
        self.log("=" * 72)
        self.log("STARTING GMAIL INDEX")
        self.log("=" * 72)

        self.log(
            "[ACCOUNT] "
            + self.account_email
        )

        self.log(
            "[INDEX VERSION] "
            + INDEX_VERSION
        )

        self.log(
            "[MODE] "
            + (
                "FORCE REINDEX"
                if self.force
                else "IDEMPOTENT"
            )
        )

        if limit is not None:

            self.log(
                "[LIMIT] "
                + str(limit)
            )

        self.log(
            "=" * 72
        )

        self.load_database_context()

        self.log(
            "[DB] Gmail account ID: "
            + str(
                self.gmail_account_id
            )
        )

        self.ensure_index_table()

        self.log(
            "[DB] Search index table ready."
        )

        messages = (
            self.get_parsed_messages(
                limit=limit
            )
        )

        self.stats[
            "messages_found"
        ] = len(messages)

        if not messages:

            self.log(
                "[STOP] No parsed Gmail messages found."
            )

            return self.stats

        self.log(
            "[FOUND] "
            + str(len(messages))
            + " parsed messages"
        )

        for index, message in enumerate(
            messages,
            1,
        ):

            self.log("")

            self.log(
                "[PROGRESS] "
                + str(index)
                + "/"
                + str(len(messages))
            )

            self.process_message(
                message
            )

        self.log("")
        self.log("=" * 72)
        self.log("GMAIL INDEX SUMMARY")
        self.log("=" * 72)

        self.log(
            "Messages found: "
            + str(
                self.stats[
                    "messages_found"
                ]
            )
        )

        self.log(
            "Messages indexed: "
            + str(
                self.stats[
                    "messages_indexed"
                ]
            )
        )

        self.log(
            "Already indexed: "
            + str(
                self.stats[
                    "messages_already_indexed"
                ]
            )
        )

        self.log(
            "Messages updated: "
            + str(
                self.stats[
                    "messages_updated"
                ]
            )
        )

        self.log(
            "Messages missing: "
            + str(
                self.stats[
                    "messages_missing"
                ]
            )
        )

        self.log(
            "Failed: "
            + str(
                self.stats[
                    "messages_failed"
                ]
            )
        )

        self.log("=" * 72)

        return self.stats


# ============================================================
# COMMAND LINE
# ============================================================

def build_argument_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description=(
            "Alcalay Gmail INDEX - "
            "idempotent PostgreSQL search indexing"
        )
    )

    parser.add_argument(
        "--account",
        default=DEFAULT_ACCOUNT,
        help=(
            "Gmail account email"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Process only the first N parsed messages"
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Re-index messages even when the "
            "same index version already exists"
        ),
    )

    return parser


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    parser = build_argument_parser()

    args = parser.parse_args()

    if args.limit is not None:

        if args.limit < 1:

            parser.error(
                "--limit must be greater than zero."
            )

    try:

        indexer = GmailIndexer(
            account_email=args.account,
            force=args.force,
        )

        indexer.run(
            limit=args.limit
        )

        if (
            indexer.stats[
                "messages_failed"
            ]
            > 0
        ):

            return 1

        return 0

    except KeyboardInterrupt:

        print(
            "\n[STOP] INDEX interrupted by user.",
            flush=True,
        )

        return 130

    except Exception as exc:

        print(
            "",
            flush=True,
        )

        print(
            "[FATAL] "
            + type(exc).__name__
            + ": "
            + str(exc),
            flush=True,
        )

        return 1


if __name__ == "__main__":

    raise SystemExit(
        main()
    )