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
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.database.connection import DatabaseConnection
from src.gmail.gmail_connection import GmailConnection
from src.gmail.gmail_window import GmailWindow
from src.search.search_window import SearchWindow


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

DEFAULT_GMAIL_ACCOUNT = "frank.avner@gmail.com"

DIRECTION_DRIVE_TO_LOCAL = "DRIVE_TO_LOCAL"
DIRECTION_LOCAL_TO_DRIVE = "LOCAL_TO_DRIVE"

MENU_ITEMS = [
    (1, "Google"),
    (2, "מסמכים"),
    (3, "חיפוש"),
    (4, "משתמשים והרשאות"),
    (5, "מסד נתונים"),
    (6, "הורדה מקומית"),
    (7, "OCR"),
    (8, "AI / ML"),
    (9, "אבטחה"),
    (10, "רענון והוספת מסמכים מהמייל"),
]


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


class GmailIndexWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(
            "Alcalay - אינדוקס מיילים"
        )
        self.setWindowModality(Qt.NonModal)
        self.resize(1000, 650)

        self.parser_process = None
        self.indexer_process = None
        self.stopping = False

        self.account = DEFAULT_GMAIL_ACCOUNT

        self.parser_script = (
            PROJECT_ROOT
            / "src"
            / "gmail"
            / "gmail_parser.py"
        )

        self.indexer_script = (
            PROJECT_ROOT
            / "src"
            / "gmail"
            / "gmail_indexer.py"
        )

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            20,
            20,
            20,
            20,
        )

        layout.setSpacing(12)

        title = QLabel(
            "אינדוקס מיילים מ-Gmail"
        )

        title.setObjectName(
            "windowTitle"
        )

        layout.addWidget(title)

        self.status_label = QLabel(
            "מוכן"
        )

        self.status_label.setObjectName(
            "statusLabel"
        )

        layout.addWidget(
            self.status_label
        )

        self.output = QPlainTextEdit()

        self.output.setReadOnly(True)

        self.output.setLineWrapMode(
            QPlainTextEdit.NoWrap
        )

        layout.addWidget(
            self.output,
            1,
        )

        button_row = QHBoxLayout()

        self.start_button = QPushButton(
            "התחל אינדוקס"
        )

        self.start_button.clicked.connect(
            self.start
        )

        button_row.addWidget(
            self.start_button
        )

        self.stop_button = QPushButton(
            "עצור"
        )

        self.stop_button.clicked.connect(
            self.stop
        )

        self.stop_button.setEnabled(
            False
        )

        button_row.addWidget(
            self.stop_button
        )

        button_row.addStretch()

        self.close_button = QPushButton(
            "סגור"
        )

        self.close_button.clicked.connect(
            self.close
        )

        button_row.addWidget(
            self.close_button
        )

        layout.addLayout(
            button_row
        )

    def _append_output(self, text):
        if not text:
            return

        cursor = self.output.textCursor()

        cursor.movePosition(
            QTextCursor.MoveOperation.End
        )

        self.output.setTextCursor(
            cursor
        )

        self.output.insertPlainText(
            text
        )

        self.output.ensureCursorVisible()

    def _create_process_environment(self):
        environment = (
            QProcessEnvironment.systemEnvironment()
        )

        existing_pythonpath = (
            environment.value(
                "PYTHONPATH",
                "",
            )
        )

        paths = [
            str(PROJECT_ROOT),
            str(SRC_ROOT),
        ]

        if existing_pythonpath:
            paths.append(
                existing_pythonpath
            )

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
        if (
            self.parser_process is not None
            and self.parser_process.state()
            != QProcess.ProcessState.NotRunning
        ):
            return

        if (
            self.indexer_process is not None
            and self.indexer_process.state()
            != QProcess.ProcessState.NotRunning
        ):
            return

        if not self.parser_script.exists():
            QMessageBox.critical(
                self,
                "שגיאה",
                "קובץ Gmail Parser לא נמצא:\n"
                f"{self.parser_script}",
            )
            return

        if not self.indexer_script.exists():
            QMessageBox.critical(
                self,
                "שגיאה",
                "קובץ Gmail Indexer לא נמצא:\n"
                f"{self.indexer_script}",
            )
            return

        self.stopping = False

        self.output.clear()

        self.start_button.setEnabled(
            False
        )

        self.stop_button.setEnabled(
            True
        )

        self.close_button.setEnabled(
            False
        )

        self.status_label.setText(
            "שלב 1/2: מבצע PARSE למיילים..."
        )

        self.start_parser()

    def start_parser(self):
        self.parser_process = QProcess(
            self
        )

        self.parser_process.setProcessEnvironment(
            self._create_process_environment()
        )

        self.parser_process.setWorkingDirectory(
            str(PROJECT_ROOT)
        )

        self.parser_process.setProgram(
            sys.executable
        )

        self.parser_process.setArguments(
            [
                "-u",
                str(self.parser_script),
                "--account",
                self.account,
            ]
        )

        self.parser_process.readyReadStandardOutput.connect(
            self._read_parser_stdout
        )

        self.parser_process.readyReadStandardError.connect(
            self._read_parser_stderr
        )

        self.parser_process.errorOccurred.connect(
            self._parser_error
        )

        self.parser_process.finished.connect(
            self._parser_finished
        )

        self.parser_process.start()

        if not self.parser_process.waitForStarted(
            5000
        ):
            self._parser_error(
                QProcess.ProcessError.FailedToStart
            )

    def _read_parser_stdout(self):
        if self.parser_process is None:
            return

        data = bytes(
            self.parser_process.readAllStandardOutput()
        )

        if not data:
            return

        self._append_output(
            data.decode(
                "utf-8",
                errors="replace",
            )
        )

    def _read_parser_stderr(self):
        if self.parser_process is None:
            return

        data = bytes(
            self.parser_process.readAllStandardError()
        )

        if not data:
            return

        self._append_output(
            data.decode(
                "utf-8",
                errors="replace",
            )
        )

    def _parser_error(self, error):
        if self.stopping:
            return

        self.status_label.setText(
            f"שגיאת Gmail Parser: {error}"
        )

        QMessageBox.critical(
            self,
            "שגיאה",
            "לא ניתן להפעיל את Gmail Parser.\n\n"
            f"שגיאה: {error}",
        )

        self.start_button.setEnabled(
            True
        )

        self.stop_button.setEnabled(
            False
        )

        self.close_button.setEnabled(
            True
        )

    def _parser_finished(
        self,
        exit_code,
        exit_status,
    ):
        if self.stopping:
            return

        if (
            exit_status != QProcess.ExitStatus.NormalExit
            or exit_code != 0
        ):
            self.status_label.setText(
                "Gmail Parser נכשל. "
                f"קוד: {exit_code}"
            )

            self.start_button.setEnabled(
                True
            )

            self.stop_button.setEnabled(
                False
            )

            self.close_button.setEnabled(
                True
            )

            return

        self.status_label.setText(
            "שלב 2/2: מבצע INDEX..."
        )

        self._append_output(
            "\n"
            "========================================\n"
            "PARSER FINISHED SUCCESSFULLY\n"
            "STARTING INDEXER\n"
            "========================================\n\n"
        )

        QTimer.singleShot(
            250,
            self.start_indexer,
        )

    def start_indexer(self):
        if self.stopping:
            return

        self.indexer_process = QProcess(
            self
        )

        self.indexer_process.setProcessEnvironment(
            self._create_process_environment()
        )

        self.indexer_process.setWorkingDirectory(
            str(PROJECT_ROOT)
        )

        self.indexer_process.setProgram(
            sys.executable
        )

        self.indexer_process.setArguments(
            [
                "-u",
                str(self.indexer_script),
            ]
        )

        self.indexer_process.readyReadStandardOutput.connect(
            self._read_indexer_stdout
        )

        self.indexer_process.readyReadStandardError.connect(
            self._read_indexer_stderr
        )

        self.indexer_process.errorOccurred.connect(
            self._indexer_error
        )

        self.indexer_process.finished.connect(
            self._indexer_finished
        )

        self.indexer_process.start()

        if not self.indexer_process.waitForStarted(
            5000
        ):
            self._indexer_error(
                QProcess.ProcessError.FailedToStart
            )

    def _read_indexer_stdout(self):
        if self.indexer_process is None:
            return

        data = bytes(
            self.indexer_process.readAllStandardOutput()
        )

        if not data:
            return

        self._append_output(
            data.decode(
                "utf-8",
                errors="replace",
            )
        )

    def _read_indexer_stderr(self):
        if self.indexer_process is None:
            return

        data = bytes(
            self.indexer_process.readAllStandardError()
        )

        if not data:
            return

        self._append_output(
            data.decode(
                "utf-8",
                errors="replace",
            )
        )

    def _indexer_error(self, error):
        if self.stopping:
            return

        self.status_label.setText(
            f"שגיאת Gmail Indexer: {error}"
        )

        QMessageBox.critical(
            self,
            "שגיאה",
            "לא ניתן להפעיל את האינדקס של Google.\n\n"
            f"שגיאת QProcess: {error}",
        )

        self.start_button.setEnabled(
            True
        )

        self.stop_button.setEnabled(
            False
        )

        self.close_button.setEnabled(
            True
        )

    def _indexer_finished(
        self,
        exit_code,
        exit_status,
    ):
        if self.stopping:
            return

        if (
            exit_status != QProcess.ExitStatus.NormalExit
            or exit_code != 0
        ):
            self.status_label.setText(
                "Gmail Indexer נכשל. "
                f"קוד: {exit_code}"
            )

            self._append_output(
                "\n"
                "========================================\n"
                f"INDEXER FAILED - EXIT CODE {exit_code}\n"
                "========================================\n"
            )

            self.start_button.setEnabled(
                True
            )

            self.stop_button.setEnabled(
                False
            )

            self.close_button.setEnabled(
                True
            )

            return

        self.status_label.setText(
            "PARSE + INDEX הסתיימו בהצלחה."
        )

        self._append_output(
            "\n"
            "========================================\n"
            "PARSE + INDEX COMPLETED SUCCESSFULLY\n"
            "========================================\n"
        )

        self.stop_button.setEnabled(
            False
        )

        self.close_button.setEnabled(
            True
        )

    def stop(self):
        self.stopping = True

        if self.parser_process is not None:
            if (
                self.parser_process.state()
                != QProcess.ProcessState.NotRunning
            ):
                self.parser_process.terminate()

                if not self.parser_process.waitForFinished(
                    1500
                ):
                    self.parser_process.kill()
                    self.parser_process.waitForFinished(
                        1000
                    )

        if self.indexer_process is not None:
            if (
                self.indexer_process.state()
                != QProcess.ProcessState.NotRunning
            ):
                self.indexer_process.terminate()

                if not self.indexer_process.waitForFinished(
                    1500
                ):
                    self.indexer_process.kill()
                    self.indexer_process.waitForFinished(
                        1000
                    )

        self.status_label.setText(
            "האינדוקס נעצר."
        )

        self.start_button.setEnabled(
            True
        )

        self.stop_button.setEnabled(
            False
        )

        self.close_button.setEnabled(
            True
        )

    def closeEvent(self, event):
        self.stop()
        event.accept()


