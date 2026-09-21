# -*- coding: utf-8 -*-

"""
Alcalay - Unified Search Window

Central search window for Alcalay repositories.

Current active repository:

    - Gmail data already downloaded, parsed and indexed in PostgreSQL.

Important:

    - This window does NOT connect to Gmail.
    - It does NOT call the Gmail API.
    - It searches only data already stored locally/PostgreSQL.
    - Future repositories can be added without changing the main search UI.

Current Gmail search sources:

    public.gmail_search_index
    public.gmail_attachment_search_index
"""

from __future__ import annotations

import json
import sys

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


from database.connection import DatabaseConnection
from search.search_result_window import SearchResultWindow


class SearchWindow(QMainWindow):
    """
    Unified Alcalay repository search window.

    Current repository:

        Gmail / PostgreSQL

    Search is performed only against data already stored
    and indexed in PostgreSQL.

    No Gmail API access is performed here.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.db: Optional[DatabaseConnection] = None
        self.connection = None
        self.results: List[Dict[str, Any]] = []

        self.setWindowTitle("Alcalay - חיפוש במאגרים")
        self.setMinimumSize(1250, 820)
        self.resize(1450, 900)

        self._build_ui()
        self._connect_database()
        self._update_source_controls()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(12)

        title = QLabel("חיפוש במאגרים")
        title.setAlignment(Qt.AlignRight)
        title.setStyleSheet(
            """
            QLabel {
                font-size: 26px;
                font-weight: bold;
                padding: 6px;
            }
            """
        )
        main_layout.addWidget(title)

        subtitle = QLabel(
            "חיפוש במידע שכבר הורד, נשמר ועבר אינדוקס במערכת Alcalay."
        )
        subtitle.setAlignment(Qt.AlignRight)
        subtitle.setStyleSheet(
            """
            QLabel {
                font-size: 14px;
                color: #555555;
                padding-right: 8px;
            }
            """
        )
        main_layout.addWidget(subtitle)

        source_group = self._build_source_group()
        main_layout.addWidget(source_group)

        criteria_group = self._build_criteria_group()
        main_layout.addWidget(criteria_group)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        self.search_button = QPushButton("חיפוש")
        self.search_button.setMinimumHeight(42)
        self.search_button.setMinimumWidth(130)
        self.search_button.clicked.connect(self._perform_search)

        self.clear_button = QPushButton("ניקוי")
        self.clear_button.setMinimumHeight(42)
        self.clear_button.setMinimumWidth(100)
        self.clear_button.clicked.connect(self._clear_search)

        self.status_label = QLabel("מוכן לחיפוש")
        self.status_label.setAlignment(
            Qt.AlignRight | Qt.AlignVCenter
        )
        self.status_label.setStyleSheet(
            """
            QLabel {
                color: #555555;
                padding: 6px;
            }
            """
        )

        action_layout.addWidget(self.search_button)
        action_layout.addWidget(self.clear_button)
        action_layout.addStretch()
        action_layout.addWidget(self.status_label)

        main_layout.addLayout(action_layout)

        results_group = self._build_results_group()
        main_layout.addWidget(results_group, 1)

    def _build_source_group(self) -> QGroupBox:
        group = QGroupBox("חיפוש במאגרים")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        mode_layout = QHBoxLayout()

        mode_label = QLabel("חפש ב:")
        mode_label.setMinimumWidth(100)

        self.source_mode_combo = QComboBox()

        self.source_mode_combo.addItem(
            "כל המאגרים",
            "all",
        )

        self.source_mode_combo.addItem(
            "בחירת מאגרים",
            "selected",
        )

        self.source_mode_combo.currentIndexChanged.connect(
            self._update_source_controls
        )

        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.source_mode_combo)
        mode_layout.addStretch()

        layout.addLayout(mode_layout)

        repositories_layout = QHBoxLayout()

        self.gmail_checkbox = QCheckBox(
            "Gmail / PostgreSQL"
        )
        self.gmail_checkbox.setChecked(True)

        self.local_checkbox = QCheckBox(
            "ספרייה מקומית"
        )
        self.local_checkbox.setChecked(False)
        self.local_checkbox.setEnabled(False)

        self.google_drive_checkbox = QCheckBox(
            "Google Drive"
        )
        self.google_drive_checkbox.setChecked(False)
        self.google_drive_checkbox.setEnabled(False)

        self.server_checkbox = QCheckBox(
            "שרת מסמכים"
        )
        self.server_checkbox.setChecked(False)
        self.server_checkbox.setEnabled(False)

        repositories_layout.addWidget(self.gmail_checkbox)
        repositories_layout.addWidget(self.local_checkbox)
        repositories_layout.addWidget(self.google_drive_checkbox)
        repositories_layout.addWidget(self.server_checkbox)
        repositories_layout.addStretch()

        layout.addLayout(repositories_layout)

        future_label = QLabel(
            "מקורות שאינם פעילים כרגע יוצגו כאן ויתווספו לחיפוש "
            "כאשר החיבור והאינדוקס שלהם יוגדרו."
        )
        future_label.setAlignment(Qt.AlignRight)
        future_label.setStyleSheet(
            """
            QLabel {
                color: #777777;
                font-size: 12px;
            }
            """
        )

        layout.addWidget(future_label)

        return group

    def _build_criteria_group(self) -> QGroupBox:
        group = QGroupBox("קריטריוני חיפוש")
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        row = 0

        text_label = QLabel("חיפוש חופשי:")
        text_label.setAlignment(Qt.AlignRight)

        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText(
            "טקסט, מילה, ביטוי או מספר..."
        )
        self.text_edit.returnPressed.connect(
            self._perform_search
        )

        layout.addWidget(text_label, row, 0)
        layout.addWidget(
            self.text_edit,
            row,
            1,
            1,
            3,
        )

        row += 1

        self.search_attachments_checkbox = QCheckBox(
            "חפש בתוך מסמכים מצורפים"
        )
        self.search_attachments_checkbox.setChecked(False)

        self.search_attachments_checkbox.setToolTip(
            "כאשר מסומן, החיפוש מתבצע גם בתוך תוכן הקבצים "
            "המצורפים שניתן היה לחלץ מהם טקסט, וכן בשם הקובץ."
        )

        layout.addWidget(
            self.search_attachments_checkbox,
            row,
            1,
            1,
            3,
        )

        row += 1

        sender_label = QLabel("שולח:")
        sender_label.setAlignment(Qt.AlignRight)

        self.sender_edit = QLineEdit()
        self.sender_edit.setPlaceholderText(
            "שם או כתובת דוא״ל"
        )

        recipient_label = QLabel("נמען:")
        recipient_label.setAlignment(Qt.AlignRight)

        self.recipient_edit = QLineEdit()
        self.recipient_edit.setPlaceholderText(
            "שם או כתובת דוא״ל"
        )

        layout.addWidget(sender_label, row, 0)
        layout.addWidget(self.sender_edit, row, 1)
        layout.addWidget(recipient_label, row, 2)
        layout.addWidget(self.recipient_edit, row, 3)

        row += 1

        subject_label = QLabel("נושא:")
        subject_label.setAlignment(Qt.AlignRight)

        self.subject_edit = QLineEdit()
        self.subject_edit.setPlaceholderText(
            "נושא ההודעה"
        )

        attachment_label = QLabel("קבצים מצורפים:")
        attachment_label.setAlignment(Qt.AlignRight)

        self.attachment_combo = QComboBox()

        self.attachment_combo.addItem(
            "הכול",
            "all",
        )

        self.attachment_combo.addItem(
            "עם קבצים מצורפים",
            "yes",
        )

        self.attachment_combo.addItem(
            "ללא קבצים מצורפים",
            "no",
        )

        layout.addWidget(subject_label, row, 0)
        layout.addWidget(self.subject_edit, row, 1)
        layout.addWidget(attachment_label, row, 2)
        layout.addWidget(self.attachment_combo, row, 3)

        row += 1

        from_label = QLabel("מתאריך:")
        from_label.setAlignment(Qt.AlignRight)

        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDisplayFormat("dd/MM/yyyy")
        self.from_date.setDate(
            self.from_date.minimumDate()
        )

        to_label = QLabel("עד תאריך:")
        to_label.setAlignment(Qt.AlignRight)

        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDisplayFormat("dd/MM/yyyy")
        self.to_date.setSpecialValueText("ללא הגבלה")
        self.to_date.setDate(
            self.to_date.minimumDate()
        )

        self.from_enabled = QCheckBox("הפעל")
        self.to_enabled = QCheckBox("הפעל")

        self.from_enabled.toggled.connect(
            self.from_date.setEnabled
        )

        self.to_enabled.toggled.connect(
            self.to_date.setEnabled
        )

        self.from_date.setEnabled(False)
        self.to_date.setEnabled(False)

        from_layout = QHBoxLayout()
        from_layout.addWidget(self.from_enabled)
        from_layout.addWidget(self.from_date)

        to_layout = QHBoxLayout()
        to_layout.addWidget(self.to_enabled)
        to_layout.addWidget(self.to_date)

        layout.addWidget(from_label, row, 0)
        layout.addLayout(from_layout, row, 1)
        layout.addWidget(to_label, row, 2)
        layout.addLayout(to_layout, row, 3)

        row += 1

        info_label = QLabel(
            "החיפוש מתבצע על מידע שכבר עבר PARSE ו-INDEX. "
            "כאשר האפשרות לחיפוש בצרופות מסומנת, "
            "החיפוש כולל גם את אינדקס הצרופות."
        )
        info_label.setAlignment(Qt.AlignRight)
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            """
            QLabel {
                color: #666666;
                font-size: 12px;
            }
            """
        )

        layout.addWidget(
            info_label,
            row,
            0,
            1,
            4,
        )

        return group

    def _build_results_group(self) -> QGroupBox:
        group = QGroupBox("תוצאות")
        layout = QVBoxLayout(group)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(10)

        self.results_table.setHorizontalHeaderLabels(
            [
                "מקור",
                "תאריך",
                "שולח",
                "נמען",
                "נושא",
                "קבצים",
                "שם צרופה",
                "מזהה הודעה",
                "חשבון",
                "תוכן",
            ]
        )

        self.results_table.setSelectionBehavior(
            QTableWidget.SelectRows
        )

        self.results_table.setSelectionMode(
            QTableWidget.SingleSelection
        )

        self.results_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )

        self.results_table.setAlternatingRowColors(True)
        self.results_table.setWordWrap(True)

        self.results_table.cellDoubleClicked.connect(
            self._show_result_details
        )

        header = self.results_table.horizontalHeader()
        header.setStretchLastSection(True)

        layout.addWidget(self.results_table)

        return group

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    def _connect_database(self) -> None:
        self._close_database_connection()

        try:
            self.db = DatabaseConnection()
            self.connection = self.db.connect()

            if self.connection is None:
                self.db = None
                self.status_label.setText(
                    "לא ניתן להתחבר ל-PostgreSQL"
                )
                return

            self.status_label.setText(
                "מחובר ל-PostgreSQL"
            )

        except Exception as exc:
            self.db = None
            self.connection = None

            self.status_label.setText(
                f"שגיאת חיבור ל-PostgreSQL: {exc}"
            )

    def _get_connection(self):
        if self.connection is not None:
            return self.connection

        self._connect_database()

        if self.connection is None:
            return None

        return self.connection

    def _close_database_connection(self) -> None:
        connection = self.connection
        self.connection = None

        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

        self.db = None

    # ------------------------------------------------------------------
    # Source handling
    # ------------------------------------------------------------------

    def _update_source_controls(self) -> None:
        mode = self.source_mode_combo.currentData()
        selected_mode = mode == "selected"

        self.gmail_checkbox.setEnabled(
            selected_mode
        )

        if mode == "all":
            self.gmail_checkbox.setChecked(True)
            self.local_checkbox.setChecked(False)
            self.google_drive_checkbox.setChecked(False)
            self.server_checkbox.setChecked(False)

    def _selected_sources(self) -> List[str]:
        mode = self.source_mode_combo.currentData()

        if mode == "all":
            return ["gmail"]

        sources = []

        if self.gmail_checkbox.isChecked():
            sources.append("gmail")

        if self.local_checkbox.isChecked():
            sources.append("local")

        if self.google_drive_checkbox.isChecked():
            sources.append("google_drive")

        if self.server_checkbox.isChecked():
            sources.append("server")

        return sources

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _perform_search(self) -> None:
        sources = self._selected_sources()

        if not sources:
            QMessageBox.warning(
                self,
                "חיפוש",
                "יש לבחור לפחות מאגר אחד לחיפוש.",
            )
            return

        unsupported = [
            source
            for source in sources
            if source != "gmail"
        ]

        if unsupported:
            QMessageBox.information(
                self,
                "מקורות שעדיין אינם פעילים",
                "כרגע מנגנון החיפוש הפעיל הוא Gmail / PostgreSQL.\n\n"
                "המקורות האחרים מוכנים להוספה בעתיד, "
                "אך עדיין אינם מחוברים למנוע החיפוש.",
            )

        if "gmail" not in sources:
            self.results = []
            self._display_results()

            self.status_label.setText(
                "המקור שנבחר עדיין אינו פעיל."
            )
            return

        try:
            self.search_button.setEnabled(False)

            if self.search_attachments_checkbox.isChecked():
                self.status_label.setText(
                    "מחפש במיילים ובצרופות..."
                )
            else:
                self.status_label.setText(
                    "מחפש בנתוני Gmail המקומיים..."
                )

            QApplication.processEvents()

            email_query, email_params = self._build_gmail_query()

            email_rows = self._execute_gmail_search(
                email_query,
                email_params,
            )

            attachment_rows: List[Dict[str, Any]] = []

            if self.search_attachments_checkbox.isChecked():
                attachment_query, attachment_params = (
                    self._build_attachment_query()
                )

                attachment_rows = self._execute_gmail_search(
                    attachment_query,
                    attachment_params,
                )

            self.results = self._merge_search_results(
                email_rows,
                attachment_rows,
            )

            self._display_results()

            self.status_label.setText(
                f"נמצאו {len(self.results):,} תוצאות"
            )

        except Exception as exc:
            self.status_label.setText(
                "שגיאה בחיפוש"
            )

            QMessageBox.critical(
                self,
                "שגיאת חיפוש",
                f"לא ניתן לבצע את החיפוש:\n\n{exc}",
            )

        finally:
            self.search_button.setEnabled(True)

    def _build_common_conditions(
        self,
        table_alias: str = "g",
    ):
        conditions: List[str] = []
        params: List[Any] = []

        sender = self.sender_edit.text().strip()
        recipient = self.recipient_edit.text().strip()
        subject = self.subject_edit.text().strip()

        attachment_mode = (
            self.attachment_combo.currentData()
        )

        if sender:
            conditions.append(
                f"""
                (
                    {table_alias}.sender_email ILIKE %s
                    OR {table_alias}.sender_name ILIKE %s
                )
                """
            )

            sender_value = f"%{sender}%"

            params.extend(
                [
                    sender_value,
                    sender_value,
                ]
            )

        if recipient:
            conditions.append(
                f"""
                (
                    {table_alias}.recipients::text ILIKE %s
                    OR {table_alias}.cc_recipients::text ILIKE %s
                    OR {table_alias}.bcc_recipients::text ILIKE %s
                )
                """
            )

            recipient_value = f"%{recipient}%"

            params.extend(
                [
                    recipient_value,
                    recipient_value,
                    recipient_value,
                ]
            )

        if subject:
            conditions.append(
                f"{table_alias}.subject ILIKE %s"
            )

            params.append(
                f"%{subject}%"
            )

        if attachment_mode == "yes":
            conditions.append(
                f"{table_alias}.has_attachments = TRUE"
            )

        elif attachment_mode == "no":
            conditions.append(
                f"{table_alias}.has_attachments = FALSE"
            )

        if self.from_enabled.isChecked():
            date_value = self.from_date.date().toPython()

            conditions.append(
                f"{table_alias}.date_sent >= %s"
            )

            params.append(
                datetime(
                    date_value.year,
                    date_value.month,
                    date_value.day,
                    0,
                    0,
                    0,
                )
            )

        if self.to_enabled.isChecked():
            date_value = self.to_date.date().toPython()

            conditions.append(
                f"{table_alias}.date_sent < %s"
            )

            next_day = date_value + timedelta(days=1)

            params.append(
                datetime(
                    next_day.year,
                    next_day.month,
                    next_day.day,
                    0,
                    0,
                    0,
                )
            )

        return conditions, params

    def _build_gmail_query(self):
        conditions: List[str] = []
        params: List[Any] = []

        free_text = self.text_edit.text().strip()

        if free_text:
            conditions.append(
                """
                g.search_vector @@
                websearch_to_tsquery('simple', %s)
                """
            )

            params.append(free_text)

        common_conditions, common_params = (
            self._build_common_conditions("g")
        )

        conditions.extend(common_conditions)
        params.extend(common_params)

        where_clause = ""

        if conditions:
            where_clause = (
                "WHERE "
                + " AND ".join(conditions)
            )

        query = f"""
            SELECT
                g.id,
                g.gmail_message_id,
                g.gmail_message_key,
                g.gmail_account_id,
                g.mime_message_id,
                g.thread_id,
                g.subject,
                g.sender_name,
                g.sender_email,
                g.recipients,
                g.cc_recipients,
                g.bcc_recipients,
                g.date_sent,
                g.body_text,
                g.body_html,
                g.search_text,
                g.has_attachments,
                g.attachment_count,
                g.raw_sha256,
                g.raw_size,
                g.parser_version,
                g.index_version,
                g.indexed_at,
                g.updated_at,
                g.metadata,
                'email' AS result_type,
                NULL::bigint AS gmail_attachment_id,
                NULL::text AS attachment_file_name,
                NULL::text AS attachment_mime_type,
                NULL::text AS attachment_local_path,
                NULL::text AS attachment_extracted_text,
                NULL::text AS attachment_search_text
            FROM gmail_search_index AS g
            {where_clause}
            ORDER BY
                g.date_sent DESC NULLS LAST,
                g.id DESC
            LIMIT 1000
        """

        return query, params

    def _build_attachment_query(self):
        conditions: List[str] = []
        params: List[Any] = []

        free_text = self.text_edit.text().strip()

        if free_text:
            conditions.append(
                """
                (
                    a.search_vector @@
                    websearch_to_tsquery('simple', %s)
                    OR a.file_name ILIKE %s
                )
                """
            )

            params.append(free_text)
            params.append(f"%{free_text}%")

        common_conditions, common_params = (
            self._build_common_conditions("g")
        )

        conditions.extend(common_conditions)
        params.extend(common_params)

        where_clause = ""

        if conditions:
            where_clause = (
                "WHERE "
                + " AND ".join(conditions)
            )

        query = f"""
            SELECT
                g.id,
                g.gmail_message_id,
                g.gmail_message_key,
                g.gmail_account_id,
                g.mime_message_id,
                g.thread_id,
                g.subject,
                g.sender_name,
                g.sender_email,
                g.recipients,
                g.cc_recipients,
                g.bcc_recipients,
                g.date_sent,
                g.body_text,
                g.body_html,
                g.search_text,
                g.has_attachments,
                g.attachment_count,
                g.raw_sha256,
                g.raw_size,
                g.parser_version,
                g.index_version,
                g.indexed_at,
                g.updated_at,
                g.metadata,

                'attachment' AS result_type,

                a.gmail_attachment_id,
                a.file_name AS attachment_file_name,
                a.mime_type AS attachment_mime_type,
                a.local_path AS attachment_local_path,
                a.extracted_text AS attachment_extracted_text,
                a.search_text AS attachment_search_text

            FROM gmail_attachment_search_index AS a
            INNER JOIN gmail_search_index AS g
                ON g.gmail_message_id = a.gmail_message_id

            {where_clause}

            ORDER BY
                g.date_sent DESC NULLS LAST,
                a.id DESC

            LIMIT 1000
        """

        return query, params

    def _merge_search_results(
        self,
        email_rows: List[Dict[str, Any]],
        attachment_rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []

        results.extend(email_rows)
        results.extend(attachment_rows)

        results.sort(
            key=self._result_sort_key,
            reverse=True,
        )

        return results[:2000]

    def _result_sort_key(
        self,
        result: Dict[str, Any],
    ):
        date_value = result.get("date_sent")

        if isinstance(date_value, datetime):
            return (
                date_value,
                result.get("id") or 0,
            )

        return (
            datetime.min,
            result.get("id") or 0,
        )

    def _execute_gmail_search(
        self,
        query: str,
        params: List[Any],
    ) -> List[Dict[str, Any]]:
        connection = self._get_connection()

        if connection is None:
            raise RuntimeError(
                "אין חיבור פעיל ל-PostgreSQL."
            )

        cursor = None

        try:
            cursor = connection.cursor()

            cursor.execute(
                query,
                params,
            )

            rows = cursor.fetchall()

            columns = [
                description[0]
                for description in cursor.description
            ]

            result = []

            for row in rows:
                item = dict(
                    zip(
                        columns,
                        row,
                    )
                )

                result.append(item)

            return result

        finally:
            if cursor is not None:
                cursor.close()

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def _display_results(self) -> None:
        self.results_table.setRowCount(0)

        for row_index, result in enumerate(
            self.results
        ):
            self.results_table.insertRow(
                row_index
            )

            result_type = result.get(
                "result_type"
            )

            if result_type == "attachment":
                source_text = "Gmail / צרופה"
            else:
                source_text = "Gmail"

            source_item = QTableWidgetItem(
                source_text
            )

            date_item = QTableWidgetItem(
                self._format_datetime(
                    result.get("date_sent")
                )
            )

            sender_item = QTableWidgetItem(
                self._sender_text(result)
            )

            recipient_item = QTableWidgetItem(
                self._recipients_text(result)
            )

            subject_item = QTableWidgetItem(
                self._safe_text(
                    result.get("subject")
                )
            )

            attachment_count = (
                result.get("attachment_count")
                or 0
            )

            if result.get("has_attachments"):
                attachment_text = (
                    f"כן ({attachment_count})"
                )
            else:
                attachment_text = "לא"

            attachment_item = QTableWidgetItem(
                attachment_text
            )

            attachment_name = (
                self._safe_text(
                    result.get(
                        "attachment_file_name"
                    )
                )
            )

            attachment_name_item = QTableWidgetItem(
                attachment_name
            )

            message_id_item = QTableWidgetItem(
                self._safe_text(
                    result.get(
                        "gmail_message_key"
                    )
                )
            )

            account_item = QTableWidgetItem(
                self._safe_text(
                    result.get(
                        "gmail_account_id"
                    )
                )
            )

            if result_type == "attachment":
                content = (
                    result.get(
                        "attachment_extracted_text"
                    )
                    or result.get(
                        "attachment_search_text"
                    )
                    or result.get(
                        "body_text"
                    )
                )
            else:
                content = result.get(
                    "body_text"
                )

                if not content:
                    content = result.get(
                        "search_text"
                    )

            content_item = QTableWidgetItem(
                self._make_preview(content)
            )

            items = [
                source_item,
                date_item,
                sender_item,
                recipient_item,
                subject_item,
                attachment_item,
                attachment_name_item,
                message_id_item,
                account_item,
                content_item,
            ]

            for column, item in enumerate(items):
                item.setTextAlignment(
                    Qt.AlignRight
                    | Qt.AlignVCenter
                )

                self.results_table.setItem(
                    row_index,
                    column,
                    item,
                )

        self.results_table.resizeColumnsToContents()

        widths = {
            0: 120,
            1: 150,
            2: 220,
            3: 260,
            4: 300,
            5: 100,
            6: 260,
            7: 240,
            8: 100,
            9: 450,
        }

        for column, width in widths.items():
            self.results_table.setColumnWidth(
                column,
                width,
            )

    # ------------------------------------------------------------------
    # Result details
    # ------------------------------------------------------------------

    def _show_result_details(
        self,
        row: int,
        column: int,
    ) -> None:
        if row < 0:
            return

        if row >= len(self.results):
            return

        result = self.results[row]

        window = SearchResultWindow(
            result,
            self,
        )

        window.setAttribute(
            Qt.WA_DeleteOnClose,
            True,
        )

        window.show()
        window.raise_()
        window.activateWindow()

    def _format_result_details(
        self,
        result: Dict[str, Any],
    ) -> str:
        lines: List[str] = []

        result_type = result.get(
            "result_type"
        )

        if result_type == "attachment":
            lines.append(
                "מקור: Gmail / צרופה"
            )

            lines.append(
                f"שם צרופה: "
                f"{self._safe_text(result.get('attachment_file_name'))}"
            )

            lines.append(
                f"סוג: "
                f"{self._safe_text(result.get('attachment_mime_type'))}"
            )

            lines.append(
                f"נתיב מקומי: "
                f"{self._safe_text(result.get('attachment_local_path'))}"
            )
        else:
            lines.append(
                "מקור: Gmail / PostgreSQL"
            )

        lines.append(
            f"תאריך: "
            f"{self._format_datetime(result.get('date_sent'))}"
        )

        lines.append(
            f"שולח: "
            f"{self._sender_text(result)}"
        )

        lines.append(
            f"נמען: "
            f"{self._recipients_text(result)}"
        )

        lines.append(
            f"נושא: "
            f"{self._safe_text(result.get('subject'))}"
        )

        lines.append(
            f"Message Key: "
            f"{self._safe_text(result.get('gmail_message_key'))}"
        )

        lines.append(
            f"Thread ID: "
            f"{self._safe_text(result.get('thread_id'))}"
        )

        lines.append(
            f"Message ID: "
            f"{self._safe_text(result.get('mime_message_id'))}"
        )

        lines.append(
            f"מצורפים: "
            f"{'כן' if result.get('has_attachments') else 'לא'}"
        )

        lines.append(
            f"מספר מצורפים: "
            f"{result.get('attachment_count') or 0}"
        )

        lines.append(
            f"SHA256: "
            f"{self._safe_text(result.get('raw_sha256'))}"
        )

        lines.append(
            f"גרסת PARSE: "
            f"{self._safe_text(result.get('parser_version'))}"
        )

        lines.append(
            f"גרסת INDEX: "
            f"{self._safe_text(result.get('index_version'))}"
        )

        lines.append("")

        if result_type == "attachment":
            lines.append(
                "תוכן הצרופה:"
            )

            attachment_content = (
                result.get(
                    "attachment_extracted_text"
                )
                or result.get(
                    "attachment_search_text"
                )
            )

            lines.append(
                self._safe_text(
                    attachment_content
                    or "לא חולץ טקסט מהצרופה."
                )
            )

        else:
            lines.append(
                "תוכן:"
            )

            lines.append(
                self._safe_text(
                    result.get("body_text")
                    or result.get("search_text")
                )
            )

        metadata = result.get("metadata")

        if metadata:
            lines.append("")
            lines.append("Metadata:")

            try:
                lines.append(
                    json.dumps(
                        metadata,
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    )
                )

            except Exception:
                lines.append(
                    self._safe_text(metadata)
                )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def _clear_search(self) -> None:
        self.text_edit.clear()
        self.sender_edit.clear()
        self.recipient_edit.clear()
        self.subject_edit.clear()

        self.search_attachments_checkbox.setChecked(
            False
        )

        self.attachment_combo.setCurrentIndex(
            0
        )

        self.from_enabled.setChecked(False)
        self.to_enabled.setChecked(False)

        self.results = []
        self.results_table.setRowCount(0)

        self.status_label.setText(
            "מוכן לחיפוש"
        )

        self.text_edit.setFocus()

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_text(value: Any) -> str:
        if value is None:
            return ""

        if isinstance(value, str):
            return value

        try:
            return str(value)
        except Exception:
            return ""

    def _format_datetime(
        self,
        value: Any,
    ) -> str:
        if value is None:
            return ""

        if isinstance(value, datetime):
            return value.strftime(
                "%d/%m/%Y %H:%M"
            )

        return self._safe_text(value)

    def _sender_text(
        self,
        result: Dict[str, Any],
    ) -> str:
        name = self._safe_text(
            result.get("sender_name")
        )

        email = self._safe_text(
            result.get("sender_email")
        )

        if name and email:
            return f"{name} <{email}>"

        return name or email

    def _recipients_text(
        self,
        result: Dict[str, Any],
    ) -> str:
        recipients = result.get(
            "recipients"
        )

        text = self._json_to_text(
            recipients
        )

        if text:
            return text

        cc = self._json_to_text(
            result.get("cc_recipients")
        )

        if cc:
            return f"CC: {cc}"

        return ""

    def _json_to_text(
        self,
        value: Any,
    ) -> str:
        if value is None:
            return ""

        if isinstance(value, str):
            return value

        if isinstance(value, list):
            parts = []

            for item in value:
                if isinstance(item, dict):
                    name = self._safe_text(
                        item.get("name")
                    )

                    email = self._safe_text(
                        item.get("email")
                    )

                    if name and email:
                        parts.append(
                            f"{name} <{email}>"
                        )

                    elif email:
                        parts.append(email)

                    elif name:
                        parts.append(name)

                    else:
                        parts.append(
                            self._safe_text(item)
                        )

                else:
                    parts.append(
                        self._safe_text(item)
                    )

            return ", ".join(
                part
                for part in parts
                if part
            )

        if isinstance(value, dict):
            name = self._safe_text(
                value.get("name")
            )

            email = self._safe_text(
                value.get("email")
            )

            if name and email:
                return f"{name} <{email}>"

            if email:
                return email

            if name:
                return name

            try:
                return json.dumps(
                    value,
                    ensure_ascii=False,
                )

            except Exception:
                return self._safe_text(value)

        return self._safe_text(value)

    def _make_preview(
        self,
        value: Any,
        maximum: int = 350,
    ) -> str:
        text = self._safe_text(value)

        text = " ".join(
            text.split()
        )

        if len(text) <= maximum:
            return text

        return text[:maximum - 3] + "..."

    # ------------------------------------------------------------------
    # Qt lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        self._close_database_connection()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = SearchWindow()
    window.show()

    sys.exit(
        app.exec()
    )