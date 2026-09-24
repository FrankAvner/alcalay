# -*- coding: utf-8 -*-

import os
import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QProcess, QProcessEnvironment, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QStackedWidget,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from database.connection import DatabaseConnection
from gmail.gmail_window import GmailWindow
from search.search_window import SearchWindow
from indexing.index_window import IndexWindow


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

DEFAULT_GMAIL_ACCOUNT = "frank.avner@gmail.com"

DIRECTION_DRIVE_TO_LOCAL = "DRIVE_TO_LOCAL"
DIRECTION_LOCAL_TO_DRIVE = "LOCAL_TO_DRIVE"


# ----------------------------------------------------------------------
# Gmail Import Window
# ----------------------------------------------------------------------

class GmailImportWindow(QDialog):
    """GUI wrapper for the Gmail COPY process."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Alcalay - Gmail Import")
        self.setModal(False)
        self.resize(1100, 760)

        self.process = None
        self.output_buffer = ""
        self.selected_labels = []
        self.copy_started = False

        self.messages_found = 0
        self.messages_unique = 0
        self.messages_new = 0
        self.messages_existing = 0
        self.attachments_total = 0
        self.attachments_new = 0
        self.attachments_existing = 0
        self.errors = 0

        self.setup_ui()
        self.load_labels()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel("ייבוא מיילים מ-Gmail")
        title.setStyleSheet(
            "font-size: 22px; font-weight: bold; padding: 8px;"
        )
        layout.addWidget(title)

        self.status_label = QLabel("טוען Labels מ-Gmail...")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        selection_frame = QFrame()
        selection_layout = QVBoxLayout(selection_frame)
        selection_layout.setContentsMargins(10, 10, 10, 10)
        selection_layout.setSpacing(8)

        selection_title = QLabel("בחר Labels לסנכרון")
        selection_title.setStyleSheet(
            "font-size: 16px; font-weight: bold;"
        )
        selection_layout.addWidget(selection_title)

        self.labels_list = QListWidget()
        self.labels_list.setSelectionMode(
            QListWidget.SelectionMode.NoSelection
        )
        selection_layout.addWidget(self.labels_list)

        selection_buttons = QHBoxLayout()

        self.select_all_button = QPushButton("בחר הכול")
        self.select_all_button.clicked.connect(self.select_all_labels)
        selection_buttons.addWidget(self.select_all_button)

        self.clear_selection_button = QPushButton("נקה בחירה")
        self.clear_selection_button.clicked.connect(
            self.clear_label_selection
        )
        selection_buttons.addWidget(self.clear_selection_button)

        selection_buttons.addStretch()
        selection_layout.addLayout(selection_buttons)

        layout.addWidget(selection_frame, 1)

        counters_frame = QFrame()
        counters_layout = QVBoxLayout(counters_frame)
        counters_layout.setContentsMargins(10, 8, 10, 8)
        counters_layout.setSpacing(4)

        counters_title = QLabel("מונה COPY")
        counters_title.setStyleSheet(
            "font-size: 15px; font-weight: bold;"
        )
        counters_layout.addWidget(counters_title)

        self.counter_label = QLabel()
        self.counter_label.setWordWrap(True)
        self.counter_label.setStyleSheet(
            "font-size: 13px; padding: 6px; border: 1px solid #cccccc;"
        )
        counters_layout.addWidget(self.counter_label)

        layout.addWidget(counters_frame)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        self.start_button = QPushButton("התחל COPY")
        self.start_button.clicked.connect(self.start_copy)
        buttons.addWidget(self.start_button)

        self.stop_button = QPushButton("עצור")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_process)
        buttons.addWidget(self.stop_button)

        self.close_button = QPushButton("סגור")
        self.close_button.clicked.connect(self.close)
        buttons.addWidget(self.close_button)

        layout.addLayout(buttons)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)

        self.reset_counters()

    def log(self, text):
        if text is None:
            return

        self.output.append(str(text))
        self.output.moveCursor(QTextCursor.End)

    def reset_counters(self):
        self.messages_found = 0
        self.messages_unique = 0
        self.messages_new = 0
        self.messages_existing = 0
        self.attachments_total = 0
        self.attachments_new = 0
        self.attachments_existing = 0
        self.errors = 0
        self.update_counter_display()

    def update_counter_display(self):
        self.counter_label.setText(
            f"מיילים שנמצאו: {self.messages_found}  |  "
            f"מיילים ייחודיים: {self.messages_unique}  |  "
            f"חדשים: {self.messages_new}  |  "
            f"קיימים: {self.messages_existing}\n"
            f"קבצים מצורפים: {self.attachments_total}  |  "
            f"קבצים חדשים: {self.attachments_new}  |  "
            f"קבצים קיימים: {self.attachments_existing}  |  "
            f"שגיאות: {self.errors}"
        )

    def load_labels(self):
        try:
            db = DatabaseConnection()
            labels = db.get_enabled_gmail_labels()
        except Exception as exc:
            self.status_label.setText(
                f"שגיאה בטעינת Labels: {exc}"
            )
            self.start_button.setEnabled(False)
            self.select_all_button.setEnabled(False)
            self.clear_selection_button.setEnabled(False)
            return

        self.labels_list.clear()

        if not labels:
            self.status_label.setText(
                "לא נמצאו Gmail Labels פעילים."
            )
            self.start_button.setEnabled(False)
            self.select_all_button.setEnabled(False)
            self.clear_selection_button.setEnabled(False)
            return

        for index, label in enumerate(labels, start=1):
            if isinstance(label, dict):
                name = (
                    label.get("label_name")
                    or label.get("name")
                    or label.get("gmail_label")
                    or str(label)
                )

                label_id = (
                    label.get("label_id")
                    or label.get("gmail_label_id")
                    or label.get("id")
                    or ""
                )

                selected_for_sync = bool(
                    label.get("selected_for_sync", False)
                )
            else:
                name = str(label)
                label_id = ""
                selected_for_sync = False

            item = QListWidgetItem(
                f"{index}. {name}"
            )

            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
            )

            item.setCheckState(
                Qt.CheckState.Checked
                if selected_for_sync
                else Qt.CheckState.Unchecked
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                {
                    "name": name,
                    "id": str(label_id).strip(),
                    "index": index,
                },
            )

            self.labels_list.addItem(item)

        self.status_label.setText(
            f"נמצאו {self.labels_list.count()} Labels פעילים. "
            "סמן את ה-Labels שברצונך להעתיק."
        )

    def select_all_labels(self):
        for row in range(self.labels_list.count()):
            item = self.labels_list.item(row)
            item.setCheckState(
                Qt.CheckState.Checked
            )

    def clear_label_selection(self):
        for row in range(self.labels_list.count()):
            item = self.labels_list.item(row)
            item.setCheckState(
                Qt.CheckState.Unchecked
            )

    def get_selected_label_data(self):
        result = []

        for row in range(self.labels_list.count()):
            item = self.labels_list.item(row)

            if item.checkState() != Qt.CheckState.Checked:
                continue

            data = item.data(
                Qt.ItemDataRole.UserRole
            )

            if not isinstance(data, dict):
                continue

            label_id = str(
                data.get("id", "")
            ).strip()

            if not label_id:
                continue

            result.append(data)

        return result

    def start_copy(self):
        if self.process is not None:
            QMessageBox.warning(
                self,
                "Gmail",
                "תהליך COPY כבר פועל.",
            )
            return

        selected = self.get_selected_label_data()

        if not selected:
            QMessageBox.warning(
                self,
                "Gmail",
                "יש לבחור לפחות Label אחד שיש לו Gmail Label ID.",
            )
            return

        self.selected_labels = selected
        self.reset_counters()
        self.output.clear()

        label_ids = [
            str(item["id"]).strip()
            for item in selected
            if str(item.get("id", "")).strip()
        ]

        label_argument = ",".join(label_ids)

        self.process = QProcess(self)

        self.process.setProcessChannelMode(
            QProcess.ProcessChannelMode.MergedChannels
        )

        env = QProcessEnvironment.systemEnvironment()

        env.insert(
            "PROJECT_ROOT",
            str(PROJECT_ROOT),
        )

        env.insert(
            "SRC_ROOT",
            str(SRC_ROOT),
        )

        existing_pythonpath = env.value(
            "PYTHONPATH"
        )

        python_paths = [
            str(PROJECT_ROOT),
            str(SRC_ROOT),
        ]

        if existing_pythonpath:
            python_paths.append(
                existing_pythonpath
            )

        env.insert(
            "PYTHONPATH",
            os.pathsep.join(
                python_paths
            ),
        )

        self.process.setProcessEnvironment(
            env
        )

        self.process.readyReadStandardOutput.connect(
            self.read_output
        )

        self.process.finished.connect(
            self.process_finished
        )

        script = (
            PROJECT_ROOT
            / "src"
            / "gmail"
            / "gmail_copy.py"
        )

        selected_names = [
            str(item.get("name", ""))
            for item in selected
        ]

        self.log("")
        self.log("=" * 80)
        self.log("Starting Gmail COPY")
        self.log(f"Script: {script}")
        self.log(
            "Selected labels: "
            + ", ".join(selected_names)
        )
        self.log(
            "Selected label IDs: "
            + label_argument
        )
        self.log("=" * 80)

        self.status_label.setText(
            f"COPY פועל עבור {len(selected)} Labels..."
        )

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.select_all_button.setEnabled(False)
        self.clear_selection_button.setEnabled(False)

        self.copy_started = True

        self.process.start(
            sys.executable,
            [
                "-u",
                str(script),
                DEFAULT_GMAIL_ACCOUNT,
                "--labels",
                label_argument,
                "--yes",
            ],
        )

    def read_output(self):
        if not self.process:
            return

        data = bytes(
            self.process.readAllStandardOutput()
        ).decode(
            "utf-8",
            errors="replace",
        )

        if not data:
            return

        self.output_buffer += data

        while "\n" in self.output_buffer:
            line, self.output_buffer = (
                self.output_buffer.split(
                    "\n",
                    1,
                )
            )

            line = line.rstrip("\r")

            if line:
                self.handle_output_line(line)

    def handle_output_line(self, line):
        self.log(line)

        normalized = line.strip().lower()

        patterns = [
            (
                r"messages? found\s*[:=]\s*(\d+)",
                "messages_found",
            ),
            (
                r"unique messages?\s*[:=]\s*(\d+)",
                "messages_unique",
            ),
            (
                r"new messages?\s*[:=]\s*(\d+)",
                "messages_new",
            ),
            (
                r"existing messages?\s*[:=]\s*(\d+)",
                "messages_existing",
            ),
            (
                r"attachments?\s*[:=]\s*(\d+)",
                "attachments_total",
            ),
            (
                r"new attachments?\s*[:=]\s*(\d+)",
                "attachments_new",
            ),
            (
                r"existing attachments?\s*[:=]\s*(\d+)",
                "attachments_existing",
            ),
            (
                r"errors?\s*[:=]\s*(\d+)",
                "errors",
            ),
        ]

        for pattern, attribute in patterns:
            match = re.search(
                pattern,
                normalized,
            )

            if match:
                try:
                    setattr(
                        self,
                        attribute,
                        int(match.group(1)),
                    )
                except ValueError:
                    pass

        if "[gmail_progress]" in normalized:
            pairs = re.findall(
                r"([a-z_]+)\s*=\s*(\d+)",
                normalized,
            )

            for key, value in pairs:
                if hasattr(self, key):
                    try:
                        setattr(
                            self,
                            key,
                            int(value),
                        )
                    except ValueError:
                        pass

        self.update_counter_display()

        if "copy completed" in normalized:
            self.status_label.setText(
                "COPY הסתיים."
            )

        elif "completed successfully" in normalized:
            self.status_label.setText(
                "COPY הסתיים בהצלחה."
            )

        elif (
            "error" in normalized
            or "exception" in normalized
        ):
            self.status_label.setText(
                "נמצאה שגיאה במהלך ה-COPY."
            )

    def stop_process(self):
        if not self.process:
            return

        if (
            self.process.state()
            == QProcess.ProcessState.Running
        ):
            self.status_label.setText(
                "נשלחה בקשת עצירה..."
            )

            QTimer.singleShot(
                1500,
                self.force_stop_if_running,
            )

    def force_stop_if_running(self):
        if (
            self.process
            and self.process.state()
            == QProcess.ProcessState.Running
        ):
            self.process.kill()

    def process_finished(
        self,
        exit_code,
        exit_status,
    ):
        if self.output_buffer:
            remaining = self.output_buffer.rstrip(
                "\r\n"
            )

            self.output_buffer = ""

            if remaining:
                self.handle_output_line(
                    remaining
                )

        self.log("")
        self.log(
            f"Gmail COPY finished. "
            f"exit_code={exit_code}, "
            f"exit_status={exit_status}"
        )

        if exit_code == 0:
            self.status_label.setText(
                "COPY הסתיים בהצלחה."
            )
        else:
            self.status_label.setText(
                f"COPY הסתיים עם שגיאה ({exit_code})."
            )

        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.select_all_button.setEnabled(True)
        self.clear_selection_button.setEnabled(True)

        self.process = None
        self.copy_started = False

    def closeEvent(self, event):
        if (
            self.process
            and self.process.state()
            == QProcess.ProcessState.Running
        ):
            answer = QMessageBox.question(
                self,
                "Gmail",
                "תהליך COPY עדיין פועל. לעצור ולסגור?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
            )

            if answer == QMessageBox.StandardButton.No:
                event.ignore()
                return

            self.stop_process()

        event.accept()


# ----------------------------------------------------------------------
# Gmail Index Window
# ----------------------------------------------------------------------

class GmailIndexWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(
            "Alcalay - Gmail Index"
        )

        self.setModal(False)
        self.resize(1100, 760)

        self.process = None
        self.stage = None

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel(
            "Gmail Parse + Index"
        )

        title.setStyleSheet(
            "font-size: 22px; font-weight: bold; padding: 8px;"
        )

        layout.addWidget(title)

        self.status_label = QLabel(
            "מוכן."
        )

        layout.addWidget(
            self.status_label
        )

        self.progress = QProgressBar()

        self.progress.setRange(
            0,
            2,
        )

        self.progress.setValue(
            0
        )

        layout.addWidget(
            self.progress
        )

        buttons = QHBoxLayout()

        self.start_button = QPushButton(
            "התחל"
        )

        self.start_button.clicked.connect(
            self.start_index
        )

        buttons.addWidget(
            self.start_button
        )

        self.stop_button = QPushButton(
            "עצור"
        )

        self.stop_button.setEnabled(
            False
        )

        self.stop_button.clicked.connect(
            self.stop_process
        )

        buttons.addWidget(
            self.stop_button
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

        self.output = QTextEdit()

        self.output.setReadOnly(
            True
        )

        layout.addWidget(
            self.output
        )

    def log(self, text):
        self.output.append(
            str(text)
        )

        self.output.moveCursor(
            QTextCursor.End
        )

    def start_index(self):
        if self.process is not None:
            return

        self.start_button.setEnabled(
            False
        )

        self.stop_button.setEnabled(
            True
        )

        self.progress.setValue(
            0
        )

        self.stage = "parser"

        self.start_process(
            PROJECT_ROOT
            / "src"
            / "gmail"
            / "gmail_parser.py",
            [
                "--account",
                DEFAULT_GMAIL_ACCOUNT,
            ],
        )

    def start_process(
        self,
        script,
        args,
    ):
        self.process = QProcess(
            self
        )

        self.process.setProcessChannelMode(
            QProcess.MergedChannels
        )

        env = (
            QProcessEnvironment
            .systemEnvironment()
        )

        env.insert(
            "PROJECT_ROOT",
            str(PROJECT_ROOT),
        )

        env.insert(
            "SRC_ROOT",
            str(SRC_ROOT),
        )

        existing_pythonpath = env.value(
            "PYTHONPATH"
        )

        python_paths = [
            str(PROJECT_ROOT),
            str(SRC_ROOT),
        ]

        if existing_pythonpath:
            python_paths.append(
                existing_pythonpath
            )

        env.insert(
            "PYTHONPATH",
            os.pathsep.join(
                python_paths
            ),
        )

        self.process.setProcessEnvironment(
            env
        )

        self.process.readyReadStandardOutput.connect(
            self.read_output
        )

        self.process.finished.connect(
            self.process_finished
        )

        self.log("")
        self.log("=" * 80)
        self.log(
            f"Running: {script}"
        )
        self.log("=" * 80)

        self.process.start(
            sys.executable,
            [str(script)] + list(args),
        )

    def read_output(self):
        if not self.process:
            return

        data = bytes(
            self.process.readAllStandardOutput()
        ).decode(
            "utf-8",
            errors="replace",
        )

        if data:
            self.log(
                data.rstrip()
            )

    def process_finished(
        self,
        exit_code,
        exit_status,
    ):
        current_stage = self.stage

        self.process = None

        if exit_code != 0:
            self.status_label.setText(
                f"{current_stage} הסתיים עם שגיאה ({exit_code})."
            )

            self.start_button.setEnabled(
                True
            )

            self.stop_button.setEnabled(
                False
            )

            return

        if current_stage == "parser":
            self.progress.setValue(
                1
            )

            self.status_label.setText(
                "PARSE הסתיים. מתחיל INDEX..."
            )

            self.stage = "indexer"

            self.start_process(
                PROJECT_ROOT
                / "src"
                / "gmail"
                / "gmail_indexer.py",
                [],
            )

            return

        self.progress.setValue(
            2
        )

        self.status_label.setText(
            "PARSE + INDEX הסתיימו בהצלחה."
        )

        self.start_button.setEnabled(
            True
        )

        self.stop_button.setEnabled(
            False
        )

    def stop_process(self):
        if (
            self.process
            and self.process.state()
            == QProcess.Running
        ):
            self.process.kill()

            self.status_label.setText(
                "התהליך נעצר."
            )

            self.start_button.setEnabled(
                True
            )

            self.stop_button.setEnabled(
                False
            )

    def closeEvent(self, event):
        if (
            self.process
            and self.process.state()
            == QProcess.Running
        ):
            answer = QMessageBox.question(
                self,
                "Gmail Index",
                "תהליך עדיין פועל. לעצור ולסגור?",
                QMessageBox.Yes
                | QMessageBox.No,
            )

            if answer == QMessageBox.No:
                event.ignore()
                return

            self.stop_process()

        event.accept()


# ----------------------------------------------------------------------
# Drive Sync Window
# ----------------------------------------------------------------------

class DriveSyncWindow(QDialog):
    def __init__(
        self,
        direction,
        parent=None,
    ):
        super().__init__(parent)

        self.direction = direction
        self.process = None

        self.total_items = 0
        self.completed_items = 0
        self.transferred_items = 0
        self.no_change_items = 0
        self.error_items = 0

        self.setWindowTitle(
            "Alcalay - Google Drive Sync"
        )

        self.setModal(False)

        self.setWindowFlag(
            Qt.WindowStaysOnTopHint,
            True,
        )

        self.resize(
            1100,
            760,
        )

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel(
            "Google Drive Synchronization"
        )

        title.setStyleSheet(
            "font-size: 22px; font-weight: bold; padding: 8px;"
        )

        layout.addWidget(
            title
        )

        direction_text = (
            "Google Drive → Local"
            if self.direction
            == DIRECTION_DRIVE_TO_LOCAL
            else "Local → Google Drive"
        )

        self.direction_label = QLabel(
            direction_text
        )

        self.direction_label.setStyleSheet(
            "font-size: 16px; font-weight: bold;"
        )

        layout.addWidget(
            self.direction_label
        )

        self.status_label = QLabel(
            "מוכן."
        )

        layout.addWidget(
            self.status_label
        )

        self.counter_label = QLabel(
            "טופלו: 0 / 0   |   "
            "הועברו: 0   |   "
            "ללא שינוי: 0   |   "
            "שגיאות: 0"
        )

        self.counter_label.setStyleSheet(
            "font-size: 16px; "
            "font-weight: bold; "
            "padding: 8px; "
            "border: 1px solid #cccccc;"
        )

        self.counter_label.setWordWrap(
            True
        )

        layout.addWidget(
            self.counter_label
        )

        self.progress = QProgressBar()

        self.progress.setRange(
            0,
            100,
        )

        self.progress.setValue(
            0
        )

        layout.addWidget(
            self.progress
        )

        self.summary_label = QLabel(
            ""
        )

        self.summary_label.setWordWrap(
            True
        )

        layout.addWidget(
            self.summary_label
        )

        self.table = QTableWidget(
            0,
            4,
        )

        self.table.setHorizontalHeaderLabels(
            [
                "Type",
                "Total",
                "Completed",
                "Errors",
            ]
        )

        self.table.horizontalHeader().setStretchLastSection(
            True
        )

        layout.addWidget(
            self.table
        )

        self.activity = QTextEdit()

        self.activity.setReadOnly(
            True
        )

        layout.addWidget(
            self.activity
        )

        buttons = QHBoxLayout()

        self.start_button = QPushButton(
            "התחל סנכרון"
        )

        self.start_button.clicked.connect(
            self.start_sync
        )

        buttons.addWidget(
            self.start_button
        )

        self.stop_button = QPushButton(
            "עצור"
        )

        self.stop_button.setEnabled(
            False
        )

        self.stop_button.clicked.connect(
            self.stop_sync
        )

        buttons.addWidget(
            self.stop_button
        )

        self.reconnect_button = QPushButton(
            "חבר מחדש ל-Google"
        )

        self.reconnect_button.clicked.connect(
            self.reconnect_google
        )

        buttons.addWidget(
            self.reconnect_button
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

    def log(self, text):
        self.activity.append(
            str(text)
        )

        self.activity.moveCursor(
            QTextCursor.End
        )

    def reset_counters(self):
        self.total_items = 0
        self.completed_items = 0
        self.transferred_items = 0
        self.no_change_items = 0
        self.error_items = 0

        self.update_counter_display()

    def update_counter_display(self):
        total_text = (
            str(self.total_items)
            if self.total_items > 0
            else "0"
        )

        self.counter_label.setText(
            f"טופלו: {self.completed_items} / {total_text}"
            f"   |   הועברו: {self.transferred_items}"
            f"   |   ללא שינוי: {self.no_change_items}"
            f"   |   שגיאות: {self.error_items}"
        )

    def start_sync(self):
        if self.process is not None:
            return

        self.reset_counters()

        self.progress.setValue(
            0
        )

        self.summary_label.setText(
            ""
        )

        self.process = QProcess(
            self
        )

        self.process.setProcessChannelMode(
            QProcess.MergedChannels
        )

        env = (
            QProcessEnvironment
            .systemEnvironment()
        )

        env.insert(
            "PROJECT_ROOT",
            str(PROJECT_ROOT),
        )

        env.insert(
            "SRC_ROOT",
            str(SRC_ROOT),
        )

        env.insert(
            "ALCALAY_SYNC_DIRECTION",
            self.direction,
        )

        existing_pythonpath = env.value(
            "PYTHONPATH"
        )

        python_paths = [
            str(PROJECT_ROOT),
            str(SRC_ROOT),
        ]

        if existing_pythonpath:
            python_paths.append(
                existing_pythonpath
            )

        env.insert(
            "PYTHONPATH",
            os.pathsep.join(
                python_paths
            ),
        )

        self.process.setProcessEnvironment(
            env
        )

        self.process.readyReadStandardOutput.connect(
            self.read_output
        )

        self.process.finished.connect(
            self.process_finished
        )

        script = (
            PROJECT_ROOT
            / "src"
            / "drive"
            / "drive_sync.py"
        )

        self.log("")
        self.log("=" * 80)
        self.log(
            f"Starting Drive Sync: {self.direction}"
        )
        self.log(
            f"Script: {script}"
        )
        self.log("=" * 80)

        self.status_label.setText(
            "סנכרון פועל..."
        )

        self.start_button.setEnabled(
            False
        )

        self.stop_button.setEnabled(
            True
        )

        self.process.start(
            sys.executable,
            [
                "-u",
                str(script),
            ],
        )

    def read_output(self):
        if not self.process:
            return

        data = bytes(
            self.process.readAllStandardOutput()
        ).decode(
            "utf-8",
            errors="replace",
        )

        if not data:
            return

        for line in data.splitlines():
            self.handle_sync_line(
                line
            )

    def handle_sync_line(self, line):
        prefix = "[SYNC_EVENT] "

        if line.startswith(prefix):
            payload = line[
                len(prefix):
            ]

            try:
                import json

                event = json.loads(
                    payload
                )

                self.handle_sync_event(
                    event
                )

                return

            except Exception:
                pass

        self.log(
            line
        )

    def handle_sync_event(self, event):
        event_type = event.get(
            "event",
            "",
        ).upper()

        if event_type == "RUN_START":
            self.total_items = 0
            self.completed_items = 0
            self.transferred_items = 0
            self.no_change_items = 0
            self.error_items = 0

            self.update_counter_display()

            message = event.get(
                "message",
                "הסנכרון התחיל.",
            )

            self.status_label.setText(
                message
            )

            self.log(
                message
            )

        elif event_type == "REPOSITORY":
            repository_id = event.get(
                "repository_id",
                "",
            )

            root_folder_id = event.get(
                "root_folder_id",
                "",
            )

            self.log(
                f"Repository: {repository_id} | "
                f"Root folder: {root_folder_id}"
            )

        elif event_type == "DRIVE_CONNECTED":
            email = event.get(
                "email",
                "",
            )

            message = (
                "Google Drive connected"
                + (
                    f": {email}"
                    if email
                    else ""
                )
            )

            self.status_label.setText(
                message
            )

            self.log(
                message
            )

        elif event_type == "CANDIDATES":
            self.total_items = int(
                event.get(
                    "count",
                    0,
                )
                or 0
            )

            self.completed_items = 0
            self.transferred_items = 0
            self.no_change_items = 0
            self.error_items = 0

            direction = event.get(
                "direction",
                self.direction,
            )

            self.update_counter_display()

            self.status_label.setText(
                f"נמצאו {self.total_items} "
                f"פריטים לסנכרון."
            )

            self.log(
                f"Candidates: {self.total_items} | "
                f"Direction: {direction}"
            )

        elif event_type == "PROGRESS":
            index = int(
                event.get(
                    "index",
                    0,
                )
                or 0
            )

            total = int(
                event.get(
                    "total_candidates",
                    self.total_items,
                )
                or 0
            )

            name = event.get(
                "name",
                "",
            )

            if total > 0:
                self.total_items = total

                percent = int(
                    (
                        max(
                            0,
                            index - 1,
                        )
                        / total
                    )
                    * 100
                )

                self.progress.setValue(
                    max(
                        0,
                        min(
                            100,
                            percent,
                        ),
                    )
                )

            self.update_counter_display()

            if total:
                self.status_label.setText(
                    f"{index}/{total}  {name}"
                )
            else:
                self.status_label.setText(
                    name
                )

            self.log(
                f"[{index}/{total}] {name}"
            )

        elif event_type == "ITEM_START":
            name = event.get(
                "name",
                "",
            )

            action = event.get(
                "action",
                "",
            )

            self.status_label.setText(
                f"מעבד: {name}"
            )

            self.log(
                f"START: {name}"
                + (
                    f" | {action}"
                    if action
                    else ""
                )
            )

        elif event_type == "ITEM_FINISH":
            name = event.get(
                "name",
                "",
            )

            result = str(
                event.get(
                    "result",
                    "",
                )
                or ""
            ).upper()

            self.completed_items += 1

            if result in (
                "UPLOADED",
                "DOWNLOADED",
                "TRANSFERRED",
                "COPIED",
                "CREATED",
                "UPDATED",
            ):
                self.transferred_items += 1

            elif result in (
                "NO_CHANGE",
                "UNCHANGED",
                "SKIPPED",
            ):
                self.no_change_items += 1

            elif result in (
                "ERROR",
                "FAILED",
                "FAIL",
            ):
                self.error_items += 1

            self.update_counter_display()

            if self.total_items > 0:
                percent = int(
                    (
                        self.completed_items
                        / self.total_items
                    )
                    * 100
                )

                self.progress.setValue(
                    max(
                        0,
                        min(
                            100,
                            percent,
                        ),
                    )
                )

            self.status_label.setText(
                (
                    f"{result}: {name}"
                    if result
                    else name
                )
            )

            self.log(
                f"FINISH: {name}"
                + (
                    f" | {result}"
                    if result
                    else ""
                )
            )

        elif event_type == "SUMMARY":
            message = event.get(
                "message",
                "",
            )

            self.summary_label.setText(
                message
            )

            self.log(
                message
            )

        elif event_type == "ERROR":
            self.error_items += 1

            self.update_counter_display()

            message = event.get(
                "message",
                str(event),
            )

            self.log(
                "ERROR: "
                + str(message)
            )

            self.status_label.setText(
                "שגיאה במהלך הסנכרון."
            )

        elif event_type in (
            "RUN_FINISH",
            "DONE",
        ):
            self.progress.setValue(
                100
            )

            message = event.get(
                "message",
                "הסנכרון הסתיים.",
            )

            self.status_label.setText(
                message
            )

            self.update_counter_display()

            self.log(
                message
            )

        else:
            message = event.get(
                "message"
            )

            if message:
                self.log(
                    message
                )

    def stop_sync(self):
        if not self.process:
            return

        if (
            self.process.state()
            == QProcess.Running
        ):
            self.process.write(
                b"STOP\n"
            )

            self.status_label.setText(
                "נשלחה בקשת עצירה..."
            )

            QTimer.singleShot(
                3000,
                self.force_stop_if_running,
            )

    def force_stop_if_running(self):
        if (
            self.process
            and self.process.state()
            == QProcess.Running
        ):
            self.process.kill()

    def reconnect_google(self):
        try:
            token_candidates = [
                PROJECT_ROOT
                / "config"
                / "google"
                / (
                    DEFAULT_GMAIL_ACCOUNT
                    + "_token.json"
                ),
                PROJECT_ROOT
                / "config"
                / "google"
                / "token.json",
                PROJECT_ROOT
                / "config"
                / "drive"
                / (
                    DEFAULT_GMAIL_ACCOUNT
                    + "_token.json"
                ),
            ]

            removed = []

            for token_path in token_candidates:
                if token_path.exists():
                    token_path.unlink()

                    removed.append(
                        str(token_path)
                    )

            from drive.drive_connection import (
                DriveConnection
            )

            connection = DriveConnection(
                account_email=DEFAULT_GMAIL_ACCOUNT
            )

            connection.connect()

            if removed:
                self.log(
                    "Removed OAuth token(s): "
                    + ", ".join(removed)
                )

            self.log(
                "Google Drive connection completed."
            )

            QMessageBox.information(
                self,
                "Google Drive",
                "החיבור ל-Google Drive הושלם.",
            )

        except Exception as exc:
            self.log(
                f"Google Drive reconnect error: "
                f"{exc}"
            )

            QMessageBox.critical(
                self,
                "Google Drive",
                f"שגיאה בחיבור מחדש:\n{exc}",
            )

    def process_finished(
        self,
        exit_code,
        exit_status,
    ):
        self.log(
            f"Drive Sync finished. "
            f"exit_code={exit_code}, "
            f"exit_status={exit_status}"
        )

        self.update_counter_display()

        if exit_code == 0:
            self.progress.setValue(
                100
            )

            self.status_label.setText(
                "הסנכרון הסתיים בהצלחה."
            )

        else:
            self.status_label.setText(
                f"הסנכרון הסתיים עם שגיאה "
                f"({exit_code})."
            )

        self.start_button.setEnabled(
            True
        )

        self.stop_button.setEnabled(
            False
        )

        self.process = None

    def closeEvent(self, event):
        if (
            self.process
            and self.process.state()
            == QProcess.Running
        ):
            answer = QMessageBox.question(
                self,
                "Drive Sync",
                "הסנכרון עדיין פועל. לעצור ולסגור?",
                QMessageBox.Yes
                | QMessageBox.No,
            )

            if answer == QMessageBox.No:
                event.ignore()
                return

            self.stop_sync()

        event.accept()


# ----------------------------------------------------------------------
# Google Drive Window
# ----------------------------------------------------------------------

class GoogleDriveWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(
            "Alcalay - Google Drive"
        )

        self.setModal(False)

        self.resize(
            1100,
            760,
        )

        self.process = None
        self.sync_window = None

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel(
            "Google Drive"
        )

        title.setStyleSheet(
            "font-size: 22px; font-weight: bold; padding: 8px;"
        )

        layout.addWidget(
            title
        )

        self.command_list = QListWidget()

        commands = [
            "Scan Google Drive",
            "Filter by file name",
            "Filter by content",
            "Check duplicates",
            "Download selected files",
            "Synchronize Drive → Local",
            "Synchronize Local → Drive",
        ]

        for command in commands:
            self.command_list.addItem(
                command
            )

        layout.addWidget(
            self.command_list
        )

        filter_layout = QHBoxLayout()

        self.name_filter = QLineEdit()

        self.name_filter.setPlaceholderText(
            "Name filter..."
        )

        filter_layout.addWidget(
            self.name_filter
        )

        self.content_filter = QLineEdit()

        self.content_filter.setPlaceholderText(
            "Content filter..."
        )

        filter_layout.addWidget(
            self.content_filter
        )

        layout.addLayout(
            filter_layout
        )

        buttons = QHBoxLayout()

        self.scan_button = QPushButton(
            "Scan"
        )

        self.scan_button.clicked.connect(
            self.scan_drive
        )

        buttons.addWidget(
            self.scan_button
        )

        self.download_button = QPushButton(
            "Download"
        )

        self.download_button.clicked.connect(
            self.download_drive
        )

        buttons.addWidget(
            self.download_button
        )

        self.sync_drive_local_button = QPushButton(
            "Drive → Local"
        )

        self.sync_drive_local_button.clicked.connect(
            lambda: self.open_sync(
                DIRECTION_DRIVE_TO_LOCAL
            )
        )

        buttons.addWidget(
            self.sync_drive_local_button
        )

        self.sync_local_drive_button = QPushButton(
            "Local → Drive"
        )

        self.sync_local_drive_button.clicked.connect(
            lambda: self.open_sync(
                DIRECTION_LOCAL_TO_DRIVE
            )
        )

        buttons.addWidget(
            self.sync_local_drive_button
        )

        self.reconnect_button = QPushButton(
            "Reconnect Google"
        )

        self.reconnect_button.clicked.connect(
            self.reconnect_google
        )

        buttons.addWidget(
            self.reconnect_button
        )

        layout.addLayout(
            buttons
        )

        self.output = QTextEdit()

        self.output.setReadOnly(
            True
        )

        layout.addWidget(
            self.output
        )

    def log(self, text):
        self.output.append(
            str(text)
        )

        self.output.moveCursor(
            QTextCursor.End
        )

    def scan_drive(self):
        self.log(
            "Google Drive metadata registry requested."
        )

        self.log(
            "Starting full Drive scan chain: "
            "DriveConnection -> DriveRepository -> "
            "DriveScanner -> PostgreSQL."
        )

        script = (
            PROJECT_ROOT
            / "src"
            / "drive"
            / "drive_registry.py"
        )

        self.run_script(
            script,
            [],
        )

    def download_drive(self):
        self.log(
            "Google Drive download requested."
        )

        script = (
            PROJECT_ROOT
            / "src"
            / "drive"
            / "drive_downloader.py"
        )

        self.run_script(
            script,
            [],
        )

    def run_script(
        self,
        script,
        args,
    ):
        if (
            self.process
            and self.process.state()
            == QProcess.Running
        ):
            QMessageBox.warning(
                self,
                "Google Drive",
                "תהליך כבר פועל.",
            )

            return

        self.process = QProcess(
            self
        )

        self.process.setProcessChannelMode(
            QProcess.MergedChannels
        )

        env = (
            QProcessEnvironment
            .systemEnvironment()
        )

        env.insert(
            "PROJECT_ROOT",
            str(PROJECT_ROOT),
        )

        env.insert(
            "SRC_ROOT",
            str(SRC_ROOT),
        )

        existing_pythonpath = env.value(
            "PYTHONPATH"
        )

        python_paths = [
            str(PROJECT_ROOT),
            str(SRC_ROOT),
        ]

        if existing_pythonpath:
            python_paths.append(
                existing_pythonpath
            )

        env.insert(
            "PYTHONPATH",
            os.pathsep.join(
                python_paths
            ),
        )

        self.process.setProcessEnvironment(
            env
        )

        self.process.readyReadStandardOutput.connect(
            self.read_output
        )

        self.process.finished.connect(
            self.process_finished
        )

        self.process.start(
            sys.executable,
            [str(script)] + list(args),
        )

    def read_output(self):
        if not self.process:
            return

        data = bytes(
            self.process.readAllStandardOutput()
        ).decode(
            "utf-8",
            errors="replace",
        )

        if data:
            self.log(
                data.rstrip()
            )

    def process_finished(
        self,
        exit_code,
        exit_status,
    ):
        self.log(
            f"Process finished. "
            f"exit_code={exit_code}, "
            f"exit_status={exit_status}"
        )

        self.process = None

    def open_sync(
        self,
        direction,
    ):
        self.sync_window = DriveSyncWindow(
            direction,
            self,
        )

        self.sync_window.show()
        self.sync_window.raise_()
        self.sync_window.activateWindow()

    def reconnect_google(self):
        try:
            from drive.drive_connection import (
                DriveConnection
            )

            connection = DriveConnection(
                account_email=DEFAULT_GMAIL_ACCOUNT
            )

            connection.connect()

            QMessageBox.information(
                self,
                "Google Drive",
                "החיבור ל-Google Drive הושלם.",
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Google Drive",
                f"שגיאה בחיבור ל-Google Drive:\n{exc}",
            )


# ----------------------------------------------------------------------
# Google Launcher Page
# ----------------------------------------------------------------------

class GoogleLauncherPage(QWidget):
    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        self.parent_window = parent

        layout = QVBoxLayout(
            self
        )

        title = QLabel(
            "Google"
        )

        title.setStyleSheet(
            "font-size: 28px; font-weight: bold; padding: 12px;"
        )

        layout.addWidget(
            title
        )

        self.drive_button = QPushButton(
            "Google Drive"
        )

        self.drive_button.setMinimumHeight(
            60
        )

        self.drive_button.clicked.connect(
            self.open_drive
        )

        layout.addWidget(
            self.drive_button
        )

        self.gmail_accounts_button = QPushButton(
            "Gmail Accounts / Labels"
        )

        self.gmail_accounts_button.setMinimumHeight(
            60
        )

        self.gmail_accounts_button.clicked.connect(
            self.open_gmail
        )

        layout.addWidget(
            self.gmail_accounts_button
        )

        self.gmail_import_button = QPushButton(
            "Gmail Import"
        )

        self.gmail_import_button.setMinimumHeight(
            60
        )

        self.gmail_import_button.clicked.connect(
            self.open_gmail_import
        )

        layout.addWidget(
            self.gmail_import_button
        )

        self.gmail_index_button = QPushButton(
            "Gmail Parse + Index"
        )

        self.gmail_index_button.setMinimumHeight(
            60
        )

        self.gmail_index_button.clicked.connect(
            self.open_gmail_index
        )

        layout.addWidget(
            self.gmail_index_button
        )

        self.search_button = QPushButton(
            "Search"
        )

        self.search_button.setMinimumHeight(
            60
        )

        self.search_button.clicked.connect(
            self.open_search
        )

        layout.addWidget(
            self.search_button
        )

        layout.addStretch()

    def open_drive(self):
        window = GoogleDriveWindow(
            self
        )

        window.show()
        window.raise_()
        window.activateWindow()

    def open_gmail(self):
        try:
            window = GmailWindow(
                self
            )

            window.show()
            window.raise_()
            window.activateWindow()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Gmail",
                f"שגיאה בפתיחת Gmail:\n{exc}",
            )

    def open_gmail_import(self):
        window = GmailImportWindow(
            self
        )

        window.show()
        window.raise_()
        window.activateWindow()

    def open_gmail_index(self):
        window = GmailIndexWindow(
            self
        )

        window.show()
        window.raise_()
        window.activateWindow()

    def open_search(self):
        try:
            window = SearchWindow(
                self
            )

            window.show()
            window.raise_()
            window.activateWindow()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Search",
                f"שגיאה בפתיחת Search:\n{exc}",
            )


# ----------------------------------------------------------------------
# Search Launcher Page
# ----------------------------------------------------------------------

class SearchLauncherPage(QWidget):
    """Central search launcher."""

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        self.parent_window = parent
        self.search_window = None
        self.index_window = None

        self.setLayoutDirection(
            Qt.RightToLeft
        )

        layout = QVBoxLayout(
            self
        )

        layout.setContentsMargins(
            30,
            30,
            30,
            30,
        )

        layout.setSpacing(
            16
        )

        title = QLabel(
            "חיפוש"
        )

        title.setAlignment(
            Qt.AlignRight
        )

        title.setStyleSheet(
            "font-size: 28px; font-weight: bold; padding: 8px;"
        )

        layout.addWidget(
            title
        )

        description = QLabel(
            "חיפוש במידע שנשמר במאגרים, או הפעלת אינדוקס מרכזי "
            "של מיילים, מסמכים ומנוע AI. ניתן להפעיל כמה אפשרויות יחד."
        )

        description.setWordWrap(
            True
        )

        description.setAlignment(
            Qt.AlignRight
        )

        description.setStyleSheet(
            "font-size: 15px; padding: 8px;"
        )

        layout.addWidget(
            description
        )

        search_frame = QFrame()

        search_frame.setObjectName(
            "searchLauncherFrame"
        )

        search_layout = QVBoxLayout(
            search_frame
        )

        search_layout.setContentsMargins(
            20,
            20,
            20,
            20,
        )

        search_layout.setSpacing(
            10
        )

        search_title = QLabel(
            "חיפוש במאגרים"
        )

        search_title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )

        search_layout.addWidget(
            search_title
        )

        search_text = QLabel(
            "פתיחת חלון החיפוש הקיים במערכת."
        )

        search_text.setWordWrap(
            True
        )

        search_layout.addWidget(
            search_text
        )

        search_button = QPushButton(
            "🔎  חיפוש"
        )

        search_button.setMinimumHeight(
            55
        )

        search_button.clicked.connect(
            self.open_search
        )

        search_layout.addWidget(
            search_button
        )

        layout.addWidget(
            search_frame
        )

        index_frame = QFrame()

        index_frame.setObjectName(
            "indexLauncherFrame"
        )

        index_layout = QVBoxLayout(
            index_frame
        )

        index_layout.setContentsMargins(
            20,
            20,
            20,
            20,
        )

        index_layout.setSpacing(
            10
        )

        index_title = QLabel(
            "אינדקס"
        )

        index_title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )

        index_layout.addWidget(
            index_title
        )

        index_text = QLabel(
            "בחירת אינדוקס של מיילים, אינדוקס מסמכים ומנוע AI. "
            "החלון מציג התקדמות, כמה טופלו, כמה נשארו, שגיאות, "
            "וכפתור עצור עם אפשרות להמשיך מאותה נקודה."
        )

        index_text.setWordWrap(
            True
        )

        index_layout.addWidget(
            index_text
        )

        index_button = QPushButton(
            "🗂  אינדקס"
        )

        index_button.setMinimumHeight(
            55
        )

        index_button.clicked.connect(
            self.open_index
        )

        index_layout.addWidget(
            index_button
        )

        layout.addWidget(
            index_frame
        )

        layout.addStretch()

    def open_search(self):
        try:
            if self.search_window is None:
                self.search_window = SearchWindow(
                    self
                )

            self.search_window.show()
            self.search_window.raise_()
            self.search_window.activateWindow()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Search",
                f"שגיאה בפתיחת Search:\n{exc}",
            )

    def open_index(self):
        try:
            if self.index_window is None:
                self.index_window = IndexWindow(
                    self
                )

            self.index_window.show()
            self.index_window.raise_()
            self.index_window.activateWindow()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "אינדקס",
                f"שגיאה בפתיחת חלון האינדקס:\n{exc}",
            )


# ----------------------------------------------------------------------
# Placeholder Page
# ----------------------------------------------------------------------

class PlaceholderPage(QWidget):
    def __init__(
        self,
        title,
        parent=None,
    ):
        super().__init__(
            parent
        )

        layout = QVBoxLayout(
            self
        )

        label = QLabel(
            title
        )

        label.setAlignment(
            Qt.AlignCenter
        )

        label.setStyleSheet(
            "font-size: 28px; font-weight: bold;"
        )

        layout.addWidget(
            label
        )


# ----------------------------------------------------------------------
# Main Window
# ----------------------------------------------------------------------

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "Alcalay"
        )

        self.resize(
            1400,
            900,
        )

        self.setLayoutDirection(
            Qt.RightToLeft
        )

        self.pages = {}

        root_layout = QHBoxLayout(
            self
        )

        root_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        root_layout.setSpacing(
            0
        )

        self.menu = QListWidget()

        self.menu.setFixedWidth(
            310
        )

        menu_items = [
            "Google",
            "מסמכים לפי קטגוריה",
            "חיפוש",
            "מסד נתונים",
            "הורדה מקומית",
            "משתמשים והרשאות",
            "מערכת",
            "דוחות",
            "הגדרות",
            "רענון והוספת מסמכים מהמייל",
        ]

        for item in menu_items:
            self.menu.addItem(
                item
            )

        root_layout.addWidget(
            self.menu
        )

        self.stack = QStackedWidget()

        root_layout.addWidget(
            self.stack
        )

        google_page = GoogleLauncherPage(
            self
        )

        self.add_page(
            "Google",
            google_page,
        )

        self.add_page(
            "מסמכים לפי קטגוריה",
            PlaceholderPage(
                "מסמכים לפי קטגוריה",
                self,
            ),
        )

        self.add_page(
            "חיפוש",
            SearchLauncherPage(
                self,
            ),
        )

        self.add_page(
            "מסד נתונים",
            PlaceholderPage(
                "מסד נתונים",
                self,
            ),
        )

        self.add_page(
            "הורדה מקומית",
            PlaceholderPage(
                "הורדה מקומית",
                self,
            ),
        )

        self.add_page(
            "משתמשים והרשאות",
            PlaceholderPage(
                "משתמשים והרשאות",
                self,
            ),
        )

        self.add_page(
            "מערכת",
            PlaceholderPage(
                "מערכת",
                self,
            ),
        )

        self.add_page(
            "דוחות",
            PlaceholderPage(
                "דוחות",
                self,
            ),
        )

        self.add_page(
            "הגדרות",
            PlaceholderPage(
                "הגדרות",
                self,
            ),
        )

        gmail_import_page = GmailImportWindow(
            self
        )

        self.add_page(
            "רענון והוספת מסמכים מהמייל",
            gmail_import_page,
        )

        self.menu.currentRowChanged.connect(
            self.change_page
        )

        self.menu.setCurrentRow(
            0
        )

    def add_page(
        self,
        name,
        widget,
    ):
        self.pages[name] = widget

        self.stack.addWidget(
            widget
        )

    def change_page(
        self,
        index,
    ):
        if index < 0:
            return

        item = self.menu.item(
            index
        )

        if not item:
            return

        name = item.text()

        widget = self.pages.get(
            name
        )

        if widget is not None:
            self.stack.setCurrentWidget(
                widget
            )


# ----------------------------------------------------------------------
# Styling
# ----------------------------------------------------------------------

def apply_styles(app):
    app.setStyleSheet(
        """
        QWidget {
            font-family: Arial;
            font-size: 14px;
        }

        QListWidget {
            border: none;
            padding: 8px;
        }

        QListWidget::item {
            padding: 14px;
            margin: 2px;
        }

        QListWidget::item:selected {
            font-weight: bold;
        }

        QPushButton {
            padding: 10px 18px;
            min-height: 36px;
        }

        QLineEdit {
            padding: 8px;
        }

        QTextEdit {
            padding: 8px;
        }

        QTableWidget {
            gridline-color: #cccccc;
        }

        QProgressBar {
            min-height: 24px;
            text-align: center;
        }
        """
    )


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    app = QApplication(
        sys.argv
    )

    apply_styles(
        app
    )

    window = MainWindow()

    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()