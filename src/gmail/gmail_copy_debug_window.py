# -*- coding: utf-8 -*-

import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QProcess, QProcessEnvironment, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
GMAIL_COPY = SRC_ROOT / "gmail" / "gmail_copy.py"

DEBUG_DIR = PROJECT_ROOT / "storage" / "gmail" / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

DEBUG_LOG = DEBUG_DIR / (
    f"gmail_copy_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
)


class GmailCopyDebugWindow(QDialog):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Alcalay - Gmail COPY DEBUG")
        self.resize(1200, 800)

        self.process = None
        self.start_time = None
        self.stop_requested = False

        self._build_ui()

        self._log("=" * 70)
        self._log("Alcalay Gmail COPY DEBUG")
        self._log(f"PROJECT_ROOT = {PROJECT_ROOT}")
        self._log(f"SRC_ROOT     = {SRC_ROOT}")
        self._log(f"GMAIL_COPY   = {GMAIL_COPY}")
        self._log(f"DEBUG_LOG    = {DEBUG_LOG}")
        self._log("=" * 70)

    # =========================================================
    # UI
    # =========================================================

    def _build_ui(self):

        layout = QVBoxLayout(self)

        info = QLabel(
            "Gmail COPY Debug\n"
            "כל stdout / stderr / שגיאות QProcess נרשמות עם timestamp."
        )
        layout.addWidget(info)

        self.command_label = QLabel(
            f"Script: {GMAIL_COPY}"
        )
        layout.addWidget(self.command_label)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.output, 1)

        input_row = QHBoxLayout()

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText(
            "הכנס תשובה ל-gmail_copy: למשל 1,4,7 או YES"
        )
        self.input_edit.returnPressed.connect(
            self.send_input
        )

        self.send_button = QPushButton("שלח")
        self.send_button.clicked.connect(
            self.send_input
        )

        input_row.addWidget(
            self.input_edit,
            1
        )

        input_row.addWidget(
            self.send_button
        )

        layout.addLayout(input_row)

        buttons = QHBoxLayout()

        self.start_button = QPushButton(
            "התחל Gmail COPY"
        )
        self.start_button.clicked.connect(
            self.start_process
        )

        self.stop_button = QPushButton(
            "עצור"
        )
        self.stop_button.clicked.connect(
            self.stop_process
        )
        self.stop_button.setEnabled(False)

        self.clear_button = QPushButton(
            "נקה"
        )
        self.clear_button.clicked.connect(
            self.output.clear
        )

        buttons.addWidget(
            self.start_button
        )

        buttons.addWidget(
            self.stop_button
        )

        buttons.addWidget(
            self.clear_button
        )

        layout.addLayout(buttons)

    # =========================================================
    # Logging
    # =========================================================

    def _timestamp(self):

        return datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]

    def _log(self, text):

        line = (
            f"[{self._timestamp()}] "
            f"{text}"
        )

        self.output.appendPlainText(
            line
        )

        try:
            with open(
                DEBUG_LOG,
                "a",
                encoding="utf-8"
            ) as f:
                f.write(
                    line + "\n"
                )
        except Exception:
            pass

        scrollbar = (
            self.output.verticalScrollBar()
        )

        scrollbar.setValue(
            scrollbar.maximum()
        )

    # =========================================================
    # Environment
    # =========================================================

    def _create_environment(self):

        env = QProcessEnvironment.systemEnvironment()

        env.insert(
            "PROJECT_ROOT",
            str(PROJECT_ROOT)
        )

        env.insert(
            "SRC_ROOT",
            str(SRC_ROOT)
        )

        env.insert(
            "PYTHONPATH",
            str(SRC_ROOT)
        )

        env.insert(
            "PYTHONUNBUFFERED",
            "1"
        )

        env.insert(
            "PYTHONIOENCODING",
            "utf-8"
        )

        env.insert(
            "PYTHONUTF8",
            "1"
        )

        return env

    # =========================================================
    # Start
    # =========================================================

    def start_process(self):

        if self.process is not None:

            if (
                self.process.state()
                != QProcess.NotRunning
            ):
                self._log(
                    "[DEBUG] Process already running."
                )
                return

        if not GMAIL_COPY.exists():

            QMessageBox.critical(
                self,
                "שגיאה",
                f"gmail_copy.py לא נמצא:\n"
                f"{GMAIL_COPY}",
            )

            return

        self.stop_requested = False
        self.start_time = datetime.now()

        self._log("")
        self._log("=" * 70)
        self._log("START GMAIL COPY")
        self._log("=" * 70)

        self._log(
            f"[DEBUG] Python executable: "
            f"{sys.executable}"
        )

        self._log(
            f"[DEBUG] Python version: "
            f"{sys.version}"
        )

        self._log(
            f"[DEBUG] Working directory: "
            f"{PROJECT_ROOT}"
        )

        self._log(
            f"[DEBUG] Script exists: "
            f"{GMAIL_COPY.exists()}"
        )

        self._log(
            f"[DEBUG] Script size: "
            f"{GMAIL_COPY.stat().st_size} bytes"
        )

        self.process = QProcess(self)

        self.process.setProcessEnvironment(
            self._create_environment()
        )

        self.process.setWorkingDirectory(
            str(PROJECT_ROOT)
        )

        self.process.setProcessChannelMode(
            QProcess.SeparateChannels
        )

        self.process.readyReadStandardOutput.connect(
            self.read_stdout
        )

        self.process.readyReadStandardError.connect(
            self.read_stderr
        )

        self.process.started.connect(
            self.process_started
        )

        self.process.errorOccurred.connect(
            self.process_error
        )

        self.process.finished.connect(
            self.process_finished
        )

        self._log(
            "[DEBUG] Command:"
        )

        self._log(
            f"{sys.executable} "
            f"-u "
            f"{GMAIL_COPY}"
        )

        self.process.start(
            sys.executable,
            [
                "-u",
                str(GMAIL_COPY),
            ],
        )

        self.start_button.setEnabled(
            False
        )

        self.stop_button.setEnabled(
            True
        )

    # =========================================================
    # Process events
    # =========================================================

    def process_started(self):

        self._log(
            "[QPROCESS] Process started successfully."
        )

        self._log(
            f"[QPROCESS] PID = "
            f"{self.process.processId()}"
        )

    def process_error(self, error):

        names = {
            QProcess.FailedToStart:
                "FailedToStart",

            QProcess.Crashed:
                "Crashed",

            QProcess.Timedout:
                "Timedout",

            QProcess.WriteError:
                "WriteError",

            QProcess.ReadError:
                "ReadError",

            QProcess.UnknownError:
                "UnknownError",
        }

        name = names.get(
            error,
            str(error)
        )

        self._log(
            f"[QPROCESS ERROR] {name}"
        )

        if self.process is not None:

            self._log(
                "[QPROCESS ERROR] "
                f"errorString = "
                f"{self.process.errorString()}"
            )

    def process_finished(
        self,
        exit_code,
        exit_status
    ):

        names = {
            QProcess.NormalExit:
                "NormalExit",

            QProcess.CrashExit:
                "CrashExit",
        }

        status_name = names.get(
            exit_status,
            str(exit_status)
        )

        self._log("")
        self._log("=" * 70)
        self._log("PROCESS FINISHED")
        self._log("=" * 70)

        self._log(
            f"[QPROCESS] exit_code = "
            f"{exit_code}"
        )

        self._log(
            f"[QPROCESS] exit_status = "
            f"{status_name}"
        )

        self._log(
            "[QPROCESS] errorString = "
            f"{self.process.errorString()}"
        )

        if self.start_time:

            elapsed = (
                datetime.now()
                - self.start_time
            )

            self._log(
                f"[QPROCESS] elapsed = "
                f"{elapsed}"
            )

        if self.stop_requested:

            self._log(
                "[QPROCESS] Process ended "
                "after STOP was requested."
            )

        self._log("=" * 70)

        self.start_button.setEnabled(
            True
        )

        self.stop_button.setEnabled(
            False
        )

    # =========================================================
    # stdout
    # =========================================================

    def read_stdout(self):

        if self.process is None:
            return

        data = bytes(
            self.process.readAllStandardOutput()
        )

        if not data:
            return

        text = data.decode(
            "utf-8",
            errors="replace"
        )

        for line in text.splitlines():

            self._inspect_line(
                "[STDOUT] ",
                line
            )

    # =========================================================
    # stderr
    # =========================================================

    def read_stderr(self):

        if self.process is None:
            return

        data = bytes(
            self.process.readAllStandardError()
        )

        if not data:
            return

        text = data.decode(
            "utf-8",
            errors="replace"
        )

        for line in text.splitlines():

            self._inspect_line(
                "[STDERR] ",
                line
            )

    # =========================================================
    # Diagnostics
    # =========================================================

    def _inspect_line(
        self,
        prefix,
        line
    ):

        clean = line.rstrip()

        upper = clean.upper()

        self._log(
            prefix + clean
        )

        if "403" in upper:

            self._log(
                "[!!! HTTP 403 DETECTED !!!]"
            )

        if (
            "RATE" in upper
            and (
                "LIMIT" in upper
                or "QUOTA" in upper
            )
        ):

            self._log(
                "[!!! RATE / QUOTA "
                "LIMIT DETECTED !!!]"
            )

        if "TOTAL QUERY COST" in upper:

            self._log(
                "[!!! GMAIL TOTAL QUERY "
                "COST QUOTA !!!]"
            )

        if "UNITS PER MINUTE" in upper:

            self._log(
                "[!!! UNITS PER MINUTE "
                "PER USER !!!]"
            )

        if "RATELIMITEXCEEDED" in upper:

            self._log(
                "[!!! rateLimitExceeded !!!]"
            )

        if "HTTPERROR" in upper:

            self._log(
                "[!!! Google API HttpError !!!]"
            )

        if "[MESSAGE]" in upper:

            self._log(
                "[DEBUG MESSAGE EVENT]"
            )

        if "[PROGRESS]" in upper:

            self._log(
                "[DEBUG PROGRESS EVENT]"
            )

        if "COPIED:" in upper:

            self._log(
                "[DEBUG COPY COUNTER EVENT]"
            )

        if "EXISTING:" in upper:

            self._log(
                "[DEBUG EXISTING COUNTER EVENT]"
            )

        if "ERROR" in upper:

            self._log(
                "[!!! ERROR LINE DETECTED !!!]"
            )

    # =========================================================
    # Input
    # =========================================================

    def send_input(self):

        if self.process is None:

            self._log(
                "[INPUT] No process."
            )

            return

        if (
            self.process.state()
            == QProcess.NotRunning
        ):

            self._log(
                "[INPUT] Process is not running."
            )

            return

        value = self.input_edit.text()

        if not value:
            return

        self._log(
            f"[INPUT -> gmail_copy] "
            f"{value}"
        )

        try:

            self.process.write(
                (
                    value + "\n"
                ).encode("utf-8")
            )

            self.process.waitForBytesWritten(
                1000
            )

        except Exception as exc:

            self._log(
                "[INPUT ERROR] "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

        self.input_edit.clear()

    # =========================================================
    # Stop
    # =========================================================

    def stop_process(self):

        if self.process is None:
            return

        if (
            self.process.state()
            == QProcess.NotRunning
        ):
            return

        self.stop_requested = True

        self._log("")
        self._log("=" * 70)
        self._log("USER REQUESTED STOP")
        self._log("=" * 70)

        self._log(
            "[STOP] Sending terminate()..."
        )

        self.process.terminate()

        QTimer.singleShot(
            5000,
            self._force_kill_if_needed
        )

    def _force_kill_if_needed(self):

        if self.process is None:
            return

        if (
            self.process.state()
            != QProcess.NotRunning
        ):

            self._log(
                "[STOP] Process did not "
                "terminate after 5 seconds."
            )

            self._log(
                "[STOP] Sending kill()..."
            )

            self.process.kill()

    # =========================================================
    # Close
    # =========================================================

    def closeEvent(self, event):

        if (
            self.process is not None
            and
            self.process.state()
            != QProcess.NotRunning
        ):

            answer = QMessageBox.question(
                self,
                "Gmail COPY עדיין רץ",
                "Gmail COPY עדיין פועל.\n"
                "האם לעצור אותו ולסגור?",
                QMessageBox.Yes
                | QMessageBox.No,
                QMessageBox.No,
            )

            if answer != QMessageBox.Yes:

                event.ignore()
                return

            self.stop_requested = True

            self.process.kill()

        event.accept()


def main():

    app = QApplication(
        sys.argv
    )

    window = GmailCopyDebugWindow()
    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()
