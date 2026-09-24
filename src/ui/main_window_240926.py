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
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QInputDialog,
    QWidget,
)

from database.connection import DatabaseConnection
from gmail.gmail_connection import GmailConnection
from gmail.gmail_window import GmailWindow
from search.search_window import SearchWindow


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

DEFAULT_GMAIL_ACCOUNT = "frank.avner@gmail.com"

DIRECTION_DRIVE_TO_LOCAL = "DRIVE_TO_LOCAL"
DIRECTION_LOCAL_TO_DRIVE = "LOCAL_TO_DRIVE"


# ----------------------------------------------------------------------
# Gmail Import Window
# ----------------------------------------------------------------------

class GmailImportWindow(QDialog):
    """Run gmail_copy.py as a real interactive terminal-like process.

    gmail_copy.py remains the single source of truth for:
    - loading the PostgreSQL-selected Gmail Labels
    - displaying their message counts
    - asking for Label numbers
    - asking for YES confirmation
    - performing the COPY

    This window only starts the process, displays stdout/stderr, and forwards
    exactly what the user types to the process stdin.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Alcalay - Gmail COPY")
        self.setWindowModality(Qt.NonModal)
        self.resize(1100, 760)
        self.setMinimumSize(900, 600)

        self.process = None
        self.process_finished = False
        self._closing = False
        self._auto_started = False

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel("ייבוא מיילים מ-Gmail")
        title.setObjectName("windowTitle")
        layout.addWidget(title)

        self.status_label = QLabel("מוכן")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        info = QLabel(
            "החלון מציג ישירות את כל הפלט של gmail_copy.py. "
            "הקלט שאתה מזין נשלח ישירות ל-gmail_copy.py ללא שינוי."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.output.setPlaceholderText("פלט Gmail COPY יופיע כאן...")
        layout.addWidget(self.output, 1)

        input_frame = QFrame()
        input_frame.setObjectName("inputFrame")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 10, 12, 10)
        input_layout.setSpacing(7)

        self.input_label = QLabel("קלט ל-gmail_copy.py")
        self.input_label.setObjectName("inputLabel")
        input_layout.addWidget(self.input_label)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText(
            "לדוגמה: 1,4,7  או  1-3,7  או  YES"
        )
        self.input_edit.returnPressed.connect(self.send_input)
        input_row.addWidget(self.input_edit, 1)

        self.send_button = QPushButton("שלח")
        self.send_button.clicked.connect(self.send_input)
        input_row.addWidget(self.send_button)

        input_layout.addLayout(input_row)

        self.input_hint = QLabel(
            "כל קלט נשלח ישירות ל-stdin של gmail_copy.py."
        )
        self.input_hint.setObjectName("inputHint")
        self.input_hint.setWordWrap(True)
        input_layout.addWidget(self.input_hint)

        layout.addWidget(input_frame)

        button_row = QHBoxLayout()

        self.start_button = QPushButton("התחל / הפעל מחדש")
        self.start_button.clicked.connect(self.start)
        button_row.addWidget(self.start_button)

        self.stop_button = QPushButton("עצור")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_process)
        button_row.addWidget(self.stop_button)

        button_row.addStretch()

        self.close_button = QPushButton("סגור")
        self.close_button.clicked.connect(self.close)
        button_row.addWidget(self.close_button)

        layout.addLayout(button_row)

        self._set_input_enabled(False)

    def _append_output(self, text):
        if not text:
            return

        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output.setTextCursor(cursor)
        self.output.insertPlainText(text)
        self.output.ensureCursorVisible()

    def _set_input_enabled(self, enabled):
        self.input_edit.setEnabled(enabled)
        self.send_button.setEnabled(enabled)

    def _create_process_environment(self):
        environment = QProcessEnvironment.systemEnvironment()

        existing_pythonpath = environment.value("PYTHONPATH", "")
        paths = [str(PROJECT_ROOT), str(SRC_ROOT)]

        if existing_pythonpath:
            paths.append(existing_pythonpath)

        environment.insert("PYTHONPATH", os.pathsep.join(paths))
        environment.insert("PYTHONUNBUFFERED", "1")
        environment.insert("PYTHONIOENCODING", "utf-8")
        environment.insert("LANG", environment.value("LANG", "en_US.UTF-8"))

        return environment

    def is_running(self):
        return (
            self.process is not None
            and self.process.state() != QProcess.ProcessState.NotRunning
        )

    def start(self):
        if self.is_running():
            self.status_label.setText("Gmail COPY כבר פעיל.")
            self.input_edit.setFocus()
            return

        script = PROJECT_ROOT / "src" / "gmail" / "gmail_copy.py"

        if not script.exists():
            QMessageBox.critical(
                self,
                "Gmail COPY",
                f"קובץ Gmail COPY לא נמצא:\n\n{script}",
            )
            return

        self.process_finished = False
        self._closing = False
        self.output.clear()
        self.input_edit.clear()
        self._set_input_enabled(True)

        self.status_label.setText(
            "מפעיל gmail_copy.py... ניתן להזין קלט כאשר התהליך מבקש."
        )

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.close_button.setEnabled(False)

        self.process = QProcess(self)
        self.process.setProcessEnvironment(self._create_process_environment())
        self.process.setWorkingDirectory(str(PROJECT_ROOT))
        self.process.setProgram(sys.executable)

        # gmail_copy.py accepts the account as its optional first positional
        # argument. Keeping it explicit makes the GUI behave exactly like:
        # python src/gmail/gmail_copy.py frank.avner@gmail.com
        self.process.setArguments([
            "-u",
            str(script),
            DEFAULT_GMAIL_ACCOUNT,
        ])

        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)
        self.process.started.connect(self._process_started)
        self.process.errorOccurred.connect(self._process_error)
        self.process.finished.connect(self._process_finished)

        self.process.start()

        if not self.process.waitForStarted(5000):
            self.status_label.setText("לא ניתן להפעיל את gmail_copy.py.")
            self._append_output(
                "\n[ERROR] QProcess לא הצליח להפעיל את gmail_copy.py.\n"
            )
            self._reset_after_process()

    def _process_started(self):
        self.status_label.setText(
            "gmail_copy.py פעיל. ממתין לפלט ולקלט מהתהליך..."
        )
        self.input_edit.setFocus()

    def send_input(self):
        if not self.is_running():
            QMessageBox.warning(
                self,
                "Gmail COPY",
                "gmail_copy.py אינו פעיל כרגע.",
            )
            return

        text = self.input_edit.text()
        if not text.strip():
            return

        # IMPORTANT: do not validate, parse, uppercase, or otherwise change
        # the input here. gmail_copy.py owns the interactive protocol.
        payload = (text + "\n").encode("utf-8")
        written = self.process.write(payload)

        if written < 0:
            self._append_output("\n[ERROR] לא ניתן לשלוח קלט ל-gmail_copy.py.\n")
            return

        self.process.waitForBytesWritten(2000)

        self._append_output(f"\n[GUI INPUT] {text}\n")
        self.input_edit.clear()
        self.input_edit.setFocus()

    def _read_stdout(self):
        if self.process is None:
            return

        data = bytes(self.process.readAllStandardOutput())
        if not data:
            return

        text = data.decode("utf-8", errors="replace")
        self._append_output(text)

    def _read_stderr(self):
        if self.process is None:
            return

        data = bytes(self.process.readAllStandardError())
        if not data:
            return

        text = data.decode("utf-8", errors="replace")
        self._append_output(text)

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            message = "לא ניתן להפעיל את gmail_copy.py."
        else:
            message = f"שגיאת QProcess: {error}"

        self.status_label.setText(message)
        self._append_output(f"\n[ERROR] {message}\n")

    def _process_finished(self, exit_code, exit_status):
        self.process_finished = True

        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self.status_label.setText("Gmail COPY הסתיים בהצלחה.")
        elif exit_code == 130:
            self.status_label.setText("Gmail COPY הופסק על ידי המשתמש.")
        else:
            self.status_label.setText(
                f"Gmail COPY הסתיים עם שגיאה. קוד יציאה: {exit_code}"
            )

        self._append_output(
            "\n"
            + "=" * 72
            + "\n"
            + f"[PROCESS FINISHED] exit_code={exit_code}\n"
            + "=" * 72
            + "\n"
        )

        self._reset_after_process()

    def _reset_after_process(self):
        self._set_input_enabled(False)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.close_button.setEnabled(True)

    def stop_process(self):
        if not self.is_running():
            return

        self.status_label.setText("עוצר את gmail_copy.py...")
        self._append_output("\n[GUI] מבקש לעצור את gmail_copy.py...\n")

        self.process.terminate()

        if not self.process.waitForFinished(1500):
            self._append_output("[GUI] terminate לא הסתיים. מבצע kill...\n")
            self.process.kill()
            self.process.waitForFinished(1000)

    def showEvent(self, event):
        super().showEvent(event)

        # The first time this dialog is opened from the menu, start COPY
        # automatically. A later manual restart uses the button.
        if not self._auto_started and not self.is_running():
            self._auto_started = True
            QTimer.singleShot(0, self.start)

    def closeEvent(self, event):
        self._closing = True

        if self.is_running():
            self._append_output("\n[GUI] סגירת החלון - עוצר את gmail_copy.py...\n")
            self.process.terminate()

            if not self.process.waitForFinished(1500):
                self.process.kill()
                self.process.waitForFinished(1000)

        event.accept()


# ----------------------------------------------------------------------
# Gmail Index Window
# ----------------------------------------------------------------------

class GmailIndexWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Alcalay - Gmail Index")
        self.setModal(False)
        self.resize(1100, 760)

        self.process = None
        self.stage = None

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Gmail Parse + Index")
        title.setStyleSheet(
            "font-size: 22px; font-weight: bold; padding: 8px;"
        )
        layout.addWidget(title)

        self.status_label = QLabel("מוכן.")
        layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 2)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        buttons = QHBoxLayout()

        self.start_button = QPushButton("התחל")
        self.start_button.clicked.connect(self.start_index)
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
        layout.addWidget(self.output)

    def log(self, text):
        self.output.append(str(text))
        self.output.moveCursor(QTextCursor.End)

    def start_index(self):
        if self.process is not None:
            return

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self.progress.setValue(0)
        self.stage = "parser"

        self.start_process(
            PROJECT_ROOT / "src" / "gmail" / "gmail_parser.py",
            ["--account", DEFAULT_GMAIL_ACCOUNT],
        )

    def start_process(self, script, args):
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)

        env = QProcessEnvironment.systemEnvironment()
        env.insert("PROJECT_ROOT", str(PROJECT_ROOT))
        env.insert("SRC_ROOT", str(SRC_ROOT))

        existing_pythonpath = env.value("PYTHONPATH")
        python_paths = [
            str(PROJECT_ROOT),
            str(SRC_ROOT),
        ]

        if existing_pythonpath:
            python_paths.append(existing_pythonpath)

        env.insert(
            "PYTHONPATH",
            os.pathsep.join(python_paths),
        )
        self.process.setProcessEnvironment(env)

        self.process.readyReadStandardOutput.connect(
            self.read_output
        )
        self.process.finished.connect(
            self.process_finished
        )

        self.log("")
        self.log("=" * 80)
        self.log(f"Running: {script}")
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
            self.log(data.rstrip())

    def process_finished(self, exit_code, exit_status):
        current_stage = self.stage

        self.process = None

        if exit_code != 0:
            self.status_label.setText(
                f"{current_stage} הסתיים עם שגיאה ({exit_code})."
            )
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            return

        if current_stage == "parser":
            self.progress.setValue(1)
            self.status_label.setText(
                "PARSE הסתיים. מתחיל INDEX..."
            )

            self.stage = "indexer"

            self.start_process(
                PROJECT_ROOT / "src" / "gmail" / "gmail_indexer.py",
                [],
            )
            return

        self.progress.setValue(2)
        self.status_label.setText(
            "PARSE + INDEX הסתיימו בהצלחה."
        )
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def stop_process(self):
        if (
            self.process
            and self.process.state() == QProcess.Running
        ):
            self.process.kill()

            self.status_label.setText("התהליך נעצר.")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)

    def closeEvent(self, event):
        if (
            self.process
            and self.process.state() == QProcess.Running
        ):
            answer = QMessageBox.question(
                self,
                "Gmail Index",
                "תהליך עדיין פועל. לעצור ולסגור?",
                QMessageBox.Yes | QMessageBox.No,
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
    def __init__(self, direction, parent=None):
        super().__init__(parent)

        self.direction = direction
        self.process = None
        self.started_at = None

        self.total_items = 0
        self.completed_items = 0
        self.transferred_items = 0
        self.no_change_items = 0
        self.error_items = 0

        self.setWindowTitle("Alcalay - Google Drive Sync")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.resize(1100, 760)

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Google Drive Synchronization")
        title.setStyleSheet(
            "font-size: 22px; font-weight: bold; padding: 8px;"
        )
        layout.addWidget(title)

        direction_text = (
            "Google Drive → Local"
            if self.direction == DIRECTION_DRIVE_TO_LOCAL
            else "Local → Google Drive"
        )

        self.direction_label = QLabel(direction_text)
        self.direction_label.setStyleSheet(
            "font-size: 16px; font-weight: bold;"
        )
        layout.addWidget(self.direction_label)

        self.status_label = QLabel("מוכן.")
        layout.addWidget(self.status_label)

        # --------------------------------------------------------------
        # Sync counters
        # --------------------------------------------------------------

        self.counter_label = QLabel(
            "טופלו: 0 / 0   |   הועברו: 0   |   "
            "ללא שינוי: 0   |   שגיאות: 0"
        )
        self.counter_label.setStyleSheet(
            "font-size: 16px; "
            "font-weight: bold; "
            "padding: 8px; "
            "border: 1px solid #cccccc;"
        )
        self.counter_label.setWordWrap(True)
        layout.addWidget(self.counter_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Type", "Total", "Completed", "Errors"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        self.activity = QTextEdit()
        self.activity.setReadOnly(True)
        layout.addWidget(self.activity)

        buttons = QHBoxLayout()

        self.start_button = QPushButton("התחל סנכרון")
        self.start_button.clicked.connect(self.start_sync)
        buttons.addWidget(self.start_button)

        self.stop_button = QPushButton("עצור")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_sync)
        buttons.addWidget(self.stop_button)

        self.reconnect_button = QPushButton("חבר מחדש ל-Google")
        self.reconnect_button.clicked.connect(
            self.reconnect_google
        )
        buttons.addWidget(self.reconnect_button)

        self.close_button = QPushButton("סגור")
        self.close_button.clicked.connect(self.close)
        buttons.addWidget(self.close_button)

        layout.addLayout(buttons)

    def log(self, text):
        self.activity.append(str(text))
        self.activity.moveCursor(QTextCursor.End)

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
        self.progress.setValue(0)
        self.summary_label.setText("")

        self.process = QProcess(self)
        self.process.setProcessChannelMode(
            QProcess.MergedChannels
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
            os.pathsep.join(python_paths),
        )

        self.process.setProcessEnvironment(env)

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
        self.log(f"Script: {script}")
        self.log("=" * 80)

        self.status_label.setText(
            "סנכרון פועל..."
        )

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        # Important:
        # -u forces Python stdout to be unbuffered so that
        # SYNC_EVENT messages arrive immediately in the GUI.
        self.process.start(
            sys.executable,
            ["-u", str(script)],
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
            self.handle_sync_line(line)

    def handle_sync_line(self, line):
        prefix = "[SYNC_EVENT] "

        if line.startswith(prefix):
            payload = line[len(prefix):]

            try:
                import json

                event = json.loads(payload)
                self.handle_sync_event(event)
                return

            except Exception:
                pass

        self.log(line)

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

            self.log(message)

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

            self.log(message)

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

            # Every ITEM_FINISH means that one candidate
            # has completed processing.
            self.completed_items += 1

            # Count actual transfers separately.
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

            self.log(message)

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
            self.progress.setValue(100)

            message = event.get(
                "message",
                "הסנכרון הסתיים.",
            )

            self.status_label.setText(
                message
            )

            self.update_counter_display()

            self.log(message)

        else:
            message = event.get(
                "message"
            )

            if message:
                self.log(message)

    def stop_sync(self):
        if not self.process:
            return

        if self.process.state() == QProcess.Running:
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
            self.progress.setValue(100)

            self.status_label.setText(
                "הסנכרון הסתיים בהצלחה."
            )

        else:
            self.status_label.setText(
                f"הסנכרון הסתיים עם שגיאה "
                f"({exit_code})."
            )

        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.process = None

    def closeEvent(self, event):
        if (
            self.process
            and self.process.state() == QProcess.Running
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

        self.setWindowTitle("Alcalay - Google Drive")
        self.setModal(False)
        self.resize(1100, 760)

        self.process = None
        self.sync_window = None

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Google Drive")
        title.setStyleSheet(
            "font-size: 22px; font-weight: bold; padding: 8px;"
        )
        layout.addWidget(title)

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
            self.command_list.addItem(command)

        layout.addWidget(self.command_list)

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

        layout.addLayout(filter_layout)

        buttons = QHBoxLayout()

        self.scan_button = QPushButton("Scan")
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

        layout.addLayout(buttons)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)

    def log(self, text):
        self.output.append(str(text))
        self.output.moveCursor(
            QTextCursor.End
        )

    def scan_drive(self):
        self.log(
            "Google Drive metadata registry requested."
        )
        self.log(
            "Starting full Drive scan chain: "
            "DriveConnection -> DriveRepository -> DriveScanner -> PostgreSQL."
        )

        # IMPORTANT:
        # drive_scanner.py is the scanning library itself and does not
        # contain a command-line entry point.  drive_registry.py is the
        # executable orchestration layer that performs the complete chain:
        #
        #   DriveConnection.connect()
        #       -> DriveRepository
        #       -> DriveScanner
        #       -> scan Documents/Gmail/Database/Backups
        #       -> register metadata in PostgreSQL
        #
        # Therefore the Google Drive Scan button must launch the registry,
        # not drive_scanner.py directly.
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

        self.process = QProcess(self)
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

    def open_sync(self, direction):
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
    def __init__(self, parent=None):
        super().__init__(parent)

        self.parent_window = parent

        layout = QVBoxLayout(self)

        title = QLabel("Google")
        title.setStyleSheet(
            "font-size: 28px; font-weight: bold; padding: 12px;"
        )
        layout.addWidget(title)

        self.drive_button = QPushButton(
            "Google Drive"
        )
        self.drive_button.setMinimumHeight(60)
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
        window = GoogleDriveWindow(self)
        window.show()
        window.raise_()
        window.activateWindow()

    def open_gmail(self):
        try:
            window = GmailWindow(self)
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
        window = GmailImportWindow(self)
        window.show()
        window.raise_()
        window.activateWindow()

    def open_gmail_index(self):
        window = GmailIndexWindow(self)
        window.show()
        window.raise_()
        window.activateWindow()

    def open_search(self):
        try:
            window = SearchWindow(self)
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
# Placeholder Page
# ----------------------------------------------------------------------

class PlaceholderPage(QWidget):
    def __init__(
        self,
        title,
        parent=None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        label = QLabel(title)
        label.setAlignment(
            Qt.AlignCenter
        )
        label.setStyleSheet(
            "font-size: 28px; font-weight: bold;"
        )

        layout.addWidget(label)


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

        root_layout.setSpacing(0)

        self.menu = QListWidget()
        self.menu.setFixedWidth(
            310
        )

        menu_items = [
            "Google",
            "מסמכים לפי קטגוריה",
            "חיפוש כללי",
            "מסד נתונים",
            "הורדה מקומית",
            "משתמשים והרשאות",
            "מערכת",
            "דוחות",
            "הגדרות",
            "רענון והוספת מסמכים מהמייל",
        ]

        for item in menu_items:
            self.menu.addItem(item)

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
            "חיפוש כללי",
            PlaceholderPage(
                "חיפוש כללי",
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

    apply_styles(app)

    window = MainWindow()
    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()