class DriveSyncWindow(QDialog):
    """
    Dedicated Google Drive <-> Local synchronization window.

    The worker is src/drive/drive_sync.py.
    The window is intentionally kept on top and shows the complete live
    synchronization state in one screen: progress, start time, elapsed
    time, estimated end time and a live activity log.
    """

    TYPES = [
        "PDF",
        "WORD / OFFICE",
        "EXCEL",
        "POWERPOINT",
        "IMAGES",
        "GMAIL",
        "FOLDER",
        "OTHER",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Alcalay - ניהול סנכרון Google Drive ↔ Local")
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.resize(1150, 900)
        self.setMinimumSize(1000, 760)

        self.process = None
        self.auth_process = None
        self.stdout_buffer = ""
        self.stopping = False
        self.started = False

        self.run_start = None
        self.last_progress_index = 0
        self.last_progress_total = 0
        self.last_progress_timestamp = None
        self.current_name = ""
        self.current_action = ""
        self.current_kind = ""
        self.stop_fallback_timer = None
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self._update_timing)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("ניהול סנכרון Google Drive ↔ Local")
        title.setObjectName("windowTitle")
        layout.addWidget(title)

        description = QLabel(
            "חלון הסנכרון נשאר מעל חלונות המערכת ומציג בזמן אמת את כל פעולות הסנכרון. "
            "הנתונים נלקחים מהרשומות הקיימות ב-PostgreSQL."
        )
        description.setObjectName("pageSubtitle")
        description.setWordWrap(True)
        layout.addWidget(description)

        direction_frame = QFrame()
        direction_frame.setObjectName("card")
        direction_layout = QHBoxLayout(direction_frame)
        direction_layout.setContentsMargins(14, 10, 14, 10)

        direction_title = QLabel("כיוון:")
        direction_title.setObjectName("cardTitle")
        direction_layout.addWidget(direction_title)

        self.drive_to_local_radio = QRadioButton("Drive → Local")
        self.drive_to_local_radio.setChecked(True)
        direction_layout.addWidget(self.drive_to_local_radio)

        self.local_to_drive_radio = QRadioButton("Local → Drive")
        direction_layout.addWidget(self.local_to_drive_radio)
        direction_layout.addStretch()
        layout.addWidget(direction_frame)

        status_frame = QFrame()
        status_frame.setObjectName("card")
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(14, 10, 14, 10)
        status_layout.setSpacing(7)

        self.status_label = QLabel("מוכן")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.status_label)

        self.current_operation_label = QLabel("פעולה נוכחית: -")
        self.current_operation_label.setWordWrap(True)
        status_layout.addWidget(self.current_operation_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        status_layout.addWidget(self.progress)

        self.progress_detail_label = QLabel("התקדמות: 0 / 0")
        status_layout.addWidget(self.progress_detail_label)

        timing_layout = QHBoxLayout()
        timing_layout.setSpacing(20)

        self.start_time_label = QLabel("זמן התחלה: -")
        self.elapsed_time_label = QLabel("זמן שחלף: 00:00:00")
        self.estimated_end_label = QLabel("סיום משוער: -")

        timing_layout.addWidget(self.start_time_label)
        timing_layout.addWidget(self.elapsed_time_label)
        timing_layout.addWidget(self.estimated_end_label)
        timing_layout.addStretch()
        status_layout.addLayout(timing_layout)

        self.estimate_basis_label = QLabel("בסיס הערכה: ממתין לנתוני התקדמות")
        status_layout.addWidget(self.estimate_basis_label)

        self.summary_label = QLabel(
            "מועמדים: 0 | הועברו: 0 | ללא שינוי: 0 | דולגו: 0 | "
            "התנגשויות: 0 | שגיאות: 0"
        )
        self.summary_label.setWordWrap(True)
        status_layout.addWidget(self.summary_label)

        layout.addWidget(status_frame)

        table_frame = QFrame()
        table_frame.setObjectName("card")
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(10, 10, 10, 10)
        table_layout.setSpacing(6)

        table_title = QLabel("סיכום חי לפי סוג נתון")
        table_title.setObjectName("cardTitle")
        table_layout.addWidget(table_title)

        self.table = QTableWidget(len(self.TYPES), 6)
        self.table.setHorizontalHeaderLabels([
            "סוג",
            "מועמדים",
            "Drive → Local",
            "Local → Drive",
            "ללא שינוי / דולגו",
            "התנגשויות / שגיאות",
        ])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        for column in range(1, 6):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.Stretch
            )
        for row, kind in enumerate(self.TYPES):
            self.table.setItem(row, 0, QTableWidgetItem(kind))
            for column in range(1, 6):
                self.table.setItem(row, column, QTableWidgetItem("0"))
        table_layout.addWidget(self.table)
        layout.addWidget(table_frame)

        activity_title = QLabel("ACTIVITY — תיעוד חי של כל פעילות")
        activity_title.setObjectName("cardTitle")
        layout.addWidget(activity_title)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.setMinimumHeight(230)
        layout.addWidget(self.output, 1)

        button_row = QHBoxLayout()

        self.start_button = QPushButton("התחל סנכרון")
        self.start_button.clicked.connect(self.start)
        button_row.addWidget(self.start_button)

        self.stop_button = QPushButton("עצור")
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setEnabled(False)
        button_row.addWidget(self.stop_button)

        button_row.addStretch()

        self.reconnect_button = QPushButton("התחבר מחדש ל-Google Drive")
        self.reconnect_button.clicked.connect(self.reconnect_drive)
        self.reconnect_button.setEnabled(True)
        button_row.addWidget(self.reconnect_button)

        self.close_button = QPushButton("סגור")
        self.close_button.clicked.connect(self.close)
        button_row.addWidget(self.close_button)

        layout.addLayout(button_row)

    @staticmethod
    def _format_duration(seconds):
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def _format_clock(value):
        return value.strftime("%H:%M:%S") if value else "-"

    def _append_output(self, text):
        if not text:
            return
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output.setTextCursor(cursor)
        self.output.insertPlainText(text)
        self.output.ensureCursorVisible()

    def _log_activity(self, message):
        timestamp = self._format_clock(__import__("datetime").datetime.now())
        self._append_output(f"[{timestamp}] {message}\n")

    def _reset_table(self):
        for row in range(self.table.rowCount()):
            for column in range(1, self.table.columnCount()):
                self.table.item(row, column).setText("0")

    def _reset_run_state(self):
        self.run_start = __import__("datetime").datetime.now()
        self.last_progress_index = 0
        self.last_progress_total = 0
        self.last_progress_timestamp = self.run_start
        self.current_name = ""
        self.current_action = ""
        self.current_kind = ""
        self.start_time_label.setText(
            f"זמן התחלה: {self._format_clock(self.run_start)}"
        )
        self.elapsed_time_label.setText("זמן שחלף: 00:00:00")
        self.estimated_end_label.setText("סיום משוער: ממתין...")
        self.estimate_basis_label.setText(
            "בסיס הערכה: ממתין לסיום הפעולה הראשונה"
        )
        self.progress_detail_label.setText("התקדמות: 0 / 0")
        self.elapsed_timer.start()

    def _update_timing(self):
        if not self.run_start:
            return

        now = __import__("datetime").datetime.now()
        elapsed = (now - self.run_start).total_seconds()
        self.elapsed_time_label.setText(
            f"זמן שחלף: {self._format_duration(elapsed)}"
        )

        total = self.last_progress_total
        index = self.last_progress_index

        if total <= 0 or index <= 0:
            return

        rate = index / max(elapsed, 0.001)
        remaining = max(total - index, 0)
        remaining_seconds = remaining / rate if rate > 0 else 0
        estimated_end = now + __import__("datetime").timedelta(
            seconds=remaining_seconds
        )

        self.estimated_end_label.setText(
            f"סיום משוער: {self._format_clock(estimated_end)}"
        )
        self.estimate_basis_label.setText(
            f"בסיס הערכה: {index:,}/{total:,} פריטים, "
            f"קצב ממוצע {rate:.2f} פריטים/שנייה"
        )

    def _update_summary(self, summary):
        if not summary:
            return
        transferred = int(summary.get("downloaded", 0)) + int(
            summary.get("uploaded", 0)
        )
        self.summary_label.setText(
            "מועמדים: " + f"{int(summary.get('candidates', 0)):,}"
            + " | הועברו: " + f"{transferred:,}"
            + " | ללא שינוי: " + f"{int(summary.get('no_change', 0)):,}"
            + " | דולגו: " + f"{int(summary.get('skipped', 0)):,}"
            + " | התנגשויות: " + f"{int(summary.get('conflicts', 0)):,}"
            + " | שגיאות: " + f"{int(summary.get('errors', 0)):,}"
        )

    def _update_table(self, by_type, direction):
        for row, kind in enumerate(self.TYPES):
            stats = by_type.get(kind) or {}
            candidates = int(stats.get("candidates", 0))
            transferred = int(stats.get("transferred", 0))
            no_change = int(stats.get("no_change", 0))
            skipped = int(stats.get("skipped", 0))
            conflicts = int(stats.get("conflicts", 0))
            errors = int(stats.get("errors", 0))

            self.table.item(row, 1).setText(f"{candidates:,}")
            self.table.item(row, 2).setText(
                f"{transferred:,}" if direction == DIRECTION_DRIVE_TO_LOCAL else "0"
            )
            self.table.item(row, 3).setText(
                f"{transferred:,}" if direction == DIRECTION_LOCAL_TO_DRIVE else "0"
            )
            self.table.item(row, 4).setText(f"{no_change + skipped:,}")
            self.table.item(row, 5).setText(f"{conflicts + errors:,}")

    def _update_from_event(self, payload):
        event = str(payload.get("event") or "").strip()
        event_upper = event.upper()
        event_lower = event.lower()

        summary = payload.get("summary") or {}
        by_type = payload.get("by_type") or {}
        direction = payload.get("direction") or (
            DIRECTION_DRIVE_TO_LOCAL
            if self.drive_to_local_radio.isChecked()
            else DIRECTION_LOCAL_TO_DRIVE
        )

        # The worker has used more than one event naming convention while
        # the synchronization protocol was being developed. Normalize the
        # known names here so the GUI remains compatible with both forms.
        if event_lower == "run_start":
            total = int(payload.get("candidates") or payload.get("count") or 0)
            self.last_progress_total = total
            self.last_progress_index = 0
            self.progress.setRange(0, max(total, 1))
            self.progress.setValue(0)
            self.progress_detail_label.setText(
                f"התקדמות: 0 / {total:,}"
            )
            self.status_label.setText(
                f"הסנכרון התחיל — {total:,} מועמדים."
            )
            self._log_activity(
                f"RUN START | כיוון={direction} | מועמדים={total:,}"
            )

        elif event_lower in ("started", "start"):
            total = int(payload.get("candidates") or payload.get("count") or 0)
            self.last_progress_total = total
            self.last_progress_index = 0
            self.progress.setRange(0, max(total, 1))
            self.progress.setValue(0)
            self.progress_detail_label.setText(
                f"התקדמות: 0 / {total:,}"
            )
            self.status_label.setText(
                f"הסנכרון התחיל — {total:,} מועמדים."
            )
            self._log_activity(
                f"STARTED | כיוון={direction} | מועמדים={total:,}"
            )

        elif event_lower == "repository":
            repository_id = payload.get("repository_id", "-")
            root_folder_id = payload.get("root_folder_id", "-")
            self.status_label.setText("Repository של Google Drive אותר.")
            self.current_operation_label.setText(
                f"Repository: {repository_id} | Root: {root_folder_id}"
            )
            self._log_activity(
                f"REPOSITORY | id={repository_id} | root={root_folder_id}"
            )

        elif event_lower in ("drive_connected", "connected"):
            email = str(payload.get("email") or "")
            self.status_label.setText(
                "מחובר ל-Google Drive"
                + (f": {email}" if email else ".")
            )
            self.current_operation_label.setText(
                "פעולה נוכחית: חיבור Google Drive תקין"
            )
            self._log_activity(
                "DRIVE CONNECTED"
                + (f" | {email}" if email else "")
            )

        elif event_lower == "candidates":
            total = int(payload.get("count") or payload.get("candidates") or 0)
            self.last_progress_total = total
            self.progress.setRange(0, max(total, 1))
            self.progress.setValue(0)
            self.progress_detail_label.setText(
                f"התקדמות: 0 / {total:,}"
            )
            self.status_label.setText(
                f"נמצאו {total:,} מועמדים לסנכרון."
            )
            self._log_activity(
                f"CANDIDATES | {total:,} מועמדים"
            )

        elif event_lower in ("item_start", "upload_start", "download_start"):
            index = int(payload.get("index") or 0)
            total = int(payload.get("total") or self.last_progress_total or 0)
            name = str(payload.get("name") or "")
            kind = str(payload.get("kind") or self._guess_kind(name))
            action = str(payload.get("action") or event_upper)
            local_path = str(payload.get("local_path") or "")

            self.current_name = name
            self.current_kind = kind
            self.current_action = action
            self.last_progress_total = total

            if event_lower == "item_start" and index > 0:
                self.progress_detail_label.setText(
                    f"התקדמות: {max(index - 1, 0):,} / {total:,}"
                )
                self.current_operation_label.setText(
                    f"פעולה נוכחית: {index:,}/{total:,} | {kind} | {name}"
                )
                self.status_label.setText(
                    f"מעבד פריט {index:,}/{total:,}"
                )
                self._log_activity(
                    f"ITEM START | {index:,}/{total:,} | {kind} | {name}"
                )
            else:
                self.current_operation_label.setText(
                    f"פעולה נוכחית: {action} | {kind} | {name}"
                )
                self.status_label.setText(
                    f"{action} | {name}"
                )
                self._log_activity(
                    f"{event_upper} | {kind} | {name}"
                    + (f" | {local_path}" if local_path else "")
                )

        elif event_lower == "item_done":
            index = int(payload.get("index") or 0)
            total = int(payload.get("total") or self.last_progress_total or 0)
            name = str(payload.get("name") or "")
            kind = str(payload.get("kind") or self._guess_kind(name))
            action = str(payload.get("action") or "")
            message = str(payload.get("message") or "")

            self.last_progress_index = index
            self.last_progress_total = total

            if total > 0:
                self.progress.setRange(0, total)
                self.progress.setValue(min(index, total))

            self.progress_detail_label.setText(
                f"התקדמות: {index:,} / {total:,}"
            )
            self.current_operation_label.setText(
                f"פעולה אחרונה: {action} | {kind} | {name}"
            )
            self.status_label.setText(
                f"הושלם {index:,}/{total:,} — {action}"
            )
            self.current_action = action
            self._log_activity(
                f"ITEM DONE | {index:,}/{total:,} | {action} | {kind} | "
                f"{name}"
                + (f" | {message}" if message else "")
            )

        elif event_lower in ("item_error", "error"):
            name = str(payload.get("name") or self.current_name or "")
            error = str(
                payload.get("error")
                or payload.get("message")
                or "שגיאה לא ידועה"
            )
            self.status_label.setText(
                f"שגיאה בפריט: {name}" if name else "שגיאה בפריט"
            )
            self.current_operation_label.setText(
                f"שגיאה: {error}"
            )
            self._log_activity(
                f"ITEM ERROR | {name} | {error}"
            )

        elif event_lower in ("auth_error", "authentication_error", "permission_error"):
            message = str(
                payload.get("message")
                or payload.get("error")
                or "אין הרשאות - נא להתחבר עם יוזר מורשה"
            )
            if "אין הרשאות" not in message:
                message = "אין הרשאות - נא להתחבר עם יוזר מורשה"

            self.status_label.setText(message)
            self.current_operation_label.setText(
                "Google Drive דורש התחברות מחדש עם הרשאות כתיבה."
            )
            self._log_activity(
                "AUTH ERROR | " + message
            )
            self.reconnect_button.setEnabled(True)

            QMessageBox.warning(
                self,
                "הרשאות Google Drive",
                message
                + "\n\n"
                "לחץ על 'התחבר מחדש ל-Google Drive' בחלון זה "
                "כדי לבצע OAuth מחדש.",
            )

        elif event_lower in ("upload_success", "download_success"):
            name = str(payload.get("name") or self.current_name or "")
            message = str(payload.get("message") or "")
            self.status_label.setText(
                f"העברה הסתיימה: {name}"
            )
            self._log_activity(
                f"{event_upper} | {name}"
                + (f" | {message}" if message else "")
            )

        elif event_lower in ("stop_requested", "stop"):
            self.status_label.setText(
                "בקשת עצירה התקבלה — עוצר את תהליך הסנכרון..."
            )
            self._log_activity(
                "STOP REQUESTED | התקבלה בקשת עצירה מהמשתמש"
            )

        elif event_lower in ("finished", "run_finished", "run_finish"):
            status = str(payload.get("status") or "UNKNOWN")
            self.status_label.setText(
                f"הסנכרון הסתיים: {status}"
            )
            self._log_activity(
                f"FINISHED | status={status}"
            )

        elif event_lower in ("fatal_error", "run_error"):
            message = str(
                payload.get("message")
                or payload.get("error")
                or "שגיאה לא ידועה"
            )
            self.status_label.setText(
                "סנכרון נכשל: " + message
            )
            self._log_activity(
                f"FATAL ERROR | {message}"
            )

        else:
            # Never silently discard a valid JSON event. This is important
            # because drive_sync.py can emit diagnostic events that are not
            # needed for progress calculations but are essential for the
            # live activity log and for troubleshooting permissions.
            details = []
            for key in (
                "message",
                "name",
                "error",
                "local_path",
                "action",
                "direction",
                "email",
                "count",
                "candidates",
            ):
                value = payload.get(key)
                if value not in (None, ""):
                    details.append(f"{key}={value}")

            self._log_activity(
                event_upper
                + (" | " + " | ".join(details) if details else "")
            )

        self._update_summary(summary)
        self._update_table(by_type, direction)
        self._update_timing()

    @staticmethod
    def _guess_kind(name):
        value = str(name or "").lower()
        if value.endswith(".pdf"):
            return "PDF"
        if value.endswith((".doc", ".docx", ".odt", ".rtf")):
            return "WORD / OFFICE"
        if value.endswith((".xls", ".xlsx", ".xlsm", ".csv")):
            return "EXCEL"
        if value.endswith((".ppt", ".pptx")):
            return "POWERPOINT"
        if value.endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff")):
            return "IMAGES"
        return "OTHER"

    def _process_event_line(self, line):
        if not line.startswith("[SYNC_EVENT] "):
            return False

        raw = line[len("[SYNC_EVENT] "):].strip()
        try:
            import json
            payload = json.loads(raw)
        except Exception as exc:
            self._log_activity(
                f"INVALID SYNC EVENT | {exc} | {raw}"
            )
            return True

        self._update_from_event(payload)
        return True

    def _read_stdout(self):
        if self.process is None:
            return

        data = bytes(self.process.readAllStandardOutput())
        if not data:
            return

        text = data.decode("utf-8", errors="replace")
        self.stdout_buffer += text

        while "\n" in self.stdout_buffer:
            line, self.stdout_buffer = self.stdout_buffer.split("\n", 1)
            line = line.rstrip("\r")
            if line:
                if not self._process_event_line(line):
                    self._append_output(line + "\n")
                    self._log_activity(line)

    def _read_stderr(self):
        if self.process is None:
            return

        data = bytes(self.process.readAllStandardError())
        if not data:
            return

        text = data.decode("utf-8", errors="replace")
        self._append_output(text)
        self._log_activity("STDERR | " + text.rstrip())

    def _create_process_environment(self, direction):
        environment = QProcessEnvironment.systemEnvironment()
        existing_pythonpath = environment.value("PYTHONPATH", "")
        paths = [str(PROJECT_ROOT), str(SRC_ROOT)]
        if existing_pythonpath:
            paths.append(existing_pythonpath)
        environment.insert("PYTHONPATH", os.pathsep.join(paths))
        environment.insert("PYTHONUNBUFFERED", "1")
        environment.insert("ALCALAY_SYNC_DIRECTION", direction)
        return environment

    def start(self):
        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            return

        script = PROJECT_ROOT / "src" / "drive" / "drive_sync.py"
        if not script.exists():
            QMessageBox.critical(
                self,
                "שגיאה",
                f"קובץ הסנכרון לא נמצא:\n{script}",
            )
            return

        direction = (
            DIRECTION_DRIVE_TO_LOCAL
            if self.drive_to_local_radio.isChecked()
            else DIRECTION_LOCAL_TO_DRIVE
        )

        self.stopping = False
        self.started = True
        self.stdout_buffer = ""
        self.output.clear()
        self._reset_table()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.summary_label.setText(
            "מועמדים: 0 | הועברו: 0 | ללא שינוי: 0 | דולגו: 0 | "
            "התנגשויות: 0 | שגיאות: 0"
        )
        self.current_operation_label.setText("פעולה נוכחית: מתחבר ומכין סנכרון...")
        self.status_label.setText(
            "מפעיל סנכרון: "
            + ("Drive → Local" if direction == DIRECTION_DRIVE_TO_LOCAL else "Local → Drive")
        )
        self._reset_run_state()
        self._log_activity(
            "RUN START | "
            + ("Drive → Local" if direction == DIRECTION_DRIVE_TO_LOCAL else "Local → Drive")
        )

        self.drive_to_local_radio.setEnabled(False)
        self.local_to_drive_radio.setEnabled(False)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.close_button.setEnabled(False)

        self.process = QProcess(self)
        self.process.setProcessChannelMode(
            QProcess.ProcessChannelMode.SeparateChannels
        )
        self.process.setProcessEnvironment(
            self._create_process_environment(direction)
        )
        self.process.setWorkingDirectory(str(PROJECT_ROOT))
        self.process.setProgram(sys.executable)
        self.process.setArguments(["-u", str(script)])
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)
        self.process.errorOccurred.connect(self._process_error)
        self.process.finished.connect(self._process_finished)
        self.process.start()

        if not self.process.waitForStarted(5000):
            self._process_error(QProcess.ProcessError.FailedToStart)

    def reconnect_drive(self):
        if self.auth_process is not None and self.auth_process.state() != QProcess.ProcessState.NotRunning:
            return

        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            self._log_activity("AUTH RECONNECT | עוצר את סנכרון Drive לפני התחברות מחדש")
            self.stop()
            if not self.process.waitForFinished(5500):
                self.process.kill()
                self.process.waitForFinished(1500)

        self.reconnect_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.status_label.setText("פותח התחברות מחדש ל-Google Drive...")
        self.current_operation_label.setText(
            "פעולה נוכחית: OAuth — יש להשלים את ההתחברות בדפדפן."
        )
        self._log_activity(
            "AUTH RECONNECT | מתחיל OAuth מחדש מתוך חלון Alcalay"
        )

        token_path = PROJECT_ROOT / "config" / "drive" / "tokens" / f"{DEFAULT_GMAIL_ACCOUNT}.json"
        script = (
            "from pathlib import Path; "
            "token=Path(r" + repr(str(token_path)) + "); "
            "token.unlink(missing_ok=True); "
            "from src.drive.drive_connection import DriveConnection; "
            "print('[AUTH] מתחיל התחברות מחדש ל-Google Drive', flush=True); "
            "email=DriveConnection(account_email=" + repr(DEFAULT_GMAIL_ACCOUNT) + ").connect(); "
            "print('[AUTH] התחברות הושלמה: ' + str(email), flush=True)"
        )

        self.auth_process = QProcess(self)
        self.auth_process.setProcessEnvironment(
            self._create_process_environment(DIRECTION_LOCAL_TO_DRIVE)
        )
        self.auth_process.setWorkingDirectory(str(PROJECT_ROOT))
        self.auth_process.setProgram(sys.executable)
        self.auth_process.setArguments(["-u", "-c", script])
        self.auth_process.readyReadStandardOutput.connect(self._read_auth_stdout)
        self.auth_process.readyReadStandardError.connect(self._read_auth_stderr)
        self.auth_process.errorOccurred.connect(self._auth_process_error)
        self.auth_process.finished.connect(self._auth_process_finished)
        self.auth_process.start()

        if not self.auth_process.waitForStarted(5000):
            self._auth_process_error(QProcess.ProcessError.FailedToStart)

    def _read_auth_stdout(self):
        if self.auth_process is None:
            return
        data = bytes(self.auth_process.readAllStandardOutput())
        if not data:
            return
        text = data.decode("utf-8", errors="replace")
        self._append_output(text)
        for line in text.splitlines():
            if line.strip():
                self._log_activity(line.strip())

    def _read_auth_stderr(self):
        if self.auth_process is None:
            return
        data = bytes(self.auth_process.readAllStandardError())
        if not data:
            return
        text = data.decode("utf-8", errors="replace")
        self._append_output(text)
        for line in text.splitlines():
            if line.strip():
                self._log_activity("AUTH STDERR | " + line.strip())

    def _auth_process_error(self, error):
        message = (
            "לא ניתן להפעיל את תהליך ההתחברות ל-Google Drive."
            if error == QProcess.ProcessError.FailedToStart
            else f"שגיאת QProcess בהתחברות: {error}"
        )
        self.status_label.setText(message)
        self._log_activity("AUTH ERROR | " + message)
        self.reconnect_button.setEnabled(True)
        self.start_button.setEnabled(True)
        self.close_button.setEnabled(True)

    def _auth_process_finished(self, exit_code, exit_status):
        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self.status_label.setText(
                "התחברות ל-Google Drive הושלמה. אפשר להפעיל את הסנכרון מחדש."
            )
            self.current_operation_label.setText(
                "פעולה נוכחית: Google Drive מחובר עם הרשאות מלאות."
            )
            self._log_activity(
                "AUTH SUCCESS | התחברות Google Drive הושלמה בהצלחה"
            )
        else:
            self.status_label.setText(
                f"התחברות Google Drive נכשלה. קוד: {exit_code}"
            )
            self._log_activity(
                f"AUTH FAILED | exit_code={exit_code}"
            )

        self.reconnect_button.setEnabled(True)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.close_button.setEnabled(True)
        self.auth_process = None

    def stop(self):
        if self.process is None or self.process.state() == QProcess.ProcessState.NotRunning:
            return

        if self.stopping:
            return

        self.stopping = True
        self.stop_button.setEnabled(False)
        self.status_label.setText(
            "עוצר... בקשת STOP נשלחה לתהליך הסנכרון."
        )
        self.current_operation_label.setText(
            "פעולה נוכחית: ממתין לעצירת תהליך הסנכרון..."
        )
        self._log_activity(
            "STOP | שולח STOP לתהליך הסנכרון"
        )

        try:
            self.process.write(b"STOP\n")
            self.process.waitForBytesWritten(1000)
        except Exception as exc:
            self._log_activity(
                f"STOP WRITE ERROR | {type(exc).__name__}: {exc}"
            )

        # The worker normally stops between files. If it is blocked in a
        # long network/file operation, do not leave the user waiting forever.
        # After 4 seconds the process is forcibly terminated.
        QTimer.singleShot(4000, self._force_stop_if_running)

    def _force_stop_if_running(self):
        if not self.stopping or self.process is None:
            return
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return

        self._log_activity(
            "STOP TIMEOUT | התהליך עדיין פעיל לאחר 4 שניות — מבצע עצירה מיידית"
        )
        self.status_label.setText(
            "מבצע עצירה מיידית של תהליך הסנכרון..."
        )
        self.process.terminate()

        if self.process.state() != QProcess.ProcessState.NotRunning:
            QTimer.singleShot(1500, self._kill_if_still_running)

    def _kill_if_still_running(self):
        if not self.stopping or self.process is None:
            return
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self._log_activity(
                "STOP KILL | terminate לא הספיק — מבצע kill לתהליך"
            )
            self.process.kill()

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            message = "לא ניתן להפעיל את Google Drive Sync."
        else:
            message = f"שגיאת QProcess: {error}"
        self.status_label.setText(message)
        self._append_output("\n[ERROR] " + message + "\n")
        self._log_activity("PROCESS ERROR | " + message)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.close_button.setEnabled(True)
        self.drive_to_local_radio.setEnabled(True)
        self.local_to_drive_radio.setEnabled(True)

    def _process_finished(self, exit_code, exit_status):
        if self.stdout_buffer:
            line = self.stdout_buffer.rstrip("\r")
            if line:
                if not self._process_event_line(line):
                    self._append_output(line + "\n")
            self.stdout_buffer = ""

        self.elapsed_timer.stop()
        self._update_timing()

        if self.stopping:
            self.status_label.setText("הסנכרון נעצר לפי בקשת המשתמש.")
            self._log_activity(
                f"RUN STOPPED | exit_code={exit_code}"
            )
        elif exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self.progress.setValue(self.progress.maximum())
            self.status_label.setText("הסנכרון הסתיים בהצלחה.")
            self.estimated_end_label.setText(
                f"סיום בפועל: {self._format_clock(__import__('datetime').datetime.now())}"
            )
            self._log_activity("RUN COMPLETED | הסנכרון הסתיים בהצלחה")
        else:
            self.status_label.setText(
                f"הסנכרון הסתיים עם שגיאה. קוד: {exit_code}"
            )
            self._log_activity(
                f"RUN ERROR | exit_code={exit_code}"
            )

        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.close_button.setEnabled(True)
        self.drive_to_local_radio.setEnabled(True)
        self.local_to_drive_radio.setEnabled(True)
        self.process = None

    def closeEvent(self, event):
        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            self.stop()
            if not self.process.waitForFinished(5500):
                self.process.kill()
                self.process.waitForFinished(1500)

        if self.auth_process is not None and self.auth_process.state() != QProcess.ProcessState.NotRunning:
            self.auth_process.terminate()
            if not self.auth_process.waitForFinished(1500):
                self.auth_process.kill()
                self.auth_process.waitForFinished(1000)

        self.elapsed_timer.stop()
        event.accept()


