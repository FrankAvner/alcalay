# -*- coding: utf-8 -*-

"""
Alcalay - Search Result Window
==============================

Independent window for displaying a single search result.

Current supported result:
    Gmail / PostgreSQL

Features:
    - Movable and resizable window
    - Display full indexed email content
    - Search inside the displayed email
    - Save displayed email as local PDF
    - Print displayed email
"""

from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SearchResultWindow(QMainWindow):
    """
    Independent window for displaying one search result.

    The window receives an already loaded result dictionary.
    It does not connect to Gmail and does not perform database queries.
    """

    def __init__(
        self,
        result: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.result = result

        self.setWindowTitle(
            self._window_title()
        )

        self.setMinimumSize(900, 650)
        self.resize(1200, 850)

        self._build_ui()
        self._load_result()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(
            16,
            16,
            16,
            16,
        )
        main_layout.setSpacing(10)

        title_layout = QHBoxLayout()
        title_layout.setSpacing(8)

        title_label = QLabel("תוצאת חיפוש")
        title_label.setStyleSheet(
            """
            QLabel {
                font-size: 22px;
                font-weight: bold;
            }
            """
        )

        source_label = QLabel(
            "Gmail / PostgreSQL"
        )
        source_label.setStyleSheet(
            """
            QLabel {
                color: #666666;
                font-size: 13px;
            }
            """
        )

        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(source_label)

        main_layout.addLayout(title_layout)

        self._build_metadata_area(
            main_layout
        )

        search_layout = QHBoxLayout()
        search_layout.setSpacing(8)

        search_label = QLabel(
            "חיפוש בתוך המייל:"
        )

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "הקלד טקסט לחיפוש בתוך המייל..."
        )
        self.search_edit.returnPressed.connect(
            self._find_next
        )

        self.find_previous_button = QPushButton(
            "הקודם"
        )
        self.find_previous_button.clicked.connect(
            self._find_previous
        )

        self.find_next_button = QPushButton(
            "הבא"
        )
        self.find_next_button.clicked.connect(
            self._find_next
        )

        self.clear_find_button = QPushButton(
            "ניקוי"
        )
        self.clear_find_button.clicked.connect(
            self._clear_find
        )

        search_layout.addWidget(
            search_label
        )
        search_layout.addWidget(
            self.search_edit,
            1,
        )
        search_layout.addWidget(
            self.find_previous_button
        )
        search_layout.addWidget(
            self.find_next_button
        )
        search_layout.addWidget(
            self.clear_find_button
        )

        main_layout.addLayout(
            search_layout
        )

        self.find_status_label = QLabel(
            ""
        )
        self.find_status_label.setAlignment(
            Qt.AlignRight
        )
        self.find_status_label.setStyleSheet(
            """
            QLabel {
                color: #666666;
                font-size: 12px;
            }
            """
        )

        main_layout.addWidget(
            self.find_status_label
        )

        self.document_view = QTextBrowser()
        self.document_view.setOpenExternalLinks(
            True
        )
        self.document_view.setReadOnly(
            True
        )
        self.document_view.setAcceptRichText(
            True
        )
        self.document_view.setLineWrapMode(
            QTextBrowser.WidgetWidth
        )

        main_layout.addWidget(
            self.document_view,
            1,
        )

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)

        self.save_pdf_button = QPushButton(
            "שמירה כ-PDF"
        )
        self.save_pdf_button.setMinimumHeight(
            38
        )
        self.save_pdf_button.clicked.connect(
            self._save_pdf
        )

        self.print_button = QPushButton(
            "הדפסה"
        )
        self.print_button.setMinimumHeight(
            38
        )
        self.print_button.clicked.connect(
            self._print
        )

        self.close_button = QPushButton(
            "סגירה"
        )
        self.close_button.setMinimumHeight(
            38
        )
        self.close_button.clicked.connect(
            self.close
        )

        buttons_layout.addWidget(
            self.save_pdf_button
        )
        buttons_layout.addWidget(
            self.print_button
        )
        buttons_layout.addStretch()
        buttons_layout.addWidget(
            self.close_button
        )

        main_layout.addLayout(
            buttons_layout
        )

    def _build_metadata_area(
        self,
        main_layout: QVBoxLayout,
    ) -> None:
        metadata_widget = QWidget()
        metadata_layout = QVBoxLayout(
            metadata_widget
        )

        metadata_layout.setContentsMargins(
            8,
            8,
            8,
            8,
        )
        metadata_layout.setSpacing(4)

        subject = self._safe_text(
            self.result.get("subject")
        )

        sender = self._sender_text()

        recipients = self._recipients_text()

        cc = self._json_to_text(
            self.result.get("cc_recipients")
        )

        date_text = self._format_datetime(
            self.result.get("date_sent")
        )

        message_key = self._safe_text(
            self.result.get(
                "gmail_message_key"
            )
        )

        thread_id = self._safe_text(
            self.result.get(
                "thread_id"
            )
        )

        self._add_metadata_row(
            metadata_layout,
            "נושא:",
            subject,
        )

        self._add_metadata_row(
            metadata_layout,
            "שולח:",
            sender,
        )

        self._add_metadata_row(
            metadata_layout,
            "נמען:",
            recipients,
        )

        if cc:
            self._add_metadata_row(
                metadata_layout,
                "CC:",
                cc,
            )

        self._add_metadata_row(
            metadata_layout,
            "תאריך:",
            date_text,
        )

        self._add_metadata_row(
            metadata_layout,
            "Message Key:",
            message_key,
        )

        if thread_id:
            self._add_metadata_row(
                metadata_layout,
                "Thread ID:",
                thread_id,
            )

        attachment_count = (
            self.result.get(
                "attachment_count"
            )
            or 0
        )

        if self.result.get(
            "has_attachments"
        ):
            attachment_text = (
                f"כן ({attachment_count})"
            )
        else:
            attachment_text = "לא"

        self._add_metadata_row(
            metadata_layout,
            "קבצים מצורפים:",
            attachment_text,
        )

        metadata_widget.setStyleSheet(
            """
            QWidget {
                background: #f5f5f5;
                border: 1px solid #dddddd;
                border-radius: 5px;
            }

            QLabel {
                background: transparent;
                border: none;
            }
            """
        )

        main_layout.addWidget(
            metadata_widget
        )

    def _add_metadata_row(
        self,
        layout: QVBoxLayout,
        label_text: str,
        value: str,
    ) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)

        label = QLabel(label_text)
        label.setMinimumWidth(110)
        label.setAlignment(
            Qt.AlignRight
            | Qt.AlignTop
        )
        label.setStyleSheet(
            """
            QLabel {
                font-weight: bold;
            }
            """
        )

        value_label = QLabel(
            self._safe_text(value)
        )
        value_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        value_label.setWordWrap(
            True
        )
        value_label.setAlignment(
            Qt.AlignRight
            | Qt.AlignTop
        )

        row.addWidget(
            label
        )
        row.addWidget(
            value_label,
            1,
        )

        layout.addLayout(
            row
        )

    # ------------------------------------------------------------------
    # Load result
    # ------------------------------------------------------------------

    def _load_result(self) -> None:
        html_content = self._build_email_html()

        self.document_view.setHtml(
            html_content
        )

    def _build_email_html(self) -> str:
        subject = self._safe_text(
            self.result.get("subject")
        )

        sender = self._sender_text()

        recipients = self._recipients_text()

        cc = self._json_to_text(
            self.result.get("cc_recipients")
        )

        date_text = self._format_datetime(
            self.result.get("date_sent")
        )

        body = self.result.get(
            "body_text"
        )

        if not body:
            body = self.result.get(
                "search_text"
            )

        body = self._safe_text(
            body
        )

        escaped_body = html.escape(
            body
        )

        escaped_body = escaped_body.replace(
            "\n",
            "<br>",
        )

        attachment_count = (
            self.result.get(
                "attachment_count"
            )
            or 0
        )

        if self.result.get(
            "has_attachments"
        ):
            attachment_text = (
                f"כן ({attachment_count})"
            )
        else:
            attachment_text = "לא"

        return f"""
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: Arial, sans-serif;
                font-size: 14px;
                direction: rtl;
                text-align: right;
                margin: 18px;
            }}

            .subject {{
                font-size: 22px;
                font-weight: bold;
                margin-bottom: 18px;
            }}

            .header {{
                border-bottom: 1px solid #dddddd;
                padding-bottom: 14px;
                margin-bottom: 20px;
            }}

            .row {{
                margin: 5px 0;
            }}

            .label {{
                font-weight: bold;
            }}

            .body {{
                font-size: 15px;
                line-height: 1.6;
                white-space: normal;
            }}

            .attachments {{
                margin-top: 15px;
                padding-top: 10px;
                border-top: 1px solid #dddddd;
                color: #555555;
            }}
        </style>
        </head>

        <body>

            <div class="subject">
                {html.escape(subject)}
            </div>

            <div class="header">

                <div class="row">
                    <span class="label">שולח:</span>
                    {html.escape(sender)}
                </div>

                <div class="row">
                    <span class="label">נמען:</span>
                    {html.escape(recipients)}
                </div>

                {
                    f'''
                    <div class="row">
                        <span class="label">CC:</span>
                        {html.escape(cc)}
                    </div>
                    '''
                    if cc
                    else ""
                }

                <div class="row">
                    <span class="label">תאריך:</span>
                    {html.escape(date_text)}
                </div>

                <div class="row">
                    <span class="label">קבצים מצורפים:</span>
                    {html.escape(attachment_text)}
                </div>

            </div>

            <div class="body">
                {escaped_body}
            </div>

        </body>
        </html>
        """

    # ------------------------------------------------------------------
    # Search inside result
    # ------------------------------------------------------------------

    def _find_next(self) -> None:
        text = self.search_edit.text()

        if not text:
            self.find_status_label.setText(
                "הקלד טקסט לחיפוש."
            )
            return

        found = self.document_view.find(
            text
        )

        if found:
            self.find_status_label.setText(
                "נמצא."
            )
            return

        self.document_view.moveCursor(
            QTextCursor.Start
        )

        found = self.document_view.find(
            text
        )

        if found:
            self.find_status_label.setText(
                "החיפוש הגיע לסוף וחזר להתחלה."
            )
        else:
            self.find_status_label.setText(
                "הטקסט לא נמצא."
            )

    def _find_previous(self) -> None:
        text = self.search_edit.text()

        if not text:
            self.find_status_label.setText(
                "הקלד טקסט לחיפוש."
            )
            return

        found = self.document_view.find(
            text,
            QTextDocument.FindBackward,
        )

        if found:
            self.find_status_label.setText(
                "נמצא."
            )
            return

        self.document_view.moveCursor(
            QTextCursor.End
        )

        found = self.document_view.find(
            text,
            QTextDocument.FindBackward,
        )

        if found:
            self.find_status_label.setText(
                "החיפוש הגיע להתחלה וחזר לסוף."
            )
        else:
            self.find_status_label.setText(
                "הטקסט לא נמצא."
            )

    def _clear_find(self) -> None:
        self.search_edit.clear()
        self.find_status_label.clear()

        self.document_view.moveCursor(
            QTextCursor.Start
        )

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------

    def _save_pdf(self) -> None:
        subject = self._safe_text(
            self.result.get("subject")
        )

        if not subject:
            subject = "alcalay_email"

        filename = (
            self._safe_filename(subject)
            + ".pdf"
        )

        default_path = str(
            Path.home() / filename
        )

        path, _ = QFileDialog.getSaveFileName(
            self,
            "שמירת מייל כ-PDF",
            default_path,
            "PDF Files (*.pdf)",
        )

        if not path:
            return

        if not path.lower().endswith(
            ".pdf"
        ):
            path += ".pdf"

        try:
            printer = QPrinter(
                QPrinter.HighResolution
            )

            printer.setOutputFormat(
                QPrinter.PdfFormat
            )

            printer.setOutputFileName(
                path
            )

            document = self.document_view.document()

            document.print(
                printer
            )

            QMessageBox.information(
                self,
                "שמירת PDF",
                f"המייל נשמר בהצלחה:\n\n{path}",
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "שגיאה בשמירת PDF",
                f"לא ניתן לשמור את המייל כ-PDF:\n\n{exc}",
            )

    # ------------------------------------------------------------------
    # Printing
    # ------------------------------------------------------------------

    def _print(self) -> None:
        try:
            printer = QPrinter(
                QPrinter.HighResolution
            )

            dialog = QPrintDialog(
                printer,
                self,
            )

            if dialog.exec() != QPrintDialog.Accepted:
                return

            document = self.document_view.document()

            document.print(
                printer
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "שגיאת הדפסה",
                f"לא ניתן להדפיס את המייל:\n\n{exc}",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _window_title(self) -> str:
        subject = self._safe_text(
            self.result.get("subject")
        )

        if subject:
            return (
                "Alcalay - "
                + subject[:100]
            )

        return "Alcalay - תוצאת חיפוש"

    def _sender_text(self) -> str:
        name = self._safe_text(
            self.result.get(
                "sender_name"
            )
        )

        email = self._safe_text(
            self.result.get(
                "sender_email"
            )
        )

        if name and email:
            return f"{name} <{email}>"

        return name or email

    def _recipients_text(self) -> str:
        recipients = self._json_to_text(
            self.result.get(
                "recipients"
            )
        )

        if recipients:
            return recipients

        return self._json_to_text(
            self.result.get(
                "cc_recipients"
            )
        )

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
                        parts.append(
                            email
                        )
                    elif name:
                        parts.append(
                            name
                        )
                    else:
                        parts.append(
                            self._safe_text(
                                item
                            )
                        )
                else:
                    parts.append(
                        self._safe_text(
                            item
                        )
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
                return self._safe_text(
                    value
                )

        return self._safe_text(
            value
        )

    @staticmethod
    def _safe_text(
        value: Any,
    ) -> str:
        if value is None:
            return ""

        if isinstance(value, str):
            return value

        try:
            return str(value)
        except Exception:
            return ""

    @staticmethod
    def _safe_filename(
        value: str,
    ) -> str:
        invalid = '<>:"/\\|?*'

        result = "".join(
            "_"
            if character in invalid
            else character
            for character in value
        )

        result = result.strip()

        if not result:
            result = "alcalay_email"

        return result[:150]

    def _format_datetime(
        self,
        value: Any,
    ) -> str:
        if value is None:
            return ""

        if isinstance(
            value,
            datetime,
        ):
            return value.strftime(
                "%d/%m/%Y %H:%M"
            )

        return self._safe_text(
            value
        )


if __name__ == "__main__":
    app = QApplication(
        sys.argv
    )

    example_result = {
        "subject": "Alcalay test",
        "sender_name": "Test",
        "sender_email": "test@example.com",
        "recipients": [
            {
                "name": "User",
                "email": "user@example.com",
            }
        ],
        "date_sent": datetime.now(),
        "gmail_message_key": "test-message",
        "thread_id": "test-thread",
        "has_attachments": False,
        "attachment_count": 0,
        "body_text": (
            "זהו מייל בדיקה.\n\n"
            "אפשר לחפש בתוך התוכן,\n"
            "לשמור PDF ולהדפיס."
        ),
    }

    window = SearchResultWindow(
        example_result
    )

    window.show()

    sys.exit(
        app.exec()
    )