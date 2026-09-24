# -*- coding: utf-8 -*-

import os
import re
import sys
import json
from datetime import datetime
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
from drive.drive_connection import DriveConnection


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

DEFAULT_GMAIL_ACCOUNT = "frank.avner@gmail.com"

DIRECTION_DRIVE_TO_LOCAL = "DRIVE_TO_LOCAL"
DIRECTION_LOCAL_TO_DRIVE = "LOCAL_TO_DRIVE"


# ----------------------------------------------------------------------
# Gmail Import Window
# ----------------------------------------------------------------------

class GmailImportWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Alcalay - ייבוא מיילים מ-Gmail")
        self.setWindowModality(Qt.NonModal)
        self.resize(1100, 760)

        self.process = None
        self.process_finished = False

        self.awaiting_label_input = False
        self.awaiting_copy_confirmation = False

        self.last_handled_prompt = ""
        self.prompt_generation = 0

        self.gmail_service = None
        self.gmail_labels = []
        self.gmail_counts_loaded = False
        self.gmail_counting = False

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("ייבוא מיילים מ-Gmail")
        title.setObjectName("windowTitle")
        layout.addWidget(title)

        self.status_label = QLabel("מוכן")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)

        counts_frame = QFrame()
        counts_frame.setObjectName("inputFrame")

        counts_layout = QVBoxLayout(counts_frame)
        counts_layout.setContentsMargins(12, 12, 12, 12)
        counts_layout.setSpacing(8)

        counts_title_row = QHBoxLayout()
        counts_title_row.setSpacing(8)

        counts_title = QLabel("מספר המיילים בכל תגית שנבחרה")
        counts_title.setObjectName("inputLabel")
        counts_title_row.addWidget(counts_title)

        counts_title_row.addStretch()

        self.refresh_counts_button = QPushButton("רענן ספירות")
        self.refresh_counts_button.clicked.connect(
            self.refresh_gmail_counts
        )
        counts_title_row.addWidget(self.refresh_counts_button)

        counts_layout.addLayout(counts_title_row)

        self.counts_output = QPlainTextEdit()
        self.counts_output.setReadOnly(True)
        self.counts_output.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.counts_output.setMaximumHeight(190)

        counts_layout.addWidget(self.counts_output)

        self.counts_status_label = QLabel(
            "הספירות יוצגו כאן לפני התחלת ה-COPY."
        )
        self.counts_status_label.setObjectName("inputHint")
        counts_layout.addWidget(self.counts_status_label)

        layout.addWidget(counts_frame)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.output, 1)

        input_frame = QFrame()
        input_frame.setObjectName("inputFrame")

        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)
        input_layout.setSpacing(8)

        self.input_label = QLabel("קלט")
        self.input_label.setObjectName("inputLabel")
        input_layout.addWidget(self.input_label)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText(
            "המתן ל-Gmail COPY..."
        )
        self.input_edit.returnPressed.connect(self.send_input)
        input_row.addWidget(self.input_edit, 1)

        self.send_button = QPushButton("שלח")
        self.send_button.clicked.connect(self.send_input)
        input_row.addWidget(self.send_button)

        input_layout.addLayout(input_row)

        self.input_hint = QLabel(
            "שדה הקלט יופעל כאשר Gmail COPY יבקש נתונים."
        )
        self.input_hint.setObjectName("inputHint")
        input_layout.addWidget(self.input_hint)

        layout.addWidget(input_frame)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.close_button = QPushButton("סגור")
        self.close_button.clicked.connect(self.close)
        button_row.addWidget(self.close_button)

        layout.addLayout(button_row)

        self._disable_input_controls()

    def _append_output(self, text):
        if not text:
            return

        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        self.output.setTextCursor(cursor)
        self.output.insertPlainText(text)
        self.output.ensureCursorVisible()

    def _enable_text_input(self, label, hint):
        self.input_label.setText(label)
        self.input_hint.setText(hint)

        self.input_edit.setEnabled(True)
        self.send_button.setEnabled(True)

        self.input_edit.setFocus()
        self.input_edit.activateWindow()

    def _disable_input_controls(self):
        self.input_edit.setEnabled(False)
        self.send_button.setEnabled(False)

    def _get_database_account(self):
        conn = DatabaseConnection().connect()

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id
                    FROM gmail_accounts
                    WHERE LOWER(email) = LOWER(%s)
                    LIMIT 1
                    """,
                    (DEFAULT_GMAIL_ACCOUNT,),
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

    def _load_selected_gmail_labels_for_counts(self):
        gmail_account_id = self._get_database_account()

        conn = DatabaseConnection().connect()

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
                    (gmail_account_id,),
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

    def _count_gmail_label_messages(self, service, label_id):
        response = (
            service.users()
            .labels()
            .get(
                userId="me",
                id=label_id,
            )
            .execute()
        )

        return int(response.get("messagesTotal", 0))

    def refresh_gmail_counts(self):
        if self.gmail_counting:
            return

        if (
            self.process is not None
            and self.process.state()
            != QProcess.ProcessState.NotRunning
        ):
            self.counts_status_label.setText(
                "לא ניתן לרענן את הספירות בזמן ש-Gmail COPY פעיל."
            )
            return

        self.gmail_counting = True
        self.gmail_counts_loaded = False

        self.refresh_counts_button.setEnabled(False)
        self.counts_output.clear()

        self.counts_status_label.setText(
            "מתחבר ל-Gmail וקורא את מספר המיילים בכל תגית..."
        )

        QApplication.processEvents()

        try:
            labels = self._load_selected_gmail_labels_for_counts()

            if not labels:
                self.counts_output.setPlainText(
                    "לא נמצאו תגיות שנבחרו ב'ניהול חשבונות Gmail'."
                )

                self.counts_status_label.setText(
                    "אין תגיות פעילות שנבחרו לייבוא."
                )

                return

            connection = GmailConnection(DEFAULT_GMAIL_ACCOUNT)

            result = connection.connect(DEFAULT_GMAIL_ACCOUNT)

            if result is False:
                raise RuntimeError("Gmail connection failed.")

            service = connection.service

            if service is None:
                raise RuntimeError("Gmail service was not created.")

            self.gmail_service = service
            self.gmail_labels = labels

            lines = []
            total_messages_across_labels = 0

            for index, label in enumerate(labels, 1):
                label_id = label["label_id"]
                label_name = label["label_name"]

                try:
                    count = self._count_gmail_label_messages(
                        service,
                        label_id,
                    )

                    total_messages_across_labels += count

                    lines.append(
                        f"{index:3}. "
                        f"{label_name}    "
                        f"{count:,} מיילים"
                    )

                except Exception as exc:
                    lines.append(
                        f"{index:3}. "
                        f"{label_name}    "
                        f"[שגיאה: {exc}]"
                    )

            lines.append("")
            lines.append("----------------------------------------")
            lines.append(
                "סה\"כ לפי תגיות: "
                f"{total_messages_across_labels:,} מיילים"
            )
            lines.append(
                "הסכום אינו בהכרח מספר מיילים ייחודיים, "
                "מפני שמייל יכול להופיע ביותר מתגית אחת."
            )

            self.counts_output.setPlainText("\n".join(lines))

            self.gmail_counts_loaded = True

            self.counts_status_label.setText(
                "הספירות התקבלו מ-Gmail. "
                "אפשר עכשיו להתחיל את ה-COPY."
            )

            self.status_label.setText(
                "מספרי המיילים בתגיות נטענו בהצלחה."
            )

        except Exception as exc:
            self.gmail_counts_loaded = False

            self.counts_output.setPlainText(
                "לא ניתן היה לקבל את מספרי המיילים מ-Gmail.\n\n"
                f"{type(exc).__name__}: {exc}"
            )

            self.counts_status_label.setText(
                "שגיאה בקבלת ספירות Gmail."
            )

            QMessageBox.warning(
                self,
                "ספירת מיילים",
                "לא ניתן היה לקבל את מספר המיילים "
                "מהתגיות ב-Gmail.\n\n"
                f"{type(exc).__name__}: {exc}\n\n"
                "ניתן לנסות שוב באמצעות 'רענן ספירות'.",
            )

        finally:
            self.gmail_counting = False
            self.refresh_counts_button.setEnabled(True)

    def _get_latest_prompt(self):
        text = self.output.toPlainText()

        if not text:
            return None

        lower_text = text.lower()

        label_prompts = (
            "labels להעתקה:",
            "labels להעתקה",
            "labels to copy:",
            "labels to copy",
            "label numbers:",
            "label numbers",
            "enter label numbers",
            "select labels",
            "selected labels",
            "labels for copy",
        )

        confirmation_prompts = (
            "להמשיך ל-copy?",
            "להמשיך ל-copy",
            "הקלד yes",
            "yes לאישור",
            "type yes to continue",
            "yes to continue",
            "continue? yes",
            "continue? type yes",
        )

        candidates = []

        for prompt in label_prompts:
            position = lower_text.rfind(prompt.lower())

            if position >= 0:
                candidates.append(
                    (
                        position,
                        "labels",
                        prompt,
                    )
                )

        for prompt in confirmation_prompts:
            position = lower_text.rfind(prompt.lower())

            if position >= 0:
                candidates.append(
                    (
                        position,
                        "confirmation",
                        prompt,
                    )
                )

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0])

        return candidates[-1]

    def _check_for_input_prompt(self):
        if self.process is None:
            return

        if self.process.state() == QProcess.NotRunning:
            return

        latest_prompt = self._get_latest_prompt()

        if latest_prompt is None:
            return

        position, prompt_type, prompt_text = latest_prompt

        prompt_signature = (
            f"{prompt_type}:{position}:{prompt_text}"
        )

        if prompt_signature == self.last_handled_prompt:
            return

        if prompt_type == "labels":
            if self.awaiting_label_input:
                return

            self.last_handled_prompt = prompt_signature
            self.prompt_generation += 1

            self.awaiting_label_input = True
            self.awaiting_copy_confirmation = False

            self._enable_text_input(
                "מספרי התגיות להעתקה",
                "לדוגמה: 1,4,7 או 1-3,7. לאחר מכן לחץ שלח.",
            )

            self.status_label.setText(
                "ממתין לבחירת תגיות..."
            )

            return

        if prompt_type == "confirmation":
            if self.awaiting_copy_confirmation:
                return

            self.last_handled_prompt = prompt_signature
            self.prompt_generation += 1

            self.awaiting_label_input = False
            self.awaiting_copy_confirmation = True

            self._enable_text_input(
                "אישור ביצוע הייבוא",
                "הקלד YES כדי להמשיך או NO כדי לבטל.",
            )

            self.status_label.setText(
                "ממתין לאישור YES..."
            )

    def _validate_label_selection(self, text):
        value = text.strip()

        if not value:
            return False

        if value.upper() == "ALL":
            return True

        if value == "0":
            return True

        pattern = (
            r"^\d+(?:\s*-\s*\d+)?"
            r"(?:\s*,\s*\d+(?:\s*-\s*\d+)?)*$"
        )

        return re.fullmatch(pattern, value) is not None

    def send_input(self):
        if self.process is None:
            QMessageBox.warning(
                self,
                "Gmail COPY",
                "תהליך Gmail COPY אינו פעיל.",
            )
            return

        if self.process.state() == QProcess.NotRunning:
            QMessageBox.warning(
                self,
                "Gmail COPY",
                "תהליך Gmail COPY אינו פעיל.",
            )
            return

        text = self.input_edit.text().strip()

        if not text:
            return

        if self.awaiting_label_input:
            if not self._validate_label_selection(text):
                QMessageBox.warning(
                    self,
                    "קלט לא תקין",
                    "יש להזין מספרי תגיות בצורה הבאה:\n\n"
                    "1,4,7\n"
                    "או\n"
                    "1-3,7\n\n"
                    "אפשר גם ALL או 0.",
                )

                self.input_edit.selectAll()
                self.input_edit.setFocus()
                return

            self.send_text(text)

            self.awaiting_label_input = False
            self.awaiting_copy_confirmation = False

            self.input_edit.clear()
            self._disable_input_controls()

            self.status_label.setText(
                "בחירת התגיות נשלחה ל-Gmail COPY. "
                "ממתין לשלב האישור..."
            )

            return

        if self.awaiting_copy_confirmation:
            answer = text.upper()

            if answer not in ("YES", "NO"):
                QMessageBox.warning(
                    self,
                    "קלט לא תקין",
                    "יש להקליד YES או NO.",
                )

                self.input_edit.selectAll()
                self.input_edit.setFocus()
                return

            self.send_text(answer)

            self.awaiting_copy_confirmation = False
            self.awaiting_label_input = False

            self.input_edit.clear()
            self._disable_input_controls()

            if answer == "YES":
                self.status_label.setText(
                    "האישור YES נשלח. Gmail COPY מבצע את הייבוא..."
                )
            else:
                self.status_label.setText(
                    "הביטול NO נשלח ל-Gmail COPY."
                )

            return

        QMessageBox.information(
            self,
            "Gmail COPY",
            "כרגע Gmail COPY אינו מבקש קלט.",
        )

    def send_text(self, text):
        if self.process is None:
            return

        if self.process.state() == QProcess.NotRunning:
            return

        data = (text + "\n").encode("utf-8")

        self.process.write(data)
        self.process.waitForBytesWritten(2000)

        self._append_output(
            f"\n[GUI INPUT] {text}\n"
        )

    def _create_process_environment(self):
        environment = QProcessEnvironment.systemEnvironment()

        existing_pythonpath = environment.value(
            "PYTHONPATH",
            "",
        )

        paths = [
            str(PROJECT_ROOT),
            str(SRC_ROOT),
        ]

        if existing_pythonpath:
            paths.append(existing_pythonpath)

        environment.insert(
            "PYTHONPATH",
            os.pathsep.join(paths),
        )

        environment.insert(
            "PYTHONUNBUFFERED",
            "1",
        )

        return environment

    def start(self):
        script = PROJECT_ROOT / "src" / "gmail" / "gmail_copy.py"

        if not script.exists():
            QMessageBox.critical(
                self,
                "שגיאה",
                f"קובץ Gmail COPY לא נמצא:\n{script}",
            )
            return

        self.process_finished = False

        self.awaiting_label_input = False
        self.awaiting_copy_confirmation = False

        self.last_handled_prompt = ""
        self.prompt_generation = 0

        self.output.clear()
        self.input_edit.clear()
        self._disable_input_controls()

        self.status_label.setText(
            "מפעיל Gmail COPY..."
        )

        self.close_button.setEnabled(False)

        self.process = QProcess(self)

        self.process.setProcessEnvironment(
            self._create_process_environment()
        )

        self.process.setWorkingDirectory(
            str(PROJECT_ROOT)
        )

        self.process.setProgram(sys.executable)

        self.process.setArguments(
            [
                "-u",
                str(script),
            ]
        )

        self.process.readyReadStandardOutput.connect(
            self._read_stdout
        )

        self.process.readyReadStandardError.connect(
            self._read_stderr
        )

        self.process.errorOccurred.connect(
            self._process_error
        )

        self.process.finished.connect(
            self._process_finished
        )

        self.process.start()

        if not self.process.waitForStarted(5000):
            QMessageBox.critical(
                self,
                "שגיאה",
                "לא ניתן להפעיל את Gmail COPY.",
            )

            self.close_button.setEnabled(True)

    def _read_stdout(self):
        if self.process is None:
            return

        data = bytes(
            self.process.readAllStandardOutput()
        )

        if not data:
            return

        text = data.decode(
            "utf-8",
            errors="replace",
        )

        self._append_output(text)

        QTimer.singleShot(
            0,
            self._check_for_input_prompt,
        )

    def _read_stderr(self):
        if self.process is None:
            return

        data = bytes(
            self.process.readAllStandardError()
        )

        if not data:
            return

        text = data.decode(
            "utf-8",
            errors="replace",
        )

        self._append_output(text)

        QTimer.singleShot(
            0,
            self._check_for_input_prompt,
        )

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            message = "לא ניתן להפעיל את Gmail COPY."
        else:
            message = f"שגיאת QProcess: {error}"

        self.status_label.setText(message)

        self._append_output(
            "\n[ERROR] "
            + message
            + "\n"
        )

        self.close_button.setEnabled(True)

    def _process_finished(self, exit_code, exit_status):
        self.process_finished = True

        self.awaiting_label_input = False
        self.awaiting_copy_confirmation = False

        self._disable_input_controls()

        if (
            exit_code == 0
            and exit_status == QProcess.ExitStatus.NormalExit
        ):
            self.status_label.setText(
                "Gmail COPY הסתיים בהצלחה."
            )
        else:
            self.status_label.setText(
                "Gmail COPY הסתיים עם שגיאה. "
                f"קוד: {exit_code}"
            )

        self.close_button.setEnabled(True)

    def closeEvent(self, event):
        if self.process is not None:
            if (
                self.process.state()
                != QProcess.ProcessState.NotRunning
            ):
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
# Drive / Local Comparison Report
# ----------------------------------------------------------------------

class ReportConnectionDialog(QDialog):
    """Authorize and test the external connections before running the report."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Alcalay - אישור חיבורי הדוח")
        self.setModal(True)
        self.resize(760, 560)
        self.setLayoutDirection(Qt.RightToLeft)

        self.drive_connection = None
        self.drive_service = None
        self.drive_repository = None
        self.gmail_connection = None
        self.gmail_service = None
        self.gmail_stats = {}
        self.drive_ok = False
        self.gmail_ok = False

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("אישור חיבורי Google לפני הפקת הדוח")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(title)

        info = QLabel(
            "לפני חישוב הסטטיסטיקות ניתן לאשר ולבדוק את שני החיבורים. "
            "הדוח הוא לקריאה בלבד ואינו מבצע סנכרון או העתקת קבצים."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        drive_frame = QFrame()
        drive_layout = QVBoxLayout(drive_frame)
        drive_layout.setContentsMargins(12, 12, 12, 12)
        drive_layout.setSpacing(7)

        self.drive_check = QLabel("☐ Google Drive — טרם אושר")
        self.drive_check.setStyleSheet("font-weight: bold;")
        drive_layout.addWidget(self.drive_check)

        self.drive_status = QLabel("לא בוצע חיבור ל-Google Drive.")
        self.drive_status.setWordWrap(True)
        drive_layout.addWidget(self.drive_status)

        self.drive_button = QPushButton("אשר וחבר ל-Google Drive")
        self.drive_button.clicked.connect(self.connect_drive)
        drive_layout.addWidget(self.drive_button)

        layout.addWidget(drive_frame)

        gmail_frame = QFrame()
        gmail_layout = QVBoxLayout(gmail_frame)
        gmail_layout.setContentsMargins(12, 12, 12, 12)
        gmail_layout.setSpacing(7)

        self.gmail_check = QLabel("☐ Gmail — טרם אושר")
        self.gmail_check.setStyleSheet("font-weight: bold;")
        gmail_layout.addWidget(self.gmail_check)

        self.gmail_status = QLabel("לא בוצע חיבור ל-Gmail.")
        self.gmail_status.setWordWrap(True)
        gmail_layout.addWidget(self.gmail_status)

        self.gmail_button = QPushButton("אשר וחבר ל-Gmail")
        self.gmail_button.clicked.connect(self.connect_gmail)
        gmail_layout.addWidget(self.gmail_button)

        layout.addWidget(gmail_frame)

        log_title = QLabel("מהלך החיבור")
        log_title.setStyleSheet("font-weight: bold;")
        layout.addWidget(log_title)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(150)
        layout.addWidget(self.log_output)

        self.progress = QProgressBar()
        self.progress.setRange(0, 2)
        self.progress.setValue(0)
        self.progress.setFormat("%v / %m")
        layout.addWidget(self.progress)

        buttons = QHBoxLayout()
        buttons.addStretch()

        self.cancel_button = QPushButton("ביטול")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)

        self.start_button = QPushButton("התחל הפקת דוח")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.accept)
        buttons.addWidget(self.start_button)

        layout.addLayout(buttons)

    def log(self, text):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.append(f"[{stamp}] {text}")
        self.log_output.moveCursor(QTextCursor.MoveOperation.End)
        QApplication.processEvents()

    def _update_ready_state(self):
        completed = int(self.drive_ok) + int(self.gmail_ok)
        self.progress.setValue(completed)
        self.start_button.setEnabled(self.drive_ok and self.gmail_ok)

    def connect_drive(self):
        self.drive_button.setEnabled(False)
        self.drive_status.setText("מתחבר ל-Google Drive...")
        self.log("מתחיל חיבור ל-Google Drive.")
        QApplication.processEvents()

        try:
            self.drive_connection = DriveConnection(
                account_email=DEFAULT_GMAIL_ACCOUNT
            )
            self.log(
                f"מבצע OAuth / חיבור לחשבון: {DEFAULT_GMAIL_ACCOUNT}"
            )
            self.drive_connection.connect()
            self.drive_service = self.drive_connection.service

            if self.drive_service is None:
                raise RuntimeError(
                    "Google Drive service was not created."
                )

            self.log("חיבור ל-Google Drive הצליח.")
            self.log("קורא את מבנה המאגר Alcalay...")
            self.drive_repository = (
                self.drive_connection.get_repository_folder_ids()
            )

            self.drive_ok = True
            self.drive_check.setText("☑ Google Drive — אושר ומחובר")
            self.drive_status.setText(
                "החיבור הצליח ומבנה המאגר Alcalay זמין."
            )
            self.log("מבנה המאגר Alcalay התקבל בהצלחה.")

        except Exception as exc:
            self.drive_ok = False
            self.drive_check.setText("☐ Google Drive — החיבור נכשל")
            self.drive_status.setText(
                f"שגיאה: {type(exc).__name__}: {exc}"
            )
            self.log(
                f"שגיאה בחיבור ל-Google Drive: "
                f"{type(exc).__name__}: {exc}"
            )
            QMessageBox.critical(
                self,
                "חיבור ל-Google Drive",
                "החיבור ל-Google Drive נכשל.\n\n"
                f"{type(exc).__name__}: {exc}",
            )
        finally:
            self.drive_button.setEnabled(True)
            self._update_ready_state()

    def _get_database_account(self):
        conn = DatabaseConnection().connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id
                    FROM gmail_accounts
                    WHERE LOWER(email) = LOWER(%s)
                    LIMIT 1
                    """,
                    (DEFAULT_GMAIL_ACCOUNT,),
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

    def _load_selected_gmail_labels(self):
        account_id = self._get_database_account()
        conn = DatabaseConnection().connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT label_id, label_name
                    FROM gmail_labels
                    WHERE gmail_account_id = %s
                      AND selected_for_sync = TRUE
                      AND enabled = TRUE
                    ORDER BY id
                    """,
                    (account_id,),
                )
                return cursor.fetchall()
        finally:
            conn.close()

    def connect_gmail(self):
        self.gmail_button.setEnabled(False)
        self.gmail_status.setText("מתחבר ל-Gmail...")
        self.log("מתחיל חיבור ל-Gmail.")
        QApplication.processEvents()

        try:
            self.gmail_connection = GmailConnection(
                DEFAULT_GMAIL_ACCOUNT
            )
            self.log(
                f"מבצע OAuth / חיבור לחשבון: {DEFAULT_GMAIL_ACCOUNT}"
            )
            result = self.gmail_connection.connect(
                DEFAULT_GMAIL_ACCOUNT
            )
            if result is False:
                raise RuntimeError("Gmail connection failed.")

            self.gmail_service = self.gmail_connection.service
            if self.gmail_service is None:
                raise RuntimeError("Gmail service was not created.")

            self.log("חיבור ל-Gmail הצליח.")
            self.log("קורא את התגיות שנבחרו ב-PostgreSQL...")

            labels = self._load_selected_gmail_labels()
            stats = []
            total = 0

            for index, (label_id, label_name) in enumerate(labels, 1):
                self.log(
                    f"סופר Gmail Label {index}/{len(labels)}: "
                    f"{label_name}"
                )
                response = (
                    self.gmail_service.users()
                    .labels()
                    .get(userId="me", id=label_id)
                    .execute()
                )
                count = int(response.get("messagesTotal", 0))
                total += count
                stats.append(
                    {
                        "label_id": label_id,
                        "label_name": label_name,
                        "messages": count,
                    }
                )
                QApplication.processEvents()

            self.gmail_stats = {
                "account": DEFAULT_GMAIL_ACCOUNT,
                "selected_labels": stats,
                "selected_label_message_total": total,
            }

            self.gmail_ok = True
            self.gmail_check.setText("☑ Gmail — אושר ומחובר")
            self.gmail_status.setText(
                f"החיבור הצליח. {len(stats)} תגיות נבחרות; "
                f"סה\"כ לפי תגיות: {total:,} מיילים."
            )
            self.log(
                f"Gmail מוכן. נמצאו {len(stats)} תגיות נבחרות "
                f"ו-{total:,} מיילים לפי תגיות."
            )

        except Exception as exc:
            self.gmail_ok = False
            self.gmail_check.setText("☐ Gmail — החיבור נכשל")
            self.gmail_status.setText(
                f"שגיאה: {type(exc).__name__}: {exc}"
            )
            self.log(
                f"שגיאה בחיבור ל-Gmail: "
                f"{type(exc).__name__}: {exc}"
            )
            QMessageBox.critical(
                self,
                "חיבור ל-Gmail",
                "החיבור ל-Gmail נכשל.\n\n"
                f"{type(exc).__name__}: {exc}",
            )
        finally:
            self.gmail_button.setEnabled(True)
            self._update_ready_state()


class DriveLocalComparisonPage(QWidget):
    """Compare local storage with Google Drive and live Gmail statistics."""

    LOCAL_ROOT = PROJECT_ROOT / "storage"

    LOCAL_FOLDERS = (
        "office",
        "pdf",
        "media",
        "gmail",
        "drive",
    )

    DRIVE_DOCUMENT_FOLDERS = (
        "office",
        "pdf",
        "media",
        "drive",
    )

    DRIVE_GMAIL_FOLDER = "gmail"
    DRIVE_GMAIL_ACCOUNT = DEFAULT_GMAIL_ACCOUNT
    GOOGLE_FOLDER_MIME = "application/vnd.google-apps.folder"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.RightToLeft)
        self.drive_connection = None
        self.drive = None
        self.gmail_connection = None
        self.gmail_service = None
        self.gmail_stats = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("דוח השוואת נפחי מאגרים")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        description = QLabel(
            "השוואת מספר הקבצים והנפח בכל ספרייה באחסון המקומי "
            "לעומת הספרייה המקבילה ב-Google Drive, ובנוסף הצגת "
            "סטטיסטיקת Gmail לפי התגיות שנבחרו ב-PostgreSQL. "
            "הבדיקה היא לקריאה בלבד ואינה מבצעת סנכרון."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.status_label = QLabel("מוכן להפקת הדוח.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        layout.addWidget(self.progress)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "ספרייה",
            "Local קבצים",
            "Local נפח",
            "Drive קבצים",
            "Drive נפח",
            "הפרש קבצים",
            "הפרש נפח",
            "מצב",
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        output_title = QLabel("מהלך הדוח / שגיאות")
        output_title.setStyleSheet("font-weight: bold;")
        layout.addWidget(output_title)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumHeight(220)
        self.output.setPlaceholderText(
            "כאן יוצגו שלבי הסריקה, החיבור ל-Drive ול-Gmail, "
            "תוצאות ושגיאות."
        )
        layout.addWidget(self.output)

        buttons = QHBoxLayout()

        self.start_button = QPushButton("הפק דוח")
        self.start_button.clicked.connect(self.generate_report)
        buttons.addWidget(self.start_button)

        self.refresh_button = QPushButton("רענן")
        self.refresh_button.clicked.connect(self.generate_report)
        buttons.addWidget(self.refresh_button)

        buttons.addStretch()
        layout.addLayout(buttons)

    def log(self, text):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.output.append(f"[{stamp}] {text}")
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        QApplication.processEvents()

    def set_progress(self, value, message=None):
        self.progress.setValue(max(0, min(100, int(value))))
        if message:
            self.status_label.setText(message)
            self.log(message)
        QApplication.processEvents()

    @staticmethod
    def format_size(size):
        """Return every volume in GB so Local and Drive use one unit."""
        size = int(size or 0)
        gigabytes = size / (1024 ** 3)
        return f"{gigabytes:,.2f} GB"

    @staticmethod
    def empty_stats():
        return {"files": 0, "bytes": 0}

    def _scan_local_folder(self, root):
        stats = {}
        root = Path(root)
        if not root.exists():
            return stats

        for directory in [root] + [p for p in root.rglob("*") if p.is_dir()]:
            try:
                relative = directory.relative_to(root)
            except ValueError:
                relative = Path()

            key = "/".join(relative.parts) if relative.parts else "."
            files = 0
            total_bytes = 0

            try:
                for item in directory.iterdir():
                    if not item.is_file():
                        continue
                    try:
                        files += 1
                        total_bytes += item.stat().st_size
                    except OSError:
                        pass
            except OSError:
                pass

            stats[key] = {
                "files": files,
                "bytes": total_bytes,
            }
            QApplication.processEvents()

        return stats

    def _list_drive_children(self, parent_id):
        page_token = None
        while True:
            self.log(f"קורא תוכן Drive של folder id={parent_id}")
            response = (
                self.drive.files()
                .list(
                    q=f"'{parent_id}' in parents and trashed = false",
                    fields="nextPageToken,files(id,name,mimeType,size)",
                    pageSize=1000,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )

            for item in response.get("files", []):
                yield item

            page_token = response.get("nextPageToken")
            if not page_token:
                break

    def _find_child_folder(self, parent_id, folder_name):
        wanted = folder_name.strip().lower()
        self.log(f"מחפש Drive folder: {folder_name}")
        for item in self._list_drive_children(parent_id):
            if item.get("mimeType") != self.GOOGLE_FOLDER_MIME:
                continue
            if str(item.get("name", "")).strip().lower() == wanted:
                self.log(
                    f"נמצאה ספרייה ב-Drive: {folder_name} "
                    f"({item.get('id', '')})"
                )
                return item
        self.log(f"ספריית Drive לא נמצאה: {folder_name}")
        return None

    def _scan_drive_folder(self, folder_id):
        stats = {}

        def walk(current_id, relative_parts):
            key = "/".join(relative_parts) if relative_parts else "."
            stats.setdefault(key, self.empty_stats())

            for item in self._list_drive_children(current_id):
                mime = item.get("mimeType", "")
                if mime == self.GOOGLE_FOLDER_MIME:
                    walk(
                        current_id=item["id"],
                        relative_parts=relative_parts + [
                            item.get("name", "")
                        ],
                    )
                else:
                    stats[key]["files"] += 1
                    try:
                        stats[key]["bytes"] += int(item.get("size") or 0)
                    except (TypeError, ValueError):
                        pass
                QApplication.processEvents()

        walk(folder_id, [])
        return stats

    def _connect_drive(self):
        self.log("מתחיל חיבור ל-Google Drive...")
        self.log(f"חשבון Drive: {DEFAULT_GMAIL_ACCOUNT}")
        self.drive_connection = DriveConnection(
            account_email=DEFAULT_GMAIL_ACCOUNT
        )
        self.drive_connection.connect()
        self.drive = self.drive_connection.service
        if self.drive is None:
            raise RuntimeError("Google Drive service was not created.")
        self.log("חיבור ל-Google Drive הצליח.")
        repository = self.drive_connection.get_repository_folder_ids()
        self.log("מבנה המאגר Alcalay התקבל.")
        return repository

    def _add_rows(self, name, local_stats, drive_stats):
        keys = sorted(set(local_stats) | set(drive_stats))
        for relative in keys:
            local = local_stats.get(relative, self.empty_stats())
            drive = drive_stats.get(relative, self.empty_stats())

            local_files = int(local["files"])
            local_bytes = int(local["bytes"])
            drive_files = int(drive["files"])
            drive_bytes = int(drive["bytes"])

            if local_files == drive_files and local_bytes == drive_bytes:
                state = "זהה"
            elif local_files == 0 and drive_files > 0:
                state = "קיים רק ב-Drive"
            elif drive_files == 0 and local_files > 0:
                state = "קיים רק ב-Local"
            else:
                state = "קיים פער"

            relative_path = "" if relative == "." else f"/{relative}"

            # Show the complete physical/repository path instead of the
            # short internal folder key.  This makes it immediately clear
            # which Local directory is compared with which Drive directory.
            local_path = f"storage/{name}{relative_path}"

            if name == "gmail":
                drive_path = (
                    f"Alcalay/gmail/{self.DRIVE_GMAIL_ACCOUNT}"
                    f"{relative_path}"
                )
            else:
                drive_path = (
                    f"Alcalay/Documents/{name}{relative_path}"
                )

            display_name = (
                f"Local: {local_path}\n"
                f"Drive: {drive_path}"
            )

            row = self.table.rowCount()
            self.table.insertRow(row)

            values = [
                display_name,
                f"{local_files:,}",
                self.format_size(local_bytes),
                f"{drive_files:,}",
                self.format_size(drive_bytes),
                f"{drive_files - local_files:+,}",
                self.format_size(drive_bytes - local_bytes),
                state,
            ]

            for column, value in enumerate(values):
                self.table.setItem(
                    row,
                    column,
                    QTableWidgetItem(str(value)),
                )

    def _open_connection_dialog(self):
        dialog = ReportConnectionDialog(self)
        result = dialog.exec()
        if result != QDialog.DialogCode.Accepted:
            self.status_label.setText(
                "הפקת הדוח בוטלה — לא אושרו שני החיבורים."
            )
            self.log(
                "הפקת הדוח בוטלה לפני התחלת הסריקה."
            )
            return None

        self.drive_connection = dialog.drive_connection
        self.drive = dialog.drive_service
        self.gmail_connection = dialog.gmail_connection
        self.gmail_service = dialog.gmail_service
        self.gmail_stats = dialog.gmail_stats
        return dialog.drive_repository

    def generate_report(self):
        self.start_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        self.table.setRowCount(0)
        self.output.clear()
        self.progress.setValue(0)

        try:
            self.log("=" * 70)
            self.log("התחלת הפקת דוח השוואת נפחים ומספרי קבצים.")
            self.log(
                "לפני הסריקה יש לאשר חיבור ל-Google Drive ול-Gmail."
            )

            repository = self._open_connection_dialog()
            if repository is None:
                return

            self.set_progress(5, "החיבורים אושרו. מתחיל סריקת Local...")

            local = {}
            local_count = len(self.LOCAL_FOLDERS)
            for index, folder_name in enumerate(self.LOCAL_FOLDERS, 1):
                self.set_progress(
                    5 + int(index / local_count * 30),
                    f"סורק Local: {folder_name}...",
                )
                local[folder_name] = self._scan_local_folder(
                    self.LOCAL_ROOT / folder_name
                )
                files = sum(
                    item["files"]
                    for item in local[folder_name].values()
                )
                bytes_total = sum(
                    item["bytes"]
                    for item in local[folder_name].values()
                )
                self.log(
                    f"Local {folder_name}: {files:,} קבצים / "
                    f"{self.format_size(bytes_total)}"
                )

            documents_id = repository["documents_folder_id"]
            gmail_id = repository["gmail_folder_id"]
            drive = {}

            drive_count = len(self.DRIVE_DOCUMENT_FOLDERS)
            for index, folder_name in enumerate(
                self.DRIVE_DOCUMENT_FOLDERS,
                1,
            ):
                self.set_progress(
                    35 + int(index / (drive_count + 1) * 35),
                    f"סורק Drive: Documents/{folder_name}...",
                )
                folder = self._find_child_folder(
                    documents_id,
                    folder_name,
                )
                drive[folder_name] = (
                    self._scan_drive_folder(folder["id"])
                    if folder
                    else {}
                )
                files = sum(
                    item["files"]
                    for item in drive[folder_name].values()
                )
                bytes_total = sum(
                    item["bytes"]
                    for item in drive[folder_name].values()
                )
                self.log(
                    f"Drive {folder_name}: {files:,} קבצים / "
                    f"{self.format_size(bytes_total)}"
                )

            self.set_progress(70, "סורק Drive: Gmail...")
            # The actual Drive structure is:
            # Alcalay/gmail/<account>/{messages,attachments,copy_audit}
            # so compare the account folder itself, not a shortened
            # intermediate name.  A fallback to the old layout is kept for
            # existing repositories.
            gmail_folder = self._find_child_folder(
                gmail_id,
                self.DRIVE_GMAIL_ACCOUNT,
            )
            if gmail_folder is None:
                gmail_folder = self._find_child_folder(
                    gmail_id,
                    self.DRIVE_GMAIL_FOLDER,
                )

            drive["gmail"] = (
                self._scan_drive_folder(gmail_folder["id"])
                if gmail_folder
                else {}
            )

            gmail_drive_files = sum(
                item["files"]
                for item in drive["gmail"].values()
            )
            gmail_drive_bytes = sum(
                item["bytes"]
                for item in drive["gmail"].values()
            )
            self.log(
                f"Drive Gmail: {gmail_drive_files:,} קבצים / "
                f"{self.format_size(gmail_drive_bytes)}"
            )

            self.set_progress(80, "בונה טבלת השוואה...")
            for folder_name in self.LOCAL_FOLDERS:
                self._add_rows(
                    folder_name,
                    local[folder_name],
                    drive[folder_name],
                )

            local_total_files = sum(
                item["files"]
                for folder in local.values()
                for item in folder.values()
            )
            local_total_bytes = sum(
                item["bytes"]
                for folder in local.values()
                for item in folder.values()
            )
            drive_total_files = sum(
                item["files"]
                for folder in drive.values()
                for item in folder.values()
            )
            drive_total_bytes = sum(
                item["bytes"]
                for folder in drive.values()
                for item in folder.values()
            )

            gmail_selected_total = int(
                self.gmail_stats.get(
                    "selected_label_message_total",
                    0,
                )
                or 0
            )
            gmail_label_count = len(
                self.gmail_stats.get("selected_labels", [])
            )

            self.set_progress(90, "שומר את הדוח ב-Local...")

            generated_at = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            report_dir = PROJECT_ROOT / "storage" / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / (
                "drive_local_comparison_"
                + datetime.now().strftime("%Y%m%d_%H%M%S")
                + ".json"
            )

            report = {
                "generated_at": generated_at,
                "account": DEFAULT_GMAIL_ACCOUNT,
                "local_total": {
                    "files": local_total_files,
                    "bytes": local_total_bytes,
                },
                "drive_total": {
                    "files": drive_total_files,
                    "bytes": drive_total_bytes,
                },
                "gmail_live": self.gmail_stats,
                "folders": {
                    folder: {
                        "local": local[folder],
                        "drive": drive[folder],
                    }
                    for folder in self.LOCAL_FOLDERS
                },
            }

            report_path.write_text(
                json.dumps(
                    report,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            self.set_progress(100, "הדוח הושלם בהצלחה.")
            self.log("=" * 70)
            self.log(f"Local: {local_total_files:,} קבצים / {self.format_size(local_total_bytes)}")
            self.log(f"Drive: {drive_total_files:,} קבצים / {self.format_size(drive_total_bytes)}")
            self.log(
                f"Gmail: {gmail_label_count:,} תגיות נבחרות / "
                f"{gmail_selected_total:,} מיילים לפי תגיות"
            )
            self.log(f"הדוח נשמר ב: {report_path}")

        except Exception as exc:
            self.status_label.setText("הפקת הדוח נכשלה.")
            self.log(
                f"שגיאה: {type(exc).__name__}: {exc}"
            )
            QMessageBox.critical(
                self,
                "דוח השוואת נפחי מאגרים",
                "לא ניתן להפיק את הדוח:\n\n"
                f"{type(exc).__name__}: {exc}",
            )

        finally:
            self.start_button.setEnabled(True)
            self.refresh_button.setEnabled(True)

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
            "חיפוש",
            "    חיפוש כללי",
            "    חיפוש במאגר מקומי",
            "    חיפוש ב-Google Drive",
            "    חיפוש ב-Gmail",
            "    חיפוש לפי קטגוריות",
            "    חיפוש AI",
            "    מילון תזאורוס",
            "מערכת",
            "    ניהול Gmail",
            "    ייבוא מיילים מ-Gmail",
            "    דוח השוואת נפחי מאגרים",
            "    ניהול קטגוריות",
            "    מסד הנתונים",
            "    הגדרות",
        ]

        for item_text in menu_items:
            item = QListWidgetItem(item_text)
            if item_text in ("חיפוש", "מערכת"):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.menu.addItem(item)

        root_layout.addWidget(
            self.menu
        )

        self.stack = QStackedWidget()
        root_layout.addWidget(
            self.stack
        )

        self.add_page(
            "חיפוש כללי",
            PlaceholderPage("חיפוש כללי", self),
        )
        self.add_page(
            "חיפוש במאגר מקומי",
            PlaceholderPage("חיפוש במאגר מקומי", self),
        )
        self.add_page(
            "חיפוש ב-Google Drive",
            PlaceholderPage("חיפוש ב-Google Drive", self),
        )
        self.add_page(
            "חיפוש ב-Gmail",
            PlaceholderPage("חיפוש ב-Gmail", self),
        )
        self.add_page(
            "חיפוש לפי קטגוריות",
            PlaceholderPage("חיפוש לפי קטגוריות", self),
        )
        self.add_page(
            "חיפוש AI",
            PlaceholderPage("חיפוש AI", self),
        )
        self.add_page(
            "מילון תזאורוס",
            PlaceholderPage("מילון תזאורוס", self),
        )
        self.add_page(
            "ניהול Gmail",
            GmailWindow(self),
        )
        self.add_page(
            "ייבוא מיילים מ-Gmail",
            GmailImportWindow(self),
        )
        self.add_page(
            "דוח השוואת נפחי מאגרים",
            DriveLocalComparisonPage(self),
        )
        self.add_page(
            "ניהול קטגוריות",
            PlaceholderPage("ניהול קטגוריות", self),
        )
        self.add_page(
            "מסד הנתונים",
            PlaceholderPage("מסד הנתונים", self),
        )
        self.add_page(
            "הגדרות",
            PlaceholderPage("הגדרות", self),
        )

        self.menu.currentRowChanged.connect(
            self.change_page
        )

        self.menu.setCurrentRow(
            1
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

        name = item.text().strip()

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