class GoogleDriveWindow(QDialog):
    """
    Alcalay - Google Drive control window.

    This window is an orchestration/UI layer only.
    The existing Drive modules remain responsible for their
    actual work:
        - drive_repository.py
        - drive_scanner.py
        - drive_registry.py
        - drive_keyword_filter.py
        - drive_content_filter.py
        - drive_duplicate_checker.py
        - drive_downloader.py

    The UI starts those modules as separate Python processes so
    the existing, tested Drive logic is not duplicated here.
    """

    COMMANDS = [
        (
            "scan",
            "סריקת Repository",
            "סריקת כל מבנה Alcalay ב-Google Drive ורישום המטא-דאטה ב-PostgreSQL.",
            "src/drive/drive_registry.py",
        ),
        (
            "name_filter",
            "סינון לפי שם ונתיב",
            "בדיקת מילות המפתח בשם הקובץ ובנתיב ה-Drive.",
            "src/drive/drive_keyword_filter.py",
        ),
        (
            "content_filter",
            "חיפוש מילות מפתח בתוכן",
            "חיפוש מילות המפתח בתוך תוכן קבצי Google Drive ללא הורדה.",
            "src/drive/drive_content_filter.py",
        ),
        (
            "duplicates",
            "בדיקת כפילויות וגרסאות",
            "בדיקה מול PostgreSQL של גרסאות, קבצים שכבר הורדו וכפילויות ידועות.",
            "src/drive/drive_duplicate_checker.py",
        ),
        (
            "download",
            "הורדה / Export",
            "הורדה או Export של קבצים רלוונטיים שאושרו בשלב הבדיקה.",
            "src/drive/drive_downloader.py",
        ),
        (
            "sync",
            "סנכרון Drive ↔ Local",
            "סנכרון דו-כיווני של הנתונים שכבר רשומים ב-PostgreSQL, ללא סריקה חדשה של Google Drive או של האחסון המקומי.",
            "src/drive/drive_sync.py",
        ),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Alcalay - Google Drive")
        self.setWindowModality(Qt.NonModal)
        self.resize(1150, 800)

        self.process = None
        self.current_command = None
        self.buttons = {}
        self.sync_window = None

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Google Drive")
        title.setObjectName("windowTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "ניהול Repository של Alcalay ב-Google Drive. "
            "הפעולות מופעלות לפי סדר העבודה של שכבת ה-Drive."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        connection_frame = QFrame()
        connection_frame.setObjectName("card")
        connection_layout = QVBoxLayout(connection_frame)
        connection_layout.setContentsMargins(18, 18, 18, 18)
        connection_layout.setSpacing(8)

        connection_title = QLabel("חיבור Google Drive")
        connection_title.setObjectName("cardTitle")
        connection_layout.addWidget(connection_title)

        connection_description = QLabel(
            "בדיקת OAuth וגישה ל-Alcalay Repository. "
            "הבדיקה אינה משנה נתונים ב-Drive."
        )
        connection_description.setObjectName("cardDescription")
        connection_description.setWordWrap(True)
        connection_layout.addWidget(connection_description)

        connection_row = QHBoxLayout()
        connection_row.setSpacing(8)

        self.connection_button = QPushButton("בדוק חיבור")
        self.connection_button.clicked.connect(self.check_connection)
        connection_row.addWidget(self.connection_button)

        connection_row.addStretch()

        connection_layout.addLayout(connection_row)
        layout.addWidget(connection_frame)

        commands_frame = QFrame()
        commands_frame.setObjectName("card")
        commands_layout = QVBoxLayout(commands_frame)
        commands_layout.setContentsMargins(18, 18, 18, 18)
        commands_layout.setSpacing(8)

        commands_title = QLabel("פעולות Google Drive")
        commands_title.setObjectName("cardTitle")
        commands_layout.addWidget(commands_title)

        for key, title_text, description, script in self.COMMANDS:
            row = QHBoxLayout()
            row.setSpacing(10)

            text_layout = QVBoxLayout()
            text_layout.setSpacing(2)

            label = QLabel(title_text)
            label.setObjectName("cardTitle")
            text_layout.addWidget(label)

            description_label = QLabel(description)
            description_label.setObjectName("cardDescription")
            description_label.setWordWrap(True)
            text_layout.addWidget(description_label)

            row.addLayout(text_layout, 1)

            button = QPushButton("הפעל")
            button.setMinimumWidth(110)
            button.clicked.connect(
                lambda checked=False, k=key: self.run_command(k)
            )
            self.buttons[key] = button
            row.addWidget(button)

            commands_layout.addLayout(row)

        layout.addWidget(commands_frame)

        status_frame = QFrame()
        status_frame.setObjectName("inputFrame")
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(12, 12, 12, 12)
        status_layout.setSpacing(8)

        self.status_label = QLabel("מוכן")
        self.status_label.setObjectName("statusLabel")
        status_layout.addWidget(self.status_label)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.NoWrap)
        status_layout.addWidget(self.output, 1)

        layout.addWidget(status_frame, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.stop_button = QPushButton("עצור")
        self.stop_button.clicked.connect(self.stop_process)
        self.stop_button.setEnabled(False)
        button_row.addWidget(self.stop_button)

        self.close_button = QPushButton("סגור")
        self.close_button.clicked.connect(self.close)
        button_row.addWidget(self.close_button)

        layout.addLayout(button_row)

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
        environment.insert("PYTHONUNBUFFERED", "1")

        return environment

    def _append_output(self, text):
        if not text:
            return

        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output.setTextCursor(cursor)
        self.output.insertPlainText(text)
        self.output.ensureCursorVisible()

    def _set_command_buttons_enabled(self, enabled):
        self.connection_button.setEnabled(enabled)

        for button in self.buttons.values():
            button.setEnabled(enabled)

        self.stop_button.setEnabled(not enabled)

    def check_connection(self):
        if (
            self.process is not None
            and self.process.state()
            != QProcess.ProcessState.NotRunning
        ):
            QMessageBox.information(
                self,
                "Google Drive",
                "פעולת Drive אחרת כבר מתבצעת.",
            )
            return

        self.output.clear()
        self.status_label.setText(
            "בודק חיבור Google Drive..."
        )
        self._set_command_buttons_enabled(False)

        code = (
            "from src.drive.drive_connection import DriveConnection\n"
            "connection = DriveConnection()\n"
            "email = connection.connect()\n"
            "print('[GOOGLE ACCOUNT]', email)\n"
            "print('[REPOSITORY]', connection.get_repository_folder_ids())\n"
            "result = connection.verify_alcalay_repository()\n"
            "print('[REPOSITORY VERIFIED]', len(result))\n"
            "for key, metadata in result.items():\n"
            "    print('[FOLDER]', key, metadata.get('id'), metadata.get('name'))\n"
            "print('GOOGLE DRIVE CONNECTION CHECK COMPLETED')\n"
        )

        self.current_command = "connection"
        self._start_python_code_process(code)

    def run_command(self, key):
        if key == "sync":
            self.open_sync_window()
            return

        if (
            self.process is not None
            and self.process.state()
            != QProcess.ProcessState.NotRunning
        ):
            QMessageBox.information(
                self,
                "Google Drive",
                "פעולת Drive אחרת כבר מתבצעת.",
            )
            return

        command = None
        for item in self.COMMANDS:
            if item[0] == key:
                command = item
                break

        if command is None:
            return

        _, title_text, _, script_relative = command
        script = PROJECT_ROOT / script_relative

        if not script.exists():
            QMessageBox.critical(
                self,
                "שגיאה",
                f"קובץ Drive לא נמצא:\n{script}",
            )
            return

        self.output.clear()
        self.status_label.setText(
            f"מפעיל: {title_text}..."
        )
        self.current_command = key

        self._set_command_buttons_enabled(False)

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
            self._process_error(
                QProcess.ProcessError.FailedToStart
            )

    def open_sync_window(self):
        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(
                self,
                "Google Drive",
                "פעולת Drive אחרת כבר מתבצעת.",
            )
            return

        if self.sync_window is None:
            self.sync_window = DriveSyncWindow(self)

        self.sync_window.show()
        self.sync_window.raise_()
        self.sync_window.activateWindow()

    def _start_python_code_process(self, code):
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
                "-c",
                code,
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
            self._process_error(
                QProcess.ProcessError.FailedToStart
            )

    def _read_stdout(self):
        if self.process is None:
            return

        data = bytes(
            self.process.readAllStandardOutput()
        )

        if not data:
            return

        self._append_output(
            data.decode(
                "utf-8",
                errors="replace",
            )
        )

    def _read_stderr(self):
        if self.process is None:
            return

        data = bytes(
            self.process.readAllStandardError()
        )

        if not data:
            return

        self._append_output(
            data.decode(
                "utf-8",
                errors="replace",
            )
        )

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            message = "לא ניתן להפעיל את פעולת Google Drive."
        else:
            message = f"שגיאת QProcess: {error}"

        self.status_label.setText(message)

        self._append_output(
            "\n[ERROR] "
            + message
            + "\n"
        )

        self._set_command_buttons_enabled(True)

    def _process_finished(self, exit_code, exit_status):
        if (
            exit_status == QProcess.ExitStatus.NormalExit
            and exit_code == 0
        ):
            self.status_label.setText(
                "הפעולה הסתיימה בהצלחה."
            )
            self._append_output(
                "\n"
                "========================================\n"
                "GOOGLE DRIVE COMMAND COMPLETED SUCCESSFULLY\n"
                "========================================\n"
            )
        else:
            self.status_label.setText(
                "הפעולה הסתיימה עם שגיאה. "
                f"קוד: {exit_code}"
            )
            self._append_output(
                "\n"
                "========================================\n"
                f"GOOGLE DRIVE COMMAND FAILED - EXIT CODE {exit_code}\n"
                "========================================\n"
            )

        self._set_command_buttons_enabled(True)
        self.process = None
        self.current_command = None

    def stop_process(self):
        if self.process is None:
            return

        if (
            self.process.state()
            == QProcess.ProcessState.NotRunning
        ):
            return

        self.status_label.setText(
            "עוצר את פעולת Google Drive..."
        )

        # The sync process supports a graceful STOP command.
        # Give it priority over terminate/kill so the current file
        # can finish and the process can stop between files.
        if self.current_command == "sync":
            try:
                self.process.write(b"STOP\n")
                self.process.waitForBytesWritten(1000)
            except Exception:
                pass

            if not self.process.waitForFinished(5000):
                self.process.terminate()

                if not self.process.waitForFinished(1500):
                    self.process.kill()
                    self.process.waitForFinished(1000)
        else:
            self.process.terminate()

            if not self.process.waitForFinished(1500):
                self.process.kill()
                self.process.waitForFinished(1000)

        self._append_output(
            "\n[GUI] Google Drive process stopped.\n"
        )

        self._set_command_buttons_enabled(True)
        self.process = None
        self.current_command = None

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

        if self.sync_window is not None:
            self.sync_window.close()

        event.accept()


class GoogleLauncherPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.gmail_window = None
        self.gmail_import_window = None
        self.gmail_index_window = None
        self.search_window = None
        self.drive_window = None

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            30,
            30,
            30,
            30,
        )

        layout.setSpacing(18)

        title = QLabel(
            "Google"
        )

        title.setObjectName(
            "pageTitle"
        )

        layout.addWidget(title)

        subtitle = QLabel(
            "ניהול Google Drive ו-Gmail, "
            "ייבוא, אינדוקס וחיפוש"
        )

        subtitle.setObjectName(
            "pageSubtitle"
        )

        layout.addWidget(subtitle)

        cards = [
            (
                "Google Drive",
                "חיבור, סריקה, סינון, בדיקת כפילויות "
                "והורדה / Export של מסמכים רלוונטיים",
                self.open_drive_window,
            ),
            (
                "חשבונות ותגיות",
                "ניהול חשבונות Gmail "
                "ותגיות שנבחרו לסנכרון",
                self.open_gmail_window,
            ),
            (
                "ייבוא מיילים",
                "COPY של מיילים "
                "מהתגיות שנבחרו בלבד",
                self.open_gmail_import,
            ),
            (
                "אינדוקס מיילים",
                "PARSE ולאחר מכן INDEX "
                "של המיילים שהועתקו",
                self.open_gmail_index,
            ),
            (
                "חיפוש במאגרים",
                "חיפוש במידע שנשמר "
                "ונוסף לאינדקס מכלל המאגרים",
                self.open_search,
            ),
        ]

        for (
            title_text,
            description,
            callback,
        ) in cards:

            frame = QFrame()
            frame.setObjectName(
                "card"
            )

            frame_layout = QVBoxLayout(
                frame
            )

            frame_layout.setContentsMargins(
                18,
                18,
                18,
                18,
            )

            frame_layout.setSpacing(8)

            card_title = QLabel(
                title_text
            )

            card_title.setObjectName(
                "cardTitle"
            )

            frame_layout.addWidget(
                card_title
            )

            card_description = QLabel(
                description
            )

            card_description.setObjectName(
                "cardDescription"
            )

            card_description.setWordWrap(
                True
            )

            frame_layout.addWidget(
                card_description
            )

            button = QPushButton(
                "פתח"
            )

            button.clicked.connect(
                callback
            )

            frame_layout.addWidget(
                button
            )

            layout.addWidget(
                frame
            )

        layout.addStretch()

    def open_drive_window(self):
        if self.drive_window is None:
            self.drive_window = GoogleDriveWindow(self)

        self.drive_window.show()
        self.drive_window.raise_()
        self.drive_window.activateWindow()

    def open_gmail_window(self):
        if self.gmail_window is None:
            self.gmail_window = GmailWindow()

        self.gmail_window.show()
        self.gmail_window.raise_()
        self.gmail_window.activateWindow()

    def open_gmail_import(self):
        if self.gmail_import_window is None:
            self.gmail_import_window = GmailImportWindow(
                self
            )

        self.gmail_import_window.show()
        self.gmail_import_window.raise_()
        self.gmail_import_window.activateWindow()

        self.gmail_import_window.refresh_gmail_counts()

        if (
            self.gmail_import_window.process is None
            or self.gmail_import_window.process.state()
            == QProcess.ProcessState.NotRunning
        ):
            self.gmail_import_window.start()

    def open_gmail_index(self):
        if self.gmail_index_window is None:
            self.gmail_index_window = GmailIndexWindow(
                self
            )

        self.gmail_index_window.show()
        self.gmail_index_window.raise_()
        self.gmail_index_window.activateWindow()

    def open_search(self):
        if self.search_window is None:
            self.search_window = SearchWindow()

        self.search_window.show()
        self.search_window.raise_()
        self.search_window.activateWindow()


class PlaceholderPage(QWidget):
    def __init__(
        self,
        title,
        parent=None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            30,
            30,
            30,
            30,
        )

        label = QLabel(title)
        label.setObjectName(
            "pageTitle"
        )

        layout.addWidget(label)

        message = QLabel(
            "מודול זה יוגדר בשלב הבא."
        )

        message.setObjectName(
            "pageSubtitle"
        )

        layout.addWidget(
            message
        )

        layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "Alcalay"
        )

        self.resize(
            1450,
            850,
        )

        self.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft
        )

        self.stack = QStackedWidget()

        self.pages = {}

        self._build_pages()

        self.setCentralWidget(
            self._build_central_widget()
        )

    def _build_pages(self):
        self.pages[1] = GoogleLauncherPage()

        for number, title in MENU_ITEMS:
            if number == 1:
                continue

            self.pages[number] = PlaceholderPage(
                title
            )

        for number in range(1, 11):
            self.stack.addWidget(
                self.pages[number]
            )

    def _build_central_widget(self):
        central = QWidget()

        main_layout = QHBoxLayout(
            central
        )

        main_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        main_layout.setSpacing(0)

        menu_frame = QFrame()
        menu_frame.setObjectName(
            "sideMenu"
        )

        menu_frame.setFixedWidth(
            310
        )

        menu_layout = QVBoxLayout(
            menu_frame
        )

        menu_layout.setContentsMargins(
            15,
            20,
            15,
            20,
        )

        menu_layout.setSpacing(8)

        logo = QLabel(
            "ALCALAY"
        )

        logo.setObjectName(
            "logo"
        )

        logo.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        menu_layout.addWidget(
            logo
        )

        separator = QFrame()

        separator.setFrameShape(
            QFrame.Shape.HLine
        )

        separator.setObjectName(
            "separator"
        )

        menu_layout.addWidget(
            separator
        )

        for number, title in MENU_ITEMS:
            button = QPushButton(
                f"{number}. {title}"
            )

            button.setObjectName(
                "menuButton"
            )

            button.setMinimumHeight(
                48
            )

            button.clicked.connect(
                lambda checked=False,
                n=number:
                self.show_page(n)
            )

            menu_layout.addWidget(
                button
            )

        menu_layout.addStretch()

        version = QLabel(
            "Alcalay"
        )

        version.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        version.setObjectName(
            "versionLabel"
        )

        menu_layout.addWidget(
            version
        )

        main_layout.addWidget(
            menu_frame
        )

        main_layout.addWidget(
            self.stack,
            1,
        )

        return central

    def show_page(self, number):
        if number not in self.pages:
            return

        self.stack.setCurrentWidget(
            self.pages[number]
        )


def apply_styles(app):
    app.setStyleSheet(
        """
        QWidget {
            font-family: "Arial";
            font-size: 14px;
        }

        QMainWindow,
        QDialog {
            background: #f4f6f8;
        }

        QLabel#logo {
            font-size: 25px;
            font-weight: bold;
            padding: 10px;
        }

        QLabel#windowTitle,
        QLabel#pageTitle {
            font-size: 24px;
            font-weight: bold;
            padding: 4px;
        }

        QLabel#pageSubtitle {
            font-size: 15px;
            color: #606770;
            padding-bottom: 10px;
        }

        QLabel#statusLabel {
            font-size: 14px;
            font-weight: bold;
            padding: 6px;
        }

        QLabel#inputLabel {
            font-weight: bold;
        }

        QLabel#inputHint {
            color: #606770;
        }

        QLabel#cardTitle {
            font-size: 18px;
            font-weight: bold;
        }

        QLabel#cardDescription {
            color: #606770;
            padding-bottom: 4px;
        }

        QLabel#versionLabel {
            color: #777777;
            padding: 8px;
        }

        QFrame#sideMenu {
            background: #ffffff;
            border-right: 1px solid #d7dce1;
        }

        QFrame#separator {
            color: #d7dce1;
            margin-top: 8px;
            margin-bottom: 8px;
        }

        QFrame#card {
            background: #ffffff;
            border: 1px solid #d9dee3;
            border-radius: 8px;
        }

        QFrame#inputFrame {
            background: #ffffff;
            border: 1px solid #d9dee3;
            border-radius: 8px;
        }

        QPushButton#menuButton {
            text-align: right;
            padding: 10px 14px;
            border: 1px solid transparent;
            border-radius: 6px;
            background: #ffffff;
        }

        QPushButton#menuButton:hover {
            background: #eef2f5;
            border: 1px solid #d7dce1;
        }

        QPushButton {
            min-height: 36px;
            padding: 6px 16px;
            border: 1px solid #c7cdd3;
            border-radius: 6px;
            background: #ffffff;
        }

        QPushButton:hover {
            background: #eef2f5;
        }

        QPushButton:disabled {
            color: #999999;
            background: #eeeeee;
        }

        QLineEdit {
            min-height: 36px;
            padding: 4px 10px;
            border: 1px solid #c7cdd3;
            border-radius: 6px;
            background: #ffffff;
        }

        QPlainTextEdit {
            background: #ffffff;
            border: 1px solid #d7dce1;
            border-radius: 6px;
            padding: 8px;
        }
        """
    )


def main():
    app = QApplication(sys.argv)

    app.setLayoutDirection(
        Qt.LayoutDirection.RightToLeft
    )

    apply_styles(app)

    window = MainWindow()
    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()