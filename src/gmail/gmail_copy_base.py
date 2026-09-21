from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
import time
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


# ============================================================
# CONFIGURATION
# ============================================================

# False = real COPY
# True  = test mode without writing to PostgreSQL/files
DRY_RUN = False

# None = process all selected messages
# Integer = temporary test limit
COPY_MAX_MESSAGES: int | None = None

# Gmail API retry configuration
GMAIL_MAX_RETRIES = 6
GMAIL_RETRY_BASE_SECONDS = 2.0
GMAIL_RETRY_MAX_SECONDS = 60.0

DEFAULT_STORAGE_ROOT = (
    PROJECT_ROOT
    / "storage"
    / "gmail"
)


class GmailCopy:
    """
    Alcalay Gmail COPY engine.

    IMPORTANT:
        This class performs COPY only.

    It does NOT:
        - download Gmail attachments separately
        - extract message body for indexing
        - create HTML/TXT derivatives
        - perform OCR
        - perform AI/ML
        - perform search indexing

    The Gmail message is downloaded once using:
        messages.get(format="raw")

    The raw MIME message is saved as:
        message.eml

    A later PROCESS/INDEX phase can read message.eml locally.
    """

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

        self.gmail_account_id: int | None = None
        self.source_account_id: int | None = None
        self.source_id: int | None = None

        self.label_rows: list[dict[str, Any]] = []

        self.stats = {
            "labels": 0,
            "messages_found": 0,
            "unique_messages": 0,
            "messages_new": 0,
            "messages_existing": 0,
            "messages_with_multiple_labels": 0,
            "raw_messages_downloaded": 0,
            "raw_messages_saved": 0,
            "errors": 0,
            "rate_limit_retries": 0,
        }

    # ========================================================
    # BASIC HELPERS
    # ========================================================

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

    def utc_iso(self) -> str:
        return self.utc_now().isoformat()

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

        padding_length = (
            4
            - (
                len(value)
                % 4
            )
        ) % 4

        padding = "=" * padding_length

        return base64.urlsafe_b64decode(
            value + padding
        )

    def get_db_connection(self):
        return DatabaseConnection().connect()

    # ========================================================
    # DATABASE CONTEXT
    # ========================================================

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

    # ========================================================
    # SELECTED LABELS
    # ========================================================

    def load_selected_labels(
        self,
    ) -> list[dict[str, Any]]:
        """
        Load ONLY Labels selected through Gmail management.

        COPY must never display all enabled Gmail Labels.
        """

        if self.gmail_account_id is None:
            raise RuntimeError(
                "Gmail account context is not loaded."
            )

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        id,
                        label_id,
                        label_name,
                        label_type,
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
                        "label_type": row[3],
                        "selected_for_sync": row[4],
                        "enabled": row[5],
                    }
                    for row in rows
                ]

                return self.label_rows

        finally:
            conn.close()

    def choose_labels_for_copy(
        self,
        labels: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Temporary COPY selection.

        The list already contains ONLY persistent selected Labels.

        ENTER:
            all currently selected Labels

        ALL:
            all displayed Labels

        1,3,7:
            specific Labels

        1-5:
            range

        0:
            cancel

        This function NEVER changes selected_for_sync.
        """

        if not labels:
            self.log(
                "[STOP] אין Labels שנבחרו ב'ניהול חשבונות Gmail'."
            )
            return []

        self.log("")
        self.log("=" * 72)
        self.log("GMAIL COPY - LABEL SELECTION")
        self.log("=" * 72)
        self.log(
            "מוצגים רק ה-Labels שנבחרו דרך "
            "'ניהול חשבונות Gmail'."
        )
        self.log("")

        for index, label in enumerate(
            labels,
            1,
        ):
            self.log(
                f"{index:3}. "
                + label["label_name"]
                + " ["
                + label["label_id"]
                + "]"
            )

        self.log("")
        self.log(
            "ENTER = כל ה-Labels המוצגים"
        )
        self.log(
            "ALL   = כל ה-Labels המוצגים"
        )
        self.log(
            "לדוגמה: 1,3,7"
        )
        self.log(
            "לדוגמה: 1-5"
        )
        self.log(
            "0 = ביטול COPY"
        )

        while True:
            try:
                value = input(
                    "Labels להעתקה: "
                ).strip()
            except EOFError:
                self.log(
                    "[STOP] COPY cancelled."
                )
                return []

            if not value:
                indexes = list(
                    range(
                        1,
                        len(labels) + 1,
                    )
                )
                break

            if value == "0":
                self.log(
                    "[STOP] COPY cancelled by user."
                )
                return []

            if value.upper() == "ALL":
                indexes = list(
                    range(
                        1,
                        len(labels) + 1,
                    )
                )
                break

            try:
                selected_indexes: set[int] = set()

                for part in value.split(","):
                    part = part.strip()

                    if not part:
                        continue

                    if "-" in part:
                        start_text, end_text = (
                            part.split(
                                "-",
                                1,
                            )
                        )

                        start = int(
                            start_text.strip()
                        )

                        end = int(
                            end_text.strip()
                        )

                        if start > end:
                            start, end = end, start

                        selected_indexes.update(
                            range(
                                start,
                                end + 1,
                            )
                        )
                    else:
                        selected_indexes.add(
                            int(part)
                        )

                if not selected_indexes:
                    raise ValueError(
                        "לא נבחר אף Label."
                    )

                invalid = sorted(
                    index
                    for index in selected_indexes
                    if index < 1
                    or index > len(labels)
                )

                if invalid:
                    raise ValueError(
                        "מספרי Labels לא תקינים: "
                        + ", ".join(
                            str(item)
                            for item in invalid
                        )
                    )

                indexes = sorted(
                    selected_indexes
                )
                break

            except ValueError as exc:
                self.log(
                    "[ERROR] "
                    + str(exc)
                )

        selected = [
            labels[index - 1]
            for index in indexes
        ]

        self.log("")
        self.log("=" * 72)
        self.log("Labels שנבחרו ל-COPY")
        self.log("=" * 72)

        for index, label in enumerate(
            selected,
            1,
        ):
            self.log(
                f"{index:3}. "
                + label["label_name"]
                + " ["
                + label["label_id"]
                + "]"
            )

        self.log("=" * 72)
        self.log(
            "[NOTE] הבחירה זמנית ואינה משנה "
            "selected_for_sync."
        )

        return selected

    # ========================================================
    # GMAIL CONNECTION
    # ========================================================

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

    # ========================================================
    # GMAIL API RETRY
    # ========================================================

    def execute_with_retry(
        self,
        request,
        description: str,
    ):
        """
        Execute a Gmail API request with retry/backoff.

        This is mainly for:
            rateLimitExceeded
            userRateLimitExceeded
            429
            transient 5xx errors
        """

        last_exception = None

        for attempt in range(
            GMAIL_MAX_RETRIES + 1
        ):
            try:
                return request.execute()

            except Exception as exc:
                last_exception = exc

                error_text = str(
                    exc
                ).lower()

                retryable = (
                    "ratelimitexceeded"
                    in error_text
                    or "userratelimitexceeded"
                    in error_text
                    or "quota exceeded"
                    in error_text
                    or "429"
                    in error_text
                    or "500"
                    in error_text
                    or "502"
                    in error_text
                    or "503"
                    in error_text
                    or "504"
                    in error_text
                )

                if not retryable:
                    raise

                if attempt >= GMAIL_MAX_RETRIES:
                    raise

                wait_seconds = min(
                    GMAIL_RETRY_BASE_SECONDS
                    * (
                        2 ** attempt
                    ),
                    GMAIL_RETRY_MAX_SECONDS,
                )

                self.stats[
                    "rate_limit_retries"
                ] += 1

                self.log(
                    "[GMAIL RETRY] "
                    + description
                    + " | ניסיון "
                    + str(attempt + 1)
                    + "/"
                    + str(GMAIL_MAX_RETRIES)
                    + " | המתנה "
                    + str(wait_seconds)
                    + " שניות"
                )

                time.sleep(
                    wait_seconds
                )

        if last_exception:
            raise last_exception

        raise RuntimeError(
            "Gmail request failed: "
            + description
        )

    # ========================================================
    # MESSAGE LISTING
    # ========================================================

    def list_label_message_ids(
        self,
        label_id: str,
    ) -> list[str]:
        if self.service is None:
            raise RuntimeError(
                "Gmail service is not connected."
            )

        message_ids: list[str] = []

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

            response = self.execute_with_retry(
                request,
                "list messages for "
                + label_id,
            )

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
    ) -> dict[
        str,
        list[dict[str, Any]],
    ]:
        """
        Build a unique message list.

        A message that appears in multiple selected
        Labels is downloaded only once.

        All selected Label relationships are retained.
        """

        message_labels: dict[
            str,
            list[dict[str, Any]],
        ] = {}

        self.stats["labels"] = len(
            self.label_rows
        )

        for label in self.label_rows:
            label_id = label[
                "label_id"
            ]

            label_name = label[
                "label_name"
            ]

            self.log("")
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

                existing_label_ids = {
                    item["label_id"]
                    for item
                    in message_labels[
                        message_id
                    ]
                }

                if (
                    label_id
                    not in existing_label_ids
                ):
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
            for labels
            in message_labels.values()
            if len(labels) > 1
        )

        return message_labels

    # ========================================================
    # RAW MESSAGE DOWNLOAD
    # ========================================================

    def get_message_raw(
        self,
        message_id: str,
    ) -> bytes:
        """
        The ONLY Gmail message-content request used by COPY.

        No format='full'.
        No separate attachment downloads.
        """

        if self.service is None:
            raise RuntimeError(
                "Gmail service is not connected."
            )

        request = (
            self.service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="raw",
            )
        )

        response = self.execute_with_retry(
            request,
            "download raw message "
            + message_id,
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

    # ========================================================
    # RAW MIME HEADER EXTRACTION
    # ========================================================

    def header_value(
        self,
        headers,
        name: str,
    ) -> str:
        wanted = name.lower()

        for header in headers:
            # email.message.Message.items() returns (name, value) tuples.
            # Gmail API headers are dictionaries, but MIME headers are tuples.
            if isinstance(header, tuple) and len(header) == 2:
                header_name, header_value = header

                if str(header_name).lower() == wanted:
                    return str(header_value or "")

                continue

            if isinstance(header, dict):
                header_name = str(
                    header.get(
                        "name",
                        "",
                    )
                ).lower()

                if header_name == wanted:
                    return str(
                        header.get(
                            "value",
                            "",
                        )
                    )

        return ""

    def extract_raw_metadata(
        self,
        raw_bytes: bytes,
        message_id: str,
    ) -> dict[str, Any]:
        """
        Read only MIME headers from the already downloaded
        local/raw message.

        No body extraction is performed.
        No attachment extraction is performed.
        """

        message = BytesParser(
            policy=policy.default
        ).parsebytes(
            raw_bytes,
            headersonly=True,
        )

        return {
            "message_id": message_id,
            "message_id_header": self.header_value(
                message.items(),
                "Message-ID",
            ),
            "thread_id": "",
            "history_id": "",
            "subject": str(
                message.get(
                    "Subject",
                    "",
                )
                or ""
            ),
            "sender": str(
                message.get(
                    "From",
                    "",
                )
                or ""
            ),
            "recipients": str(
                message.get(
                    "To",
                    "",
                )
                or ""
            ),
            "cc": str(
                message.get(
                    "Cc",
                    "",
                )
                or ""
            ),
            "bcc": str(
                message.get(
                    "Bcc",
                    "",
                )
                or ""
            ),
            "date_header": str(
                message.get(
                    "Date",
                    "",
                )
                or ""
            ),
            "references": str(
                message.get(
                    "References",
                    "",
                )
                or ""
            ),
            "in_reply_to": str(
                message.get(
                    "In-Reply-To",
                    "",
                )
                or ""
            ),
        }

    # ========================================================
    # LOCAL STORAGE
    # ========================================================

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

    def save_raw_message(
        self,
        message_id: str,
        raw_bytes: bytes,
    ) -> dict[str, Any]:
        directory = self.message_directory(
            message_id
        )

        eml_path = (
            directory
            / "message.eml"
        )

        raw_hash = self.sha256_bytes(
            raw_bytes
        )

        if not self.dry_run:
            self.save_file_atomic(
                eml_path,
                raw_bytes,
            )

            self.stats[
                "raw_messages_saved"
            ] += 1

        return {
            "raw_eml_path": str(
                eml_path
            ),
            "raw_sha256": raw_hash,
            "raw_size": len(
                raw_bytes
            ),
        }

    # ========================================================
    # DATABASE MESSAGE OPERATIONS
    # ========================================================

    def message_exists(
        self,
        message_id: str,
    ) -> int | None:
        if self.gmail_account_id is None:
            raise RuntimeError(
                "Gmail account ID is not loaded."
            )

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

    def add_label_relationships(
        self,
        message_db_id: int,
        selected_labels: list[
            dict[str, Any]
        ],
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
                            label[
                                "db_label_id"
                            ],
                        ),
                    )

                conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

    def create_message(
        self,
        metadata: dict[str, Any],
        file_info: dict[str, Any],
        selected_labels: list[
            dict[str, Any]
        ],
    ) -> int:
        if self.gmail_account_id is None:
            raise RuntimeError(
                "Gmail account ID is not loaded."
            )

        conn = self.get_db_connection()

        try:
            with conn.cursor() as cursor:
                message_metadata = {
                    "source": "gmail",
                    "copy_mode": "raw_eml_only",
                    "raw_eml_path": file_info[
                        "raw_eml_path"
                    ],
                    "raw_sha256": file_info[
                        "raw_sha256"
                    ],
                    "raw_size": file_info[
                        "raw_size"
                    ],
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
                    "processing_status": "COPIED",
                    "processing_required": True,
                    "attachments_processing_required": True,
                    "selected_labels": [
                        {
                            "id": label[
                                "label_id"
                            ],
                            "name": label[
                                "label_name"
                            ],
                        }
                        for label
                        in selected_labels
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
                        None,
                        None,
                        None,
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
                        None,
                        None,
                        None,
                        json.dumps(
                            message_metadata,
                            ensure_ascii=False,
                        ),
                    ),
                )

                row = cursor.fetchone()

                if not row:
                    raise RuntimeError(
                        "Could not create or update "
                        "gmail_messages."
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
                            label[
                                "db_label_id"
                            ],
                        ),
                    )

                conn.commit()

                return message_db_id

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

    # ========================================================
    # CONFIRMATION
    # ========================================================

    def confirm_copy(
        self,
        selected: list[
            dict[str, Any]
        ],
        unique_count: int,
    ) -> bool:
        self.log("")
        self.log("=" * 72)
        self.log("אישור COPY")
        self.log("=" * 72)

        self.log(
            "Labels שנבחרו: "
            + str(len(selected))
        )

        self.log(
            "הודעות ייחודיות: "
            + str(unique_count)
        )

        self.log("")
        self.log(
            "COPY ישמור את הודעות Gmail "
            "כקובצי Raw/EML בלבד."
        )

        self.log(
            "לא יבוצע בשלב זה:"
        )
        self.log(
            "  - OCR"
        )
        self.log(
            "  - AI/ML"
        )
        self.log(
            "  - אינדוקס"
        )
        self.log(
            "  - הורדת Attachments בנפרד"
        )
        self.log(
            "  - יצירת HTML/TXT"
        )

        self.log("")
        self.log(
            "ה-Attachments יישארו בתוך message.eml "
            "ויעובדו בשלב PROCESS נפרד."
        )

        self.log("")
        self.log(
            "מצב: "
            + (
                "DRY RUN"
                if self.dry_run
                else "REAL COPY"
            )
        )

        self.log("=" * 72)

        answer = input(
            "להמשיך ל-COPY? הקלד YES לאישור: "
        ).strip()

        return answer == "YES"

    # ========================================================
    # AUDIT
    # ========================================================

    def create_audit_data(
        self,
        selected: list[
            dict[str, Any]
        ],
        status: str,
        copy_started_at: str,
        copy_finished_at: str | None = None,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "account": self.account_email,
            "copy_mode": "raw_eml_only",
            "dry_run": self.dry_run,
            "copy_started_at": copy_started_at,
            "copy_finished_at": copy_finished_at,
            "selected_labels": [
                {
                    "db_id": label["id"],
                    "label_id": label["label_id"],
                    "label_name": label["label_name"],
                }
                for label in selected
            ],
            "messages_found_across_labels":
                self.stats[
                    "messages_found"
                ],
            "unique_messages":
                self.stats[
                    "unique_messages"
                ],
            "messages_with_multiple_labels":
                self.stats[
                    "messages_with_multiple_labels"
                ],
            "stats": dict(
                self.stats
            ),
        }

    def save_audit_file(
        self,
        audit_data: dict[str, Any],
    ) -> Path:
        account_name = self.safe_name(
            self.account_email
        )

        timestamp = (
            self.utc_now()
            .strftime(
                "%Y%m%d_%H%M%S"
            )
        )

        directory = (
            self.storage_root
            / account_name
            / "copy_audit"
        )

        path = (
            directory
            / (
                timestamp
                + "_gmail_copy_audit.json"
            )
        )

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            json.dumps(
                audit_data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return path

    # ========================================================
    # PROCESS ONE MESSAGE
    # ========================================================

    def process_message(
        self,
        message_id: str,
        selected_labels: list[
            dict[str, Any]
        ],
    ) -> str:
        self.log("")
        self.log(
            "[MESSAGE] "
            + message_id
        )

        if len(
            selected_labels
        ) > 1:
            self.log(
                "[MESSAGE] Appears in "
                + str(
                    len(
                        selected_labels
                    )
                )
                + " selected labels."
            )

        existing_id = (
            self.message_exists(
                message_id
            )
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

        # ----------------------------------------------------
        # ONE Gmail content request only:
        # format="raw"
        # ----------------------------------------------------

        raw_bytes = (
            self.get_message_raw(
                message_id
            )
        )

        self.stats[
            "raw_messages_downloaded"
        ] += 1

        raw_hash = self.sha256_bytes(
            raw_bytes
        )

        # Header parsing happens locally on the already
        # downloaded MIME data. It is NOT another Gmail call.
        metadata = (
            self.extract_raw_metadata(
                raw_bytes,
                message_id,
            )
        )

        file_info = (
            self.save_raw_message(
                message_id,
                raw_bytes,
            )
        )

        self.log(
            "[COPY] Raw size: "
            + str(
                len(raw_bytes)
            )
            + " bytes"
        )

        self.log(
            "[COPY] SHA256: "
            + raw_hash
        )

        self.log(
            "[COPY] Subject: "
            + metadata.get(
                "subject",
                "",
            )
        )

        self.log(
            "[COPY] Sender: "
            + metadata.get(
                "sender",
                "",
            )
        )

        if self.dry_run:
            self.log(
                "[DRY RUN] Would save: "
                + file_info[
                    "raw_eml_path"
                ]
            )

            return "new"

        self.create_message(
            metadata,
            file_info,
            selected_labels,
        )

        self.stats[
            "messages_new"
        ] += 1

        return "new"

    # ========================================================
    # RUN
    # ========================================================

    def run(
        self,
    ) -> dict[str, Any]:
        self.log("=" * 72)
        self.log(
            "ALCALAY - GMAIL COPY"
        )
        self.log(
            "COPY MODE: RAW / EML ONLY"
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
        self.log("=" * 72)

        # ----------------------------------------------------
        # 1. PostgreSQL account
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # 2. ONLY persistent selected Labels
        # ----------------------------------------------------

        selected_labels = (
            self.load_selected_labels()
        )

        if not selected_labels:
            self.log(
                "[STOP] אין Labels שנבחרו "
                "ב'ניהול חשבונות Gmail'."
            )
            return self.stats

        self.log(
            "[DB] Selected Labels: "
            + str(
                len(
                    selected_labels
                )
            )
        )

        # ----------------------------------------------------
        # 3. Gmail connection
        # ----------------------------------------------------

        self.connect_gmail()

        # ----------------------------------------------------
        # 4. Temporary COPY selection
        # ----------------------------------------------------

        selected = (
            self.choose_labels_for_copy(
                selected_labels
            )
        )

        if not selected:
            self.log(
                "[STOP] No Labels selected."
            )
            return self.stats

        self.label_rows = selected

        self.stats[
            "labels"
        ] = len(
            selected
        )

        # ----------------------------------------------------
        # 5. Collect Message IDs only
        # ----------------------------------------------------

        self.log("")
        self.log(
            "=" * 72
        )
        self.log(
            "COLLECTING MESSAGE IDS"
        )
        self.log(
            "=" * 72
        )

        copy_started_at = (
            self.utc_iso()
        )

        message_labels = (
            self.collect_selected_messages()
        )

        self.log("")
        self.log(
            "=" * 72
        )
        self.log(
            "MESSAGE COLLECTION SUMMARY"
        )
        self.log(
            "=" * 72
        )

        self.log(
            "Messages found across Labels: "
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
            "Multiple-Label duplicates: "
            + str(
                self.stats[
                    "messages_found"
                ]
                - self.stats[
                    "unique_messages"
                ]
            )
        )

        self.log(
            "=" * 72
        )

        # ----------------------------------------------------
        # 6. Safety confirmation
        # ----------------------------------------------------

        if not self.confirm_copy(
            selected,
            self.stats[
                "unique_messages"
            ],
        ):
            self.log("")
            self.log(
                "[STOP] COPY בוטל לפני הורדת "
                "הודעות."
            )

            audit = (
                self.create_audit_data(
                    selected,
                    "CANCELLED_BEFORE_COPY",
                    copy_started_at,
                    self.utc_iso(),
                )
            )

            if not self.dry_run:
                audit_path = (
                    self.save_audit_file(
                        audit
                    )
                )

                self.log(
                    "[AUDIT] "
                    + str(
                        audit_path
                    )
                )

            return self.stats

        # ----------------------------------------------------
        # 7. COPY
        # ----------------------------------------------------

        messages_to_process = (
            message_labels
        )

        if (
            COPY_MAX_MESSAGES
            is not None
        ):
            max_messages = min(
                COPY_MAX_MESSAGES,
                len(
                    message_labels
                ),
            )

            messages_to_process = dict(
                list(
                    message_labels.items()
                )[
                    :max_messages
                ]
            )

            self.log("")
            self.log(
                "[COPY TEST] מוגבל ל-"
                + str(
                    max_messages
                )
                + " הודעה/ות לצורך בדיקה."
            )

            self.log(
                "[COPY TEST] "
                + str(
                    len(
                        message_labels
                    )
                    - max_messages
                )
                + " הודעות נוספות לא יעובדו."
            )

        self.log("")
        self.log(
            "=" * 72
        )
        self.log(
            "STARTING RAW/EML COPY"
        )
        self.log(
            "=" * 72
        )

        total_to_process = len(
            messages_to_process
        )

        for index, (
            message_id,
            labels,
        ) in enumerate(
            messages_to_process.items(),
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
                    total_to_process
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
                    + type(
                        exc
                    ).__name__
                    + ": "
                    + str(exc)
                )

        # ----------------------------------------------------
        # 8. Audit
        # ----------------------------------------------------

        copy_finished_at = (
            self.utc_iso()
        )

        audit_status = (
            "DRY_RUN_COMPLETED"
            if self.dry_run
            else "COPY_COMPLETED"
        )

        if (
            self.stats[
                "errors"
            ] > 0
        ):
            audit_status = (
                "DRY_RUN_COMPLETED_WITH_ERRORS"
                if self.dry_run
                else "COPY_COMPLETED_WITH_ERRORS"
            )

        audit = (
            self.create_audit_data(
                selected,
                audit_status,
                copy_started_at,
                copy_finished_at,
            )
        )

        if not self.dry_run:
            audit_path = (
                self.save_audit_file(
                    audit
                )
            )

            self.log(
                "[AUDIT] "
                + str(
                    audit_path
                )
            )

        # ----------------------------------------------------
        # 9. Final summary
        # ----------------------------------------------------

        self.log("")
        self.log(
            "=" * 72
        )
        self.log(
            "FINAL COPY SUMMARY"
        )
        self.log(
            "=" * 72
        )

        self.log(
            "COPY mode: RAW / EML ONLY"
        )

        self.log(
            "Labels: "
            + str(
                self.stats[
                    "labels"
                ]
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
            "Messages with multiple Labels: "
            + str(
                self.stats[
                    "messages_with_multiple_labels"
                ]
            )
        )

        self.log(
            "Raw messages downloaded: "
            + str(
                self.stats[
                    "raw_messages_downloaded"
                ]
            )
        )

        self.log(
            "Raw messages saved: "
            + str(
                self.stats[
                    "raw_messages_saved"
                ]
            )
        )

        self.log(
            "Gmail rate-limit retries: "
            + str(
                self.stats[
                    "rate_limit_retries"
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