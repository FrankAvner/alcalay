# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QProcess,
    QProcessEnvironment,
    QTimer,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QPushButton,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QFrame,
    QPlainTextEdit,
    QDialog,
    QLineEdit,
)

from gmail.gmail_window import GmailWindow
from gmail.gmail_search_window import GmailSearchWindow


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

DEFAULT_GMAIL_ACCOUNT = "frank.avner@gmail.com"


MENU_ITEMS = [
    (1, "Google"),
    (2, "מסמכים"),
    (3, "חיפוש"),
    (4, "ניהול משתמשים"),
    (5, "הרשאות"),
    (6, "מסד נתונים"),
    (7, "הורדות"),
    (8, "הגדרות"),
    (9, "מערכת"),
    (10, "רענון והוספת מסמכים מהמייל"),
]


class GmailImportWindow(QDialog):
    """
    GUI wrapper around gmail_copy.py.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.parent_window = parent
        self.process = None
        self.process_finished = False

        self.output_buffer = ""

        self.awaiting_label_input = False
        self.awaiting_copy_confirmation = False

        self.setWindowTitle(
            "Alcalay - ייבוא מיילים"
        )

        self.setModal(False)
        self.setWindowModality(Qt.NonModal)

        self.resize(
            1100,
            700,
        )

        self.setMinimumSize(
            850,
            500,
        )

        self.setLayoutDirection(
            Qt.RightToLeft
        )

        self.script_path = (
            PROJECT_ROOT
            / "src"
            / "gmail"
            / "gmail_copy.py"
        )

        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(
            20,
            20,
            20,
            20,
        )

        main_layout.setSpacing(12)

        title = QLabel(
            "ייבוא מיילים מ-Gmail"
        )

        title.setObjectName(
            "gmailImportTitle"
        )

        title.setAlignment(
            Qt.AlignRight
        )

        self.status_label = QLabel(
            "מכין את ייבוא המיילים..."
        )

        self.status_label.setObjectName(
            "gmailImportStatus"
        )

        self.status_label.setAlignment(
            Qt.AlignRight
        )

        self.output = QPlainTextEdit()

        self.output.setObjectName(
            "gmailImportOutput"
        )

        self.output.setReadOnly(True)

        self.output.setLineWrapMode(
            QPlainTextEdit.NoWrap
        )

        self.output.setLayoutDirection(
            Qt.LeftToRight
        )

        input_frame = QFrame()

        input_frame.setObjectName(
            "gmailImportInputFrame"
        )

        input_layout = QHBoxLayout(
            input_frame
        )

        input_layout.setContentsMargins(
            10,
            8,
            10,
            8,
        )

        input_layout.setSpacing(8)

        self.input_label = QLabel(
            "קלט:"
        )

        self.input_label.setObjectName(
            "gmailImportInputLabel"
        )

        self.input_edit = QLineEdit()

        self.input_edit.setObjectName(
            "gmailImportInput"
        )

        self.input_edit.setPlaceholderText(
            "הקלד כאן..."
        )

        self.input_edit.setEnabled(False)

        self.input_edit.returnPressed.connect(
            self.send_input
        )

        self.send_button = QPushButton(
            "שלח"
        )

        self.send_button.setObjectName(
            "gmailImportSendButton"
        )

        self.send_button.setEnabled(False)

        self.send_button.clicked.connect(
            self.send_input
        )

        self.yes_button = QPushButton(
            "YES"
        )

        self.yes_button.setObjectName(
            "gmailImportYesButton"
        )

        self.yes_button.setEnabled(False)

        self.yes_button.clicked.connect(
            lambda: self.send_text("YES")
        )

        self.no_button = QPushButton(
            "NO"
        )

        self.no_button.setObjectName(
            "gmailImportNoButton"
        )

        self.no_button.setEnabled(False)

        self.no_button.clicked.connect(
            lambda: self.send_text("NO")
        )

        input_layout.addWidget(
            self.input_label
        )

        input_layout.addWidget(
            self.input_edit,
            1,
        )

        input_layout.addWidget(
            self.send_button
        )

        input_layout.addWidget(
            self.yes_button
        )

        input_layout.addWidget(
            self.no_button
        )

        self.close_button = QPushButton(
            "סגור"
        )

        self.close_button.setObjectName(
            "gmailImportCloseButton"
        )

        self.close_button.setMinimumHeight(
            42
        )

        self.close_button.setEnabled(False)

        self.close_button.clicked.connect(
            self.close
        )

        buttons_layout = QHBoxLayout()

        buttons_layout.addStretch()

        buttons_layout.addWidget(
            self.close_button
        )

        main_layout.addWidget(
            title
        )

        main_layout.addWidget(
            self.status_label
        )

        main_layout.addWidget(
            self.output,
            1,
        )

        main_layout.addWidget(
            input_frame
        )

        main_layout.addLayout(
            buttons_layout
        )

    def append_output(self, text):
        if not text:
            return

        self.output_buffer += text

        cursor = self.output.textCursor()

        cursor.movePosition(
            cursor.MoveOperation.End
        )

        self.output.setTextCursor(cursor)

        self.output.insertPlainText(text)

        cursor = self.output.textCursor()

        cursor.movePosition(
            cursor.MoveOperation.End
        )

        self.output.setTextCursor(cursor)

        self.output.ensureCursorVisible()

        self._check_for_input_prompt()

    def append_line(self, text):
        self.append_output(
            text + "\n"
        )

    def _check_for_input_prompt(self):
        if self.process is None:
            return

        if self.process.state() == QProcess.NotRunning:
            return

        if (
            not self.awaiting_label_input
            and "Labels to copy:" in self.output_buffer
        ):
            self.awaiting_label_input = True
            self.awaiting_copy_confirmation = False

            self._enable_text_input(
                "הקלד את מספרי ה-Labels, לדוגמה: 1,4,7 או 1-3,7"
            )

            self.status_label.setText(
                "ממתין לבחירת ה-Labels לייבוא"
            )

            return

        if (
            not self.awaiting_copy_confirmation
            and "להמשיך ל-COPY? הקלד YES לאישור:" in self.output_buffer
        ):
            self.awaiting_label_input = False
            self.awaiting_copy_confirmation = True

            self._enable_confirmation_buttons()

            self.status_label.setText(
                "נדרש אישור לפני הורדת תוכן המיילים"
            )

    def _enable_text_input(self, placeholder):
        self.input_edit.setEnabled(True)

        self.input_edit.setPlaceholderText(
            placeholder
        )

        self.send_button.setEnabled(True)

        self.yes_button.setEnabled(False)
        self.no_button.setEnabled(False)

        self.input_edit.setFocus()

    def _enable_confirmation_buttons(self):
        self.input_edit.setEnabled(False)

        self.send_button.setEnabled(False)

        self.yes_button.setEnabled(True)
        self.no_button.setEnabled(True)

        self.input_edit.clear()

    def _disable_input_controls(self):
        self.input_edit.setEnabled(False)
        self.send_button.setEnabled(False)
        self.yes_button.setEnabled(False)
        self.no_button.setEnabled(False)

    def send_input(self):
        value = self.input_edit.text().strip()

        if not value:
            return

        self.send_text(value)

    def send_text(self, value):
        if self.process is None:
            return

        if self.process.state() == QProcess.NotRunning:
            return

        text = str(value).strip()

        if not text:
            return

        self.append_line("")
        self.append_line(
            f"[GUI INPUT] {text}"
        )

        self.process.write(
            (
                text + "\n"
            ).encode("utf-8")
        )

        self.input_edit.clear()

        self.awaiting_label_input = False
        self.awaiting_copy_confirmation = False

        self._disable_input_controls()

        if text.upper() == "YES":
            self.status_label.setText(
                "אישור התקבל — מתחיל COPY..."
            )

        elif text.upper() == "NO":
            self.status_label.setText(
                "COPY בוטל..."
            )

        else:
            self.status_label.setText(
                "בחירת ה-Labels נשלחה ל-gmail_copy.py..."
            )

    def _create_process_environment(self, env):
        process_environment = (
            QProcessEnvironment.systemEnvironment()
        )

        for key, value in env.items():
            process_environment.insert(
                key,
                value,
            )

        return process_environment

    def start(self):
        if not self.script_path.exists():
            self.status_label.setText(
                "שגיאה: קובץ הייבוא לא נמצא"
            )

            self.append_line(
                "ERROR: Gmail COPY script was not found:"
            )

            self.append_line(
                str(self.script_path)
            )

            self.close_button.setEnabled(True)

            return

        env = os.environ.copy()

        existing_pythonpath = env.get(
            "PYTHONPATH",
            "",
        )

        python_paths = [
            str(SRC_ROOT),
            str(PROJECT_ROOT),
        ]

        if existing_pythonpath:
            python_paths.append(
                existing_pythonpath
            )

        env["PYTHONPATH"] = (
            os.pathsep.join(python_paths)
        )

        env["PYTHONUNBUFFERED"] = "1"

        self.append_line(
            "========================================================================"
        )

        self.append_line(
            "ALCALAY - GMAIL COPY"
        )

        self.append_line(
            "========================================================================"
        )

        self.append_line("")

        self.append_line(
            f"[PROCESS] Python: {sys.executable}"
        )

        self.append_line(
            f"[PROCESS] Script: {self.script_path}"
        )

        self.append_line(
            f"[PROCESS] Working directory: {PROJECT_ROOT}"
        )

        self.append_line("")

        self.append_line(
            "[PROCESS] Starting gmail_copy.py..."
        )

        self.append_line("")

        self.status_label.setText(
            "שלב 2: ייבוא מיילים מתבצע..."
        )

        self.process = QProcess(self)

        self.process.setWorkingDirectory(
            str(PROJECT_ROOT)
        )

        self.process.setProcessEnvironment(
            self._create_process_environment(env)
        )

        self.process.setProgram(
            sys.executable
        )

        self.process.setArguments(
            [
                "-u",
                str(self.script_path),
            ]
        )

        self.process.readyReadStandardOutput.connect(
            self._read_stdout
        )

        self.process.readyReadStandardError.connect(
            self._read_stderr
        )

        self.process.finished.connect(
            self._process_finished
        )

        self.process.errorOccurred.connect(
            self._process_error
        )

        self.process.start()

        if not self.process.waitForStarted(5000):
            self.append_line("")
            self.append_line(
                "[ERROR] Could not start gmail_copy.py."
            )

            self.status_label.setText(
                "שגיאה בהפעלת ייבוא Gmail"
            )

            self.close_button.setEnabled(True)

    def _read_stdout(self):
        if self.process is None:
            return

        data = (
            self.process.readAllStandardOutput()
        )

        if not data:
            return

        text = bytes(data).decode(
            "utf-8",
            errors="replace",
        )

        self.append_output(text)

    def _read_stderr(self):
        if self.process is None:
            return

        data = (
            self.process.readAllStandardError()
        )

        if not data:
            return

        text = bytes(data).decode(
            "utf-8",
            errors="replace",
        )

        self.append_output(text)

    def _process_error(self, error):
        self.append_line("")
        self.append_line(
            "[PROCESS ERROR] "
            + str(error)
        )

        self.status_label.setText(
            "שגיאה בתהליך ייבוא Gmail"
        )

    def _process_finished(
        self,
        exit_code,
        exit_status,
    ):
        self._read_stdout()
        self._read_stderr()

        self.process_finished = True

        self._disable_input_controls()

        self.append_line("")
        self.append_line(
            "========================================================================"
        )

        if exit_code == 0:
            self.append_line(
                "[PROCESS] Gmail COPY completed successfully."
            )

            self.status_label.setText(
                "ייבוא המיילים הסתיים בהצלחה"
            )

        else:
            self.append_line(
                "[PROCESS] Gmail COPY finished "
                f"with exit code {exit_code}."
            )

            self.status_label.setText(
                "ייבוא המיילים הסתיים עם שגיאה"
            )

        self.append_line(
            "========================================================================"
        )

        self.close_button.setEnabled(True)

        if self.parent_window is not None:
            if exit_code == 0:
                self.parent_window.statusBar().showMessage(
                    "שלב 2: ייבוא מיילים הסתיים בהצלחה"
                )
            else:
                self.parent_window.statusBar().showMessage(
                    "שלב 2: ייבוא מיילים הסתיים עם שגיאה"
                )

    def closeEvent(self, event):
        if (
            self.process is not None
            and self.process.state()
            != QProcess.NotRunning
        ):
            answer = QMessageBox.question(
                self,
                "ייבוא עדיין מתבצע",
                "ייבוא המיילים עדיין מתבצע.\n\n"
                "האם לסגור את החלון ולהפסיק את התהליך?",
                QMessageBox.Yes
                | QMessageBox.No,
                QMessageBox.No,
            )

            if answer != QMessageBox.Yes:
                event.ignore()
                return

            self.process.kill()

            self.process.waitForFinished(2000)

        event.accept()


class GmailIndexWindow(QDialog):
    """
    Combined Gmail INDEX workflow.

    When INDEX is selected:

        1. gmail_parser.py
        2. gmail_indexer.py
        3. automatic window close

    The parser is started with the configured/default Gmail account.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.parent_window = parent

        self.process = None

        self.current_stage = None

        self.stop_requested = False
        self.process_finished = False

        self.parse_script_path = (
            PROJECT_ROOT
            / "src"
            / "gmail"
            / "gmail_parser.py"
        )

        self.index_script_path = (
            PROJECT_ROOT
            / "src"
            / "gmail"
            / "gmail_indexer.py"
        )

        self.account_email = (
            DEFAULT_GMAIL_ACCOUNT
        )

        self.setWindowTitle(
            "Alcalay - Gmail INDEX"
        )

        self.setModal(False)
        self.setWindowModality(Qt.NonModal)

        # Intentionally smaller than the old 1100x700 window.
        self.resize(
            900,
            520,
        )

        self.setMinimumSize(
            700,
            400,
        )

        self.setLayoutDirection(
            Qt.RightToLeft
        )

        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(
            15,
            15,
            15,
            15,
        )

        main_layout.setSpacing(8)

        self.title = QLabel(
            "Gmail INDEX"
        )

        self.title.setObjectName(
            "gmailIndexTitle"
        )

        self.title.setAlignment(
            Qt.AlignRight
        )

        self.status_label = QLabel(
            "מכין את תהליך האינדוקס..."
        )

        self.status_label.setObjectName(
            "gmailIndexStatus"
        )

        self.status_label.setAlignment(
            Qt.AlignRight
        )

        self.output = QPlainTextEdit()

        self.output.setObjectName(
            "gmailIndexOutput"
        )

        self.output.setReadOnly(True)

        self.output.setLineWrapMode(
            QPlainTextEdit.NoWrap
        )

        self.output.setLayoutDirection(
            Qt.LeftToRight
        )

        buttons_layout = QHBoxLayout()

        self.stop_button = QPushButton(
            "עצור"
        )

        self.stop_button.setObjectName(
            "gmailIndexStopButton"
        )

        self.stop_button.setMinimumHeight(36)

        self.stop_button.clicked.connect(
            self.stop_process
        )

        self.close_button = QPushButton(
            "סגור"
        )

        self.close_button.setObjectName(
            "gmailIndexCloseButton"
        )

        self.close_button.setMinimumHeight(36)

        self.close_button.setEnabled(False)

        self.close_button.clicked.connect(
            self.close
        )

        buttons_layout.addWidget(
            self.stop_button
        )

        buttons_layout.addStretch()

        buttons_layout.addWidget(
            self.close_button
        )

        main_layout.addWidget(
            self.title
        )

        main_layout.addWidget(
            self.status_label
        )

        main_layout.addWidget(
            self.output,
            1,
        )

        main_layout.addLayout(
            buttons_layout
        )

    def append_output(self, text):
        if not text:
            return

        cursor = self.output.textCursor()

        cursor.movePosition(
            cursor.MoveOperation.End
        )

        self.output.setTextCursor(cursor)

        self.output.insertPlainText(text)

        cursor = self.output.textCursor()

        cursor.movePosition(
            cursor.MoveOperation.End
        )

        self.output.setTextCursor(cursor)

        self.output.ensureCursorVisible()

    def append_line(self, text):
        self.append_output(
            text + "\n"
        )

    def _create_process_environment(self, env):
        process_environment = (
            QProcessEnvironment.systemEnvironment()
        )

        for key, value in env.items():
            process_environment.insert(
                key,
                value,
            )

        return process_environment

    def _build_environment(self):
        env = os.environ.copy()

        existing_pythonpath = env.get(
            "PYTHONPATH",
            "",
        )

        python_paths = [
            str(SRC_ROOT),
            str(PROJECT_ROOT),
        ]

        if existing_pythonpath:
            python_paths.append(
                existing_pythonpath
            )

        env["PYTHONPATH"] = (
            os.pathsep.join(python_paths)
        )

        env["PYTHONUNBUFFERED"] = "1"

        return env

    def start(self):
        if not self.parse_script_path.exists():
            self._show_error(
                "קובץ ה-PARSER לא נמצא",
                self.parse_script_path,
            )
            return

        if not self.index_script_path.exists():
            self._show_error(
                "קובץ ה-INDEXER לא נמצא",
                self.index_script_path,
            )
            return

        self.append_line(
            "============================================================"
        )

        self.append_line(
            "ALCALAY - GMAIL INDEX"
        )

        self.append_line(
            "============================================================"
        )

        self.append_line("")

        self.append_line(
            f"[PROCESS] Python: {sys.executable}"
        )

        self.append_line(
            f"[PROCESS] Gmail account: {self.account_email}"
        )

        self.append_line(
            f"[PROCESS] Working directory: {PROJECT_ROOT}"
        )

        self.append_line("")

        self.append_line(
            "[WORKFLOW] INDEX started."
        )

        self.append_line(
            "[WORKFLOW] First: PARSE"
        )

        self.append_line(
            "[WORKFLOW] Second: INDEX"
        )

        self.append_line("")

        self.start_parser()

    def start_parser(self):
        self.current_stage = "PARSE"

        self.title.setText(
            "Gmail INDEX — שלב 1 מתוך 2: PARSE"
        )

        self.status_label.setText(
            "מפרש את המיילים שעדיין לא נותחו..."
        )

        self.append_line(
            "============================================================"
        )

        self.append_line(
            "ALCALAY - GMAIL PARSE"
        )

        self.append_line(
            "============================================================"
        )

        self.append_line("")

        self.append_line(
            f"[PROCESS] Python: {sys.executable}"
        )

        self.append_line(
            f"[PROCESS] Script: {self.parse_script_path}"
        )

        self.append_line(
            f"[PROCESS] Working directory: {PROJECT_ROOT}"
        )

        self.append_line("")

        self.append_line(
            "[PROCESS] Starting gmail_parser.py..."
        )

        self.append_line(
            f"[PROCESS] Account: {self.account_email}"
        )

        self.append_line("")

        env = self._build_environment()

        self.process = QProcess(self)

        self.process.setWorkingDirectory(
            str(PROJECT_ROOT)
        )

        self.process.setProcessEnvironment(
            self._create_process_environment(env)
        )

        self.process.setProgram(
            sys.executable
        )

        # IMPORTANT:
        # gmail_parser.py requires --account.
        #
        # This was the source of the previous:
        #
        # gmail_parser.py: error:
        # the following arguments are required: --account
        #
        # Therefore --account is explicitly passed here.
        self.process.setArguments(
            [
                "-u",
                str(self.parse_script_path),
                "--account",
                self.account_email,
            ]
        )

        self.process.readyReadStandardOutput.connect(
            self._read_stdout
        )

        self.process.readyReadStandardError.connect(
            self._read_stderr
        )

        self.process.finished.connect(
            self._process_finished
        )

        self.process.errorOccurred.connect(
            self._process_error
        )

        self.process.start()

        if not self.process.waitForStarted(5000):
            self.append_line("")
            self.append_line(
                "[ERROR] Could not start gmail_parser.py."
            )

            self.status_label.setText(
                "שגיאה בהפעלת PARSE"
            )

            self.stop_button.setEnabled(False)
            self.close_button.setEnabled(True)

    def start_indexer(self):
        self.current_stage = "INDEX"

        self.title.setText(
            "Gmail INDEX — שלב 2 מתוך 2: INDEX"
        )

        self.status_label.setText(
            "מאנדקס את המיילים שנותחו..."
        )

        self.append_line("")
        self.append_line(
            "============================================================"
        )

        self.append_line(
            "ALCALAY - GMAIL INDEXER"
        )

        self.append_line(
            "============================================================"
        )

        self.append_line("")

        self.append_line(
            f"[PROCESS] Python: {sys.executable}"
        )

        self.append_line(
            f"[PROCESS] Script: {self.index_script_path}"
        )

        self.append_line(
            f"[PROCESS] Working directory: {PROJECT_ROOT}"
        )

        self.append_line("")

        self.append_line(
            "[PROCESS] Starting gmail_indexer.py..."
        )

        self.append_line("")

        env = self._build_environment()

        self.process = QProcess(self)

        self.process.setWorkingDirectory(
            str(PROJECT_ROOT)
        )

        self.process.setProcessEnvironment(
            self._create_process_environment(env)
        )

        self.process.setProgram(
            sys.executable
        )

        self.process.setArguments(
            [
                "-u",
                str(self.index_script_path),
            ]
        )

        self.process.readyReadStandardOutput.connect(
            self._read_stdout
        )

        self.process.readyReadStandardError.connect(
            self._read_stderr
        )

        self.process.finished.connect(
            self._process_finished
        )

        self.process.errorOccurred.connect(
            self._process_error
        )

        self.process.start()

        if not self.process.waitForStarted(5000):
            self.append_line("")
            self.append_line(
                "[ERROR] Could not start gmail_indexer.py."
            )

            self.status_label.setText(
                "שגיאה בהפעלת INDEX"
            )

            self.stop_button.setEnabled(False)
            self.close_button.setEnabled(True)

    def _read_stdout(self):
        if self.process is None:
            return

        data = (
            self.process.readAllStandardOutput()
        )

        if not data:
            return

        text = bytes(data).decode(
            "utf-8",
            errors="replace",
        )

        self.append_output(text)

    def _read_stderr(self):
        if self.process is None:
            return

        data = (
            self.process.readAllStandardError()
        )

        if not data:
            return

        text = bytes(data).decode(
            "utf-8",
            errors="replace",
        )

        self.append_output(text)

    def _process_error(self, error):
        self.append_line("")
        self.append_line(
            "[PROCESS ERROR] "
            + str(error)
        )

        if self.current_stage == "PARSE":
            self.status_label.setText(
                "שגיאה בתהליך PARSE"
            )
        else:
            self.status_label.setText(
                "שגיאה בתהליך INDEX"
            )

    def _process_finished(
        self,
        exit_code,
        exit_status,
    ):
        self._read_stdout()
        self._read_stderr()

        stage = self.current_stage

        self.process_finished = True

        self.append_line("")
        self.append_line(
            "============================================================"
        )

        if self.stop_requested:
            self.append_line(
                f"[PROCESS] Gmail {stage} stopped by user."
            )

            self.status_label.setText(
                f"{stage} הופסק על ידי המשתמש"
            )

            self.stop_button.setEnabled(False)
            self.close_button.setEnabled(True)

            if self.parent_window is not None:
                self.parent_window.statusBar().showMessage(
                    f"Gmail {stage} הופסק"
                )

            return

        if exit_code != 0:
            self.append_line(
                f"[PROCESS] Gmail {stage} finished "
                f"with exit code {exit_code}."
            )

            self.status_label.setText(
                f"{stage} הסתיים עם שגיאה"
            )

            self.stop_button.setEnabled(False)
            self.close_button.setEnabled(True)

            if self.parent_window is not None:
                self.parent_window.statusBar().showMessage(
                    f"Gmail {stage} הסתיים עם שגיאה"
                )

            self.append_line(
                "============================================================"
            )

            return

        if stage == "PARSE":
            self.append_line(
                "[PROCESS] Gmail PARSE completed successfully."
            )

            self.append_line(
                "[WORKFLOW] PARSE completed."
            )

            self.append_line(
                "[WORKFLOW] Starting INDEX automatically..."
            )

            self.append_line(
                "============================================================"
            )

            self.status_label.setText(
                "PARSE הסתיים בהצלחה — עובר אוטומטית ל-INDEX..."
            )

            self.process.deleteLater()
            self.process = None

            QTimer.singleShot(
                250,
                self.start_indexer,
            )

            return

        self.append_line(
            "[PROCESS] Gmail INDEX completed successfully."
        )

        self.append_line(
            "[WORKFLOW] PARSE + INDEX completed successfully."
        )

        self.append_line(
            "============================================================"
        )

        self.status_label.setText(
            "PARSE ו-INDEX הסתיימו בהצלחה"
        )

        self.stop_button.setEnabled(False)

        if self.parent_window is not None:
            self.parent_window.statusBar().showMessage(
                "Gmail PARSE ו-INDEX הסתיימו בהצלחה"
            )

        # Automatic close after successful INDEX.
        QTimer.singleShot(
            1200,
            self._close_successfully,
        )

    def _close_successfully(self):
        self.accept()

    def _show_error(self, title, path):
        self.append_line("")
        self.append_line(
            f"[ERROR] {title}:"
        )
        self.append_line(
            str(path)
        )

        self.status_label.setText(
            title
        )

        self.stop_button.setEnabled(False)
        self.close_button.setEnabled(True)

    def stop_process(self):
        if self.process is None:
            return

        if self.process.state() == QProcess.NotRunning:
            return

        answer = QMessageBox.question(
            self,
            "עצירת תהליך",
            "תהליך Gmail עדיין מתבצע.\n\n"
            "האם אתה בטוח שברצונך לעצור אותו?",
            QMessageBox.Yes
            | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        self.stop_requested = True

        self.status_label.setText(
            "עוצר את התהליך..."
        )

        self.append_line("")
        self.append_line(
            "[USER] Stop requested."
        )

        self.stop_button.setEnabled(False)

        self.process.terminate()

        if not self.process.waitForFinished(2000):
            self.append_line(
                "[PROCESS] Normal termination timed out."
            )

            self.append_line(
                "[PROCESS] Killing process..."
            )

            self.process.kill()

            self.process.waitForFinished(2000)

    def closeEvent(self, event):
        if (
            self.process is not None
            and self.process.state()
            != QProcess.NotRunning
        ):
            answer = QMessageBox.question(
                self,
                "תהליך עדיין מתבצע",
                "תהליך Gmail עדיין מתבצע.\n\n"
                "האם לסגור את החלון ולהפסיק את התהליך?",
                QMessageBox.Yes
                | QMessageBox.No,
                QMessageBox.No,
            )

            if answer != QMessageBox.Yes:
                event.ignore()
                return

            self.stop_requested = True

            self.process.terminate()

            if not self.process.waitForFinished(2000):
                self.process.kill()

                self.process.waitForFinished(2000)

        event.accept()


class GoogleLauncherPage(QWidget):
    def __init__(self, main_window):
        super().__init__()

        self.main_window = main_window

        self.setLayoutDirection(
            Qt.RightToLeft
        )

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            30,
            30,
            30,
            30,
        )

        layout.setSpacing(20)

        title = QLabel(
            "Google / Gmail"
        )

        title.setObjectName(
            "pageTitle"
        )

        title.setAlignment(
            Qt.AlignRight
        )

        subtitle = QLabel(
            "עבודה עם Gmail בשלושה שלבים: "
            "בחירת חשבון ותגיות → ייבוא → PARSE + INDEX"
        )

        subtitle.setObjectName(
            "pageSubtitle"
        )

        subtitle.setAlignment(
            Qt.AlignRight
        )

        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)

        cards_layout = QHBoxLayout()

        cards_layout.setSpacing(20)

        cards_layout.addWidget(
            self.create_card(
                "1. חשבונות ותגיות",
                "הצגת חשבונות Gmail הקיימים במערכת, "
                "בחירת חשבון והצגת ובחירת התגיות שלו.",
                "חשבונות ותגיות",
                self.main_window.open_gmail_window,
            )
        )

        cards_layout.addWidget(
            self.create_card(
                "2. ייבוא מיילים",
                "ייבוא המיילים מהחשבון והתגיות שנבחרו "
                "לאחסון המקומי של Alcalay.",
                "ייבוא מיילים",
                self.main_window.open_gmail_import,
            )
        )

        cards_layout.addWidget(
            self.create_card(
                "3. אינדוקס מיילים",
                "בעת בחירת אינדוקס המערכת מבצעת קודם "
                "PARSE לכל המיילים שעדיין לא נותחו, "
                "ולאחר מכן INDEX. החלון נסגר אוטומטית "
                "בסיום מוצלח.",
                "אינדוקס מיילים",
                self.main_window.open_gmail_indexer,
            )
        )

        cards_layout.addWidget(
            self.create_card(
                "חיפוש במיילים",
                "חיפוש במידע שנאסף מהמיילים "
                "באמצעות מנגנון החיפוש של Alcalay.",
                "חיפוש במיילים",
                self.main_window.open_gmail_search,
            )
        )

        layout.addLayout(cards_layout)
        layout.addStretch()

    def create_card(
        self,
        title_text,
        description_text,
        button_text,
        callback,
    ):
        card = QFrame()

        card.setObjectName("card")

        card.setMinimumWidth(250)
        card.setMaximumWidth(360)

        layout = QVBoxLayout(card)

        layout.setContentsMargins(
            20,
            20,
            20,
            20,
        )

        layout.setSpacing(12)

        title = QLabel(title_text)

        title.setObjectName(
            "cardTitle"
        )

        title.setAlignment(
            Qt.AlignRight
        )

        title.setWordWrap(True)

        description = QLabel(
            description_text
        )

        description.setObjectName(
            "cardDescription"
        )

        description.setAlignment(
            Qt.AlignRight
        )

        description.setWordWrap(True)

        button = QPushButton(
            button_text
        )

        button.setObjectName(
            "primaryButton"
        )

        button.clicked.connect(callback)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addStretch()
        layout.addWidget(button)

        return card


class PlaceholderPage(QWidget):
    def __init__(
        self,
        title_text,
        description_text,
    ):
        super().__init__()

        self.setLayoutDirection(
            Qt.RightToLeft
        )

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            40,
            40,
            40,
            40,
        )

        layout.setSpacing(15)

        title = QLabel(title_text)

        title.setObjectName(
            "pageTitle"
        )

        title.setAlignment(
            Qt.AlignRight
        )

        description = QLabel(
            description_text
        )

        description.setObjectName(
            "pageSubtitle"
        )

        description.setAlignment(
            Qt.AlignRight
        )

        description.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(description)
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
            Qt.RightToLeft
        )

        self.stack = QStackedWidget()

        self.pages = {}

        self.google_page = GoogleLauncherPage(
            self
        )

        self.pages[1] = self.google_page

        self.pages[2] = PlaceholderPage(
            "מסמכים",
            "ניהול מסמכים ומקורות מידע.",
        )

        self.pages[3] = PlaceholderPage(
            "חיפוש",
            "חיפוש במסמכים ובמידע המאונדקס.",
        )

        self.pages[4] = PlaceholderPage(
            "ניהול משתמשים",
            "ניהול משתמשים במערכת.",
        )

        self.pages[5] = PlaceholderPage(
            "הרשאות",
            "ניהול הרשאות וגישה למידע.",
        )

        self.pages[6] = PlaceholderPage(
            "מסד נתונים",
            "חיבור וניהול מסדי הנתונים.",
        )

        self.pages[7] = PlaceholderPage(
            "הורדות",
            "ניהול הורדות ואחסון מקומי.",
        )

        self.pages[8] = PlaceholderPage(
            "הגדרות",
            "הגדרות המערכת.",
        )

        self.pages[9] = PlaceholderPage(
            "מערכת",
            "כלי מערכת ותחזוקה.",
        )

        self.pages[10] = PlaceholderPage(
            "רענון והוספת מסמכים מהמייל",
            "תהליך העבודה עם Gmail: "
            "בחירת חשבון ותגיות → ייבוא → PARSE → INDEX.",
        )

        for page in self.pages.values():
            self.stack.addWidget(page)

        self.menu_buttons = {}

        central = QWidget()

        central_layout = QHBoxLayout(
            central
        )

        central_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        central_layout.setSpacing(0)

        menu = self.create_menu()

        central_layout.addWidget(
            self.stack,
            1,
        )

        central_layout.addWidget(
            menu
        )

        self.setCentralWidget(central)

        self.statusBar().showMessage(
            "Alcalay מוכן"
        )

        self.show_page(1)

    def create_menu(self):
        menu = QFrame()

        menu.setObjectName(
            "sideMenu"
        )

        menu.setFixedWidth(260)

        layout = QVBoxLayout(menu)

        layout.setContentsMargins(
            15,
            20,
            15,
            20,
        )

        layout.setSpacing(8)

        title = QLabel("ALCALAY")

        title.setObjectName(
            "menuTitle"
        )

        title.setAlignment(
            Qt.AlignCenter
        )

        layout.addWidget(title)

        layout.addSpacing(15)

        for number, text in MENU_ITEMS:
            button = QPushButton(
                f"{number}. {text}"
            )

            button.setObjectName(
                "menuButton"
            )

            button.setMinimumHeight(45)

            button.clicked.connect(
                lambda checked=False,
                page_number=number:
                self.show_page(page_number)
            )

            self.menu_buttons[number] = button

            layout.addWidget(button)

        layout.addStretch()

        return menu

    def show_page(self, page_number):
        if page_number not in self.pages:
            return

        page = self.pages[page_number]

        self.stack.setCurrentWidget(page)

        for number, button in self.menu_buttons.items():
            button.setProperty(
                "selected",
                number == page_number,
            )

            button.style().unpolish(button)
            button.style().polish(button)

        self.statusBar().showMessage(
            MENU_ITEMS[page_number - 1][1]
        )

    def open_gmail_window(self):
        try:
            self.gmail_window = GmailWindow(self)

            self.gmail_window.setWindowModality(
                Qt.ApplicationModal
            )

            self.gmail_window.show()

            self.gmail_window.raise_()
            self.gmail_window.activateWindow()

            self.statusBar().showMessage(
                "שלב 1: חשבונות Gmail ותגיות"
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "שגיאה",
                f"לא ניתן לפתוח את ניהול Gmail:\n\n{exc}",
            )

    def open_gmail_search(self):
        try:
            self.gmail_search_window = (
                GmailSearchWindow(self)
            )

            self.gmail_search_window.setWindowModality(
                Qt.ApplicationModal
            )

            self.gmail_search_window.show()

            self.gmail_search_window.raise_()
            self.gmail_search_window.activateWindow()

            self.statusBar().showMessage(
                "חיפוש במיילים"
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "שגיאה",
                f"לא ניתן לפתוח את חיפוש Gmail:\n\n{exc}",
            )

    def _get_subprocess_environment(self):
        env = os.environ.copy()

        existing_pythonpath = env.get(
            "PYTHONPATH",
            "",
        )

        python_paths = [
            str(SRC_ROOT),
            str(PROJECT_ROOT),
        ]

        if existing_pythonpath:
            python_paths.append(
                existing_pythonpath
            )

        env["PYTHONPATH"] = (
            os.pathsep.join(python_paths)
        )

        env["PYTHONUNBUFFERED"] = "1"

        return env

    def open_gmail_import(self):
        script_path = (
            PROJECT_ROOT
            / "src"
            / "gmail"
            / "gmail_copy.py"
        )

        if not script_path.exists():
            QMessageBox.critical(
                self,
                "קובץ חסר",
                f"קובץ הייבוא לא נמצא:\n\n{script_path}",
            )

            return

        answer = QMessageBox.question(
            self,
            "ייבוא מיילים",
            "להפעיל את שלב 2 - ייבוא המיילים "
            "לפי חשבון ותגיות Gmail שהוגדרו?",
            QMessageBox.Yes
            | QMessageBox.No,
            QMessageBox.Yes,
        )

        if answer != QMessageBox.Yes:
            return

        try:
            self.gmail_import_window = (
                GmailImportWindow(self)
            )

            self.gmail_import_window.setModal(False)

            self.gmail_import_window.setWindowModality(
                Qt.NonModal
            )

            self.gmail_import_window.show()

            self.gmail_import_window.raise_()
            self.gmail_import_window.activateWindow()

            self.statusBar().showMessage(
                "שלב 2: ייבוא מיילים מתבצע"
            )

            self.gmail_import_window.start()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "שגיאה",
                f"לא ניתן להפעיל את ייבוא Gmail:\n\n{exc}",
            )

    def open_gmail_indexer(self):
        """
        Start the complete Gmail INDEX workflow.

        The workflow is:

            PARSE
              ↓
            INDEX
              ↓
            automatic window close

        The parser receives --account explicitly.
        """

        parse_script_path = (
            PROJECT_ROOT
            / "src"
            / "gmail"
            / "gmail_parser.py"
        )

        index_script_path = (
            PROJECT_ROOT
            / "src"
            / "gmail"
            / "gmail_indexer.py"
        )

        if not parse_script_path.exists():
            QMessageBox.critical(
                self,
                "קובץ חסר",
                f"קובץ ה-PARSE לא נמצא:\n\n"
                f"{parse_script_path}",
            )

            return

        if not index_script_path.exists():
            QMessageBox.critical(
                self,
                "קובץ חסר",
                f"קובץ ה-INDEX לא נמצא:\n\n"
                f"{index_script_path}",
            )

            return

        try:
            self.gmail_index_window = (
                GmailIndexWindow(self)
            )

            self.gmail_index_window.setModal(False)

            self.gmail_index_window.setWindowModality(
                Qt.NonModal
            )

            self.gmail_index_window.show()

            self.gmail_index_window.raise_()
            self.gmail_index_window.activateWindow()

            self.statusBar().showMessage(
                "Gmail INDEX: מתחיל PARSE..."
            )

            self.gmail_index_window.start()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "שגיאה",
                f"לא ניתן להפעיל את Gmail INDEX:\n\n{exc}",
            )


def apply_styles(app):
    app.setStyleSheet(
        """
        QMainWindow {
            background: #f4f5f7;
        }

        QWidget {
            font-family: Arial;
            font-size: 14px;
        }

        #sideMenu {
            background: #20242a;
        }

        #menuTitle {
            color: white;
            font-size: 24px;
            font-weight: bold;
            padding: 10px;
        }

        #menuButton {
            background: transparent;
            color: #d9dde3;
            border: none;
            border-radius: 6px;
            padding: 10px;
            text-align: right;
            font-size: 14px;
        }

        #menuButton:hover {
            background: #30363d;
            color: white;
        }

        #menuButton[selected="true"] {
            background: #3b4350;
            color: white;
            font-weight: bold;
        }

        #pageTitle {
            font-size: 30px;
            font-weight: bold;
            color: #20242a;
        }

        #pageSubtitle {
            font-size: 16px;
            color: #606872;
        }

        #card {
            background: white;
            border: 1px solid #d9dde3;
            border-radius: 10px;
        }

        #cardTitle {
            font-size: 19px;
            font-weight: bold;
            color: #20242a;
        }

        #cardDescription {
            color: #606872;
            font-size: 14px;
        }

        #primaryButton {
            background: #2f6fed;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 10px 15px;
            font-weight: bold;
        }

        #primaryButton:hover {
            background: #245dcc;
        }

        #primaryButton:pressed {
            background: #1e4fae;
        }

        QStatusBar {
            background: #e9ebef;
            color: #40464f;
        }

        #gmailImportTitle {
            font-size: 25px;
            font-weight: bold;
            color: #20242a;
        }

        #gmailImportStatus {
            font-size: 15px;
            font-weight: bold;
            color: #40464f;
            padding-bottom: 5px;
        }

        #gmailImportOutput {
            background: #111418;
            color: #e6e9ed;
            border: 1px solid #343a40;
            border-radius: 7px;
            padding: 10px;
            font-family: Menlo, Monaco, Consolas, monospace;
            font-size: 12px;
        }

        #gmailImportInputFrame {
            background: #e9ebef;
            border: 1px solid #cdd2d8;
            border-radius: 7px;
        }

        #gmailImportInputLabel {
            font-weight: bold;
            color: #30353b;
        }

        #gmailImportInput {
            background: white;
            color: #20242a;
            border: 1px solid #aeb4bc;
            border-radius: 5px;
            padding: 8px;
            font-family: Menlo, Monaco, Consolas, monospace;
        }

        #gmailImportInput:focus {
            border: 2px solid #2f6fed;
        }

        #gmailImportSendButton {
            background: #2f6fed;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 8px 18px;
            font-weight: bold;
        }

        #gmailImportSendButton:disabled {
            background: #aeb4bc;
            color: #e8eaed;
        }

        #gmailImportYesButton {
            background: #2e8b57;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 8px 20px;
            font-weight: bold;
        }

        #gmailImportYesButton:disabled {
            background: #aeb4bc;
            color: #e8eaed;
        }

        #gmailImportNoButton {
            background: #b23b3b;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 8px 20px;
            font-weight: bold;
        }

        #gmailImportNoButton:disabled {
            background: #aeb4bc;
            color: #e8eaed;
        }

        #gmailImportCloseButton {
            background: #2f6fed;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 10px 25px;
            font-weight: bold;
            min-width: 120px;
        }

        #gmailImportCloseButton:hover {
            background: #245dcc;
        }

        #gmailImportCloseButton:disabled {
            background: #aeb4bc;
            color: #e8eaed;
        }

        #gmailIndexTitle {
            font-size: 22px;
            font-weight: bold;
            color: #20242a;
        }

        #gmailIndexStatus {
            font-size: 14px;
            font-weight: bold;
            color: #40464f;
            padding-bottom: 3px;
        }

        #gmailIndexOutput {
            background: #111418;
            color: #e6e9ed;
            border: 1px solid #343a40;
            border-radius: 7px;
            padding: 8px;
            font-family: Menlo, Monaco, Consolas, monospace;
            font-size: 11px;
        }

        #gmailIndexStopButton {
            background: #b23b3b;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 8px 22px;
            font-weight: bold;
            min-width: 100px;
        }

        #gmailIndexStopButton:hover {
            background: #982f2f;
        }

        #gmailIndexStopButton:pressed {
            background: #7f2626;
        }

        #gmailIndexStopButton:disabled {
            background: #aeb4bc;
            color: #e8eaed;
        }

        #gmailIndexCloseButton {
            background: #2f6fed;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 8px 22px;
            font-weight: bold;
            min-width: 100px;
        }

        #gmailIndexCloseButton:hover {
            background: #245dcc;
        }

        #gmailIndexCloseButton:disabled {
            background: #aeb4bc;
            color: #e8eaed;
        }
        """
    )


def main():
    app = QApplication(sys.argv)

    app.setApplicationName(
        "Alcalay"
    )

    app.setOrganizationName(
        "Alcalay"
    )

    apply_styles(app)

    window = MainWindow()

    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()