# -*- coding: utf-8 -*-

"""
Alcalay - Gmail Storage Size Estimator

READ-ONLY

הקובץ מבצע Sampling של Gmail כדי להעריך:

1. נפח המיילים.
2. נפח הצרופות (Attachments).
3. מספר הצרופות.
4. נפח משוער לכל Label.
5. נפח משוער כולל לכל המיילים הייחודיים.

אין COPY.
אין הורדת תוכן של Attachments.
אין שינוי Gmail.
אין שינוי Google Drive.
אין שינוי PostgreSQL.

הודעות נבדקות באמצעות messages.get(format="full"),
אך הקובץ אינו מוריד את תוכן הצרופות עצמן.

הרצה:

    cd /Users/AvnerFrank/alcalay
    source .venv/bin/activate
    python sizing_gmail.py
"""

from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


# ============================================================
# IMPORTS
# ============================================================

from database.connection import DatabaseConnection
from gmail.gmail_connection import GmailConnection


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_GMAIL_ACCOUNT = "frank.avner@gmail.com"

# מספר מיילים במדגם.
SAMPLE_SIZE = 500

# Seed קבוע.
RANDOM_SEED = 42391


# ============================================================
# FORMATTING
# ============================================================

def format_bytes(value: float | int) -> str:
    value = float(value or 0)

    gb = 1024 ** 3
    mb = 1024 ** 2
    kb = 1024

    if value >= gb:
        return f"{value / gb:,.2f} GB"

    if value >= mb:
        return f"{value / mb:,.2f} MB"

    if value >= kb:
        return f"{value / kb:,.2f} KB"

    return f"{value:,.0f} bytes"


# ============================================================
# DATABASE
# ============================================================

def get_database_connection():
    return DatabaseConnection().connect()


def get_gmail_account_id() -> int:

    conn = get_database_connection()

    try:
        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT id
                FROM gmail_accounts
                WHERE LOWER(email) = LOWER(%s)
                LIMIT 1
                """,
                (
                    DEFAULT_GMAIL_ACCOUNT,
                ),
            )

            row = cursor.fetchone()

            if not row:
                raise RuntimeError(
                    "Gmail account was not found in PostgreSQL: "
                    + DEFAULT_GMAIL_ACCOUNT
                )

            return row[0]

    finally:
        conn.close()


def load_selected_labels(
    gmail_account_id: int,
) -> list[dict]:

    conn = get_database_connection()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    label_id,
                    label_name
                FROM gmail_labels
                WHERE gmail_account_id = %s
                  AND selected_for_sync = TRUE
                  AND enabled = TRUE
                ORDER BY id
                """,
                (
                    gmail_account_id,
                ),
            )

            rows = cursor.fetchall()

            return [
                {
                    "id": row[0],
                    "label_id": row[1],
                    "label_name": row[2],
                }
                for row in rows
            ]

    finally:
        conn.close()


# ============================================================
# GMAIL
# ============================================================

def connect_to_gmail():

    connection = GmailConnection(
        DEFAULT_GMAIL_ACCOUNT
    )

    result = connection.connect(
        DEFAULT_GMAIL_ACCOUNT
    )

    if result is False:
        raise RuntimeError(
            "Gmail connection failed."
        )

    service = connection.service

    if service is None:
        raise RuntimeError(
            "Gmail service was not created."
        )

    return service


# ============================================================
# LIST MESSAGE IDS
# ============================================================

