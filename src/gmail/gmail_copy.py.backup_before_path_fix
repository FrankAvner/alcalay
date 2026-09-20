from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from database.connection import connect
from gmail.gmail_connection import GmailConnection


DRY_RUN = True

DEFAULT_STORAGE_ROOT = PROJECT_ROOT / "storage" / "gmail"


class GmailCopy:

    def __init__(
        self,
        account_email: str,
        dry_run: bool = DRY_RUN,
        storage_root: str | Path | None = None,
    ):
        self.account_email = account_email
        self.dry_run = dry_run

        if storage_root:
            self.storage_root = Path(storage_root)
        else:
            self.storage_root = DEFAULT_STORAGE_ROOT

        self.connection = GmailConnection(
            account_email
        )

        self.service = None

        self.gmail_account_id = None
        self.source_account_id = None
        self.source_id = None

        self.label_rows = []

        self.stats = {
            "labels": 0,
            "messages_found": 0,
            "unique_messages": 0,
            "messages_new": 0,
            "messages_existing": 0,
            "messages_with_multiple_labels": 0,
            "attachments": 0,
            "attachments_new": 0,
            "attachments_existing": 0,
            "errors": 0,
        }

    def log(self, message: str) -> None:
        print(
            message,
            flush=True,
        )

    def utc_now(self) -> datetime:
        return datetime.now(
            timezone.utc
        )

    def utc_iso(self) -> str:
        return self.utc_now().isoformat()

    def safe_name(self, value: str) -> str:
        value = str(value or "").strip()

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

    def sha256_bytes(
        self,
        data: bytes,
    ) -> str:
        return hashlib.sha256(
            data
        ).hexdigest()

    def decode_base64url(
        self,
        value: str | None,
    ) -> bytes:
        if not value:
            return b""

        padding = (
            "="
            * (
                4
                - len(value) % 4
            )
            % 4
        )

        return base64.urlsafe_b64decode(
            value + padding
        )

    def get_db_connection(self):
        return connect()

    def load_database_context(
        self,
    ) -> None:

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        ga.id,
                        ga.source_account_id,
                        sa.source_id
                    FROM gmail_accounts ga
                    JOIN source_accounts sa
                        ON sa.id = ga.source_account_id
                    WHERE LOWER(ga.email) = LOWER(%s)
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
                self.source_account_id = row[1]
                self.source_id = row[2]

        finally:
            conn.close()

    def load_selected_labels(
        self,
    ) -> list[dict[str, Any]]:

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        id,
                        label_id,
                        label_name,
                        selected_for_sync,
                        enabled
                    FROM gmail_labels
                    WHERE gmail_account_id = %s
                      AND selected_for_sync = TRUE
                      AND enabled = TRUE
                    ORDER BY id
                    """,
                    (
                        self.gmail_account_id,
                    ),
                )

                rows = cursor.fetchall()

                self.label_rows = [
                    {
                        "id": row[0],
                        "label_id": row[1],
                        "label_name": row[2],
                        "selected_for_sync": row[3],
                        "enabled": row[4],
                    }
                    for row in rows
                ]

                return self.label_rows

        finally:
            conn.close()

    def connect_gmail(self) -> None:

        self.log(
            "[GMAIL] Connecting: "
            + self.account_email
        )

        result = self.connection.connect(
            self.account_email
        )

        if result is False:
            raise RuntimeError(
                "Gmail connection failed."
            )

        self.service = self.connection.service

        if self.service is None:
            raise RuntimeError(
                "Gmail service was not created."
            )

        self.log(
            "[GMAIL] Connected."
        )

    def list_label_message_ids(
        self,
        label_id: str,
    ) -> list[str]:

        if self.service is None:
            raise RuntimeError(
                "Gmail service is not connected."
            )

        message_ids = []

        page_token = None

        while True:

            request = (
                self.service.users()
                .messages()
                .list(
                    userId="me",
                    labelIds=[label_id],
                    maxResults=500,
                    pageToken=page_token,
                )
            )

            response = request.execute()

            for item in response.get(
                "messages",
                [],
            ):

                message_id = item.get(
                    "id"
                )

                if message_id:
                    message_ids.append(
                        message_id
                    )

            page_token = response.get(
                "nextPageToken"
            )

            if not page_token:
                break

        return message_ids

    def collect_selected_messages(
        self,
    ) -> dict[str, list[dict[str, Any]]]:

        message_labels = {}

        self.stats["labels"] = len(
            self.label_rows
        )

        for label in self.label_rows:

            label_id = label["label_id"]
            label_name = label["label_name"]

            self.log(
                ""
            )

            self.log(
                "[LABEL] "
                + label_name
                + " ["
                + label_id
                + "]"
            )

            ids = self.list_label_message_ids(
                label_id
            )

            self.log(
                "[LABEL] Messages found: "
                + str(len(ids))
            )

            self.stats[
                "messages_found"
            ] += len(ids)

            for message_id in ids:

                message_labels.setdefault(
                    message_id,
                    [],
                )

                existing_ids = {
                    item["label_id"]
                    for item in message_labels[
                        message_id
                    ]
                }

                if label_id not in existing_ids:

                    message_labels[
                        message_id
                    ].append(
                        {
                            "label_id": label_id,
                            "label_name": label_name,
                            "db_label_id": label["id"],
                        }
                    )

        self.stats[
            "unique_messages"
        ] = len(
            message_labels
        )

        self.stats[
            "messages_with_multiple_labels"
        ] = sum(
            1
            for labels in message_labels.values()
            if len(labels) > 1
        )

        return message_labels

    def get_message_full(
        self,
        message_id: str,
    ) -> dict[str, Any]:

        if self.service is None:
            raise RuntimeError(
                "Gmail service is not connected."
            )

        return (
            self.service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="full",
            )
            .execute()
        )

    def get_message_raw(
        self,
        message_id: str,
    ) -> bytes:

        if self.service is None:
            raise RuntimeError(
                "Gmail service is not connected."
            )

        response = (
            self.service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="raw",
            )
            .execute()
        )

        raw_value = response.get(
            "raw"
        )

        if not raw_value:
            raise RuntimeError(
                "Gmail returned no raw MIME data "
                "for message "
                + message_id
            )

        return self.decode_base64url(
            raw_value
        )

    def header_value(
        self,
        headers: list[dict[str, Any]],
        name: str,
    ) -> str:

        wanted = name.lower()

        for header in headers:

            if (
                str(
                    header.get(
                        "name",
                        "",
                    )
                ).lower()
                == wanted
            ):
                return str(
                    header.get(
                        "value",
                        "",
                    )
                )

        return ""

    def extract_full_metadata(
        self,
        full_message: dict[str, Any],
    ) -> dict[str, Any]:

        payload = full_message.get(
            "payload",
            {},
        )

        headers = payload.get(
            "headers",
            [],
        )

        return {
            "message_id": full_message.get(
                "id",
                "",
            ),
            "thread_id": full_message.get(
                "threadId",
                "",
            ),
            "history_id": full_message.get(
                "historyId",
                "",
            ),
            "internal_date": full_message.get(
                "internalDate"
            ),
            "subject": self.header_value(
                headers,
                "Subject",
            ),
            "sender": self.header_value(
                headers,
                "From",
            ),
            "recipients": self.header_value(
                headers,
                "To",
            ),
            "cc": self.header_value(
                headers,
                "Cc",
            ),
            "bcc": self.header_value(
                headers,
                "Bcc",
            ),
            "date_header": self.header_value(
                headers,
                "Date",
            ),
            "message_id_header": self.header_value(
                headers,
                "Message-ID",
            ),
            "references": self.header_value(
                headers,
                "References",
            ),
            "in_reply_to": self.header_value(
                headers,
                "In-Reply-To",
            ),
            "snippet": full_message.get(
                "snippet",
                "",
            ),
        }

    def decode_mime_part(
        self,
        part,
    ) -> bytes:

        body = part.get_payload(
            decode=True
        )

        if isinstance(
            body,
            bytes,
        ):
            return body

        encoded = (
            part.get_payload()
        )

        if isinstance(
            encoded,
            str,
        ):
            try:
                return base64.b64decode(
                    encoded
                )
            except Exception:
                return encoded.encode(
                    "utf-8",
                    errors="replace",
                )

        return b""

    def extract_mime_content(
        self,
        raw_bytes: bytes,
    ) -> dict[str, Any]:

        message = BytesParser(
            policy=policy.default
        ).parsebytes(
            raw_bytes
        )

        plain_parts = []
        html_parts = []
        attachments = []

        if message.is_multipart():

            parts = message.walk()

        else:

            parts = [
                message
            ]

        for part in parts:

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
                or ""
            )

            is_attachment = (
                disposition == "attachment"
                or bool(filename)
            )

            if is_attachment:

                attachments.append(
                    {
                        "filename": filename,
                        "mime_type": content_type,
                        "content_id": part.get(
                            "Content-ID",
                            "",
                        ),
                        "content_disposition": disposition,
                    }
                )

                continue

            if content_type not in (
                "text/plain",
                "text/html",
            ):
                continue

            try:
                content = part.get_content()
            except Exception:
                raw_part = (
                    self.decode_mime_part(
                        part
                    )
                )

                content = raw_part.decode(
                    "utf-8",
                    errors="replace",
                )

            if not isinstance(
                content,
                str,
            ):
                content = str(
                    content
                )

            if content_type == "text/plain":
                plain_parts.append(
                    content
                )

            elif content_type == "text/html":
                html_parts.append(
                    content
                )

        body_text = "\n\n".join(
            item.strip()
            for item in plain_parts
            if item and item.strip()
        )

        body_html = "\n\n".join(
            item.strip()
            for item in html_parts
            if item and item.strip()
        )

        return {
            "body_text": body_text,
            "body_html": body_html,
            "attachments": attachments,
        }

    def collect_attachment_parts(
        self,
        full_message: dict[str, Any],
    ) -> list[dict[str, Any]]:

        result = []

        def walk(part):

            if not isinstance(
                part,
                dict,
            ):
                return

            body = part.get(
                "body",
                {},
            )

            filename = (
                part.get(
                    "filename",
                    "",
                )
                or ""
            )

            attachment_id = body.get(
                "attachmentId"
            )

            mime_type = (
                part.get(
                    "mimeType",
                    "application/octet-stream",
                )
                or "application/octet-stream"
            )

            if (
                filename
                and attachment_id
            ):

                result.append(
                    {
                        "attachment_id": attachment_id,
                        "file_name": filename,
                        "mime_type": mime_type,
                        "file_size": body.get(
                            "size"
                        ),
                    }
                )

            for child in part.get(
                "parts",
                [],
            ):

                walk(
                    child
                )

        walk(
            full_message.get(
                "payload",
                {},
            )
        )

        return result

    def message_exists(
        self,
        message_id: str,
    ) -> int | None:

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT id
                    FROM gmail_messages
                    WHERE gmail_account_id = %s
                      AND message_id = %s
                    LIMIT 1
                    """,
                    (
                        self.gmail_account_id,
                        message_id,
                    ),
                )

                row = cursor.fetchone()

                if row:
                    return row[0]

                return None

        finally:
            conn.close()

    def create_message(
        self,
        metadata: dict[str, Any],
        body_text: str,
        body_html: str,
        raw_path: str,
        html_path: str,
        text_path: str,
        raw_hash: str,
        raw_size: int,
        selected_labels: list[dict[str, Any]],
    ) -> int:

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                internal_date = (
                    metadata.get(
                        "internal_date"
                    )
                )

                received_at = None

                if internal_date:

                    try:
                        received_at = datetime.fromtimestamp(
                            int(
                                internal_date
                            )
                            / 1000,
                            tz=timezone.utc,
                        )
                    except Exception:
                        received_at = None

                message_metadata = {
                    "source": "gmail",
                    "raw_eml_path": raw_path,
                    "html_path": html_path,
                    "text_path": text_path,
                    "raw_sha256": raw_hash,
                    "raw_size": raw_size,
                    "message_id_header": metadata.get(
                        "message_id_header",
                        "",
                    ),
                    "date_header": metadata.get(
                        "date_header",
                        "",
                    ),
                    "references": metadata.get(
                        "references",
                        "",
                    ),
                    "in_reply_to": metadata.get(
                        "in_reply_to",
                        "",
                    ),
                    "selected_labels": [
                        {
                            "id": item["label_id"],
                            "name": item["label_name"],
                        }
                        for item in selected_labels
                    ],
                }

                cursor.execute(
                    """
                    INSERT INTO gmail_messages (
                        gmail_account_id,
                        message_id,
                        thread_id,
                        history_id,
                        internal_date,
                        sender,
                        recipients,
                        cc,
                        bcc,
                        subject,
                        snippet,
                        body_text,
                        received_at,
                        metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (
                        gmail_account_id,
                        message_id
                    )
                    DO UPDATE SET
                        thread_id = EXCLUDED.thread_id,
                        history_id = EXCLUDED.history_id,
                        internal_date = EXCLUDED.internal_date,
                        sender = EXCLUDED.sender,
                        recipients = EXCLUDED.recipients,
                        cc = EXCLUDED.cc,
                        bcc = EXCLUDED.bcc,
                        subject = EXCLUDED.subject,
                        snippet = EXCLUDED.snippet,
                        body_text = EXCLUDED.body_text,
                        received_at = EXCLUDED.received_at,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                    """,
                    (
                        self.gmail_account_id,
                        metadata.get(
                            "message_id",
                            "",
                        ),
                        metadata.get(
                            "thread_id",
                            "",
                        ),
                        metadata.get(
                            "history_id",
                            "",
                        ),
                        received_at,
                        metadata.get(
                            "sender",
                            "",
                        ),
                        metadata.get(
                            "recipients",
                            "",
                        ),
                        metadata.get(
                            "cc",
                            "",
                        ),
                        metadata.get(
                            "bcc",
                            "",
                        ),
                        metadata.get(
                            "subject",
                            "",
                        ),
                        metadata.get(
                            "snippet",
                            "",
                        ),
                        body_text,
                        received_at,
                        json.dumps(
                            message_metadata,
                            ensure_ascii=False,
                        ),
                    ),
                )

                row = cursor.fetchone()

                if not row:
                    raise RuntimeError(
                        "Could not create or update gmail_messages."
                    )

                message_db_id = row[0]

                for label in selected_labels:

                    cursor.execute(
                        """
                        INSERT INTO gmail_message_labels (
                            message_id,
                            label_id
                        )
                        VALUES (
                            %s,
                            %s
                        )
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            message_db_id,
                            label["db_label_id"],
                        ),
                    )

                conn.commit()

                return message_db_id

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

    def add_label_relationships(
        self,
        message_db_id: int,
        selected_labels: list[dict[str, Any]],
    ) -> None:

        if self.dry_run:
            return

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                for label in selected_labels:

                    cursor.execute(
                        """
                        INSERT INTO gmail_message_labels (
                            message_id,
                            label_id
                        )
                        VALUES (
                            %s,
                            %s
                        )
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            message_db_id,
                            label["db_label_id"],
                        ),
                    )

                conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

    def save_file_atomic(
        self,
        path: Path,
        data: bytes,
    ) -> None:

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temp_path = path.with_suffix(
            path.suffix
            + ".tmp"
        )

        temp_path.write_bytes(
            data
        )

        temp_path.replace(
            path
        )

    def message_directory(
        self,
        message_id: str,
    ) -> Path:

        account_name = self.safe_name(
            self.account_email
        )

        return (
            self.storage_root
            / account_name
            / "messages"
            / message_id
        )

    def save_message_files(
        self,
        message_id: str,
        raw_bytes: bytes,
        body_text: str,
        body_html: str,
    ) -> dict[str, Any]:

        directory = self.message_directory(
            message_id
        )

        raw_hash = self.sha256_bytes(
            raw_bytes
        )

        eml_path = (
            directory
            / "message.eml"
        )

        html_path = (
            directory
            / "message.html"
        )

        text_path = (
            directory
            / "message.txt"
        )

        if not self.dry_run:

            self.save_file_atomic(
                eml_path,
                raw_bytes,
            )

            self.save_file_atomic(
                html_path,
                body_html.encode(
                    "utf-8"
                ),
            )

            self.save_file_atomic(
                text_path,
                body_text.encode(
                    "utf-8"
                ),
            )

        return {
            "raw_eml_path": str(
                eml_path
            ),
            "html_path": str(
                html_path
            ),
            "text_path": str(
                text_path
            ),
            "raw_sha256": raw_hash,
            "raw_size": len(
                raw_bytes
            ),
        }

    def download_attachment(
        self,
        message_id: str,
        attachment_id: str,
    ) -> bytes:

        response = (
            self.service.users()
            .messages()
            .attachments()
            .get(
                userId="me",
                messageId=message_id,
                id=attachment_id,
            )
            .execute()
        )

        return self.decode_base64url(
            response.get(
                "data",
                "",
            )
        )

    def find_existing_attachment_by_hash(
        self,
        content_hash: str,
    ) -> dict[str, Any] | None:

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        id,
                        local_file_id,
                        metadata
                    FROM gmail_attachments
                    WHERE content_hash = %s
                    ORDER BY id
                    LIMIT 1
                    """,
                    (
                        content_hash,
                    ),
                )

                row = cursor.fetchone()

                if not row:
                    return None

                return {
                    "id": row[0],
                    "local_file_id": row[1],
                    "metadata": row[2],
                }

        finally:
            conn.close()

    def save_attachment_file(
        self,
        content_hash: str,
        file_name: str,
        data: bytes,
    ) -> Path:

        account_name = self.safe_name(
            self.account_email
        )

        safe_filename = self.safe_name(
            file_name
        )

        directory = (
            self.storage_root
            / account_name
            / "attachments"
        )

        return (
            directory
            / (
                content_hash
                + "_"
                + safe_filename
            )
        )

    def save_attachment_record(
        self,
        message_db_id: int,
        attachment: dict[str, Any],
        local_path: Path,
        content_hash: str,
        file_size: int,
    ) -> None:

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                metadata = {
                    "local_path": str(
                        local_path
                    ),
                    "content_hash": content_hash,
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
                        attachment["attachment_id"],
                        attachment["file_name"],
                        attachment["mime_type"],
                        file_size,
                        content_hash,
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

    def process_attachments(
        self,
        message_id: str,
        message_db_id: int | None,
        full_message: dict[str, Any],
    ) -> None:

        attachments = (
            self.collect_attachment_parts(
                full_message
            )
        )

        self.stats[
            "attachments"
        ] += len(
            attachments
        )

        if not attachments:
            return

        self.log(
            "[ATTACHMENTS] "
            + str(len(attachments))
            + " for "
            + message_id
        )

        if self.dry_run:

            for attachment in attachments:

                self.log(
                    "  [DRY RUN] "
                    + attachment[
                        "file_name"
                    ]
                )

            return

        if message_db_id is None:
            raise RuntimeError(
                "Missing database message ID."
            )

        for attachment in attachments:

            attachment_id = attachment[
                "attachment_id"
            ]

            data = self.download_attachment(
                message_id,
                attachment_id,
            )

            content_hash = (
                self.sha256_bytes(
                    data
                )
            )

            existing = (
                self.find_existing_attachment_by_hash(
                    content_hash
                )
            )

            local_path = (
                self.save_attachment_file(
                    content_hash,
                    attachment[
                        "file_name"
                    ],
                    data,
                )
            )

            if existing:

                self.stats[
                    "attachments_existing"
                ] += 1

                if not local_path.exists():
                    self.save_file_atomic(
                        local_path,
                        data,
                    )

            else:

                self.stats[
                    "attachments_new"
                ] += 1

                if not local_path.exists():
                    self.save_file_atomic(
                        local_path,
                        data,
                    )

            self.save_attachment_record(
                message_db_id,
                attachment,
                local_path,
                content_hash,
                len(data),
            )

    def update_sync_state(
        self,
        label: dict[str, Any],
        status: str,
        items_checked: int,
        items_added: int,
        items_already_exists: int,
        items_failed: int,
        history_id: str | None = None,
        last_fetched: bool = False,
        last_saved: bool = False,
        error_message: str | None = None,
    ) -> None:

        if self.dry_run:
            return

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT id
                    FROM source_locations
                    WHERE source_id = %s
                      AND account_id = %s
                      AND external_id = %s
                    LIMIT 1
                    """,
                    (
                        self.source_id,
                        self.source_account_id,
                        label["label_id"],
                    ),
                )

                row = cursor.fetchone()

                if not row:
                    raise RuntimeError(
                        "source_locations row not found for label: "
                        + label["label_name"]
                    )

                source_location_id = row[0]

                fetched_at = (
                    self.utc_now()
                    if last_fetched
                    else None
                )

                saved_at = (
                    self.utc_now()
                    if last_saved
                    else None
                )

                cursor.execute(
                    """
                    INSERT INTO sync_states (
                        source_id,
                        source_location_id,
                        source_account_id,
                        status,
                        last_sync_started_at,
                        last_sync_completed_at,
                        last_success_at,
                        last_fetched_at,
                        last_saved_at,
                        history_id,
                        items_checked,
                        items_added,
                        items_already_exists,
                        items_failed,
                        last_error
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        CASE
                            WHEN %s = 'SUCCESS'
                            THEN CURRENT_TIMESTAMP
                            ELSE NULL
                        END,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    ON CONFLICT (
                        source_id,
                        source_location_id,
                        source_account_id
                    )
                    DO UPDATE SET
                        status = EXCLUDED.status,
                        last_sync_completed_at =
                            EXCLUDED.last_sync_completed_at,
                        last_success_at =
                            CASE
                                WHEN EXCLUDED.status = 'SUCCESS'
                                THEN CURRENT_TIMESTAMP
                                ELSE sync_states.last_success_at
                            END,
                        last_fetched_at =
                            COALESCE(
                                EXCLUDED.last_fetched_at,
                                sync_states.last_fetched_at
                            ),
                        last_saved_at =
                            COALESCE(
                                EXCLUDED.last_saved_at,
                                sync_states.last_saved_at
                            ),
                        history_id =
                            COALESCE(
                                EXCLUDED.history_id,
                                sync_states.history_id
                            ),
                        items_checked =
                            EXCLUDED.items_checked,
                        items_added =
                            EXCLUDED.items_added,
                        items_already_exists =
                            EXCLUDED.items_already_exists,
                        items_failed =
                            EXCLUDED.items_failed,
                        last_error =
                            EXCLUDED.last_error,
                        updated_at =
                            CURRENT_TIMESTAMP
                    """,
                    (
                        self.source_id,
                        source_location_id,
                        self.source_account_id,
                        status,
                        status,
                        fetched_at,
                        saved_at,
                        history_id,
                        items_checked,
                        items_added,
                        items_already_exists,
                        items_failed,
                        error_message,
                    ),
                )

                conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

    def process_message(
        self,
        message_id: str,
        selected_labels: list[dict[str, Any]],
    ) -> str:

        self.log(
            ""
        )

        self.log(
            "[MESSAGE] "
            + message_id
        )

        if len(selected_labels) > 1:

            self.log(
                "[MESSAGE] Appears in "
                + str(
                    len(selected_labels)
                )
                + " selected labels."
            )

        existing_id = self.message_exists(
            message_id
        )

        if existing_id:

            self.stats[
                "messages_existing"
            ] += 1

            self.log(
                "[MESSAGE] Already exists: "
                + str(existing_id)
            )

            if not self.dry_run:

                self.add_label_relationships(
                    existing_id,
                    selected_labels,
                )

            return "existing"

        self.stats[
            "messages_new"
        ] += 1

        full_message = (
            self.get_message_full(
                message_id
            )
        )

        raw_bytes = (
            self.get_message_raw(
                message_id
            )
        )

        metadata = (
            self.extract_full_metadata(
                full_message
            )
        )

        mime_content = (
            self.extract_mime_content(
                raw_bytes
            )
        )

        body_text = mime_content[
            "body_text"
        ]

        body_html = mime_content[
            "body_html"
        ]

        self.log(
            "[MESSAGE] Subject: "
            + metadata.get(
                "subject",
                "",
            )
        )

        self.log(
            "[MESSAGE] Text length: "
            + str(
                len(body_text)
            )
        )

        self.log(
            "[MESSAGE] HTML length: "
            + str(
                len(body_html)
            )
        )

        file_info = (
            self.save_message_files(
                message_id,
                raw_bytes,
                body_text,
                body_html,
            )
        )

        if self.dry_run:

            self.log(
                "[DRY RUN] Would save EML: "
                + file_info[
                    "raw_eml_path"
                ]
            )

            self.log(
                "[DRY RUN] Would save HTML: "
                + file_info[
                    "html_path"
                ]
            )

            self.log(
                "[DRY RUN] Would save TEXT: "
                + file_info[
                    "text_path"
                ]
            )

            self.process_attachments(
                message_id,
                None,
                full_message,
            )

            return "new"

        message_db_id = (
            self.create_message(
                metadata,
                body_text,
                body_html,
                file_info[
                    "raw_eml_path"
                ],
                file_info[
                    "html_path"
                ],
                file_info[
                    "text_path"
                ],
                file_info[
                    "raw_sha256"
                ],
                file_info[
                    "raw_size"
                ],
                selected_labels,
            )
        )

        self.process_attachments(
            message_id,
            message_db_id,
            full_message,
        )

        return "new"

    def run(
        self,
    ) -> dict[str, Any]:

        self.log(
            "=" * 72
        )

        self.log(
            "ALCALAY - GMAIL COPY"
        )

        self.log(
            "Account: "
            + self.account_email
        )

        self.log(
            "Mode: "
            + (
                "DRY RUN"
                if self.dry_run
                else "REAL COPY"
            )
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

        self.log(
            "[DB] Source account ID: "
            + str(
                self.source_account_id
            )
        )

        self.log(
            "[DB] Source ID: "
            + str(
                self.source_id
            )
        )

        self.label_rows = (
            self.load_selected_labels()
        )

        if not self.label_rows:

            self.log(
                "[STOP] No selected Gmail labels."
            )

            return self.stats

        self.log(
            "[DB] Selected labels: "
            + str(
                len(self.label_rows)
            )
        )

        self.connect_gmail()

        message_labels = (
            self.collect_selected_messages()
        )

        self.log(
            ""
        )

        self.log(
            "=" * 72
        )

        self.log(
            "MESSAGE COLLECTION SUMMARY"
        )

        self.log(
            "Labels: "
            + str(
                self.stats["labels"]
            )
        )

        self.log(
            "Messages found across labels: "
            + str(
                self.stats[
                    "messages_found"
                ]
            )
        )

        self.log(
            "Unique messages: "
            + str(
                self.stats[
                    "unique_messages"
                ]
            )
        )

        self.log(
            "Messages in multiple selected labels: "
            + str(
                self.stats[
                    "messages_with_multiple_labels"
                ]
            )
        )

        self.log(
            "=" * 72
        )

        for index, (
            message_id,
            labels,
        ) in enumerate(
            message_labels.items(),
            1,
        ):

            self.log(
                ""
            )

            self.log(
                "[PROGRESS] "
                + str(index)
                + "/"
                + str(
                    len(message_labels)
                )
            )

            try:

                self.process_message(
                    message_id,
                    labels,
                )

            except Exception as exc:

                self.stats[
                    "errors"
                ] += 1

                self.log(
                    "[ERROR] "
                    + message_id
                    + ": "
                    + type(exc).__name__
                    + ": "
                    + str(exc)
                )

        self.log(
            ""
        )

        self.log(
            "=" * 72
        )

        self.log(
            "FINAL SUMMARY"
        )

        self.log(
            "Labels: "
            + str(
                self.stats["labels"]
            )
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
            "Unique messages: "
            + str(
                self.stats[
                    "unique_messages"
                ]
            )
        )

        self.log(
            "New messages: "
            + str(
                self.stats[
                    "messages_new"
                ]
            )
        )

        self.log(
            "Existing messages: "
            + str(
                self.stats[
                    "messages_existing"
                ]
            )

        )

        self.log(
            "Messages with multiple labels: "
            + str(
                self.stats[
                    "messages_with_multiple_labels"
                ]
            )
        )

        self.log(
            "Attachments: "
            + str(
                self.stats[
                    "attachments"
                ]
            )
        )

        self.log(
            "New attachments: "
            + str(
                self.stats[
                    "attachments_new"
                ]
            )
        )

        self.log(
            "Existing attachments: "
            + str(
                self.stats[
                    "attachments_existing"
                ]
            )
        )

        self.log(
            "Errors: "
            + str(
                self.stats[
                    "errors"
                ]
            )
        )

        self.log(
            "Mode: "
            + (
                "DRY RUN"
                if self.dry_run
                else "REAL COPY"
            )
        )

        self.log(
            "=" * 72
        )

        return self.stats


def main() -> int:

    account_email = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "frank.avner@gmail.com"
    )

    copy_engine = GmailCopy(
        account_email=account_email,
        dry_run=DRY_RUN,
    )

    try:

        copy_engine.run()

        return 0

    except KeyboardInterrupt:

        print(
            "",
            flush=True,
        )

        print(
            "Stopped by user.",
            flush=True,
        )

        return 130

    except Exception as exc:

        print(
            "",
            flush=True,
        )

        print(
            "GMAIL COPY FAILED",
            flush=True,
        )

        print(
            type(exc).__name__
            + ": "
            + str(exc),
            flush=True,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )