# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from drive.drive_connection import DriveConnection


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_GMAIL_ACCOUNT = "frank.avner@gmail.com"


class DriveLocalComparisonWindow(QDialog):
    """
    Alcalay - דוח השוואת נפחי מאגרים.

    משווה בין:
        storage/office
        storage/pdf
        storage/media
        storage/gmail
        storage/drive

    לבין המבנה המקביל ב-Google Drive.

    הפעולה היא READ ONLY:
    אין הורדה.
    אין העלאה.
    אין סנכרון.
    """

    LOCAL_ROOTS = {
        "office": PROJECT_ROOT / "storage" / "office",
        "pdf": PROJECT_ROOT / "storage" / "pdf",
        "media": PROJECT_ROOT / "storage" / "media",
        "gmail": PROJECT_ROOT / "storage" / "gmail",
        "drive": PROJECT_ROOT / "storage" / "drive",
    }

    GOOGLE_FOLDER_MIME = "application/vnd.google-apps.folder"

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(
            "Alcalay - דוח השוואת נפחי מאגרים"
        )

        self.resize(1250, 800)

        self.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft
        )

        self.drive_connection = None
        self.drive = None
        self.running = False

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel(
            "דוח השוואת נפחי מאגרים"
        )

        title.setStyleSheet(
            "font-size: 22px; "
            "font-weight: bold; "
            "padding: 8px;"
        )

        layout.addWidget(title)

        self.status_label = QLabel(
            "מוכן. לחץ על 'הפק דוח'."
        )

        self.status_label.setWordWrap(True)

        layout.addWidget(
            self.status_label
        )

        self.progress = QProgressBar()

        self.progress.setRange(
            0,
            0
        )

        self.progress.setVisible(False)

        layout.addWidget(
            self.progress
        )

        self.summary_label = QLabel("")

        self.summary_label.setStyleSheet(
            "font-size: 15px; "
            "font-weight: bold; "
            "padding: 8px;"
        )

        layout.addWidget(
            self.summary_label
        )

        self.table = QTableWidget(
            0,
            7,
        )

        self.table.setHorizontalHeaderLabels(
            [
                "ספרייה",
                "Local - קבצים",
                "Local - נפח",
                "Drive - קבצים",
                "Drive - נפח",
                "הפרש קבצים",
                "הפרש נפח",
            ]
        )

        self.table.horizontalHeader().setStretchLastSection(
            True
        )

        layout.addWidget(
            self.table,
            1,
        )

        self.output = QTextEdit()

        self.output.setReadOnly(True)

        layout.addWidget(
            self.output,
            1,
        )

        buttons = QHBoxLayout()

        self.start_button = QPushButton(
            "הפק דוח"
        )

        self.start_button.clicked.connect(
            self.generate_report
        )

        buttons.addWidget(
            self.start_button
        )

        self.close_button = QPushButton(
            "סגור"
        )

        self.close_button.clicked.connect(
            self.close
        )

        buttons.addWidget(
            self.close_button
        )

        layout.addLayout(
            buttons
        )

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def format_size(value):
        value = int(value or 0)

        units = [
            "B",
            "KB",
            "MB",
            "GB",
            "TB",
        ]

        size = float(value)

        for unit in units:

            if size < 1024 or unit == "TB":
                return f"{size:,.2f} {unit}"

            size /= 1024

        return f"{value:,} B"

    @staticmethod
    def folder_key(parts):
        return "/".join(
            str(part).strip().lower()
            for part in parts
            if str(part).strip()
        )

    # ------------------------------------------------------------------
    # Local scan
    # ------------------------------------------------------------------

    def scan_local(self):
        result = {}

        total_files = 0
        total_bytes = 0

        for root_name, root in self.LOCAL_ROOTS.items():

            if not root.exists():

                result[
                    self.folder_key([root_name])
                ] = {
                    "files": 0,
                    "bytes": 0,
                }

                continue

            directories = [
                root
            ]

            try:
                directories.extend(
                    p
                    for p in root.rglob("*")
                    if p.is_dir()
                )
            except Exception:
                pass

            for directory in directories:

                try:
                    relative = directory.relative_to(
                        root
                    )

                except ValueError:
                    relative = Path()

                parts = [
                    root_name
                ]

                parts.extend(
                    relative.parts
                )

                key = self.folder_key(
                    parts
                )

                file_count = 0
                byte_count = 0

                try:

                    for child in directory.iterdir():

                        if not child.is_file():
                            continue

                        try:
                            file_count += 1
                            byte_count += child.stat().st_size

                        except OSError:
                            pass

                except OSError:
                    pass

                result[key] = {
                    "files": file_count,
                    "bytes": byte_count,
                }

                total_files += file_count
                total_bytes += byte_count

                QApplication.processEvents()

        return (
            result,
            total_files,
            total_bytes,
        )

    # ------------------------------------------------------------------
    # Drive
    # ------------------------------------------------------------------

    def connect_drive(self):

        self.drive_connection = DriveConnection(
            account_email=DEFAULT_GMAIL_ACCOUNT
        )

        self.drive_connection.connect()

        self.drive = (
            self.drive_connection.service
        )

        if self.drive is None:
            raise RuntimeError(
                "לא נוצר חיבור פעיל ל-Google Drive."
            )

        repository = (
            self.drive_connection.verify_alcalay_repository()
        )

        return repository

    def list_children(self, parent_id):

        page_token = None

        while True:

            response = (
                self.drive.files()
                .list(
                    q=(
                        f"'{parent_id}' in parents "
                        "and trashed = false"
                    ),
                    fields=(
                        "nextPageToken,"
                        "files(id,name,mimeType,size)"
                    ),
                    pageSize=1000,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )

            for item in response.get(
                "files",
                [],
            ):
                yield item

            page_token = response.get(
                "nextPageToken"
            )

            if not page_token:
                break

    def find_folder(
        self,
        parent_id,
        names,
    ):

        wanted = {
            str(name).strip().lower()
            for name in names
        }

        for item in self.list_children(
            parent_id
        ):

            if item.get("mimeType") != self.GOOGLE_FOLDER_MIME:
                continue

            name = str(
                item.get("name", "")
            ).strip().lower()

            if name in wanted:
                return item

        return None

    # ------------------------------------------------------------------
    # Recursive Drive scan
    # ------------------------------------------------------------------

    def scan_drive_folder(
        self,
        folder_id,
        path_parts,
        result,
    ):

        key = self.folder_key(
            path_parts
        )

        result.setdefault(
            key,
            {
                "files": 0,
                "bytes": 0,
            },
        )

        for item in self.list_children(
            folder_id
        ):

            mime_type = item.get(
                "mimeType",
                "",
            )

            if mime_type == self.GOOGLE_FOLDER_MIME:

                self.scan_drive_folder(
                    item["id"],
                    path_parts
                    + [
                        item.get(
                            "name",
                            "",
                        )
                    ],
                    result,
                )

            else:

                result[key]["files"] += 1

                try:
                    result[key]["bytes"] += int(
                        item.get("size") or 0
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    pass

            QApplication.processEvents()

    def scan_drive(
        self,
        repository,
    ):

        result = {}

        total_files = 0
        total_bytes = 0

        documents_id = repository.get(
            "documents_folder_id"
        )

        gmail_id = repository.get(
            "gmail_folder_id"
        )

        # --------------------------------------------------------------
        # Documents
        # --------------------------------------------------------------

        if documents_id:

            for root_name in (
                "office",
                "pdf",
                "media",
                "drive",
            ):

                folder = self.find_folder(
                    documents_id,
                    [
                        root_name,
                    ],
                )

                if folder is None:

                    key = self.folder_key(
                        [
                            root_name,
                        ]
                    )

                    result.setdefault(
                        key,
                        {
                            "files": 0,
                            "bytes": 0,
                        },
                    )

                    continue

                self.scan_drive_folder(
                    folder["id"],
                    [
                        root_name,
                    ],
                    result,
                )

        # --------------------------------------------------------------
        # Gmail
        # --------------------------------------------------------------

        if gmail_id:

            gmail_folder = self.find_folder(
                gmail_id,
                [
                    "gmail",
                    "Gmail",
                ],
            )

            if gmail_folder:

                self.scan_drive_folder(
                    gmail_folder["id"],
                    [
                        "gmail",
                    ],
                    result,
                )

            else:

                result.setdefault(
                    "gmail",
                    {
                        "files": 0,
                        "bytes": 0,
                    },
                )

        # --------------------------------------------------------------
        # Totals
        # --------------------------------------------------------------

        for data in result.values():

            total_files += int(
                data.get("files", 0)
            )

            total_bytes += int(
                data.get("bytes", 0)
            )

        return (
            result,
            total_files,
            total_bytes,
        )

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def generate_report(self):

        if self.running:
            return

        self.running = True

        self.start_button.setEnabled(
            False
        )

        self.progress.setVisible(
            True
        )

        self.table.setRowCount(
            0
        )

        self.output.clear()

        self.summary_label.clear()

        self.status_label.setText(
            "סורק את האחסון המקומי..."
        )

        QApplication.processEvents()

        try:

            local, local_files, local_bytes = (
                self.scan_local()
            )

            self.status_label.setText(
                "Local נסרק. מתחבר ל-Google Drive..."
            )

            QApplication.processEvents()

            repository = (
                self.connect_drive()
            )

            self.status_label.setText(
                "מחובר ל-Google Drive. סורק את המאגר..."
            )

            QApplication.processEvents()

            drive, drive_files, drive_bytes = (
                self.scan_drive(
                    repository
                )
            )

            keys = sorted(
                set(local)
                | set(drive)
            )

            for key in keys:

                local_data = local.get(
                    key,
                    {
                        "files": 0,
                        "bytes": 0,
                    },
                )

                drive_data = drive.get(
                    key,
                    {
                        "files": 0,
                        "bytes": 0,
                    },
                )

                local_count = int(
                    local_data["files"]
                )

                local_size = int(
                    local_data["bytes"]
                )

                drive_count = int(
                    drive_data["files"]
                )

                drive_size = int(
                    drive_data["bytes"]
                )

                row = self.table.rowCount()

                self.table.insertRow(
                    row
                )

                values = [
                    key,
                    f"{local_count:,}",
                    self.format_size(
                        local_size
                    ),
                    f"{drive_count:,}",
                    self.format_size(
                        drive_size
                    ),
                    f"{drive_count - local_count:+,}",
                    self.format_size(
                        drive_size - local_size
                    ),
                ]

                for column, value in enumerate(
                    values
                ):

                    self.table.setItem(
                        row,
                        column,
                        QTableWidgetItem(
                            str(value)
                        ),
                    )

            self.summary_label.setText(
                "Local: "
                f"{local_files:,} קבצים / "
                f"{self.format_size(local_bytes)}"
                "    |    "
                "Drive: "
                f"{drive_files:,} קבצים / "
                f"{self.format_size(drive_bytes)}"
            )

            generated_at = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            self.output.append(
                f"דוח הופק: {generated_at}"
            )

            self.output.append(
                "ההשוואה בוצעה לפי metadata של "
                "Google Drive ולפי הקבצים הקיימים "
                "באחסון המקומי."
            )

            self.output.append(
                "לא בוצעה הורדה או העלאה של קבצים."
            )

            # ----------------------------------------------------------
            # Save JSON report
            # ----------------------------------------------------------

            report_directory = (
                PROJECT_ROOT
                / "storage"
                / "reports"
            )

            report_directory.mkdir(
                parents=True,
                exist_ok=True,
            )

            report_file = (
                report_directory
                / (
                    "drive_local_comparison_"
                    + datetime.now().strftime(
                        "%Y%m%d_%H%M%S"
                    )
                    + ".json"
                )
            )

            report_data = {
                "generated_at": generated_at,

                "local_total": {
                    "files": local_files,
                    "bytes": local_bytes,
                },

                "drive_total": {
                    "files": drive_files,
                    "bytes": drive_bytes,
                },

                "folders": {},
            }

            for key in keys:

                report_data[
                    "folders"
                ][key] = {
                    "local": local.get(
                        key,
                        {
                            "files": 0,
                            "bytes": 0,
                        },
                    ),
                    "drive": drive.get(
                        key,
                        {
                            "files": 0,
                            "bytes": 0,
                        },
                    ),
                }

            report_file.write_text(
                json.dumps(
                    report_data,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            self.output.append(
                ""
            )

            self.output.append(
                "הדוח נשמר גם בקובץ:"
            )

            self.output.append(
                str(report_file)
            )

            self.status_label.setText(
                "הדוח הושלם בהצלחה."
            )

        except Exception as exc:

            self.status_label.setText(
                "הפקת הדוח נכשלה."
            )

            self.output.append(
                ""
            )

            self.output.append(
                "ERROR:"
            )

            self.output.append(
                f"{type(exc).__name__}: {exc}"
            )

            QMessageBox.critical(
                self,
                "דוח השוואת מאגרים",
                "לא ניתן להפיק את הדוח:\n\n"
                + str(exc),
            )

        finally:

            self.running = False

            self.start_button.setEnabled(
                True
            )

            self.progress.setVisible(
                False
            )

    def closeEvent(self, event):

        if self.running:

            QMessageBox.warning(
                self,
                "דוח השוואת מאגרים",
                "הדוח עדיין מופק. "
                "יש להמתין עד לסיום הסריקה.",
            )

            event.ignore()
            return

        event.accept()