def get_message_ids_for_label(
    service,
    label_id: str,
) -> list[str]:

    message_ids = []

    page_token = None

    while True:

        request = (
            service.users()
            .messages()
            .list(
                userId="me",
                labelIds=[label_id],
                maxResults=500,
                pageToken=page_token,
            )
        )

        response = request.execute()

        messages = response.get(
            "messages",
            [],
        )

        for message in messages:

            message_id = message.get(
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


# ============================================================
# ATTACHMENT ANALYSIS
# ============================================================

def walk_parts(
    parts: list | None,
):
    """
    Recursively walk all MIME parts.
    """

    if not parts:
        return

    for part in parts:

        yield part

        children = part.get(
            "parts",
            [],
        )

        if children:

            yield from walk_parts(
                children
            )


def analyze_message(
    service,
    message_id: str,
) -> dict:

    response = (
        service.users()
        .messages()
        .get(
            userId="me",
            id=message_id,
            format="full",
        )
        .execute()
    )

    # Gmail's total estimated message size.
    size_estimate = int(
        response.get(
            "sizeEstimate",
            0,
        )
        or 0
    )

    payload = response.get(
        "payload",
        {},
    )

    attachment_count = 0
    attachment_bytes = 0

    # Gmail MIME tree.
    parts = payload.get(
        "parts",
        [],
    )

    for part in walk_parts(parts):

        filename = (
            part.get(
                "filename",
                ""
            )
            or ""
        ).strip()

        body = part.get(
            "body",
            {}
        ) or {}

        # Gmail normally exposes attachmentId for
        # externally stored attachment content.
        attachment_id = body.get(
            "attachmentId"
        )

        # size is the important field for this
        # read-only estimation.
        part_size = int(
            body.get(
                "size",
                0,
            )
            or 0
        )

        # We regard a MIME part as an attachment when
        # it has a filename.
        #
        # This catches normal Gmail attachments such as:
        # PDF, DOCX, XLSX, JPG, ZIP, etc.
        if filename:

            attachment_count += 1

            attachment_bytes += part_size

        elif attachment_id and part_size > 0:

            # Some messages may contain an attachment
            # with attachmentId but no filename.
            attachment_count += 1

            attachment_bytes += part_size

    return {
        "message_id": message_id,
        "message_size": size_estimate,
        "attachment_count": attachment_count,
        "attachment_bytes": attachment_bytes,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 80)
    print("ALCALAY - GMAIL MESSAGE + ATTACHMENT SIZE ESTIMATOR")
    print("=" * 80)
    print()

    print(
        f"חשבון Gmail: {DEFAULT_GMAIL_ACCOUNT}"
    )

    print(
        f"מדגם: עד {SAMPLE_SIZE:,} מיילים ייחודיים"
    )

    print()

    print(
        "מצב: READ-ONLY"
    )

    print(
        "לא מתבצע COPY, שינוי Gmail, שינוי Drive או שינוי PostgreSQL."
    )

    print(
        "לא מורידים את תוכן הצרופות."
    )

    print()

    # ========================================================
    # DATABASE
    # ========================================================

    print(
        "1. קורא את חשבון Gmail מ-PostgreSQL..."
    )

    gmail_account_id = get_gmail_account_id()

    print(
        f"   Account ID: {gmail_account_id}"
    )

    print()

    # ========================================================
    # LABELS
    # ========================================================

    print(
        "2. טוען את כל ה-Labels שנבחרו ל-SYNC..."
    )

    labels = load_selected_labels(
        gmail_account_id
    )

    if not labels:

        print()
        print(
            "לא נמצאו Labels שנבחרו ל-SYNC."
        )
        print()

        return

    print(
        f"   נמצאו {len(labels):,} Labels."
    )

    print()

    # ========================================================
    # GMAIL CONNECTION
    # ========================================================

    print(
        "3. מתחבר ל-Gmail..."
    )

    service = connect_to_gmail()

    print(
        "   החיבור הצליח."
    )

    print()

    # ========================================================
    # MESSAGE IDS
    # ========================================================

    print(
        "4. אוסף Message IDs מכל ה-Labels..."
    )

    print()

    label_message_ids = {}

    all_unique_message_ids = set()

    total_label_occurrences = 0

    for index, label in enumerate(
        labels,
        start=1,
    ):

        label_id = label["label_id"]
        label_name = label["label_name"]

        print(
            f"   [{index}/{len(labels)}] "
            f"{label_name}",
            flush=True,
        )

        message_ids = get_message_ids_for_label(
            service,
            label_id,
        )

        label_message_ids[
            label_id
        ] = message_ids

        all_unique_message_ids.update(
            message_ids
        )

        total_label_occurrences += len(
            message_ids
        )

        print(
            f"       {len(message_ids):,} מיילים"
        )

    unique_count = len(
        all_unique_message_ids
    )

    duplicate_count = (
        total_label_occurrences
        - unique_count
    )

    print()

    print(
        f"   סה\"כ הופעות לפי Labels: "
        f"{total_label_occurrences:,}"
    )

    print(
        f"   סה\"כ מיילים ייחודיים: "
        f"{unique_count:,}"
    )

    print(
        f"   כפילויות בין Labels: "
        f"{duplicate_count:,}"
    )

    print()

    # ========================================================
    # SAMPLE
    # ========================================================

    print(
        "5. בוחר מדגם אקראי של מיילים ייחודיים..."
    )

    rng = random.Random(
        RANDOM_SEED
    )

    if unique_count <= SAMPLE_SIZE:

        sample_ids = list(
            all_unique_message_ids
        )

        print(
            f"   כל {unique_count:,} המיילים ייבדקו."
        )

    else:

        sample_ids = rng.sample(
            list(all_unique_message_ids),
            SAMPLE_SIZE,
        )

        print(
            f"   נבחרו {len(sample_ids):,} "
            f"מתוך {unique_count:,}."
        )

    print()

    # ========================================================
    # SAMPLE ANALYSIS
    # ========================================================

    print(
        "6. מנתח את המיילים והצרופות במדגם..."
    )

    print()

    sample_data = {}

    errors = 0

    total_sample = len(
        sample_ids
    )

    for index, message_id in enumerate(
        sample_ids,
        start=1,
    ):

        if (
            index == 1
            or index % 25 == 0
            or index == total_sample
        ):

            print(
                f"   {index:,} / {total_sample:,}",
                flush=True,
            )

        try:

            data = analyze_message(
                service,
                message_id,
            )

            sample_data[
                message_id
            ] = data

        except Exception as exc:

            errors += 1

            print()

            print(
                f"   [WARNING] "
                f"{message_id}: {exc}"
            )

    print()

    if not sample_data:

        raise RuntimeError(
            "לא ניתן היה לנתח אף מייל במדגם."
        )

    # ========================================================
    # GLOBAL STATISTICS
    # ========================================================

    message_sizes = [
        item["message_size"]
        for item in sample_data.values()
    ]

    attachment_counts = [
        item["attachment_count"]
        for item in sample_data.values()
    ]

    attachment_sizes = [
        item["attachment_bytes"]
        for item in sample_data.values()
    ]

    valid_sample_count = len(
        sample_data
    )

    average_message_size = statistics.mean(
        message_sizes
    )

    median_message_size = statistics.median(
        message_sizes
    )

    average_attachment_count = statistics.mean(
        attachment_counts
    )

    average_attachment_bytes_per_message = (
        statistics.mean(
            attachment_sizes
        )
    )

    median_attachment_bytes_per_message = (
        statistics.median(
            attachment_sizes
        )
    )

    total_sample_attachment_bytes = sum(
        attachment_sizes
    )

    messages_with_attachments = sum(
        1
        for count in attachment_counts
        if count > 0
    )

    total_sample_attachments = sum(
        attachment_counts
    )

    # ========================================================
    # ESTIMATED GLOBAL TOTAL
    # ========================================================

    estimated_message_total = (
        average_message_size
        * unique_count
    )

    estimated_attachment_total = (
        average_attachment_bytes_per_message
        * unique_count
    )

    estimated_total = (
        estimated_message_total
        + estimated_attachment_total
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Gmail sizeEstimate normally already includes the
    # message's stored data, including MIME data.
    #
    # Therefore we must NOT simply add:
    #
    #     sizeEstimate + attachment_bytes
    #
    # because that could double-count attachments.
    #
    # Instead we present:
    #
    # 1. Gmail estimated message size
    # 2. Attachment component identified in the sample
    # 3. Estimated total based on Gmail sizeEstimate
    #
    # The attachment analysis is used to understand the
    # composition and scale of the storage.
    # --------------------------------------------------------

    # ========================================================
    # PER-LABEL ESTIMATION
    # ========================================================

    print(
        "=" * 80
    )

    print(
        "הערכת נפח לפי Label"
    )

    print(
        "=" * 80
    )

    print()

    for index, label in enumerate(
        labels,
        start=1,
    ):

        label_id = label["label_id"]
        label_name = label["label_name"]

        message_ids = label_message_ids.get(
            label_id,
            [],
        )

        label_message_count = len(
            message_ids
        )

        # ----------------------------------------------------
        # Important:
        #
        # A message can belong to multiple Labels.
        #
        # For each Label we estimate its size based on
        # the global sample average.
        # ----------------------------------------------------

        estimated_label_message_size = (
            label_message_count
            * average_message_size
        )

        estimated_label_attachment_size = (
            label_message_count
            * average_attachment_bytes_per_message
        )

        estimated_label_total = (
            estimated_label_message_size
        )

        print(
            f"{index:2}. {label_name}"
        )

        print(
            f"    מיילים: "
            f"{label_message_count:,}"
        )

        print(
            f"    נפח Gmail משוער: "
            f"{format_bytes(estimated_label_message_size)}"
        )

        print(
            f"    מתוכם צרופות - אומדן: "
            f"{format_bytes(estimated_label_attachment_size)}"
        )

        print(
            f"    סה\"כ נפח משוער: "
            f"{format_bytes(estimated_label_total)}"
        )

        print()

    # ========================================================
    # SAMPLE RESULTS
    # ========================================================

    print(
        "=" * 80
    )

    print(
        "סטטיסטיקות המדגם"
    )

    print(
        "=" * 80
    )

    print()

    print(
        f"מיילים במדגם: "
        f"{valid_sample_count:,}"
    )

    print(
        f"שגיאות: "
        f"{errors:,}"
    )

    print()

    print(
        "גודל ממוצע של מייל:"
    )

    print(
        f"  {format_bytes(average_message_size)}"
    )

    print()

    print(
        "חציון גודל מייל:"
    )

    print(
        f"  {format_bytes(median_message_size)}"
    )

    print()

    print(
        "מספר ממוצע של צרופות למייל:"
    )

    print(
        f"  {average_attachment_count:,.2f}"
    )

    print()

    print(
        "מיילים במדגם שיש בהם לפחות צרופה:"
    )

    print(
        f"  {messages_with_attachments:,}"
        f" / {valid_sample_count:,}"
    )

    print()

    print(
        "סה\"כ צרופות במדגם:"
    )

    print(
        f"  {total_sample_attachments:,}"
    )

    print()

    print(
        "ממוצע נפח צרופות למייל:"
    )

    print(
        f"  {format_bytes(average_attachment_bytes_per_message)}"
    )

    print()

    print(
        "חציון נפח צרופות למייל:"
    )

    print(
        f"  {format_bytes(median_attachment_bytes_per_message)}"
    )

    print()

    print(
        "סה\"כ נפח צרופות שנמדד במדגם:"
    )

    print(
        f"  {format_bytes(total_sample_attachment_bytes)}"
    )

    print()

    # ========================================================
    # GLOBAL ESTIMATE
    # ========================================================

    print(
        "=" * 80
    )

    print(
        "הערכת נפח כוללת"
    )

    print(
        "=" * 80
    )

    print()

    print(
        f"מספר מיילים ייחודיים: "
        f"{unique_count:,}"
    )

    print()

    print(
        "נפח Gmail משוער לפי sizeEstimate:"
    )

    print(
        f"  {format_bytes(estimated_message_total)}"
    )

    print()

    print(
        "נפח צרופות משוער לפי המדגם:"
    )

    print(
        f"  {format_bytes(estimated_attachment_total)}"
    )

    print()

    print(
        "חשוב:"
    )

    print(
        "נפח הצרופות מוצג בנפרד לצורך ניתוח,"
    )

    print(
        "אך אינו מתווסף שוב ל-sizeEstimate,"
    )

    print(
        "כדי לא ליצור ספירה כפולה של הצרופות."
    )

    print()

    print(
        "סה\"כ נפח משוער של Gmail:"
    )

    print(
        f"  {format_bytes(estimated_total)}"
    )

    print()

    # ========================================================
    # ATTACHMENT RATIO
    # ========================================================

    if average_message_size > 0:

        attachment_ratio = (
            average_attachment_bytes_per_message
            / average_message_size
            * 100
        )

    else:

        attachment_ratio = 0

    print(
        "חלק הצרופות מתוך גודל המייל הממוצע:"
    )

    print(
        f"  {attachment_ratio:,.1f}%"
    )

    print()

    # ========================================================
    # FINAL NOTES
    # ========================================================

    print(
        "=" * 80
    )

    print(
        "הערות חשובות"
    )

    print(
        "=" * 80
    )

    print()

    print(
        "1. זהו אומדן המבוסס על Sampling."
    )

    print(
        "2. sizeEstimate של Gmail הוא אומדן של גודל ההודעה."
    )

    print(
        "3. הצרופות נותחו מתוך מבנה ה-MIME של המדגם."
    )

    print(
        "4. תוכן הצרופות עצמן לא הורד."
    )

    print(
        "5. אם אותו מייל נמצא בכמה Labels,"
    )

    print(
        "   הוא נספר פעם אחת בלבד בסך המיילים הייחודיים."
    )

    print(
        "6. בהצגה לפי Label, אותו מייל יכול להופיע"
    )

    print(
        "   ביותר מ-Label אחד — לכן סכום כל ה-Labels"
    )

    print(
        "   אינו בהכרח שווה לנפח הייחודי הכולל."
    )

    print()

    print(
        "לא בוצע COPY."
    )

    print(
        "לא בוצע שינוי ב-Gmail."
    )

    print(
        "לא בוצע שינוי ב-Google Drive."
    )

    print(
        "לא בוצע שינוי ב-PostgreSQL."
    )

    print()

    print(
        "=" * 80
    )

    print(
        "הבדיקה הסתיימה."
    )

    print(
        "=" * 80
    )

    print()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()