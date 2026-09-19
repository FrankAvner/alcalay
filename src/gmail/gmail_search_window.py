# -*- coding: utf-8 -*-

"""
Alcalay - Gmail Search Window

Direct Gmail search UI.

This version searches Gmail directly through the Gmail API.
It does NOT synchronize or save messages locally.

Supported search criteria:
    - Gmail account
    - Gmail labels
    - message type
    - sender
    - recipient
    - subject
    - message content
    - attachments
    - date range

The UI is intentionally independent from the future local/PostgreSQL
search layer.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# ==============================================================
# PROJECT PATH
# ==============================================================

# מאפשר להריץ את הקובץ ישירות:
#
# ./.venv/bin/python src/gmail/gmail_search_window.py
#
# בלי לקבל:
# ModuleNotFoundError: No module named 'gmail'

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# ==============================================================
# PYTHON / QT IMPORTS
# ==============================================================

from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QAbstractItemView,
)

# ==============================================================
# ALCALAY GMAIL MODULES
# ==============================================================

from gmail.gmail_connection import GmailConnection
from gmail.gmail_accounts import GmailAccountsManager


class GmailSearchWindow(QMainWindow):
    """
    Direct Gmail search window.

    No local synchronization is performed here.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Alcalay - חיפוש Gmail")
        self.setMinimumSize(1250, 800)

        self.accounts_manager = GmailAccountsManager()

        self.connection: Optional[GmailConnection] = None
        self.selected_email = ""

        self.account_data = []
        self.available_labels = []
        self.last_results = []

        self._build_ui()
        self._apply_style()
        self._load_accounts()

    # ==============================================================
    # STYLE
    # ==============================================================

    def _apply_style(self):
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #f5f6f8;
            }

            QWidget {
                font-size: 13px;
            }

            QLabel {
                color: #202124;
            }

            QLabel#windowTitle {
                font-size: 22px;
                font-weight: bold;
                color: #202124;
            }

            QLabel#sectionTitle {
                font-size: 16px;
                font-weight: bold;
                color: #202124;
            }

            QLabel#sectionInfo {
                color: #6b7280;
                font-size: 12px;
            }

            QLabel#queryLabel {
                color: #5f6368;
                font-size: 12px;
            }

            QLabel#resultCount {
                color: #1a73e8;
                font-weight: bold;
            }

            QFrame#card {
                background-color: white;
                border: 1px solid #d9dce1;
                border-radius: 8px;
            }

            QLineEdit,
            QComboBox,
            QDateEdit {
                background-color: white;
                border: 1px solid #c9cdd3;
                border-radius: 5px;
                padding: 7px;
                min-height: 20px;
            }

            QLineEdit:focus,
            QComboBox:focus,
            QDateEdit:focus {
                border: 1px solid #1a73e8;
            }

            QListWidget {
                background-color: white;
                border: 1px solid #d9dce1;
                border-radius: 5px;
                padding: 4px;
            }

            QListWidget::item {
                padding: 6px;
                border-radius: 4px;
            }

            QListWidget::item:hover {
                background-color: #f1f3f4;
            }

            QListWidget::item:selected {
                background-color: #dbeafe;
                color: #111827;
            }

            QPushButton {
                background-color: white;
                border: 1px solid #c9cdd3;
                border-radius: 5px;
                padding: 7px 14px;
                min-height: 20px;
            }

            QPushButton:hover {
                background-color: #f0f2f5;
            }

            QPushButton:pressed {
                background-color: #e5e7eb;
            }

            QPushButton:disabled {
                color: #9ca3af;
                background-color: #f3f4f6;
            }

            QPushButton#primaryButton {
                background-color: #1a73e8;
                color: white;
                border: 1px solid #1a73e8;
                font-weight: bold;
            }

            QPushButton#primaryButton:hover {
                background-color: #1765cc;
            }

            QTableWidget {
                background-color: white;
                border: 1px solid #d9dce1;
                border-radius: 5px;
                gridline-color: #e5e7eb;
            }

            QTableWidget::item {
                padding: 6px;
            }

            QTableWidget::item:selected {
                background-color: #dbeafe;
                color: #111827;
            }

            QHeaderView::section {
                background-color: #f8f9fa;
                border: none;
                border-bottom: 1px solid #d9dce1;
                padding: 7px;
                font-weight: bold;
            }

            QSplitter::handle {
                background-color: #e5e7eb;
            }
            """
        )

    # ==============================================================
    # UI
    # ==============================================================

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        title = QLabel("חיפוש Gmail")
        title.setObjectName("windowTitle")

        subtitle = QLabel(
            "חיפוש ישיר מול Gmail. "
            "בשלב זה לא מתבצעת שמירה או סנכרון למאגר המקומי."
        )
        subtitle.setObjectName("sectionInfo")

        main_layout.addWidget(title)
        main_layout.addWidget(subtitle)

        search_card = QFrame()
        search_card.setObjectName("card")

        search_layout = QVBoxLayout(search_card)
        search_layout.setContentsMargins(15, 15, 15, 15)
        search_layout.setSpacing(10)

        section_title = QLabel("תנאי חיפוש")
        section_title.setObjectName("sectionTitle")

        search_layout.addWidget(section_title)

        account_row = QHBoxLayout()

        account_label = QLabel("חשבון Gmail:")
        account_label.setFixedWidth(120)

        self.account_combo = QComboBox()
        self.account_combo.setMinimumWidth(350)
        self.account_combo.currentIndexChanged.connect(
            self._account_changed
        )

        account_row.addWidget(account_label)
        account_row.addWidget(self.account_combo)
        account_row.addStretch()

        search_layout.addLayout(account_row)

        labels_title = QLabel("תגיות:")
        labels_title.setObjectName("sectionInfo")

        search_layout.addWidget(labels_title)

        self.labels_list = QListWidget()
        self.labels_list.setSelectionMode(
            QAbstractItemView.NoSelection
        )
        self.labels_list.setMinimumHeight(120)
        self.labels_list.setMaximumHeight(170)

        search_layout.addWidget(self.labels_list)

        type_row = QHBoxLayout()

        type_label = QLabel("סוג מייל:")
        type_label.setFixedWidth(120)

        self.type_combo = QComboBox()

        self.type_combo.addItem("כל סוגי המייל", "")
        self.type_combo.addItem("נכנס", "in:inbox")
        self.type_combo.addItem("נשלח", "from:me")
        self.type_combo.addItem("טיוטה", "in:drafts")
        self.type_combo.addItem("לא נקרא", "is:unread")
        self.type_combo.addItem("נקרא", "is:read")
        self.type_combo.addItem("חשוב", "is:important")
        self.type_combo.addItem("מסומן בכוכב", "is:starred")

        type_row.addWidget(type_label)
        type_row.addWidget(self.type_combo)
        type_row.addStretch()

        search_layout.addLayout(type_row)

        people_row = QHBoxLayout()

        sender_label = QLabel("שולח:")
        sender_label.setFixedWidth(70)

        self.sender_edit = QLineEdit()
        self.sender_edit.setPlaceholderText(
            "כתובת או שם השולח"
        )

        recipient_label = QLabel("נמען:")
        recipient_label.setFixedWidth(70)

        self.recipient_edit = QLineEdit()
        self.recipient_edit.setPlaceholderText(
            "כתובת או שם הנמען"
        )

        people_row.addWidget(sender_label)
        people_row.addWidget(self.sender_edit, 1)
        people_row.addWidget(recipient_label)
        people_row.addWidget(self.recipient_edit, 1)

        search_layout.addLayout(people_row)

        text_row = QHBoxLayout()

        subject_label = QLabel("נושא:")
        subject_label.setFixedWidth(70)

        self.subject_edit = QLineEdit()
        self.subject_edit.setPlaceholderText(
            "חיפוש בתוך נושא המייל"
        )

        content_label = QLabel("תוכן:")
        content_label.setFixedWidth(70)

        self.content_edit = QLineEdit()
        self.content_edit.setPlaceholderText(
            "חיפוש בתוך תוכן המייל"
        )

        text_row.addWidget(subject_label)
        text_row.addWidget(self.subject_edit, 1)
        text_row.addWidget(content_label)
        text_row.addWidget(self.content_edit, 1)

        search_layout.addLayout(text_row)

        attachment_row = QHBoxLayout()

        attachment_label = QLabel("צרופות:")
        attachment_label.setFixedWidth(120)

        self.attachment_combo = QComboBox()
        self.attachment_combo.addItem("לא משנה", "")
        self.attachment_combo.addItem(
            "יש צרופה",
            "has:attachment",
        )
        self.attachment_combo.addItem(
            "אין צרופה",
            "-has:attachment",
        )

        attachment_row.addWidget(attachment_label)
        attachment_row.addWidget(self.attachment_combo)
        attachment_row.addStretch()

        search_layout.addLayout(attachment_row)

        dates_row = QHBoxLayout()

        from_label = QLabel("מתאריך:")
        from_label.setFixedWidth(120)

        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDisplayFormat("dd/MM/yyyy")
        self.from_date.setSpecialValueText("ללא תאריך")

        to_label = QLabel("עד תאריך:")
        to_label.setFixedWidth(100)

        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDisplayFormat("dd/MM/yyyy")
        self.to_date.setSpecialValueText("ללא תאריך")

        dates_row.addWidget(from_label)
        dates_row.addWidget(self.from_date)
        dates_row.addSpacing(20)
        dates_row.addWidget(to_label)
        dates_row.addWidget(self.to_date)
        dates_row.addStretch()

        search_layout.addLayout(dates_row)

        buttons_row = QHBoxLayout()

        self.search_button = QPushButton("🔍 חיפוש")
        self.search_button.setObjectName("primaryButton")
        self.search_button.clicked.connect(
            self._perform_search
        )

        self.clear_button = QPushButton("נקה")
        self.clear_button.clicked.connect(
            self._clear_search
        )

        buttons_row.addWidget(self.search_button)
        buttons_row.addWidget(self.clear_button)
        buttons_row.addStretch()

        search_layout.addLayout(buttons_row)

        query_title = QLabel(
            "שאילתת Gmail שנבנתה:"
        )
        query_title.setObjectName("queryLabel")

        search_layout.addWidget(query_title)

        self.query_label = QLabel("")
        self.query_label.setObjectName(
            "queryLabel"
        )
        self.query_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        self.query_label.setWordWrap(True)

        search_layout.addWidget(
            self.query_label
        )

        main_layout.addWidget(search_card)

        results_card = QFrame()
        results_card.setObjectName("card")

        results_layout = QVBoxLayout(
            results_card
        )
        results_layout.setContentsMargins(
            15,
            15,
            15,
            15,
        )

        results_header = QHBoxLayout()

        results_title = QLabel("תוצאות")
        results_title.setObjectName(
            "sectionTitle"
        )

        self.result_count_label = QLabel(
            "0 תוצאות"
        )
        self.result_count_label.setObjectName(
            "resultCount"
        )

        results_header.addWidget(
            results_title
        )
        results_header.addSpacing(15)
        results_header.addWidget(
            self.result_count_label
        )
        results_header.addStretch()

        results_layout.addLayout(
            results_header
        )

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(7)
        self.results_table.setHorizontalHeaderLabels(
            [
                "תאריך",
                "שולח",
                "נמען",
                "נושא",
                "תגיות",
                "צרופות",
                "Snippet",
            ]
        )

        self.results_table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.results_table.setSelectionMode(
            QAbstractItemView.SingleSelection
        )
        self.results_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.results_table.setAlternatingRowColors(
            True
        )
        self.results_table.doubleClicked.connect(
            self._show_message_details
        )

        header = self.results_table.horizontalHeader()
        header.setStretchLastSection(True)

        results_layout.addWidget(
            self.results_table
        )

        main_layout.addWidget(
            results_card,
            1,
        )

        self.status_label = QLabel("")
        self.status_label.setObjectName(
            "sectionInfo"
        )

        main_layout.addWidget(
            self.status_label
        )

    # ==============================================================
    # ACCOUNTS
    # ==============================================================

    def _load_accounts(self):
        self.account_data = (
            self.accounts_manager.get_accounts()
        )

        self.account_combo.blockSignals(True)
        self.account_combo.clear()

        for account in self.account_data:
            if not account.get(
                "enabled",
                True,
            ):
                continue

            email = account.get(
                "email",
                "",
            ).strip()

            if not email:
                continue

            self.account_combo.addItem(
                email,
                email,
            )

        self.account_combo.blockSignals(
            False
        )

        if self.account_combo.count() > 0:
            self.account_combo.setCurrentIndex(
                0
            )
            self._account_changed(0)
        else:
            self._set_status(
                "לא נמצאו חשבונות Gmail מוגדרים."
            )

    def _account_changed(self, index: int):
        if index < 0:
            return

        email = self.account_combo.currentData()

        if not email:
            return

        self.selected_email = email

        try:
            self.connection = GmailConnection(
                email
            )

            connected_email = (
                self.connection.connect(email)
            )

            self.selected_email = (
                connected_email
            )

            self._load_labels()

            self._set_status(
                f"מחובר ל־Gmail: {connected_email}"
            )

        except Exception as exc:
            self.connection = None
            self.labels_list.clear()

            self._set_status(
                f"שגיאה בחיבור ל־Gmail: {exc}"
            )

            QMessageBox.critical(
                self,
                "שגיאת Gmail",
                f"לא ניתן להתחבר לחשבון:\n\n"
                f"{email}\n\n"
                f"{exc}",
            )

    # ==============================================================
    # LABELS
    # ==============================================================

    def _load_labels(self):
        self.labels_list.clear()

        if not self.connection:
            return

        service = self.connection.get_service()

        if service is None:
            return

        try:
            response = (
                service.users()
                .labels()
                .list(userId="me")
                .execute()
            )

            labels = response.get(
                "labels",
                [],
            )

            linked = (
                self.accounts_manager.get_labels(
                    self.selected_email
                )
            )

            labels_by_id = {
                item.get("id"): item
                for item in labels
            }

            self.available_labels = []

            for linked_label in linked:
                label_id = linked_label.get(
                    "id"
                )

                gmail_label = labels_by_id.get(
                    label_id
                )

                if not gmail_label:
                    continue

                label_name = gmail_label.get(
                    "name",
                    linked_label.get(
                        "name",
                        label_id,
                    ),
                )

                item = QListWidgetItem(
                    label_name
                )

                item.setData(
                    Qt.UserRole,
                    label_id,
                )

                item.setCheckState(
                    Qt.Unchecked
                )

                self.labels_list.addItem(
                    item
                )

                self.available_labels.append(
                    {
                        "id": label_id,
                        "name": label_name,
                    }
                )

            if not self.labels_list.count():
                item = QListWidgetItem(
                    "לא הוגדרו תגיות עבור החשבון"
                )

                item.setFlags(
                    Qt.ItemIsEnabled
                )

                self.labels_list.addItem(
                    item
                )

        except Exception as exc:
            self._set_status(
                f"שגיאה בטעינת תגיות: {exc}"
            )

    # ==============================================================
    # SEARCH QUERY
    # ==============================================================

    def _build_query(self) -> str:
        parts = []

        selected_labels = []

        for index in range(
            self.labels_list.count()
        ):
            item = self.labels_list.item(
                index
            )

            if not item:
                continue

            label_id = item.data(
                Qt.UserRole
            )

            if not label_id:
                continue

            if (
                item.checkState()
                == Qt.Checked
            ):
                selected_labels.append(
                    label_id
                )

        for label_id in selected_labels:
            parts.append(
                f"label:{self._quote_if_needed(label_id)}"
            )

        type_query = (
            self.type_combo.currentData()
        )

        if type_query:
            parts.append(type_query)

        sender = (
            self.sender_edit.text().strip()
        )

        if sender:
            parts.append(
                f"from:{self._quote_if_needed(sender)}"
            )

        recipient = (
            self.recipient_edit.text().strip()
        )

        if recipient:
            parts.append(
                f"to:{self._quote_if_needed(recipient)}"
            )

        subject = (
            self.subject_edit.text().strip()
        )

        if subject:
            parts.append(
                f"subject:{self._quote_if_needed(subject)}"
            )

        content = (
            self.content_edit.text().strip()
        )

        if content:
            parts.append(
                self._quote_if_needed(content)
            )

        attachment_query = (
            self.attachment_combo.currentData()
        )

        if attachment_query:
            parts.append(
                attachment_query
            )

        if (
            self.from_date.date().isValid()
            and self.from_date.date()
            != self.from_date.minimumDate()
        ):
            from_date = (
                self.from_date.date().toString(
                    "yyyy/MM/dd"
                )
            )

            parts.append(
                f"after:{from_date}"
            )

        if (
            self.to_date.date().isValid()
            and self.to_date.date()
            != self.to_date.minimumDate()
        ):
            next_day = (
                self.to_date.date().addDays(1)
            )

            to_date = next_day.toString(
                "yyyy/MM/dd"
            )

            parts.append(
                f"before:{to_date}"
            )

        return " ".join(parts)

    @staticmethod
    def _quote_if_needed(
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            return value

        if any(
            char.isspace()
            for char in value
        ):
            escaped = value.replace(
                '"',
                '\\"',
            )

            return f'"{escaped}"'

        return value

    # ==============================================================
    # SEARCH
    # ==============================================================

    def _perform_search(self):
        if not self.connection:
            QMessageBox.warning(
                self,
                "אין חיבור",
                "אין חיבור פעיל לחשבון Gmail.",
            )
            return

        service = (
            self.connection.get_service()
        )

        if service is None:
            QMessageBox.warning(
                self,
                "אין חיבור",
                "שירות Gmail אינו זמין.",
            )
            return

        query = self._build_query()

        self.query_label.setText(
            query
            if query
            else "(ללא תנאי חיפוש)"
        )

        self.search_button.setEnabled(
            False
        )

        self._set_status(
            "מבצע חיפוש ב־Gmail..."
        )

        QApplication.processEvents()

        try:
            messages = (
                self._search_messages(
                    service,
                    query,
                )
            )

            self.last_results = messages

            self._display_results(
                messages
            )

            self._set_status(
                f"החיפוש הסתיים. נמצאו "
                f"{len(messages)} תוצאות."
            )

        except Exception as exc:
            self._set_status(
                f"שגיאה בחיפוש: {exc}"
            )

            QMessageBox.critical(
                self,
                "שגיאת חיפוש",
                f"החיפוש ב־Gmail נכשל:\n\n{exc}",
            )

        finally:
            self.search_button.setEnabled(
                True
            )

    def _search_messages(
        self,
        service,
        query: str,
    ):
        results = []

        request = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=100,
            )
        )

        while (
            request
            and len(results) < 500
        ):
            response = request.execute()

            message_refs = response.get(
                "messages",
                [],
            )

            for message_ref in message_refs:
                if len(results) >= 500:
                    break

                message_id = (
                    message_ref.get("id")
                )

                if not message_id:
                    continue

                message = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=message_id,
                        format="full",
                    )
                    .execute()
                )

                results.append(
                    self._extract_message_summary(
                        message
                    )
                )

            next_page_token = (
                response.get(
                    "nextPageToken"
                )
            )

            if not next_page_token:
                break

            request = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=100,
                    pageToken=next_page_token,
                )
            )

        return results

    # ==============================================================
    # MESSAGE EXTRACTION
    # ==============================================================

    def _extract_message_summary(
        self,
        message,
    ):
        payload = message.get(
            "payload",
            {},
        )

        headers = {}

        for header in payload.get(
            "headers",
            [],
        ):
            name = header.get(
                "name",
                "",
            ).lower()

            value = header.get(
                "value",
                "",
            )

            if name:
                headers[name] = value

        label_ids = message.get(
            "labelIds",
            [],
        )

        label_names = self._label_names(
            label_ids
        )

        attachments = (
            self._find_attachments(
                payload
            )
        )

        internal_date = message.get(
            "internalDate"
        )

        date_text = ""

        if internal_date:
            try:
                dt = datetime.fromtimestamp(
                    int(internal_date) / 1000
                )

                date_text = dt.strftime(
                    "%d/%m/%Y %H:%M"
                )

            except Exception:
                date_text = str(
                    internal_date
                )

        return {
            "id": message.get(
                "id",
                "",
            ),
            "thread_id": message.get(
                "threadId",
                "",
            ),
            "date": date_text,
            "sender": headers.get(
                "from",
                "",
            ),
            "recipient": headers.get(
                "to",
                "",
            ),
            "cc": headers.get(
                "cc",
                "",
            ),
            "subject": headers.get(
                "subject",
                "",
            ),
            "labels": label_names,
            "label_ids": label_ids,
            "attachments": attachments,
            "snippet": message.get(
                "snippet",
                "",
            ),
        }

    def _label_names(
        self,
        label_ids,
    ):
        names = []

        service = (
            self.connection.get_service()
            if self.connection
            else None
        )

        if service is None:
            return label_ids

        for label_id in label_ids:
            try:
                response = (
                    service.users()
                    .labels()
                    .get(
                        userId="me",
                        id=label_id,
                    )
                    .execute()
                )

                name = response.get(
                    "name",
                    label_id,
                )

                names.append(name)

            except Exception:
                names.append(label_id)

        return names

    def _find_attachments(
        self,
        payload,
    ):
        attachments = []

        def walk(part):
            filename = part.get(
                "filename",
                "",
            )

            body = part.get(
                "body",
                {},
            )

            attachment_id = body.get(
                "attachmentId"
            )

            if filename:
                attachments.append(
                    {
                        "filename": filename,
                        "mime_type": part.get(
                            "mimeType",
                            "",
                        ),
                        "attachment_id":
                            attachment_id,
                        "size": body.get(
                            "size",
                            0,
                        ),
                    }
                )

            for child in part.get(
                "parts",
                [],
            ):
                walk(child)

        walk(payload)

        return attachments

    # ==============================================================
    # RESULTS
    # ==============================================================

    def _display_results(
        self,
        results,
    ):
        self.results_table.setRowCount(0)

        self.result_count_label.setText(
            f"{len(results)} תוצאות"
        )

        for row, result in enumerate(
            results
        ):
            self.results_table.insertRow(
                row
            )

            values = [
                result.get(
                    "date",
                    "",
                ),
                result.get(
                    "sender",
                    "",
                ),
                result.get(
                    "recipient",
                    "",
                ),
                result.get(
                    "subject",
                    "",
                ),
                ", ".join(
                    result.get(
                        "labels",
                        [],
                    )
                ),
                self._attachment_text(
                    result.get(
                        "attachments",
                        [],
                    )
                ),
                result.get(
                    "snippet",
                    "",
                ),
            ]

            for column, value in enumerate(
                values
            ):
                item = QTableWidgetItem(
                    str(value)
                )

                item.setData(
                    Qt.UserRole,
                    result.get(
                        "id",
                        "",
                    ),
                )

                self.results_table.setItem(
                    row,
                    column,
                    item,
                )

        self.results_table.resizeColumnsToContents()

        if (
            self.results_table.columnCount()
            >= 7
        ):
            self.results_table.setColumnWidth(
                6,
                350,
            )

    @staticmethod
    def _attachment_text(
        attachments,
    ):
        if not attachments:
            return "אין"

        names = [
            item.get(
                "filename",
                "",
            )
            for item in attachments
            if item.get("filename")
        ]

        if not names:
            return "כן"

        return ", ".join(names)

    # ==============================================================
    # MESSAGE DETAILS
    # ==============================================================

    def _show_message_details(
        self,
        index,
    ):
        row = index.row()

        if (
            row < 0
            or row >= len(self.last_results)
        ):
            return

        result = self.last_results[row]

        attachments = result.get(
            "attachments",
            [],
        )

        attachment_text = "אין"

        if attachments:
            lines = []

            for attachment in attachments:
                name = attachment.get(
                    "filename",
                    "",
                )

                mime = attachment.get(
                    "mime_type",
                    "",
                )

                size = attachment.get(
                    "size",
                    0,
                )

                lines.append(
                    f"{name} | {mime} | "
                    f"{size} bytes"
                )

            attachment_text = "\n".join(
                lines
            )

        details = (
            f"ID: {result.get('id', '')}\n\n"
            f"תאריך: {result.get('date', '')}\n\n"
            f"שולח: {result.get('sender', '')}\n\n"
            f"נמען: {result.get('recipient', '')}\n\n"
            f"CC: {result.get('cc', '')}\n\n"
            f"נושא: {result.get('subject', '')}\n\n"
            f"תגיות:\n"
            f"{', '.join(result.get('labels', []))}\n\n"
            f"צרופות:\n"
            f"{attachment_text}\n\n"
            f"Snippet:\n"
            f"{result.get('snippet', '')}"
        )

        QMessageBox.information(
            self,
            "פרטי הודעה",
            details,
        )

    # ==============================================================
    # CLEAR
    # ==============================================================

    def _clear_search(self):
        self.labels_list.blockSignals(True)

        for index in range(
            self.labels_list.count()
        ):
            item = self.labels_list.item(
                index
            )

            if item:
                item.setCheckState(
                    Qt.Unchecked
                )

        self.labels_list.blockSignals(False)

        self.type_combo.setCurrentIndex(0)
        self.sender_edit.clear()
        self.recipient_edit.clear()
        self.subject_edit.clear()
        self.content_edit.clear()

        self.attachment_combo.setCurrentIndex(
            0
        )

        self.results_table.setRowCount(0)
        self.last_results = []

        self.result_count_label.setText(
            "0 תוצאות"
        )

        self.query_label.clear()

        self._set_status(
            "תנאי החיפוש נוקו."
        )

    # ==============================================================
    # STATUS
    # ==============================================================

    def _set_status(
        self,
        text: str,
    ):
        self.status_label.setText(text)

    # ==============================================================
    # CLOSE
    # ==============================================================

    def closeEvent(
        self,
        event,
    ):
        self.connection = None
        super().closeEvent(event)


# ==============================================================
# STANDALONE TEST
# ==============================================================

def main():
    app = QApplication(sys.argv)

    window = GmailSearchWindow()
    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()