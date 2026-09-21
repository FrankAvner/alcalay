# -*- coding: utf-8 -*-

"""
Alcalay - Gmail INDEXER
=======================

Indexes Gmail messages and existing local attachments.

Architecture:

    Gmail
      |
      v
    COPY
      |
      v
    gmail_messages
      |
      v
    PARSE
      |
      +------------------------------+
      |                              |
      v                              v
gmail_parsed_messages         gmail_attachments
      |                              |
      v                              v
gmail_search_index         gmail_attachment_search_index


IMPORTANT:

- This module does NOT connect to Gmail.
- This module does NOT download messages.
- This module does NOT download attachments.
- Existing EML files and existing gmail_attachments are used.
- Attachment content is indexed in a separate table.
- Email content remains in gmail_search_index.
- Attachment content remains in gmail_attachment_search_index.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


from database.connection import DatabaseConnection


INDEX_VERSION = "2.0"
ATTACHMENT_INDEX_VERSION = "1.0"

DEFAULT_ACCOUNT = "frank.avner@gmail.com"

DEFAULT_STORAGE_ROOT = (
    PROJECT_ROOT
    / "storage"
    / "gmail"
)

MAX_EXTRACTED_TEXT_LENGTH = 5_000_000


class GmailIndexer:

    def __init__(
        self,
        account_email: str,
        force: bool = False,
        storage_root: str | Path | None = None,
    ):
        self.account_email = account_email
        self.force = force

        if storage_root:
            self.storage_root = Path(
                storage_root
            )
        else:
            self.storage_root = DEFAULT_STORAGE_ROOT

        self.gmail_account_id: int | None = None

        self.stats = {
            "messages_found": 0,
            "messages_indexed": 0,
            "messages_already_indexed": 0,
            "messages_updated": 0,
            "messages_missing": 0,
            "messages_failed": 0,

            "attachments_found": 0,
            "attachments_indexed": 0,
            "attachments_already_indexed": 0,
            "attachments_updated": 0,
            "attachments_unsupported": 0,
            "attachments_missing": 0,
            "attachments_failed": 0,
            "attachments_with_text": 0,
            "attachments_without_text": 0,
        }

    # ============================================================
    # GENERAL
    # ============================================================

    def log(
        self,
        message: str,
    ) -> None:
        print(
            message,
            flush=True,
        )

    def utc_now(self) -> datetime:
        return datetime.now(
            timezone.utc
        )

    def get_db_connection(self):
        return DatabaseConnection().connect()

    def sha256_bytes(
        self,
        data: bytes,
    ) -> str:
        return hashlib.sha256(
            data
        ).hexdigest()

    def normalize_text(
        self,
        value: Any,
    ) -> str:
        if value is None:
            return ""

        text = str(value)

        text = text.replace(
            "\x00",
            " ",
        )

        text = re.sub(
            r"\r\n?",
            "\n",
            text,
        )

        text = re.sub(
            r"[ \t]+",
            " ",
            text,
        )

        text = re.sub(
            r"\n{3,}",
            "\n\n",
            text,
        )

        return text.strip()

    def truncate_text(
        self,
        text: str,
        maximum: int = MAX_EXTRACTED_TEXT_LENGTH,
    ) -> str:
        text = self.normalize_text(
            text
        )

        if len(text) <= maximum:
            return text

        return text[:maximum]

    # ============================================================
    # DATABASE CONTEXT
    # ============================================================

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
                        "Gmail account was not found in PostgreSQL: "
                        + self.account_email
                    )

                self.gmail_account_id = int(
                    row[0]
                )

                self.log(
                    "[DB] Gmail account ID: "
                    + str(
                        self.gmail_account_id
                    )
                )

        finally:
            conn.close()

    # ============================================================
    # EMAIL INDEX TABLE
    # ============================================================

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

                        has_attachments BOOLEAN
                            NOT NULL DEFAULT FALSE,

                        attachment_count INTEGER
                            NOT NULL DEFAULT 0,

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
                        idx_gmail_search_index_date
                    ON gmail_search_index (
                        date_sent
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

    # ============================================================
    # ATTACHMENT INDEX TABLE
    # ============================================================

    def ensure_attachment_index_table(
        self,
    ) -> None:

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS
                        gmail_attachment_search_index (

                        id BIGSERIAL PRIMARY KEY,

                        gmail_attachment_id BIGINT NOT NULL,

                        gmail_message_id BIGINT NOT NULL,

                        gmail_account_id BIGINT NOT NULL,

                        gmail_message_key TEXT,

                        file_name TEXT,

                        mime_type TEXT,

                        local_path TEXT,

                        content_hash TEXT,

                        file_size BIGINT,

                        extracted_text TEXT,

                        search_text TEXT,

                        parser_version TEXT,

                        index_version TEXT NOT NULL,

                        indexed_at TIMESTAMPTZ NOT NULL,

                        updated_at TIMESTAMPTZ NOT NULL,

                        search_vector TSVECTOR,

                        metadata JSONB,

                        CONSTRAINT
                            uq_gmail_attachment_search_index
                            UNIQUE (
                                gmail_attachment_id
                            )
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_gmail_attachment_index_message
                    ON gmail_attachment_search_index (
                        gmail_message_id
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_gmail_attachment_index_account
                    ON gmail_attachment_search_index (
                        gmail_account_id
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_gmail_attachment_index_filename
                    ON gmail_attachment_search_index (
                        file_name
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_gmail_attachment_index_mime
                    ON gmail_attachment_search_index (
                        mime_type
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_gmail_attachment_index_hash
                    ON gmail_attachment_search_index (
                        content_hash
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_gmail_attachment_index_search_vector
                    ON gmail_attachment_search_index
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

    # ============================================================
    # PARSED EMAILS
    # ============================================================

    def get_parsed_messages(
        self,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:

        if self.gmail_account_id is None:
            raise RuntimeError(
                "Database context has not been loaded."
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
                        gpm.raw_sha256,
                        gpm.raw_size,
                        gpm.has_attachments,
                        gpm.attachment_count,
                        gpm.headers,
                        gpm.metadata,
                        gpm.parser_version,
                        gm.metadata
                    FROM gmail_parsed_messages gpm
                    JOIN gmail_messages gm
                        ON gm.id = gpm.gmail_message_id
                    WHERE gm.gmail_account_id = %s
                    ORDER BY gpm.gmail_message_id
                """

                params: list[Any] = [
                    self.gmail_account_id
                ]

                if limit is not None:
                    sql += """
                        LIMIT %s
                    """

                    params.append(
                        int(limit)
                    )

                cursor.execute(
                    sql,
                    tuple(params),
                )

                columns = [
                    column.name
                    for column in cursor.description
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

    # ============================================================
    # EMAIL INDEX CHECK
    # ============================================================

    def get_existing_email_index(
        self,
        gmail_message_id: int,
    ) -> dict[str, Any] | None:

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        id,
                        index_version,
                        raw_sha256
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
                    return None

                return {
                    "id": row[0],
                    "index_version": row[1],
                    "raw_sha256": row[2],
                }

        finally:
            conn.close()

    # ============================================================
    # EMAIL INDEX
    # ============================================================

    def index_message(
        self,
        message: dict[str, Any],
    ) -> str:

        gmail_message_id = int(
            message["gmail_message_id"]
        )

        existing = (
            self.get_existing_email_index(
                gmail_message_id
            )
        )

        if (
            not self.force
            and existing
            and existing["index_version"]
            == INDEX_VERSION
            and existing["raw_sha256"]
            == message.get(
                "raw_sha256"
            )
        ):
            self.stats[
                "messages_already_indexed"
            ] += 1

            return "already_indexed"

        now = self.utc_now()

        recipients = (
            message.get(
                "recipients"
            )
            or []
        )

        cc_recipients = (
            message.get(
                "cc_recipients"
            )
            or []
        )

        bcc_recipients = (
            message.get(
                "bcc_recipients"
            )
            or []
        )

        reply_to = (
            message.get(
                "reply_to"
            )
            or []
        )

        metadata = (
            message.get(
                "metadata"
            )
            or {}
        )

        search_text = (
            message.get(
                "search_text"
            )
            or ""
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
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        to_tsvector(
                            'simple',
                            coalesce(%s, '')
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

                        indexed_at =
                            EXCLUDED.indexed_at,

                        updated_at =
                            EXCLUDED.updated_at,

                        search_vector =
                            EXCLUDED.search_vector,

                        metadata =
                            EXCLUDED.metadata
                    """,
                    (
                        gmail_message_id,
                        message.get(
                            "gmail_message_key"
                        ),
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
                            recipients,
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            cc_recipients,
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            bcc_recipients,
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            reply_to,
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
                        search_text,
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
                        search_text,
                        json.dumps(
                            metadata,
                            ensure_ascii=False,
                        ),
                    ),
                )

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

        if existing:
            self.stats[
                "messages_updated"
            ] += 1

            return "updated"

        self.stats[
            "messages_indexed"
        ] += 1

        return "indexed"

    # ============================================================
    # ATTACHMENTS
    # ============================================================

    def get_attachments(
        self,
        message_ids: set[int] | None = None,
    ) -> list[dict[str, Any]]:

        if self.gmail_account_id is None:
            raise RuntimeError(
                "Database context has not been loaded."
            )

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                sql = """
                    SELECT
                        ga.id,
                        ga.gmail_message_id,
                        ga.attachment_id,
                        ga.file_name,
                        ga.mime_type,
                        ga.file_size,
                        ga.content_hash,
                        ga.local_file_id,
                        ga.saved_to_local,
                        ga.metadata,
                        gm.message_id,
                        gm.thread_id
                    FROM gmail_attachments ga
                    JOIN gmail_messages gm
                        ON gm.id = ga.gmail_message_id
                    WHERE gm.gmail_account_id = %s
                """

                params: list[Any] = [
                    self.gmail_account_id
                ]

                if message_ids:
                    sorted_ids = sorted(
                        int(
                            value
                        )
                        for value in message_ids
                    )

                    sql += """
                        AND ga.gmail_message_id =
                            ANY(%s)
                    """

                    params.append(
                        sorted_ids
                    )

                sql += """
                    ORDER BY ga.id
                """

                cursor.execute(
                    sql,
                    tuple(params),
                )

                columns = [
                    column.name
                    for column in cursor.description
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

    # ============================================================
    # ATTACHMENT PATH
    # ============================================================

    def attachment_local_path(
        self,
        attachment: dict[str, Any],
    ) -> Path | None:

        metadata = (
            attachment.get(
                "metadata"
            )
            or {}
        )

        if isinstance(
            metadata,
            str,
        ):
            try:
                metadata = json.loads(
                    metadata
                )
            except Exception:
                metadata = {}

        if isinstance(
            metadata,
            dict,
        ):
            local_path = metadata.get(
                "local_path"
            )

            if local_path:
                path = Path(
                    str(
                        local_path
                    )
                )

                if path.exists():
                    return path

        local_file_id = (
            attachment.get(
                "local_file_id"
            )
        )

        if local_file_id:
            possible_path = (
                self.storage_root
                / str(
                    local_file_id
                )
            )

            if possible_path.exists():
                return possible_path

        return None

    # ============================================================
    # ATTACHMENT INDEX CHECK
    # ============================================================

    def get_existing_attachment_index(
        self,
        gmail_attachment_id: int,
    ) -> dict[str, Any] | None:

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        id,
                        content_hash,
                        index_version
                    FROM gmail_attachment_search_index
                    WHERE gmail_attachment_id = %s
                    LIMIT 1
                    """,
                    (
                        gmail_attachment_id,
                    ),
                )

                row = cursor.fetchone()

                if not row:
                    return None

                return {
                    "id": row[0],
                    "content_hash": row[1],
                    "index_version": row[2],
                }

        finally:
            conn.close()

    # ============================================================
    # TEXT EXTRACTION - HTML
    # ============================================================

    def extract_html_text(
        self,
        data: bytes,
    ) -> str:

        text = data.decode(
            "utf-8",
            errors="replace",
        )

        text = re.sub(
            r"(?is)<script.*?>.*?</script>",
            " ",
            text,
        )

        text = re.sub(
            r"(?is)<style.*?>.*?</style>",
            " ",
            text,
        )

        text = re.sub(
            r"(?i)<br\s*/?>",
            "\n",
            text,
        )

        text = re.sub(
            r"(?i)</(?:p|div|li|tr|h[1-6])>",
            "\n",
            text,
        )

        text = re.sub(
            r"<[^>]+>",
            " ",
            text,
        )

        text = html.unescape(
            text
        )

        return self.normalize_text(
            text
        )

    # ============================================================
    # TEXT EXTRACTION - TXT / CSV
    # ============================================================

    def extract_plain_text(
        self,
        data: bytes,
    ) -> str:

        encodings = [
            "utf-8",
            "utf-8-sig",
            "cp1255",
            "windows-1252",
            "latin-1",
        ]

        best_text = ""

        for encoding in encodings:
            try:
                text = data.decode(
                    encoding
                )

                if len(text) > len(
                    best_text
                ):
                    best_text = text

                if "\x00" not in text:
                    break

            except Exception:
                continue

        return self.normalize_text(
            best_text
        )

    # ============================================================
    # TEXT EXTRACTION - PDF
    # ============================================================

    def extract_pdf_text(
        self,
        path: Path,
    ) -> str:

        try:
            from pypdf import PdfReader
        except ImportError:
            return ""

        reader = PdfReader(
            str(path)
        )

        parts: list[str] = []

        for page in reader.pages:
            try:
                page_text = page.extract_text()

                if page_text:
                    parts.append(
                        page_text
                    )

            except Exception:
                continue

        return self.normalize_text(
            "\n".join(parts)
        )

    # ============================================================
    # TEXT EXTRACTION - DOCX
    # ============================================================

    def extract_docx_text(
        self,
        path: Path,
    ) -> str:

        try:
            from docx import Document
        except ImportError:
            return ""

        document = Document(
            str(path)
        )

        parts: list[str] = []

        for paragraph in document.paragraphs:
            if paragraph.text:
                parts.append(
                    paragraph.text
                )

        for table in document.tables:
            for row in table.rows:
                values = []

                for cell in row.cells:
                    values.append(
                        cell.text
                    )

                if values:
                    parts.append(
                        " | ".join(
                            values
                        )
                    )

        return self.normalize_text(
            "\n".join(parts)
        )

    # ============================================================
    # TEXT EXTRACTION - XLSX
    # ============================================================

    def extract_xlsx_text(
        self,
        path: Path,
    ) -> str:

        try:
            from openpyxl import load_workbook
        except ImportError:
            return ""

        workbook = load_workbook(
            filename=str(path),
            read_only=True,
            data_only=True,
        )

        parts: list[str] = []

        try:
            for worksheet in workbook.worksheets:

                parts.append(
                    "SHEET: "
                    + str(
                        worksheet.title
                    )
                )

                for row in worksheet.iter_rows(
                    values_only=True
                ):
                    values = []

                    for value in row:
                        if value is not None:
                            values.append(
                                str(value)
                            )

                    if values:
                        parts.append(
                            " | ".join(
                                values
                            )
                        )

        finally:
            workbook.close()

        return self.normalize_text(
            "\n".join(parts)
        )

    # ============================================================
    # TEXT EXTRACTION - PPTX
    # ============================================================

    def extract_pptx_text(
        self,
        path: Path,
    ) -> str:

        try:
            from pptx import Presentation
        except ImportError:
            return ""

        presentation = Presentation(
            str(path)
        )

        parts: list[str] = []

        for slide_number, slide in enumerate(
            presentation.slides,
            start=1,
        ):

            parts.append(
                "SLIDE: "
                + str(
                    slide_number
                )
            )

            for shape in slide.shapes:

                if not hasattr(
                    shape,
                    "text",
                ):
                    continue

                text = shape.text

                if text:
                    parts.append(
                        text
                    )

        return self.normalize_text(
            "\n".join(parts)
        )

    # ============================================================
    # TEXT EXTRACTION - DOCX XML FALLBACK
    # ============================================================

    def extract_openxml_text(
        self,
        path: Path,
    ) -> str:

        try:
            with zipfile.ZipFile(
                path,
                "r",
            ) as archive:

                names = archive.namelist()

                candidates = [
                    name
                    for name in names
                    if name.endswith(
                        ".xml"
                    )
                    and (
                        "document"
                        in name
                        or "sheet"
                        in name
                        or "slide"
                        in name
                    )
                ]

                parts: list[str] = []

                for name in candidates:

                    try:
                        raw = archive.read(
                            name
                        )

                        root = ElementTree.fromstring(
                            raw
                        )

                        values = []

                        for element in root.iter():

                            tag = element.tag

                            if "}" in tag:
                                tag = tag.rsplit(
                                    "}",
                                    1,
                                )[1]

                            if tag in (
                                "t",
                                "v",
                            ):
                                if element.text:
                                    values.append(
                                        element.text
                                    )

                        if values:
                            parts.append(
                                " ".join(
                                    values
                                )
                            )

                    except Exception:
                        continue

                return self.normalize_text(
                    "\n".join(parts)
                )

        except Exception:
            return ""

    # ============================================================
    # ATTACHMENT TEXT EXTRACTION
    # ============================================================

    def extract_attachment_text(
        self,
        path: Path,
        mime_type: str | None,
    ) -> tuple[str, str]:

        suffix = (
            path.suffix
            .lower()
        )

        mime = (
            str(
                mime_type
                or ""
            )
            .lower()
            .strip()
        )

        try:

            if (
                suffix == ".pdf"
                or mime == "application/pdf"
            ):
                return (
                    self.extract_pdf_text(
                        path
                    ),
                    "pdf",
                )

            if (
                suffix == ".docx"
                or mime
                == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ):
                text = self.extract_docx_text(
                    path
                )

                if not text:
                    text = self.extract_openxml_text(
                        path
                    )

                return (
                    text,
                    "docx",
                )

            if (
                suffix == ".xlsx"
                or mime
                == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ):
                text = self.extract_xlsx_text(
                    path
                )

                if not text:
                    text = self.extract_openxml_text(
                        path
                    )

                return (
                    text,
                    "xlsx",
                )

            if (
                suffix == ".pptx"
                or mime
                == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ):
                text = self.extract_pptx_text(
                    path
                )

                if not text:
                    text = self.extract_openxml_text(
                        path
                    )

                return (
                    text,
                    "pptx",
                )

            if suffix in (
                ".txt",
                ".text",
                ".log",
                ".md",
                ".csv",
                ".tsv",
                ".json",
                ".xml",
                ".html",
                ".htm",
            ):
                data = path.read_bytes()

                if suffix in (
                    ".html",
                    ".htm",
                ):
                    return (
                        self.extract_html_text(
                            data
                        ),
                        "html",
                    )

                if suffix == ".csv":
                    try:
                        text = self.extract_plain_text(
                            data
                        )

                        rows = []

                        for row in csv.reader(
                            text.splitlines()
                        ):
                            rows.append(
                                " | ".join(
                                    row
                                )
                            )

                        return (
                            self.normalize_text(
                                "\n".join(rows)
                            ),
                            "csv",
                        )

                    except Exception:
                        return (
                            self.extract_plain_text(
                                data
                            ),
                            "csv",
                        )

                return (
                    self.extract_plain_text(
                        data
                    ),
                    "text",
                )

            if mime.startswith(
                "text/"
            ):
                return (
                    self.extract_plain_text(
                        path.read_bytes()
                    ),
                    "text",
                )

        except Exception:
            raise

        return (
            "",
            "unsupported",
        )

    # ============================================================
    # ATTACHMENT INDEX
    # ============================================================

    def index_attachment(
        self,
        attachment: dict[str, Any],
    ) -> str:

        attachment_id = int(
            attachment["id"]
        )

        self.stats[
            "attachments_found"
        ] += 1

        local_path = (
            self.attachment_local_path(
                attachment
            )
        )

        if local_path is None:
            self.stats[
                "attachments_missing"
            ] += 1

            self.log(
                "[ATTACHMENT] Missing local file: "
                + str(
                    attachment.get(
                        "file_name"
                    )
                    or attachment_id
                )
            )

            return "missing"

        existing = (
            self.get_existing_attachment_index(
                attachment_id
            )
        )

        content_hash = (
            attachment.get(
                "content_hash"
            )
        )

        if not content_hash:
            content_hash = self.sha256_bytes(
                local_path.read_bytes()
            )

        if (
            not self.force
            and existing
            and existing[
                "index_version"
            ]
            == ATTACHMENT_INDEX_VERSION
            and existing[
                "content_hash"
            ]
            == content_hash
        ):

            self.stats[
                "attachments_already_indexed"
            ] += 1

            return "already_indexed"

        mime_type = (
            attachment.get(
                "mime_type"
            )
            or ""
        )

        file_name = (
            attachment.get(
                "file_name"
            )
            or local_path.name
        )

        self.log(
            "[ATTACHMENT] Indexing: "
            + str(
                file_name
            )
        )

        extracted_text, extractor = (
            self.extract_attachment_text(
                local_path,
                mime_type,
            )
        )

        extracted_text = self.truncate_text(
            extracted_text
        )

        if extracted_text:
            self.stats[
                "attachments_with_text"
            ] += 1
        else:
            self.stats[
                "attachments_without_text"
            ] += 1

        if extractor == "unsupported":
            self.stats[
                "attachments_unsupported"
            ] += 1

        search_text = self.normalize_text(
            "\n".join(
                [
                    str(
                        file_name
                        or ""
                    ),
                    str(
                        mime_type
                        or ""
                    ),
                    extracted_text,
                ]
            )
        )

        metadata = (
            attachment.get(
                "metadata"
            )
            or {}
        )

        if isinstance(
            metadata,
            str,
        ):
            try:
                metadata = json.loads(
                    metadata
                )
            except Exception:
                metadata = {}

        if not isinstance(
            metadata,
            dict,
        ):
            metadata = {}

        metadata = dict(
            metadata
        )

        metadata.update(
            {
                "extractor": extractor,
                "local_path": str(
                    local_path
                ),
                "content_hash": content_hash,
                "indexed_by": "GmailIndexer",
                "attachment_index_version":
                    ATTACHMENT_INDEX_VERSION,
            }
        )

        now = self.utc_now()

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    INSERT INTO
                        gmail_attachment_search_index (
                            gmail_attachment_id,
                            gmail_message_id,
                            gmail_account_id,
                            gmail_message_key,
                            file_name,
                            mime_type,
                            local_path,
                            content_hash,
                            file_size,
                            extracted_text,
                            search_text,
                            parser_version,
                            index_version,
                            indexed_at,
                            updated_at,
                            search_vector,
                            metadata
                        )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        to_tsvector(
                            'simple',
                            coalesce(%s, '')
                        ),
                        %s
                    )
                    ON CONFLICT (
                        gmail_attachment_id
                    )
                    DO UPDATE SET
                        gmail_message_id =
                            EXCLUDED.gmail_message_id,

                        gmail_account_id =
                            EXCLUDED.gmail_account_id,

                        gmail_message_key =
                            EXCLUDED.gmail_message_key,

                        file_name =
                            EXCLUDED.file_name,

                        mime_type =
                            EXCLUDED.mime_type,

                        local_path =
                            EXCLUDED.local_path,

                        content_hash =
                            EXCLUDED.content_hash,

                        file_size =
                            EXCLUDED.file_size,

                        extracted_text =
                            EXCLUDED.extracted_text,

                        search_text =
                            EXCLUDED.search_text,

                        parser_version =
                            EXCLUDED.parser_version,

                        index_version =
                            EXCLUDED.index_version,

                        indexed_at =
                            EXCLUDED.indexed_at,

                        updated_at =
                            EXCLUDED.updated_at,

                        search_vector =
                            EXCLUDED.search_vector,

                        metadata =
                            EXCLUDED.metadata
                    """,
                    (
                        attachment_id,
                        attachment[
                            "gmail_message_id"
                        ],
                        self.gmail_account_id,
                        attachment.get(
                            "message_id"
                        ),
                        file_name,
                        mime_type,
                        str(
                            local_path
                        ),
                        content_hash,
                        attachment.get(
                            "file_size"
                        )
                        or local_path.stat().st_size,
                        extracted_text,
                        search_text,
                        ATTACHMENT_INDEX_VERSION,
                        ATTACHMENT_INDEX_VERSION,
                        now,
                        now,
                        search_text,
                        json.dumps(
                            metadata,
                            ensure_ascii=False,
                        ),
                    ),
                )

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

        if existing:
            self.stats[
                "attachments_updated"
            ] += 1

            return "updated"

        self.stats[
            "attachments_indexed"
        ] += 1

        return "indexed"

    # ============================================================
    # PROCESS EMAILS
    # ============================================================

    def process_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> set[int]:

        message_ids: set[int] = set()

        total = len(
            messages
        )

        self.stats[
            "messages_found"
        ] = total

        self.log(
            "[INDEX] Parsed messages found: "
            + str(
                total
            )
        )

        for number, message in enumerate(
            messages,
            start=1,
        ):

            gmail_message_id = int(
                message[
                    "gmail_message_id"
                ]
            )

            message_ids.add(
                gmail_message_id
            )

            message_key = (
                message.get(
                    "gmail_message_key"
                )
                or ""
            )

            subject = (
                message.get(
                    "subject"
                )
                or ""
            )

            self.log(
                "[MESSAGE] "
                + str(number)
                + "/"
                + str(total)
                + " | "
                + message_key
                + " | "
                + subject[:120]
            )

            try:
                result = self.index_message(
                    message
                )

                self.log(
                    "[MESSAGE] "
                    + result
                )

            except Exception as exc:

                self.stats[
                    "messages_failed"
                ] += 1

                self.log(
                    "[MESSAGE] ERROR: "
                    + str(exc)
                )

        return message_ids

    # ============================================================
    # PROCESS ATTACHMENTS
    # ============================================================

    def process_attachments(
        self,
        message_ids: set[int] | None = None,
    ) -> None:

        attachments = self.get_attachments(
            message_ids
        )

        total = len(
            attachments
        )

        self.log(
            "[INDEX] Existing attachments found: "
            + str(
                total
            )
        )

        for number, attachment in enumerate(
            attachments,
            start=1,
        ):

            file_name = (
                attachment.get(
                    "file_name"
                )
                or "unknown"
            )

            self.log(
                "[ATTACHMENT] "
                + str(number)
                + "/"
                + str(total)
                + " | "
                + str(file_name)
            )

            try:

                result = self.index_attachment(
                    attachment
                )

                self.log(
                    "[ATTACHMENT] "
                    + result
                    + " | "
                    + str(
                        file_name
                    )
                )

            except Exception as exc:

                self.stats[
                    "attachments_failed"
                ] += 1

                self.log(
                    "[ATTACHMENT] ERROR: "
                    + str(exc)
                )

    # ============================================================
    # SUMMARY
    # ============================================================

    def print_summary(
        self,
    ) -> None:

        self.log("")
        self.log(
            "=" * 72
        )
        self.log(
            "ALCALAY - GMAIL INDEX SUMMARY"
        )
        self.log(
            "=" * 72
        )

        self.log(
            "Account: "
            + self.account_email
        )

        self.log("")

        self.log(
            "EMAILS"
        )

        self.log(
            "  Found: "
            + str(
                self.stats[
                    "messages_found"
                ]
            )
        )

        self.log(
            "  Indexed new: "
            + str(
                self.stats[
                    "messages_indexed"
                ]
            )
        )

        self.log(
            "  Already indexed: "
            + str(
                self.stats[
                    "messages_already_indexed"
                ]
            )
        )

        self.log(
            "  Updated: "
            + str(
                self.stats[
                    "messages_updated"
                ]
            )
        )

        self.log(
            "  Missing: "
            + str(
                self.stats[
                    "messages_missing"
                ]
            )
        )

        self.log(
            "  Failed: "
            + str(
                self.stats[
                    "messages_failed"
                ]
            )
        )

        self.log("")

        self.log(
            "ATTACHMENTS"
        )

        self.log(
            "  Found: "
            + str(
                self.stats[
                    "attachments_found"
                ]
            )
        )

        self.log(
            "  Indexed new: "
            + str(
                self.stats[
                    "attachments_indexed"
                ]
            )
        )

        self.log(
            "  Already indexed: "
            + str(
                self.stats[
                    "attachments_already_indexed"
                ]
            )
        )

        self.log(
            "  Updated: "
            + str(
                self.stats[
                    "attachments_updated"
                ]
            )
        )

        self.log(
            "  With extracted text: "
            + str(
                self.stats[
                    "attachments_with_text"
                ]
            )
        )

        self.log(
            "  Without extracted text: "
            + str(
                self.stats[
                    "attachments_without_text"
                ]
            )
        )

        self.log(
            "  Unsupported: "
            + str(
                self.stats[
                    "attachments_unsupported"
                ]
            )
        )

        self.log(
            "  Missing local file: "
            + str(
                self.stats[
                    "attachments_missing"
                ]
            )
        )

        self.log(
            "  Failed: "
            + str(
                self.stats[
                    "attachments_failed"
                ]
            )
        )

        self.log(
            "=" * 72
        )

    # ============================================================
    # RUN
    # ============================================================

    def run(
        self,
        limit: int | None = None,
    ) -> dict[str, Any]:

        self.log(
            "=" * 72
        )

        self.log(
            "ALCALAY - GMAIL INDEX"
        )

        self.log(
            "Account: "
            + self.account_email
        )

        self.log(
            "Mode: "
            + (
                "FORCE"
                if self.force
                else "NORMAL"
            )
        )

        self.log(
            "Storage: "
            + str(
                self.storage_root
            )
        )

        self.log(
            "=" * 72
        )

        self.load_database_context()

        self.log(
            "[DB] Ensuring email index table..."
        )

        self.ensure_index_table()

        self.log(
            "[DB] Ensuring attachment index table..."
        )

        self.ensure_attachment_index_table()

        self.log(
            "[INDEX] Loading parsed messages..."
        )

        messages = (
            self.get_parsed_messages(
                limit=limit
            )
        )

        message_ids = (
            self.process_messages(
                messages
            )
        )

        self.log("")

        self.log(
            "[INDEX] Loading existing attachments..."
        )

        self.process_attachments(
            message_ids
        )

        self.print_summary()

        return self.stats


def build_argument_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description=(
            "Alcalay Gmail INDEX - "
            "email and existing attachment indexing"
        )
    )

    parser.add_argument(
        "--account",
        default=DEFAULT_ACCOUNT,
        help=(
            "Gmail account email. "
            "Default: "
            + DEFAULT_ACCOUNT
        ),
    )

    parser.add_argument(
        "--storage-root",
        default=None,
        help=(
            "Gmail storage root. "
            "Default: storage/gmail"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum number of parsed messages "
            "to process."
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Re-index messages and attachments "
            "even when the same version/hash already exists."
        ),
    )

    return parser


def main() -> int:

    parser = build_argument_parser()

    args = parser.parse_args()

    indexer = GmailIndexer(
        account_email=args.account,
        force=args.force,
        storage_root=args.storage_root,
    )

    try:

        indexer.run(
            limit=args.limit
        )

        return 0

    except KeyboardInterrupt:

        print(
            "\n[STOP] Interrupted by user.",
            flush=True,
        )

        return 130

    except Exception as exc:

        print(
            "",
            flush=True,
        )

        print(
            "=" * 72,
            flush=True,
        )

        print(
            "GMAIL INDEX FAILED",
            flush=True,
        )

        print(
            str(exc),
            flush=True,
        )

        print(
            "=" * 72,
            flush=True,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )