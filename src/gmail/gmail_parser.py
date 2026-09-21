from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from datetime import datetime, timezone
from email import policy
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from database.connection import DatabaseConnection


DEFAULT_STORAGE_ROOT = (
    PROJECT_ROOT
    / "storage"
    / "gmail"
)

PARSER_VERSION = "1.0"

MAX_SEARCH_TEXT_LENGTH = 5_000_000


class GmailParser:

    def __init__(
        self,
        account_email: str | None = None,
        storage_root: str | Path | None = None,
        force: bool = False,
    ):
        self.account_email = (
            account_email.strip()
            if account_email
            else None
        )

        if storage_root:
            self.storage_root = Path(
                storage_root
            )
        else:
            self.storage_root = (
                DEFAULT_STORAGE_ROOT
            )

        self.force = force

        self.gmail_account_id = None

        self.stats = {
            "messages_found": 0,
            "messages_parsed": 0,
            "messages_already_parsed": 0,
            "messages_missing_database": 0,
            "messages_failed": 0,
            "attachments_found": 0,
            "attachments_saved": 0,
            "attachments_existing": 0,
            "attachments_failed": 0,
        }

    # =========================================================
    # GENERAL
    # =========================================================

    def log(
        self,
        message: str,
    ) -> None:
        print(
            message,
            flush=True,
        )

    def get_db_connection(self):
        return DatabaseConnection().connect()

    def utc_now(self) -> datetime:
        return datetime.now(
            timezone.utc
        )

    def sha256_bytes(
        self,
        data: bytes,
    ) -> str:
        return hashlib.sha256(
            data
        ).hexdigest()

    def safe_name(
        self,
        value: str,
    ) -> str:
        value = str(
            value or ""
        ).strip()

        value = re.sub(
            r"[^\w.\-@]+",
            "_",
            value,
            flags=re.UNICODE,
        )

        value = value.strip(
            "._ "
        )

        return value or "unknown"

    # =========================================================
    # DATABASE
    # =========================================================

    def load_database_context(
        self,
    ) -> None:

        if not self.account_email:
            return

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

                self.gmail_account_id = row[0]

        finally:
            conn.close()

    def ensure_parsed_table(
        self,
    ) -> None:

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gmail_parsed_messages (
                        id BIGSERIAL PRIMARY KEY,

                        gmail_message_id BIGINT NOT NULL,

                        gmail_message_key TEXT NOT NULL,

                        mime_message_id TEXT,

                        thread_id TEXT,

                        subject TEXT,

                        sender_name TEXT,

                        sender_email TEXT,

                        recipients JSONB,

                        cc_recipients JSONB,

                        bcc_recipients JSONB,

                        reply_to JSONB,

                        date_header TEXT,

                        date_sent TIMESTAMPTZ,

                        in_reply_to TEXT,

                        references_header TEXT,

                        content_type TEXT,

                        charset TEXT,

                        body_text TEXT,

                        body_html TEXT,

                        search_text TEXT,

                        raw_sha256 TEXT,

                        raw_size BIGINT,

                        has_attachments BOOLEAN DEFAULT FALSE,

                        attachment_count INTEGER DEFAULT 0,

                        headers JSONB,

                        metadata JSONB,

                        parser_version TEXT,

                        parsed_at TIMESTAMPTZ,

                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

                        CONSTRAINT uq_gmail_parsed_messages_message
                            UNIQUE (gmail_message_id)
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_gmail_parsed_messages_sender
                    ON gmail_parsed_messages(sender_email)
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_gmail_parsed_messages_date_sent
                    ON gmail_parsed_messages(date_sent)
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_gmail_parsed_messages_subject
                    ON gmail_parsed_messages(subject)
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_gmail_parsed_messages_mime_id
                    ON gmail_parsed_messages(mime_message_id)
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    idx_gmail_parsed_messages_search_text
                    ON gmail_parsed_messages
                    USING GIN (
                        to_tsvector(
                            'simple',
                            COALESCE(search_text, '')
                        )
                    )
                    """
                )

                conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

    # =========================================================
    # FILE LOCATION
    # =========================================================

    def account_directory(
        self,
        account_email: str,
    ) -> Path:

        return (
            self.storage_root
            / self.safe_name(account_email)
        )

    def messages_directory(
        self,
        account_email: str,
    ) -> Path:

        return (
            self.account_directory(
                account_email
            )
            / "messages"
        )

    def find_message_files(
        self,
        account_email: str,
    ) -> list[Path]:

        directory = self.messages_directory(
            account_email
        )

        if not directory.exists():
            return []

        return sorted(
            directory.glob(
                "*/message.eml"
            )
        )

    # =========================================================
    # MIME DECODING
    # =========================================================

    def decode_header_value(
        self,
        value: str | None,
    ) -> str:

        if not value:
            return ""

        try:
            return str(
                make_header(
                    decode_header(
                        value
                    )
                )
            ).strip()

        except Exception:
            return str(
                value
            ).strip()

    def decode_payload(
        self,
        part,
    ) -> str:

        try:
            payload = part.get_payload(
                decode=True
            )
        except Exception:
            payload = None

        if isinstance(
            payload,
            bytes,
        ):

            charset = (
                part.get_content_charset()
                or "utf-8"
            )

            try:
                return payload.decode(
                    charset,
                    errors="replace",
                )
            except Exception:
                return payload.decode(
                    "utf-8",
                    errors="replace",
                )

        if isinstance(
            payload,
            str,
        ):
            return payload

        raw_payload = part.get_payload()

        if isinstance(
            raw_payload,
            str,
        ):
            return raw_payload

        return ""

    def strip_html(
        self,
        value: str,
    ) -> str:

        if not value:
            return ""

        value = re.sub(
            r"(?is)<(script|style).*?>.*?</\1>",
            " ",
            value,
        )

        value = re.sub(
            r"(?i)<br\s*/?>",
            "\n",
            value,
        )

        value = re.sub(
            r"(?i)</p\s*>",
            "\n",
            value,
        )

        value = re.sub(
            r"(?i)</div\s*>",
            "\n",
            value,
        )

        value = re.sub(
            r"<[^>]+>",
            " ",
            value,
        )

        value = html.unescape(
            value
        )

        value = re.sub(
            r"[ \t]+",
            " ",
            value,
        )

        value = re.sub(
            r"\n[ \t]+",
            "\n",
            value,
        )

        value = re.sub(
            r"\n{3,}",
            "\n\n",
            value,
        )

        return value.strip()

    def normalize_text(
        self,
        value: str,
    ) -> str:

        if not value:
            return ""

        value = value.replace(
            "\x00",
            " ",
        )

        value = value.replace(
            "\r\n",
            "\n",
        )

        value = value.replace(
            "\r",
            "\n",
        )

        value = re.sub(
            r"[ \t]+\n",
            "\n",
            value,
        )

        value = re.sub(
            r"\n{3,}",
            "\n\n",
            value,
        )

        return value.strip()

    # =========================================================
    # ADDRESS PARSING
    # =========================================================

    def parse_addresses(
        self,
        value: str | None,
    ) -> list[dict[str, str]]:

        if not value:
            return []

        decoded = self.decode_header_value(
            value
        )

        result = []

        try:
            addresses = getaddresses(
                [decoded]
            )
        except Exception:
            addresses = []

        for name, email_address in addresses:

            name = (
                self.decode_header_value(
                    name
                )
                if name
                else ""
            )

            email_address = (
                email_address.strip()
                if email_address
                else ""
            )

            if not name and not email_address:
                continue

            result.append(
                {
                    "name": name,
                    "email": email_address,
                }
            )

        return result

    # =========================================================
    # DATE PARSING
    # =========================================================

    def parse_date(
        self,
        value: str | None,
    ) -> datetime | None:

        if not value:
            return None

        try:
            parsed = parsedate_to_datetime(
                value
            )

            if parsed is None:
                return None

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed.astimezone(
                timezone.utc
            )

        except Exception:
            return None

    # =========================================================
    # HEADER EXTRACTION
    # =========================================================

    def extract_headers(
        self,
        message,
    ) -> dict[str, Any]:

        headers = {}

        for name, value in message.items():

            decoded_name = str(
                name
            ).strip()

            decoded_value = (
                self.decode_header_value(
                    value
                )
            )

            if decoded_name.lower() in {
                key.lower()
                for key in headers
            }:
                continue

            headers[
                decoded_name
            ] = decoded_value

        return headers

    def header(
        self,
        message,
        name: str,
    ) -> str:

        value = message.get(
            name,
            "",
        )

        return self.decode_header_value(
            value
        )

    # =========================================================
    # MIME CONTENT
    # =========================================================

    def extract_mime_content(
        self,
        message,
    ) -> dict[str, Any]:

        plain_parts = []
        html_parts = []
        attachments = []

        for part in message.walk():

            if part.is_multipart():
                continue

            content_type = (
                part.get_content_type()
                or ""
            ).lower()

            disposition = (
                part.get_content_disposition()
                or ""
            ).lower()

            filename = (
                part.get_filename()
            )

            if filename:
                filename = (
                    self.decode_header_value(
                        filename
                    )
                )

            is_attachment = (
                disposition == "attachment"
                or bool(filename)
            )

            if is_attachment:

                attachments.append(
                    self.extract_attachment_info(
                        part,
                        len(attachments) + 1,
                    )
                )

                continue

            if content_type == "text/plain":

                text = self.decode_payload(
                    part
                )

                if text:
                    plain_parts.append(
                        text
                    )

                continue

            if content_type == "text/html":

                text = self.decode_payload(
                    part
                )

                if text:
                    html_parts.append(
                        text
                    )

                continue

        body_text = self.normalize_text(
            "\n\n".join(
                plain_parts
            )
        )

        body_html = "\n\n".join(
            html_parts
        ).strip()

        if not body_text and body_html:
            body_text = self.normalize_text(
                self.strip_html(
                    body_html
                )
            )

        return {
            "body_text": body_text,
            "body_html": body_html,
            "attachments": attachments,
        }

    def extract_attachment_info(
        self,
        part,
        attachment_number: int,
    ) -> dict[str, Any]:

        filename = part.get_filename()

        if filename:
            filename = (
                self.decode_header_value(
                    filename
                )
            )
        else:
            filename = (
                "attachment_"
                + str(attachment_number)
            )

        content_type = (
            part.get_content_type()
            or "application/octet-stream"
        )

        content_id = (
            part.get(
                "Content-ID",
                "",
            )
            or ""
        )

        content_id = (
            self.decode_header_value(
                content_id
            )
        )

        data = b""

        try:
            payload = part.get_payload(
                decode=True
            )

            if isinstance(
                payload,
                bytes,
            ):
                data = payload

            elif isinstance(
                payload,
                str,
            ):
                data = payload.encode(
                    "utf-8",
                    errors="replace",
                )

        except Exception:
            data = b""

        return {
            "attachment_number": attachment_number,
            "attachment_id": (
                "mime-"
                + str(attachment_number)
            ),
            "file_name": filename,
            "mime_type": content_type,
            "content_id": content_id,
            "size_bytes": len(data),
            "data": data,
        }

    # =========================================================
    # MESSAGE PARSING
    # =========================================================

    def parse_eml(
        self,
        eml_path: Path,
    ) -> dict[str, Any]:

        raw_bytes = eml_path.read_bytes()

        message = BytesParser(
            policy=policy.default
        ).parsebytes(
            raw_bytes
        )

        headers = self.extract_headers(
            message
        )

        subject = self.header(
            message,
            "Subject",
        )

        sender_list = self.parse_addresses(
            self.header(
                message,
                "From",
            )
        )

        to_list = self.parse_addresses(
            self.header(
                message,
                "To",
            )
        )

        cc_list = self.parse_addresses(
            self.header(
                message,
                "Cc",
            )
        )

        bcc_list = self.parse_addresses(
            self.header(
                message,
                "Bcc",
            )
        )

        reply_to_list = self.parse_addresses(
            self.header(
                message,
                "Reply-To",
            )
        )

        mime_content = (
            self.extract_mime_content(
                message
            )
        )

        body_text = mime_content[
            "body_text"
        ]

        body_html = mime_content[
            "body_html"
        ]

        attachments = mime_content[
            "attachments"
        ]

        sender_name = ""

        sender_email = ""

        if sender_list:

            sender_name = sender_list[0].get(
                "name",
                "",
            )

            sender_email = sender_list[0].get(
                "email",
                "",
            )

        date_header = self.header(
            message,
            "Date",
        )

        date_sent = self.parse_date(
            date_header
        )

        mime_message_id = self.header(
            message,
            "Message-ID",
        )

        in_reply_to = self.header(
            message,
            "In-Reply-To",
        )

        references_header = self.header(
            message,
            "References",
        )

        content_type = (
            message.get_content_type()
            or ""
        )

        charset = (
            message.get_content_charset()
            or ""
        )

        search_text = self.build_search_text(
            subject=subject,
            sender_name=sender_name,
            sender_email=sender_email,
            recipients=to_list,
            cc=cc_list,
            bcc=bcc_list,
            reply_to=reply_to_list,
            body_text=body_text,
            body_html=body_html,
            attachments=attachments,
        )

        return {
            "raw_bytes": raw_bytes,
            "raw_sha256": self.sha256_bytes(
                raw_bytes
            ),
            "raw_size": len(
                raw_bytes
            ),
            "mime_message_id": mime_message_id,
            "subject": subject,
            "sender_name": sender_name,
            "sender_email": sender_email,
            "recipients": to_list,
            "cc_recipients": cc_list,
            "bcc_recipients": bcc_list,
            "reply_to": reply_to_list,
            "date_header": date_header,
            "date_sent": date_sent,
            "in_reply_to": in_reply_to,
            "references_header": references_header,
            "content_type": content_type,
            "charset": charset,
            "body_text": body_text,
            "body_html": body_html,
            "search_text": search_text,
            "attachments": attachments,
            "headers": headers,
        }

    # =========================================================
    # SEARCH TEXT
    # =========================================================

    def build_search_text(
        self,
        subject: str,
        sender_name: str,
        sender_email: str,
        recipients: list[dict[str, str]],
        cc: list[dict[str, str]],
        bcc: list[dict[str, str]],
        reply_to: list[dict[str, str]],
        body_text: str,
        body_html: str,
        attachments: list[dict[str, Any]],
    ) -> str:

        parts = []

        parts.append(
            subject
        )

        parts.append(
            sender_name
        )

        parts.append(
            sender_email
        )

        def add_addresses(
            values: list[dict[str, str]],
        ) -> None:

            for item in values:

                parts.append(
                    item.get(
                        "name",
                        "",
                    )
                )

                parts.append(
                    item.get(
                        "email",
                        "",
                    )
                )

        add_addresses(
            recipients
        )

        add_addresses(
            cc
        )

        add_addresses(
            bcc
        )

        add_addresses(
            reply_to
        )

        parts.append(
            body_text
        )

        if body_html:
            parts.append(
                self.strip_html(
                    body_html
                )
            )

        for attachment in attachments:

            parts.append(
                attachment.get(
                    "file_name",
                    "",
                )
            )

            parts.append(
                attachment.get(
                    "mime_type",
                    "",
                )
            )

        value = "\n".join(
            str(part)
            for part in parts
            if part
        )

        value = self.normalize_text(
            value
        )

        if len(value) > MAX_SEARCH_TEXT_LENGTH:
            value = value[
                :MAX_SEARCH_TEXT_LENGTH
            ]

        return value

    # =========================================================
    # MESSAGE ID / DATABASE MATCH
    # =========================================================

    def extract_gmail_message_id_from_path(
        self,
        eml_path: Path,
    ) -> str:

        return eml_path.parent.name

    def find_database_message(
        self,
        gmail_message_key: str,
    ) -> dict[str, Any] | None:

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                if self.gmail_account_id is not None:

                    cursor.execute(
                        """
                        SELECT
                            id,
                            gmail_account_id,
                            message_id,
                            thread_id,
                            history_id,
                            metadata
                        FROM gmail_messages
                        WHERE gmail_account_id = %s
                          AND message_id = %s
                        LIMIT 1
                        """,
                        (
                            self.gmail_account_id,
                            gmail_message_key,
                        ),
                    )

                else:

                    cursor.execute(
                        """
                        SELECT
                            id,
                            gmail_account_id,
                            message_id,
                            thread_id,
                            history_id,
                            metadata
                        FROM gmail_messages
                        WHERE message_id = %s
                        ORDER BY id
                        LIMIT 1
                        """,
                        (
                            gmail_message_key,
                        ),
                    )

                row = cursor.fetchone()

                if not row:
                    return None

                return {
                    "id": row[0],
                    "gmail_account_id": row[1],
                    "message_id": row[2],
                    "thread_id": row[3],
                    "history_id": row[4],
                    "metadata": row[5],
                }

        finally:
            conn.close()

    # =========================================================
    # PARSED STATUS
    # =========================================================

    def is_already_parsed(
        self,
        gmail_message_db_id: int,
    ) -> bool:

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        id
                    FROM gmail_parsed_messages
                    WHERE gmail_message_id = %s
                    LIMIT 1
                    """,
                    (
                        gmail_message_db_id,
                    ),
                )

                return (
                    cursor.fetchone()
                    is not None
                )

        finally:
            conn.close()

    # =========================================================
    # LOCAL ATTACHMENTS
    # =========================================================

    def attachment_directory(
        self,
        eml_path: Path,
    ) -> Path:

        return (
            eml_path.parent
            / "attachments"
        )

    def safe_attachment_filename(
        self,
        filename: str,
        number: int,
    ) -> str:

        filename = str(
            filename or ""
        ).strip()

        filename = Path(
            filename
        ).name

        filename = re.sub(
            r"[^\w.\- ()@\[\]]+",
            "_",
            filename,
            flags=re.UNICODE,
        )

        filename = filename.strip(
            " ."
        )

        if not filename:
            filename = (
                "attachment_"
                + str(number)
            )

        return filename

    def save_attachment(
        self,
        eml_path: Path,
        attachment: dict[str, Any],
    ) -> dict[str, Any]:

        data = attachment.get(
            "data",
            b"",
        )

        content_hash = self.sha256_bytes(
            data
        )

        directory = (
            self.attachment_directory(
                eml_path
            )
        )

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        filename = (
            self.safe_attachment_filename(
                attachment.get(
                    "file_name",
                    "",
                ),
                attachment.get(
                    "attachment_number",
                    1,
                ),
            )
        )

        target = (
            directory
            / filename
        )

        if target.exists():

            try:
                existing_hash = (
                    self.sha256_bytes(
                        target.read_bytes()
                    )
                )
            except Exception:
                existing_hash = ""

            if existing_hash == content_hash:

                self.stats[
                    "attachments_existing"
                ] += 1

                return {
                    "local_path": str(
                        target
                    ),
                    "content_hash": content_hash,
                    "size_bytes": len(data),
                    "status": "existing",
                }

            stem = target.stem
            suffix = target.suffix

            target = (
                directory
                / (
                    stem
                    + "_"
                    + content_hash[:12]
                    + suffix
                )
            )

        temp_path = target.with_suffix(
            target.suffix
            + ".tmp"
        )

        temp_path.write_bytes(
            data
        )

        temp_path.replace(
            target
        )

        self.stats[
            "attachments_saved"
        ] += 1

        return {
            "local_path": str(
                target
            ),
            "content_hash": content_hash,
            "size_bytes": len(data),
            "status": "saved",
        }

    # =========================================================
    # ATTACHMENT DATABASE
    # =========================================================

    def save_attachment_database_record(
        self,
        message_db_id: int,
        attachment: dict[str, Any],
        saved_info: dict[str, Any],
    ) -> None:

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                metadata = {
                    "parser_version": PARSER_VERSION,
                    "attachment_number": attachment.get(
                        "attachment_number"
                    ),
                    "content_id": attachment.get(
                        "content_id",
                        "",
                    ),
                    "local_path": saved_info.get(
                        "local_path",
                        "",
                    ),
                    "content_hash": saved_info.get(
                        "content_hash",
                        "",
                    ),
                    "source": "message.eml",
                }

                cursor.execute(
                    """
                    INSERT INTO gmail_attachments (
                        gmail_message_id,
                        attachment_id,
                        file_name,
                        mime_type,
                        file_size,
                        content_hash,
                        local_file_id,
                        saved_to_local,
                        metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, NULL, TRUE, %s
                    )
                    ON CONFLICT (
                        gmail_message_id,
                        attachment_id
                    )
                    DO UPDATE SET
                        file_name = EXCLUDED.file_name,
                        mime_type = EXCLUDED.mime_type,
                        file_size = EXCLUDED.file_size,
                        content_hash = EXCLUDED.content_hash,
                        saved_to_local = TRUE,
                        metadata = EXCLUDED.metadata
                    """,
                    (
                        message_db_id,
                        attachment.get(
                            "attachment_id",
                            "",
                        ),
                        attachment.get(
                            "file_name",
                            "",
                        ),
                        attachment.get(
                            "mime_type",
                            "application/octet-stream",
                        ),
                        saved_info.get(
                            "size_bytes",
                            0,
                        ),
                        saved_info.get(
                            "content_hash",
                            "",
                        ),
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

    # =========================================================
    # SAVE PARSED MESSAGE
    # =========================================================

    def save_parsed_message(
        self,
        database_message: dict[str, Any],
        parsed: dict[str, Any],
        eml_path: Path,
    ) -> None:

        message_db_id = database_message[
            "id"
        ]

        gmail_message_key = str(
            database_message[
                "message_id"
            ]
        )

        raw_sha256 = parsed[
            "raw_sha256"
        ]

        raw_size = parsed[
            "raw_size"
        ]

        attachment_metadata = []

        for attachment in parsed[
            "attachments"
        ]:

            attachment_metadata.append(
                {
                    "attachment_id": attachment.get(
                        "attachment_id",
                        "",
                    ),
                    "file_name": attachment.get(
                        "file_name",
                        "",
                    ),
                    "mime_type": attachment.get(
                        "mime_type",
                        "",
                    ),
                    "content_id": attachment.get(
                        "content_id",
                        "",
                    ),
                    "size_bytes": attachment.get(
                        "size_bytes",
                        0,
                    ),
                }
            )

        metadata = {
            "source": "gmail",
            "parser": "gmail_parser.py",
            "parser_version": PARSER_VERSION,
            "gmail_message_key": gmail_message_key,
            "gmail_message_db_id": message_db_id,
            "raw_eml_path": str(
                eml_path
            ),
            "raw_sha256": raw_sha256,
            "raw_size": raw_size,
            "mime_message_id": parsed.get(
                "mime_message_id",
                "",
            ),
            "date_header": parsed.get(
                "date_header",
                "",
            ),
            "content_type": parsed.get(
                "content_type",
                "",
            ),
            "charset": parsed.get(
                "charset",
                "",
            ),
            "attachments": attachment_metadata,
            "parsed_at": self.utc_now().isoformat(),
        }

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    INSERT INTO gmail_parsed_messages (
                        gmail_message_id,
                        gmail_message_key,
                        mime_message_id,
                        thread_id,
                        subject,
                        sender_name,
                        sender_email,
                        recipients,
                        cc_recipients,
                        bcc_recipients,
                        reply_to,
                        date_header,
                        date_sent,
                        in_reply_to,
                        references_header,
                        content_type,
                        charset,
                        body_text,
                        body_html,
                        search_text,
                        raw_sha256,
                        raw_size,
                        has_attachments,
                        attachment_count,
                        headers,
                        metadata,
                        parser_version,
                        parsed_at,
                        updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        CURRENT_TIMESTAMP
                    )

                    ON CONFLICT (
                        gmail_message_id
                    )
                    DO UPDATE SET
                        gmail_message_key =
                            EXCLUDED.gmail_message_key,
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
                        date_header =
                            EXCLUDED.date_header,
                        date_sent =
                            EXCLUDED.date_sent,
                        in_reply_to =
                            EXCLUDED.in_reply_to,
                        references_header =
                            EXCLUDED.references_header,
                        content_type =
                            EXCLUDED.content_type,
                        charset =
                            EXCLUDED.charset,
                        body_text =
                            EXCLUDED.body_text,
                        body_html =
                            EXCLUDED.body_html,
                        search_text =
                            EXCLUDED.search_text,
                        raw_sha256 =
                            EXCLUDED.raw_sha256,
                        raw_size =
                            EXCLUDED.raw_size,
                        has_attachments =
                            EXCLUDED.has_attachments,
                        attachment_count =
                            EXCLUDED.attachment_count,
                        headers =
                            EXCLUDED.headers,
                        metadata =
                            EXCLUDED.metadata,
                        parser_version =
                            EXCLUDED.parser_version,
                        parsed_at =
                            EXCLUDED.parsed_at,
                        updated_at =
                            CURRENT_TIMESTAMP
                    """,
                    (
                        message_db_id,
                        gmail_message_key,
                        parsed.get(
                            "mime_message_id",
                            "",
                        ),
                        database_message.get(
                            "thread_id",
                            "",
                        ),
                        parsed.get(
                            "subject",
                            "",
                        ),
                        parsed.get(
                            "sender_name",
                            "",
                        ),
                        parsed.get(
                            "sender_email",
                            "",
                        ),
                        json.dumps(
                            parsed.get(
                                "recipients",
                                [],
                            ),
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            parsed.get(
                                "cc_recipients",
                                [],
                            ),
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            parsed.get(
                                "bcc_recipients",
                                [],
                            ),
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            parsed.get(
                                "reply_to",
                                [],
                            ),
                            ensure_ascii=False,
                        ),
                        parsed.get(
                            "date_header",
                            "",
                        ),
                        parsed.get(
                            "date_sent"
                        ),
                        parsed.get(
                            "in_reply_to",
                            "",
                        ),
                        parsed.get(
                            "references_header",
                            "",
                        ),
                        parsed.get(
                            "content_type",
                            "",
                        ),
                        parsed.get(
                            "charset",
                            "",
                        ),
                        parsed.get(
                            "body_text",
                            "",
                        ),
                        parsed.get(
                            "body_html",
                            "",
                        ),
                        parsed.get(
                            "search_text",
                            "",
                        ),
                        raw_sha256,
                        raw_size,
                        bool(
                            parsed.get(
                                "attachments"
                            )
                        ),
                        len(
                            parsed.get(
                                "attachments",
                                [],
                            )
                        ),
                        json.dumps(
                            parsed.get(
                                "headers",
                                {},
                            ),
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            metadata,
                            ensure_ascii=False,
                        ),
                        PARSER_VERSION,
                        self.utc_now(),
                    ),
                )

                cursor.execute(
                    """
                    UPDATE gmail_messages
                    SET
                        sender = %s,
                        recipients = %s,
                        cc = %s,
                        bcc = %s,
                        subject = %s,
                        body_text = %s,
                        received_at = %s,
                        metadata = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (
                        parsed.get(
                            "sender_email",
                            "",
                        ),
                        self.format_addresses(
                            parsed.get(
                                "recipients",
                                [],
                            )
                        ),
                        self.format_addresses(
                            parsed.get(
                                "cc_recipients",
                                [],
                            )
                        ),
                        self.format_addresses(
                            parsed.get(
                                "bcc_recipients",
                                [],
                            )
                        ),
                        parsed.get(
                            "subject",
                            "",
                        ),
                        parsed.get(
                            "body_text",
                            "",
                        ),
                        parsed.get(
                            "date_sent"
                        ),
                        json.dumps(
                            metadata,
                            ensure_ascii=False,
                        ),
                        message_db_id,
                    ),
                )

                conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

    # =========================================================
    # ADDRESS FORMAT
    # =========================================================

    def format_addresses(
        self,
        values: list[dict[str, str]],
    ) -> str:

        result = []

        for item in values:

            name = item.get(
                "name",
                "",
            ).strip()

            email_address = item.get(
                "email",
                "",
            ).strip()

            if name and email_address:
                result.append(
                    name
                    + " <"
                    + email_address
                    + ">"
                )

            elif email_address:
                result.append(
                    email_address
                )

            elif name:
                result.append(
                    name
                )

        return ", ".join(
            result
        )

    # =========================================================
    # LABEL RELATIONSHIPS
    # =========================================================

    def refresh_message_metadata(
        self,
        message_db_id: int,
        parsed: dict[str, Any],
    ) -> None:

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT metadata
                    FROM gmail_messages
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (
                        message_db_id,
                    ),
                )

                row = cursor.fetchone()

                current_metadata = {}

                if row:

                    value = row[0]

                    if isinstance(
                        value,
                        dict,
                    ):
                        current_metadata = value

                    elif isinstance(
                        value,
                        str,
                    ):
                        try:
                            current_metadata = json.loads(
                                value
                            )
                        except Exception:
                            current_metadata = {}

                current_metadata[
                    "parsing"
                ] = {
                    "status": "PARSED",
                    "parser_version": PARSER_VERSION,
                    "parsed_at": self.utc_now().isoformat(),
                    "raw_sha256": parsed.get(
                        "raw_sha256",
                        "",
                    ),
                    "raw_size": parsed.get(
                        "raw_size",
                        0,
                    ),
                    "mime_message_id": parsed.get(
                        "mime_message_id",
                        "",
                    ),
                    "attachment_count": len(
                        parsed.get(
                            "attachments",
                            [],
                        )
                    ),
                }

                cursor.execute(
                    """
                    UPDATE gmail_messages
                    SET metadata = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (
                        json.dumps(
                            current_metadata,
                            ensure_ascii=False,
                        ),
                        message_db_id,
                    ),
                )

                conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

    # =========================================================
    # ONE MESSAGE
    # =========================================================

    def process_message(
        self,
        eml_path: Path,
    ) -> str:

        gmail_message_key = (
            self.extract_gmail_message_id_from_path(
                eml_path
            )
        )

        self.log("")
        self.log(
            "[MESSAGE] "
            + gmail_message_key
        )

        database_message = (
            self.find_database_message(
                gmail_message_key
            )
        )

        if not database_message:

            self.stats[
                "messages_missing_database"
            ] += 1

            self.log(
                "[WARNING] Message exists locally "
                "but was not found in gmail_messages: "
                + gmail_message_key
            )

            return "missing_database"

        message_db_id = database_message[
            "id"
        ]

        if (
            not self.force
            and self.is_already_parsed(
                message_db_id
            )
        ):

            self.stats[
                "messages_already_parsed"
            ] += 1

            self.log(
                "[MESSAGE] Already parsed"
            )

            return "already_parsed"

        try:

            parsed = self.parse_eml(
                eml_path
            )

            self.stats[
                "attachments_found"
            ] += len(
                parsed.get(
                    "attachments",
                    [],
                )
            )

            self.log(
                "[PARSE] Subject: "
                + parsed.get(
                    "subject",
                    "",
                )
            )

            self.log(
                "[PARSE] From: "
                + parsed.get(
                    "sender_email",
                    "",
                )
            )

            self.log(
                "[PARSE] Text length: "
                + str(
                    len(
                        parsed.get(
                            "body_text",
                            "",
                        )
                    )
                )
            )

            self.log(
                "[PARSE] Attachments: "
                + str(
                    len(
                        parsed.get(
                            "attachments",
                            [],
                        )
                    )
                )
            )

            self.save_parsed_message(
                database_message,
                parsed,
                eml_path,
            )

            for attachment in parsed.get(
                "attachments",
                [],
            ):

                try:

                    saved_info = (
                        self.save_attachment(
                            eml_path,
                            attachment,
                        )
                    )

                    self.save_attachment_database_record(
                        message_db_id,
                        attachment,
                        saved_info,
                    )

                except Exception as exc:

                    self.stats[
                        "attachments_failed"
                    ] += 1

                    self.log(
                        "[ATTACHMENT ERROR] "
                        + str(exc)
                    )

            self.refresh_message_metadata(
                message_db_id,
                parsed,
            )

            self.stats[
                "messages_parsed"
            ] += 1

            self.log(
                "[MESSAGE] PARSED"
            )

            return "parsed"

        except Exception as exc:

            self.stats[
                "messages_failed"
            ] += 1

            self.log(
                "[ERROR] "
                + gmail_message_key
                + ": "
                + type(exc).__name__
                + ": "
                + str(exc)
            )

            return "failed"

    # =========================================================
    # RUN
    # =========================================================

    def run(
        self,
        account_email: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:

        if account_email:

            self.account_email = (
                account_email.strip()
            )

        if not self.account_email:

            raise RuntimeError(
                "Gmail account email is required."
            )

        self.log("")
        self.log(
            "=" * 72
        )
        self.log(
            "STARTING GMAIL PARSE"
        )
        self.log(
            "=" * 72
        )

        self.log(
            "[ACCOUNT] "
            + self.account_email
        )

        self.log(
            "[STORAGE] "
            + str(
                self.storage_root
            )
        )

        self.load_database_context()

        self.ensure_parsed_table()

        files = (
            self.find_message_files(
                self.account_email
            )
        )

        if limit is not None:
            files = files[
                :limit
            ]

        self.stats[
            "messages_found"
        ] = len(files)

        self.log(
            "[FOUND] "
            + str(
                len(files)
            )
            + " message.eml files"
        )

        for index, eml_path in enumerate(
            files,
            1,
        ):

            self.log("")
            self.log(
                "[PROGRESS] "
                + str(index)
                + "/"
                + str(len(files))
            )

            self.process_message(
                eml_path
            )

        self.log("")
        self.log(
            "=" * 72
        )
        self.log(
            "GMAIL PARSE SUMMARY"
        )
        self.log(
            "=" * 72
        )

        self.log(
            "Messages found: "
            + str(
                self.stats[
                    "messages_found"
                ]
            )
        )

        self.log(
            "Messages parsed: "
            + str(
                self.stats[
                    "messages_parsed"
                ]
            )
        )

        self.log(
            "Already parsed: "
            + str(
                self.stats[
                    "messages_already_parsed"
                ]
            )
        )

        self.log(
            "Missing database row: "
            + str(
                self.stats[
                    "messages_missing_database"
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

        self.log(
            "Attachments found: "
            + str(
                self.stats[
                    "attachments_found"
                ]
            )
        )

        self.log(
            "Attachments saved: "
            + str(
                self.stats[
                    "attachments_saved"
                ]
            )
        )

        self.log(
            "Attachments already exist: "
            + str(
                self.stats[
                    "attachments_existing"
                ]
            )
        )

        self.log(
            "Attachment errors: "
            + str(
                self.stats[
                    "attachments_failed"
                ]
            )
        )

        self.log(
            "=" * 72
        )

        return dict(
            self.stats
        )


def main() -> None:

    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Alcalay Gmail EML parser"
        )
    )

    parser.add_argument(
        "--account",
        required=True,
        help=(
            "Gmail account email"
        ),
    )

    parser.add_argument(
        "--storage-root",
        default=None,
        help=(
            "Gmail storage root"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum number of messages"
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Parse messages again even if already parsed"
        ),
    )

    args = parser.parse_args()

    parser_instance = GmailParser(
        account_email=args.account,
        storage_root=args.storage_root,
        force=args.force,
    )

    parser_instance.run(
        limit=args.limit
    )


if __name__ == "__main__":
    main()