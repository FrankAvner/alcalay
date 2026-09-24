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


from database.connection import DatabaseConnection
from gmail.gmail_connection import GmailConnection


DRY_RUN = False

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
        return DatabaseConnection().connect()

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

    def load_available_labels(self) -> list[dict[str, Any]]:

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
                      AND enabled = TRUE
                    ORDER BY id
                    """,
                    (self.gmail_account_id,),
                )

                rows = cursor.fetchall()

                return [
                    {
                        "id": row[0],
                        "label_id": row[1],
                        "label_name": row[2],
                        "selected_for_sync": row[3],
                        "enabled": row[4],
                    }
                    for row in rows
                ]
        finally:
            conn.close()

    def count_label_messages(self, label_id: str) -> int:

        if self.service is None:
            raise RuntimeError("Gmail service is not connected.")

        total = 0
        page_token = None

        while True:
            response = (
                self.service.users()
                .messages()
                .list(
                    userId="me",
                    labelIds=[label_id],
                    maxResults=500,
                    pageToken=page_token,
                )
                .execute()
            )

            total += len(response.get("messages", []))
            page_token = response.get("nextPageToken")

            if not page_token:
                return total

    def count_all_labels(self, labels: list[dict[str, Any]]) -> None:

        self.log("")
        self.log("=" * 72)
        self.log("GMAIL LABEL MESSAGE COUNTS")
        self.log("=" * 72)

        for index, label in enumerate(labels, 1):
            count = self.count_label_messages(label["label_id"])
            label["message_count"] = count
            selected = " *" if label.get("selected_for_sync") else ""
            self.log(
                str(index) + ". "
                + label["label_name"]
                + " — " + str(count) + " הודעות"
                + selected
            )

        self.log("=" * 72)
        self.log("* = מסומן כרגע ב-PostgreSQL")
        self.log("=")

    def parse_label_selection(self, value: str, labels: list[dict[str, Any]]) -> list[int]:

        value = value.strip()

        if not value:
            return [
                index
                for index, label in enumerate(labels, 1)
                if label.get("selected_for_sync")
            ]

        if value.upper() == "ALL":
            return list(range(1, len(labels) + 1))

        selected = set()

        for token in value.split(","):
            token = token.strip()
            if not token:
                continue

            if "-" in token:
                start_text, end_text = token.split("-", 1)
                start = int(start_text.strip())
                end = int(end_text.strip())
                if start > end:
                    start, end = end, start
                selected.update(range(start, end + 1))
            else:
                selected.add(int(token))

        if not selected:
            raise ValueError("לא נבחרו Labels.")

        invalid = [i for i in selected if i < 1 or i > len(labels)]
        if invalid:
            raise ValueError("מספר Label לא חוקי: " + ", ".join(map(str, invalid)))

        return sorted(selected)

    def select_labels_for_copy(
        self,
        labels: list[dict[str, Any]],
        forced_label_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:

        if forced_label_ids is not None:
            requested = {str(value).strip() for value in forced_label_ids if str(value).strip()}
            selected = [
                label
                for label in labels
                if str(label.get("label_id", "")).strip() in requested
                or str(label.get("id", "")).strip() in requested
            ]

            missing = requested - {
                str(label.get("label_id", "")).strip()
                for label in selected
            } - {
                str(label.get("id", "")).strip()
                for label in selected
            }

            if missing:
                raise ValueError(
                    "Labels not found: " + ", ".join(sorted(missing))
                )

            if not selected:
                raise ValueError("לא נבחרו Labels.")
        else:
            self.log("")
            self.log("Labels להעתקה: ניתן לרשום למשל 1,4,7 או 1-3,7")
            self.log("Enter = להשתמש בבחירה הנוכחית ב-PostgreSQL")
            self.log("ALL = כל ה-Labels")

            value = input("Labels להעתקה: ")
            indexes = self.parse_label_selection(value, labels)
            selected = [labels[index - 1] for index in indexes]

        self.log("")
        self.log("=" * 72)
        self.log("ה-Labels שנבחרו להעתקה")
        self.log("=" * 72)

        for label in selected:
            self.log(
                "- " + label["label_name"]
                + " — " + str(label.get("message_count", 0)) + " הודעות"
            )

        self.log("=" * 72)
        return selected

    def save_selected_labels_to_database(self, selected: list[dict[str, Any]], all_labels: list[dict[str, Any]]) -> None:

        if self.dry_run:
            return

        selected_ids = {label["id"] for label in selected}
        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:
                for label in all_labels:
                    cursor.execute(
                        """
                        UPDATE gmail_labels
                        SET selected_for_sync = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                          AND gmail_account_id = %s
                        """,
                        (
                            label["id"] in selected_ids,
                            label["id"],
                            self.gmail_account_id,
                        ),
                    )
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def confirm_copy(self, selected: list[dict[str, Any]], unique_count: int) -> bool:

        self.log("")
        self.log("=" * 72)
        self.log("אישור COPY")
        self.log("=" * 72)
        self.log("מספר Labels שנבחרו: " + str(len(selected)))
        self.log(
            "מספר הודעות לפי Labels: "
            + str(sum(label.get("message_count", 0) for label in selected))
        )
        self.log("מספר הודעות ייחודיות: " + str(unique_count))
        self.log(
            "הערה: אם הודעה נמצאת ביותר מ-Label אחד שנבחר, היא תועתק פעם אחת בלבד."
        )
        self.log("הקשרים לכל ה-Labels שנבחרו יישמרו.")
        self.log("מצב נוכחי: " + ("DRY RUN" if self.dry_run else "REAL COPY"))
        if self.dry_run:
            self.log("לא יישמר מידע בפועל.")
        self.log("=" * 72)

        answer = input("להמשיך ל-COPY? הקלד YES לאישור: ").strip()
        return answer == "YES"

    def create_audit_data(self, selected: list[dict[str, Any]], status: str, copy_started_at: str, copy_finished_at: str | None = None) -> dict[str, Any]:
        return {
            "status": status,
            "account": self.account_email,
            "dry_run": self.dry_run,
            "copy_started_at": copy_started_at,
            "copy_finished_at": copy_finished_at,
            "selected_labels": [
                {
                    "db_id": label["id"],
                    "label_id": label["label_id"],
                    "label_name": label["label_name"],
                    "message_count": label.get("message_count", 0),
                }
                for label in selected
            ],
            "messages_found_across_labels": self.stats["messages_found"],
            "unique_messages": self.stats["unique_messages"],
            "messages_with_multiple_labels": self.stats["messages_with_multiple_labels"],
            "stats": dict(self.stats),
        }

    def save_audit_file(self, audit_data: dict[str, Any]) -> Path:
        account_name = self.safe_name(self.account_email)
        timestamp = self.utc_now().strftime("%Y%m%d_%H%M%S")
        directory = self.storage_root / account_name / "copy_audit"
        path = directory / (timestamp + "_gmail_copy_audit.json")
        directory.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(audit_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

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

            if self.dry_run:
                full_message = self.get_message_full(message_id)
                self.process_attachments(
                    message_id,
                    None,
                    full_message,
                )
                return "existing"

            self.add_label_relationships(
                existing_id,
                selected_labels,
            )

            # An existing email may have been imported before its attachments
            # were available. Re-read the Gmail message and reconcile all
            # attachments instead of skipping the message completely.
            full_message = self.get_message_full(message_id)
            self.process_attachments(
                message_id,
                existing_id,
                full_message,
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
        forced_label_ids: list[str] | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:

        self.log("=" * 72)
        self.log("ALCALAY - GMAIL COPY")
        self.log("Account: " + self.account_email)
        self.log("Mode: " + ("DRY RUN" if self.dry_run else "REAL COPY"))
        self.log("=" * 72)

        self.load_database_context()
        self.log("[DB] Gmail account ID: " + str(self.gmail_account_id))
        self.log("[DB] Source account ID: " + str(self.source_account_id))
        self.log("[DB] Source ID: " + str(self.source_id))

        all_labels = self.load_available_labels()
        if not all_labels:
            self.log("[STOP] No enabled Gmail labels.")
            return self.stats

        self.log("[DB] Enabled labels: " + str(len(all_labels)))
        self.connect_gmail()

        # First phase: counts only. No message bodies, MIME, attachments or files are downloaded.
        self.count_all_labels(all_labels)
        selected = self.select_labels_for_copy(
            all_labels,
            forced_label_ids=forced_label_ids,
        )

        if not selected:
            self.log("[STOP] No labels selected.")
            return self.stats

        self.label_rows = selected
        self.stats["labels"] = len(selected)

        copy_started_at = self.utc_iso()

        # Second phase: list message IDs only and deduplicate them across selected labels.
        message_labels = self.collect_selected_messages()

        self.log("")
        self.log("=" * 72)
        self.log("בדיקת הודעות ייחודיות לפני הורדת תוכן")
        self.log("=" * 72)
        self.log("מספר הודעות לפי Labels: " + str(self.stats["messages_found"]))
        self.log("מספר הודעות ייחודיות: " + str(self.stats["unique_messages"]))
        self.log(
            "כפילויות בין Labels: "
            + str(self.stats["messages_found"] - self.stats["unique_messages"])
        )
        self.log("=" * 72)

        # This is the safety gate. Nothing below this point fetches message bodies until YES is entered.
        if not confirmed and not self.confirm_copy(selected, self.stats["unique_messages"]):
            self.log("")
            self.log("[STOP] COPY בוטל לפני הורדת הודעות.")
            audit = self.create_audit_data(
                selected,
                "CANCELLED_BEFORE_MESSAGE_DOWNLOAD",
                copy_started_at,
                self.utc_iso(),
            )
            if not self.dry_run:
                self.save_audit_file(audit)
            return self.stats

        self.save_selected_labels_to_database(selected, all_labels)

        self.log("")
        self.log("[COPY] Starting message processing...")

        for index, (message_id, labels) in enumerate(message_labels.items(), 1):
            if index == 1 or index == len(message_labels) or index % 25 == 0:
                self.log(
                    "[PROGRESS] " + str(index) + "/" + str(len(message_labels))
                )
            try:
                self.process_message(message_id, labels)
            except Exception as exc:
                self.stats["errors"] += 1
                self.log(
                    "[ERROR] " + message_id + ": "
                    + type(exc).__name__ + ": " + str(exc)
                )

        copy_finished_at = self.utc_iso()
        audit = self.create_audit_data(
            selected,
            "DRY_RUN_COMPLETED" if self.dry_run else "COPY_COMPLETED",
            copy_started_at,
            copy_finished_at,
        )

        if not self.dry_run:
            audit_path = self.save_audit_file(audit)
            self.log("[AUDIT] " + str(audit_path))

        self.log("")
        self.log("=" * 72)
        self.log("FINAL SUMMARY")
        self.log("=" * 72)
        self.log("Labels: " + str(self.stats["labels"]))
        self.log("Messages found: " + str(self.stats["messages_found"]))
        self.log("Unique messages: " + str(self.stats["unique_messages"]))
        self.log("New messages: " + str(self.stats["messages_new"]))
        self.log("Existing messages: " + str(self.stats["messages_existing"]))
        self.log(
            "Messages with multiple labels: "
            + str(self.stats["messages_with_multiple_labels"])
        )
        self.log("Attachments: " + str(self.stats["attachments"]))
        self.log("New attachments: " + str(self.stats["attachments_new"]))
        self.log("Existing attachments: " + str(self.stats["attachments_existing"]))
        self.log("Errors: " + str(self.stats["errors"]))
        self.log("Mode: " + ("DRY RUN" if self.dry_run else "REAL COPY"))
        self.log("=" * 72)

        return self.stats


def main() -> int:

    import argparse

    parser = argparse.ArgumentParser(
        description="Alcalay Gmail COPY"
    )
    parser.add_argument(
        "account",
        nargs="?",
        default="frank.avner@gmail.com",
        help="Gmail account email",
    )
    parser.add_argument(
        "--labels",
        default=None,
        help="Comma-separated Gmail label IDs or database label IDs",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm COPY without interactive input",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without writing data",
    )

    args = parser.parse_args()

    forced_label_ids = None
    if args.labels:
        forced_label_ids = [
            value.strip()
            for value in args.labels.split(",")
            if value.strip()
        ]

    copy_engine = GmailCopy(
        account_email=args.account,
        dry_run=(True if args.dry_run else DRY_RUN),
    )

    try:

        copy_engine.run(
            forced_label_ids=forced_label_ids,
            confirmed=args.yes,
        )

        return 0

    except KeyboardInterrupt:

        print("", flush=True)
        print("Stopped by user.", flush=True)
        return 130

    except Exception as exc:

        print("", flush=True)
        print("GMAIL COPY FAILED", flush=True)
        print(
            type(exc).__name__ + ": " + str(exc),
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )