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
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
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
    """
    GUI wrapper around gmail_copy.py.

    IMPORTANT:
        gmail_copy.py owns the complete interactive COPY logic.

        This window does NOT:
        - choose Labels
        - automatically send --labels
        - automatically send --yes
        - duplicate the COPY confirmation logic

        The GUI only:
        1. starts gmail_copy.py
        2. displays stdout/stderr
        3. detects when gmail_copy.py is waiting for input
        4. sends the user's input to gmail_copy.py stdin
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(
            "Alcalay - ייבוא מיילים מ-Gmail"
        )
        self.setWindowModality(Qt.NonModal)
        self.resize(1100, 760)

        self.process = None
        self.process_finished = False

        self.awaiting_label_input = False
        self.awaiting_copy_confirmation = False

        self.last_prompt_signature = ""
        self.stdout_buffer = ""
        self.stderr_buffer = ""

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel(
            "ייבוא מיילים מ-Gmail"
        )
        title.setObjectName("windowTitle")
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

        # --------------------------------------------------------------
        # Main COPY output
        # --------------------------------------------------------------

        output_frame = QFrame()
        output_frame.setObjectName(
            "inputFrame"
        )

        output_layout = QVBoxLayout(
            output_frame
        )
        output_layout.setContentsMargins(
            12,
            12,
            12,
            12,
        )
        output_layout.setSpacing(8)

        output_title = QLabel(
            "Gmail COPY - פלט מלא"
        )
        output_title.setObjectName(
            "inputLabel"
        )
        output_layout.addWidget(
            output_title
        )

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(
            QPlainTextEdit.NoWrap
        )

        output_layout.addWidget(
            self.output
        )

        layout.addWidget(
            output_frame,
            1,
        )

        # --------------------------------------------------------------
        # Interactive input
        # --------------------------------------------------------------

        input_frame = QFrame()
        input_frame.setObjectName(
            "inputFrame"
        )

        input_layout = QVBoxLayout(
            input_frame
        )
        input_layout.setContentsMargins(
            12,
            12,
            12,
            12,
        )
        input_layout.setSpacing(8)

        self.input_label = QLabel(
            "קלט"
        )
        self.input_label.setObjectName(
            "inputLabel"
        )
        input_layout.addWidget(
            self.input_label
        )

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText(
            "המתן לבקשת קלט מ-Gmail COPY..."
        )
        self.input_edit.returnPressed.connect(
            self.send_input
        )

        input_row.addWidget(
            self.input_edit,
            1,
        )

        self.send_button = QPushButton(
            "שלח"
        )
        self.send_button.clicked.connect(
            self.send_input
        )

        input_row.addWidget(
            self.send_button
        )

        input_layout.addLayout(
            input_row
        )

        self.input_hint = QLabel(
            "כאשר gmail_copy.py יבקש קלט, "
            "השדה כאן יופעל."
        )
        self.input_hint.setObjectName(
            "inputHint"
        )
        input_layout.addWidget(
            self.input_hint
        )

        layout.addWidget(
            input_frame
        )

        # --------------------------------------------------------------
        # Buttons
        # --------------------------------------------------------------

        button_row = QHBoxLayout()

        self.start_button = QPushButton(
            "התחל Gmail COPY"
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
        self.stop_button.setEnabled(
            False
        )
        self.stop_button.clicked.connect(
            self.stop_process
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

        self._disable_input_controls()

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Input controls
    # ------------------------------------------------------------------

    def _enable_text_input(
        self,
        label,
        hint,
    ):
        self.input_label.setText(
            label
        )

        self.input_hint.setText(
            hint
        )

        self.input_edit.setEnabled(
            True
        )

        self.send_button.setEnabled(
            True
        )

        self.input_edit.setFocus()

    def _disable_input_controls(self):
        self.input_edit.setEnabled(
            False
        )

        self.send_button.setEnabled(
            False
        )

    # ------------------------------------------------------------------
    # Prompt detection
    # ------------------------------------------------------------------

    def _detect_prompt(self):
        """
        Detect the actual prompts emitted by gmail_copy.py.

        Current gmail_copy.py uses:

            Labels להעתקה:

        and:

            להמשיך ל-COPY? הקלד YES לאישור:

        The detection is intentionally based on the actual text
        produced by gmail_copy.py rather than duplicating its logic.
        """

        text = (
            self.stdout_buffer
            + self.stderr_buffer
        )

        if not text:
            return None

        lower_text = text.lower()

        # --------------------------------------------------------------
        # Label selection
        # --------------------------------------------------------------

        label_patterns = (
            "labels להעתקה:",
            "labels להעתקה",
        )

        label_positions = []

        for pattern in label_patterns:
            position = lower_text.rfind(
                pattern.lower()
            )

            if position >= 0:
                label_positions.append(
                    (
                        position,
                        pattern,
                    )
                )

        # --------------------------------------------------------------
        # YES confirmation
        # --------------------------------------------------------------

        confirmation_patterns = (
            "להמשיך ל-copy? הקלד yes לאישור:",
            "להמשיך ל-copy?",
            "הקלד yes לאישור:",
        )

        confirmation_positions = []

        for pattern in confirmation_patterns:
            position = lower_text.rfind(
                pattern.lower()
            )

            if position >= 0:
                confirmation_positions.append(
                    (
                        position,
                        pattern,
                    )
                )

        candidates = []

        for position, pattern in label_positions:
            candidates.append(
                (
                    position,
                    "labels",
                    pattern,
                )
            )

        for position, pattern in confirmation_positions:
            candidates.append(
                (
                    position,
                    "confirmation",
                    pattern,
                )
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: item[0]
        )

        return candidates[-1]

    def _check_for_input_prompt(self):
        if self.process is None:
            return

        if (
            self.process.state()
            == QProcess.ProcessState.NotRunning
        ):
            return

        prompt = self._detect_prompt()

        if prompt is None:
            return

        position, prompt_type, prompt_text = (
            prompt
        )

        signature = (
            f"{prompt_type}:"
            f"{position}:"
            f"{prompt_text}"
        )

        if (
            signature
            == self.last_prompt_signature
        ):
            return

        self.last_prompt_signature = (
            signature
        )

        # --------------------------------------------------------------
        # Label input
        # --------------------------------------------------------------

        if prompt_type == "labels":
            self.awaiting_label_input = True
            self.awaiting_copy_confirmation = False

            self._enable_text_input(
                "מספרי התגיות להעתקה",
                "לדוגמה: 1,3,7 או 1-5. "
                "אפשר גם ALL או 0.",
            )

            self.status_label.setText(
                "Gmail COPY ממתין לבחירת תגיות."
            )

            return

        # --------------------------------------------------------------
        # YES confirmation
        # --------------------------------------------------------------

        if prompt_type == "confirmation":
            self.awaiting_label_input = False
            self.awaiting_copy_confirmation = True

            self._enable_text_input(
                "אישור COPY",
                "הקלד YES כדי להתחיל את ה-COPY "
                "או NO כדי לבטל.",
            )

            self.status_label.setText(
                "Gmail COPY ממתין לאישור YES."
            )

    # ------------------------------------------------------------------
    # Sending input
    # ------------------------------------------------------------------

    def _validate_label_input(self, value):
        """
        Only a light GUI validation.

        The real validation remains inside gmail_copy.py.
        """

        value = value.strip()

        if not value:
            return False

        if value.upper() in (
            "ALL",
            "0",
        ):
            return True

        pattern = (
            r"^\d+(?:\s*-\s*\d+)?"
            r"(?:\s*,\s*\d+(?:\s*-\s*\d+)?)*$"
        )

        return (
            re.fullmatch(
                pattern,
                value,
            )
            is not None
        )

    def send_input(self):
        if self.process is None:
            QMessageBox.warning(
                self,
                "Gmail COPY",
                "Gmail COPY אינו פעיל.",
            )
            return

        if (
            self.process.state()
            == QProcess.ProcessState.NotRunning
        ):
            QMessageBox.warning(
                self,
                "Gmail COPY",
                "Gmail COPY כבר הסתיים.",
            )
            return

        value = (
            self.input_edit.text()
            .strip()
        )

        if not value:
            return

        # --------------------------------------------------------------
        # Label selection
        # --------------------------------------------------------------

        if self.awaiting_label_input:
            if not self._validate_label_input(
                value
            ):
                QMessageBox.warning(
                    self,
                    "קלט לא תקין",
                    "הזן מספרי תגיות לדוגמה:\n\n"
                    "1,3,7\n"
                    "1-5\n"
                    "1-3,7\n\n"
                    "או ALL / 0.",
                )

                self.input_edit.selectAll()
                self.input_edit.setFocus()
                return

            self._write_to_process(
                value
            )

            self.awaiting_label_input = False

            self._disable_input_controls()

            self.input_edit.clear()

            self.status_label.setText(
                "בחירת התגיות נשלחה ל-Gmail COPY."
            )

            return

        # --------------------------------------------------------------
        # YES / NO
        # --------------------------------------------------------------

        if self.awaiting_copy_confirmation:
            answer = value.upper()

            if answer not in (
                "YES",
                "NO",
            ):
                QMessageBox.warning(
                    self,
                    "קלט לא תקין",
                    "יש להקליד YES או NO.",
                )

                self.input_edit.selectAll()
                self.input_edit.setFocus()
                return

            self._write_to_process(
                answer
            )

            self.awaiting_copy_confirmation = False

            self._disable_input_controls()

            self.input_edit.clear()

            if answer == "YES":
                self.status_label.setText(
                    "YES נשלח. Gmail COPY מתחיל."
                )
            else:
                self.status_label.setText(
                    "NO נשלח. Gmail COPY יבוטל."
                )

            return

        QMessageBox.information(
            self,
            "Gmail COPY",
            "כרגע gmail_copy.py אינו ממתין לקלט.",
        )

    def _write_to_process(self, text):
        if self.process is None:
            return

        if (
            self.process.state()
            == QProcess.ProcessState.NotRunning
        ):
            return

        data = (
            text + "\n"
        ).encode(
            "utf-8"
        )

        self.process.write(
            data
        )

        self.process.waitForBytesWritten(
            2000
        )

        self._append_output(
            "\n[GUI INPUT] "
            + text
            + "\n"
        )

    # ------------------------------------------------------------------
    # Process environment
    # ------------------------------------------------------------------

    def _create_process_environment(self):
        environment = (
            QProcessEnvironment
            .systemEnvironment()
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
            os.pathsep.join(
                paths
            ),
        )

        environment.insert(
            "PYTHONUNBUFFERED",
            "1",
        )

        return environment

    # ------------------------------------------------------------------
    # Start Gmail COPY
    # ------------------------------------------------------------------

    def start(self):
        if (
            self.process is not None
            and self.process.state()
            != QProcess.ProcessState.NotRunning
        ):
            return

        script = (
            PROJECT_ROOT
            / "src"
            / "gmail"
            / "gmail_copy.py"
        )

        if not script.exists():
            QMessageBox.critical(
                self,
                "שגיאה",
                "קובץ Gmail COPY לא נמצא:\n"
                + str(script),
            )
            return

        self.process_finished = False

        self.awaiting_label_input = False
        self.awaiting_copy_confirmation = False

        self.last_prompt_signature = ""

        self.stdout_buffer = ""
        self.stderr_buffer = ""

        self.output.clear()
        self.input_edit.clear()

        self._disable_input_controls()

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
            "מפעיל gmail_copy.py..."
        )

        self.process = QProcess(
            self
        )

        self.process.setProcessEnvironment(
            self._create_process_environment()
        )

        self.process.setWorkingDirectory(
            str(PROJECT_ROOT)
        )

        self.process.setProcessChannelMode(
            QProcess.SeparateChannels
        )

        self.process.setProgram(
            sys.executable
        )

        # IMPORTANT:
        # We deliberately do NOT pass:
        #
        #   --labels
        #   --yes
        #
        # because gmail_copy.py itself owns the interactive
        # Label selection and YES confirmation.
        self.process.setArguments(
            [
                "-u",
                str(script),
                DEFAULT_GMAIL_ACCOUNT,
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

        self._append_output(
            "=" * 80
            + "\n"
            + "GMAIL COPY\n"
            + "=" * 80
            + "\n"
            + "Script: "
            + str(script)
            + "\n"
            + "Account: "
            + DEFAULT_GMAIL_ACCOUNT
            + "\n"
            + "-" * 80
            + "\n"
        )

        self.process.start()

        if not self.process.waitForStarted(
            5000
        ):
            self._append_output(
                "\n[ERROR] "
                "לא ניתן להפעיל את gmail_copy.py.\n"
            )

            self.status_label.setText(
                "לא ניתן להפעיל את Gmail COPY."
            )

            self.process = None

            self.start_button.setEnabled(
                True
            )

            self.stop_button.setEnabled(
                False
            )

            self.close_button.setEnabled(
                True
            )

    # ------------------------------------------------------------------
    # Read stdout
    # ------------------------------------------------------------------

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

        self.stdout_buffer += text

        self._append_output(
            text
        )

        # input() prints its prompt without necessarily
        # ending it with a newline. Therefore prompt detection
        # must happen after every stdout chunk.
        QTimer.singleShot(
            0,
            self._check_for_input_prompt,
        )

    # ------------------------------------------------------------------
    # Read stderr
    # ------------------------------------------------------------------

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

        self.stderr_buffer += text

        self._append_output(
            text
        )

        QTimer.singleShot(
            0,
            self._check_for_input_prompt,
        )

    # ------------------------------------------------------------------
    # Process errors
    # ------------------------------------------------------------------

    def _process_error(self, error):
        if (
            error
            == QProcess.ProcessError.FailedToStart
        ):
            message = (
                "לא ניתן להפעיל את gmail_copy.py."
            )
        else:
            message = (
                "שגיאת QProcess: "
                + str(error)
            )

        self._append_output(
            "\n[PROCESS ERROR] "
            + message
            + "\n"
        )

        self.status_label.setText(
            message
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

    # ------------------------------------------------------------------
    # Process finished
    # ------------------------------------------------------------------

    def _process_finished(
        self,
        exit_code,
        exit_status,
    ):
        self.process_finished = True

        self.awaiting_label_input = False
        self.awaiting_copy_confirmation = False

        self._disable_input_controls()

        self.stop_button.setEnabled(
            False
        )

        self.start_button.setEnabled(
            True
        )

        self.close_button.setEnabled(
            True
        )

        self._append_output(
            "\n"
            + "=" * 80
            + "\n"
            + "GMAIL COPY PROCESS FINISHED"
            + "\n"
            + f"exit_code={exit_code}"
            + "\n"
            + f"exit_status={exit_status}"
            + "\n"
            + "=" * 80
            + "\n"
        )

        if (
            exit_code == 0
            and exit_status
            == QProcess.ExitStatus.NormalExit
        ):
            self.status_label.setText(
                "Gmail COPY הסתיים."
            )
        else:
            self.status_label.setText(
                "Gmail COPY הסתיים עם שגיאה. "
                f"קוד: {exit_code}"
            )

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------

    def stop_process(self):
        if self.process is None:
            return

        if (
            self.process.state()
            == QProcess.ProcessState.NotRunning
        ):
            return

        answer = QMessageBox.question(
            self,
            "עצירת Gmail COPY",
            "האם לעצור את Gmail COPY?",
            QMessageBox.Yes
            | QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        self._append_output(
            "\n[GUI] מבקש לעצור את Gmail COPY...\n"
        )

        self.status_label.setText(
            "עוצר Gmail COPY..."
        )

        self.process.terminate()

        QTimer.singleShot(
            2000,
            self._force_stop_if_running,
        )

    def _force_stop_if_running(self):
        if (
            self.process is not None
            and self.process.state()
            != QProcess.ProcessState.NotRunning
        ):
            self._append_output(
                "[GUI] terminate לא הספיק. "
                "מבצע kill.\n"
            )

            self.process.kill()

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        if (
            self.process is not None
            and self.process.state()
            != QProcess.ProcessState.NotRunning
        ):
            answer = QMessageBox.question(
                self,
                "Gmail COPY",
                "Gmail COPY עדיין פועל.\n\n"
                "האם לעצור אותו ולסגור?",
                QMessageBox.Yes
                | QMessageBox.No,
            )

            if answer == QMessageBox.No:
                event.ignore()
                return

            self.process.terminate()

            if not self.process.waitForFinished(
                1500
            ):
                self.process.kill()
                self.process.waitForFinished(
                    1000
                )

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
            "font-size: 22px; "
            "font-weight: bold; "
            "padding: 8px;"
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
                f"{current_stage} הסתיים "
                f"עם שגיאה ({exit_code})."
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
                "PARSE הסתיים. "
                "מתחיל INDEX..."
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
                "תהליך עדיין פועל. "
                "לעצור ולסגור?",
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
            "font-size: 22px; "
            "font-weight: bold; "
            "padding: 8px;"
        )
        layout.addWidget(title)

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
            "font-size: 16px; "
            "font-weight: bold;"
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
            f"Starting Drive Sync: "
            f"{self.direction}"
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

        if line.startswith(
            prefix
        ):
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
        event_type = str(
            event.get(
                "event",
                "",
            )
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
                f"Repository: "
                f"{repository_id} | "
                f"Root folder: "
                f"{root_folder_id}"
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
                f"Candidates: "
                f"{self.total_items} | "
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
                    f"{index}/{total}  "
                    f"{name}"
                )
            else:
                self.status_label.setText(
                    name
                )

            self.log(
                f"[{index}/{total}] "
                f"{name}"
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
                "Google Drive reconnect error: "
                + str(exc)
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
                "הסנכרון עדיין פועל. "
                "לעצור ולסגור?",
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
            "font-size: 22px; "
            "font-weight: bold; "
            "padding: 8px;"
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
        super().__init__(
            parent
        )

        self.parent_window = parent

        layout = QVBoxLayout(
            self
        )

        title = QLabel(
            "Google"
        )
        title.setStyleSheet(
            "font-size: 28px; "
            "font-weight: bold; "
            "padding: 12px;"
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

        # Start immediately so that the user sees
        # the exact gmail_copy.py interaction in the GUI.
        window.start()

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
            "font-size: 28px; "
            "font-weight: bold;"
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

        QPlainTextEdit {
            padding: 8px;
        }

        QFrame#inputFrame {
            border: 1px solid #cccccc;
            border-radius: 5px;
        }

        QLabel#inputLabel {
            font-weight: bold;
        }

        QLabel#inputHint {
            color: #666666;
        }

        QLabel#statusLabel {
            font-weight: bold;
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