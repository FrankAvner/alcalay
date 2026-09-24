# -*- coding: utf-8 -*-

from __future__ import annotations

import mimetypes
import os
import platform
import subprocess
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView

    PDF_AVAILABLE = True

except Exception:
    QPdfDocument = None
    QPdfView = None
    PDF_AVAILABLE = False


# ======================================================================
# External application
# ======================================================================

def open_external(
    path: str,
) -> None:

    file_path = Path(
        path
    ).expanduser()

    if not file_path.exists():
        return

    system = platform.system()

    if system == "Darwin":

        subprocess.Popen(
            [
                "open",
                str(file_path),
            ]
        )

    elif system == "Windows":

        os.startfile(
            str(file_path)
        )

    else:

        subprocess.Popen(
            [
                "xdg-open",
                str(file_path),
            ]
        )


# ======================================================================
# Image Viewer
# ======================================================================

class ImageViewer(QWidget):

    def __init__(
        self,
        path: str,
        parent=None,
    ):
        super().__init__(
            parent
        )

        self.path = path

        self.pixmap = QPixmap(
            path
        )

        layout = QVBoxLayout(
            self
        )

        self.label = QLabel()

        self.label.setAlignment(
            Qt.AlignCenter
        )

        self.label.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        self.scroll = QScrollArea()

        self.scroll.setWidgetResizable(
            True
        )

        self.scroll.setWidget(
            self.label
        )

        layout.addWidget(
            self.scroll
        )

        self._refresh()

    def _refresh(
        self,
    ) -> None:

        if self.pixmap.isNull():

            self.label.setText(
                "לא ניתן לטעון את התמונה."
            )

            return

        available = self.label.size()

        width = max(
            1,
            available.width() - 20,
        )

        height = max(
            1,
            available.height() - 20,
        )

        scaled = self.pixmap.scaled(
            width,
            height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        self.label.setPixmap(
            scaled
        )

    def resizeEvent(
        self,
        event,
    ) -> None:

        super().resizeEvent(
            event
        )

        self._refresh()


# ======================================================================
# PDF Viewer
# ======================================================================

class PdfViewer(QWidget):

    def __init__(
        self,
        path: str,
        parent=None,
    ):
        super().__init__(
            parent
        )

        layout = QVBoxLayout(
            self
        )

        if not PDF_AVAILABLE:

            label = QLabel(
                "QtPdf אינו זמין בסביבה הנוכחית.\n\n"
                "אפשר להשתמש בכפתור "
                "'פתח ביישום חיצוני'."
            )

            label.setAlignment(
                Qt.AlignCenter
            )

            label.setWordWrap(
                True
            )

            layout.addWidget(
                label
            )

            return

        self.document = QPdfDocument(
            self
        )

        error = self.document.load(
            path
        )

        if error != QPdfDocument.Error.None_:

            label = QLabel(
                "לא ניתן לפתוח את קובץ ה-PDF:\n\n"
                + path
            )

            label.setAlignment(
                Qt.AlignCenter
            )

            label.setWordWrap(
                True
            )

            layout.addWidget(
                label
            )

            return

        self.view = QPdfView()

        self.view.setDocument(
            self.document
        )

        self.view.setPageMode(
            QPdfView.PageMode.MultiPage
        )

        self.view.setZoomMode(
            QPdfView.ZoomMode.FitToWidth
        )

        layout.addWidget(
            self.view
        )


# ======================================================================
# Text Viewer
# ======================================================================

class TextViewer(QWidget):

    def __init__(
        self,
        path: str,
        parent=None,
    ):
        super().__init__(
            parent
        )

        layout = QVBoxLayout(
            self
        )

        browser = QTextBrowser()

        try:

            text = Path(
                path
            ).read_text(
                encoding="utf-8",
                errors="replace",
            )

            browser.setPlainText(
                text
            )

        except Exception as exc:

            browser.setPlainText(
                "לא ניתן לקרוא את הקובץ:\n\n"
                + str(exc)
            )

        layout.addWidget(
            browser
        )


# ======================================================================
# EML Viewer
# ======================================================================

class EmailViewer(QWidget):

    def __init__(
        self,
        path: str,
        attachment_callback: Optional[
            Callable[[dict], None]
        ] = None,
        parent=None,
    ):
        super().__init__(
            parent
        )

        self.path = path

        self.attachment_callback = (
            attachment_callback
        )

        layout = QVBoxLayout(
            self
        )

        try:

            with open(
                path,
                "rb",
            ) as handle:

                message = BytesParser(
                    policy=policy.default
                ).parse(handle)

            # ----------------------------------------------------------
            # Headers
            # ----------------------------------------------------------

            headers = QFrame()

            headers_layout = QVBoxLayout(
                headers
            )

            headers_layout.addWidget(
                QLabel(
                    f"<b>מאת:</b> "
                    f"{message.get('From', '')}"
                )
            )

            headers_layout.addWidget(
                QLabel(
                    f"<b>אל:</b> "
                    f"{message.get('To', '')}"
                )
            )

            headers_layout.addWidget(
                QLabel(
                    f"<b>נושא:</b> "
                    f"{message.get('Subject', '')}"
                )
            )

            headers_layout.addWidget(
                QLabel(
                    f"<b>תאריך:</b> "
                    f"{message.get('Date', '')}"
                )
            )

            layout.addWidget(
                headers
            )

            # ----------------------------------------------------------
            # Body
            # ----------------------------------------------------------

            body = self._extract_body(
                message
            )

            browser = QTextBrowser()

            browser.setOpenExternalLinks(
                False
            )

            browser.setHtml(
                body
            )

            layout.addWidget(
                browser,
                1,
            )

            # ----------------------------------------------------------
            # Attachments
            # ----------------------------------------------------------

            attachments = self._attachments(
                message
            )

            if attachments:

                layout.addWidget(
                    QLabel(
                        "<b>צרופות</b>"
                    )
                )

                for attachment in attachments:

                    filename = (
                        attachment["filename"]
                    )

                    content_type = (
                        attachment[
                            "content_type"
                        ]
                    )

                    button = QPushButton(
                        "📎 "
                        + filename
                        + " ("
                        + content_type
                        + ")"
                    )

                    button.clicked.connect(
                        lambda checked=False,
                        item=attachment:
                        self._open_attachment(
                            item
                        )
                    )

                    layout.addWidget(
                        button
                    )

        except Exception as exc:

            error_label = QLabel(
                "שגיאה בקריאת קובץ EML:\n\n"
                + str(exc)
            )

            error_label.setWordWrap(
                True
            )

            layout.addWidget(
                error_label
            )

    @staticmethod
    def _extract_body(
        message,
    ) -> str:

        if message.is_multipart():

            parts = list(
                message.walk()
            )

            # ----------------------------------------------------------
            # Prefer HTML
            # ----------------------------------------------------------

            for part in parts:

                if (
                    part.get_content_type()
                    == "text/html"
                ):

                    try:
                        return part.get_content()
                    except Exception:
                        pass

            # ----------------------------------------------------------
            # Fallback to plain text
            # ----------------------------------------------------------

            for part in parts:

                if (
                    part.get_content_type()
                    == "text/plain"
                ):

                    try:

                        text = part.get_content()

                        escaped = (
                            text
                            .replace(
                                "&",
                                "&amp;",
                            )
                            .replace(
                                "<",
                                "&lt;",
                            )
                            .replace(
                                ">",
                                "&gt;",
                            )
                        )

                        return (
                            "<pre "
                            "style='white-space:pre-wrap;'>"
                            + escaped
                            + "</pre>"
                        )

                    except Exception:
                        pass

            return (
                "<i>"
                "לא נמצא גוף הודעה להצגה."
                "</i>"
            )

        try:

            content = message.get_content()

            if (
                message.get_content_type()
                == "text/html"
            ):

                return content

            escaped = (
                content
                .replace(
                    "&",
                    "&amp;",
                )
                .replace(
                    "<",
                    "&lt;",
                )
                .replace(
                    ">",
                    "&gt;",
                )
            )

            return (
                "<pre "
                "style='white-space:pre-wrap;'>"
                + escaped
                + "</pre>"
            )

        except Exception:

            return (
                "<i>"
                "לא ניתן לקרוא את גוף ההודעה."
                "</i>"
            )

    @staticmethod
    def _attachments(
        message,
    ) -> list[dict]:

        items = []

        for part in message.iter_attachments():

            filename = (
                part.get_filename()
                or "attachment"
            )

            payload = part.get_payload(
                decode=True
            )

            items.append(
                {
                    "filename": filename,
                    "content_type": (
                        part.get_content_type()
                    ),
                    "payload": payload,
                }
            )

        return items

    def _open_attachment(
        self,
        attachment: dict,
    ) -> None:

        if self.attachment_callback:

            self.attachment_callback(
                attachment
            )


# ======================================================================
# Unsupported Viewer
# ======================================================================

class UnsupportedViewer(QWidget):

    def __init__(
        self,
        path: str,
        parent=None,
    ):
        super().__init__(
            parent
        )

        layout = QVBoxLayout(
            self
        )

        label = QLabel(
            "אין כרגע Viewer פנימי לסוג הקובץ הזה.\n\n"
            + Path(path).name
        )

        label.setAlignment(
            Qt.AlignCenter
        )

        label.setWordWrap(
            True
        )

        layout.addWidget(
            label
        )

        button = QPushButton(
            "פתח ביישום החיצוני"
        )

        button.clicked.connect(
            lambda: open_external(
                path
            )
        )

        layout.addWidget(
            button
        )


# ======================================================================
# Main Document Viewer
# ======================================================================

class DocumentViewer(QWidget):

    """
    Viewer אחיד למסמכים.

    PDF       -> PdfViewer
    תמונות    -> ImageViewer
    EML       -> EmailViewer
    TXT/HTML  -> TextViewer
    אחר       -> UnsupportedViewer
    """

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(
            parent
        )

        self.current_path = ""

        self.root_layout = QVBoxLayout(
            self
        )

        # ==============================================================
        # Toolbar
        # ==============================================================

        toolbar = QHBoxLayout()

        self.title_label = QLabel(
            "לא נבחר מסמך"
        )

        self.title_label.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )

        self.external_button = QPushButton(
            "פתח ביישום חיצוני"
        )

        self.external_button.setEnabled(
            False
        )

        self.external_button.clicked.connect(
            self._open_external_current
        )

        toolbar.addWidget(
            self.title_label
        )

        toolbar.addWidget(
            self.external_button
        )

        self.root_layout.addLayout(
            toolbar
        )

        # ==============================================================
        # Viewer container
        # ==============================================================

        self.viewer_container = QWidget()

        self.viewer_layout = QVBoxLayout(
            self.viewer_container
        )

        self.viewer_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self.root_layout.addWidget(
            self.viewer_container,
            1,
        )

        self._show_message(
            "בחר מסמך להצגה."
        )

    # ==================================================================
    # Internal
    # ==================================================================

    def clear_viewer(
        self,
    ) -> None:

        while self.viewer_layout.count():

            item = self.viewer_layout.takeAt(
                0
            )

            widget = item.widget()

            if widget is not None:

                widget.deleteLater()

    def _show_message(
        self,
        text: str,
    ) -> None:

        self.clear_viewer()

        label = QLabel(
            text
        )

        label.setAlignment(
            Qt.AlignCenter
        )

        label.setWordWrap(
            True
        )

        self.viewer_layout.addWidget(
            label
        )

    # ==================================================================
    # Public API
    # ==================================================================

    def show_file(
        self,
        path: str,
        title: str = "",
    ) -> None:

        self.clear_viewer()

        if not path:

            self.current_path = ""

            self.title_label.setText(
                "לא נבחר מסמך"
            )

            self.external_button.setEnabled(
                False
            )

            self._show_message(
                "לא הוגדר נתיב לקובץ."
            )

            return

        file_path = Path(
            path
        ).expanduser()

        self.current_path = str(
            file_path
        )

        self.title_label.setText(
            title
            or file_path.name
        )

        self.external_button.setEnabled(
            file_path.exists()
        )

        if not file_path.exists():

            self._show_message(
                "הקובץ אינו קיים "
                "באחסון המקומי:\n\n"
                + str(file_path)
            )

            return

        mime, _ = mimetypes.guess_type(
            str(file_path)
        )

        mime = mime or ""

        suffix = file_path.suffix.lower()

        # ==============================================================
        # PDF
        # ==============================================================

        if (
            mime == "application/pdf"
            or suffix == ".pdf"
        ):

            widget = PdfViewer(
                str(file_path)
            )

        # ==============================================================
        # Images
        # ==============================================================

        elif (
            mime.startswith("image/")
            or suffix in {
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".bmp",
                ".webp",
                ".tif",
                ".tiff",
            }
        ):

            widget = ImageViewer(
                str(file_path)
            )

        # ==============================================================
        # EML
        # ==============================================================

        elif (
            mime == "message/rfc822"
            or suffix == ".eml"
        ):

            widget = EmailViewer(
                str(file_path)
            )

        # ==============================================================
        # Text
        # ==============================================================

        elif (
            mime.startswith("text/")
            or suffix in {
                ".txt",
                ".log",
                ".csv",
                ".html",
                ".htm",
            }
        ):

            widget = TextViewer(
                str(file_path)
            )

        # ==============================================================
        # Unsupported
        # ==============================================================

        else:

            widget = UnsupportedViewer(
                str(file_path)
            )

        self.viewer_layout.addWidget(
            widget
        )

    def _open_external_current(
        self,
    ) -> None:

        if self.current_path:

            open_external(
                self.current_path
            )