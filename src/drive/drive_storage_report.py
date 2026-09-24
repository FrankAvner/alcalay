# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QProcess, QProcessEnvironment
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class DriveStorageReportWindow(QDialog):
    """
    חלון להרצת דוח השוואת קבצים:
    Google Drive מול האחסון המקומי.

    אפשרויות:
    - הפעלת הדוח
    - עצירה באמצע
    - חזרה לתפריט הראשי
    - הצגת פלט חי של הדוח
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Alcalay - דוח השוואת Google Drive מול אחסון מקומי")
        self.resize(1000, 700)

        self.process: QProcess | None = None
        self.is_running = False

        self._build_ui()

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # --------------------------------------------------------
        # כותרת
        # --------------------------------------------------------

        title = QLabel(
            "דוח השוואת מספר הקבצים\n"
            "Google Drive ←→ האחסון המקומי"
        )
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            """
            QLabel {
                font-size: 20px;
                font-weight: bold;
                padding: 15px;
            }
            """
        )

        layout.addWidget(title)

        # --------------------------------------------------------
        # סטטוס
        # --------------------------------------------------------

        self.status_label = QLabel("מוכן להרצת הדוח")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(
            """
            QLabel {
                font-size: 14px;
                padding: 8px;
            }
            """
        )

        layout.addWidget(self.status_label)

        # --------------------------------------------------------
        # פלט
        # --------------------------------------------------------

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setLayoutDirection(Qt.LeftToRight)

        layout.addWidget(self.output, 1)

        # --------------------------------------------------------
        # כפתורים
        # --------------------------------------------------------

        buttons_layout = QHBoxLayout()

        self.start_button = QPushButton("▶ הרצת הדוח")
        self.start_button.clicked.connect(self.start_report)

        self.stop_button = QPushButton("■ עצור")
        self.stop_button.clicked.connect(self.stop_report)
        self.stop_button.setEnabled(False)

        self.back_button = QPushButton("← חזרה לתפריט הראשי")
        self.back_button.clicked.connect(self.go_back)

        buttons_layout.addWidget(self.start_button)
        buttons_layout.addWidget(self.stop_button)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.back_button)

        layout.addLayout(buttons_layout)

    # ============================================================
    # הפעלת הדוח
    # ============================================================

    def start_report(self):
        if self.process is not None:
            if self.process.state() != QProcess.NotRunning:
                QMessageBox.information(
                    self,
                    "הדוח כבר פועל",
                    "דוח השוואת הקבצים כבר נמצא בתהליך הרצה.",
                )
                return

        self.output.clear()

        self.append_output("=" * 70)
        self.append_output("הפעלת דוח השוואת Google Drive מול האחסון המקומי")
        self.append_output("=" * 70)
        self.append_output("")

        project_root = Path(__file__).resolve().parents[2]

        report_script = (
            project_root
            / "src"
            / "drive"
            / "drive_storage_report.py"
        )

        if not report_script.exists():
            QMessageBox.critical(
                self,
                "קובץ הדוח לא נמצא",
                f"קובץ הדוח לא נמצא:\n\n{report_script}",
            )
            return

        python_executable = sys.executable

        # --------------------------------------------------------
        # סביבת הרצה
        # --------------------------------------------------------

        env = QProcessEnvironment.systemEnvironment()

        env.insert("PROJECT_ROOT", str(project_root))
        env.insert("SRC_ROOT", str(project_root / "src"))
        env.insert(
            "PYTHONPATH",
            str(project_root / "src")
            + os.pathsep
            + env.value("PYTHONPATH"),
        )
        env.insert("PYTHONUNBUFFERED", "1")

        # --------------------------------------------------------
        # QProcess
        # --------------------------------------------------------

        self.process = QProcess(self)

        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(str(project_root))

        self.process.setProgram(python_executable)

        self.process.setArguments(
            [
                "-u",
                str(report_script),
            ]
        )

        self.process.readyReadStandardOutput.connect(
            self.read_stdout
        )

        self.process.readyReadStandardError.connect(
            self.read_stderr
        )

        self.process.finished.connect(
            self.report_finished
        )

        self.process.errorOccurred.connect(
            self.process_error
        )

        self.is_running = True

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self.status_label.setText(
            "הדוח פועל..."
        )

        self.append_output(
            f"Python: {python_executable}"
        )
        self.append_output(
            f"דוח: {report_script}"
        )
        self.append_output("")
        self.append_output("מתחיל לסרוק...")
        self.append_output("")

        self.process.start()

        if not self.process.waitForStarted(3000):
            self.append_output(
                "ERROR: לא ניתן היה להפעיל את הדוח."
            )

            self.is_running = False
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)

            self.status_label.setText(
                "שגיאה בהפעלת הדוח"
            )

    # ============================================================
    # stdout
    # ============================================================

    def read_stdout(self):
        if not self.process:
            return

        data = self.process.readAllStandardOutput()

        text = bytes(data).decode(
            "utf-8",
            errors="replace",
        )

        if text:
            self.append_output(text)

    # ============================================================
    # stderr
    # ============================================================

    def read_stderr(self):
        if not self.process:
            return

        data = self.process.readAllStandardError()

        text = bytes(data).decode(
            "utf-8",
            errors="replace",
        )

        if text:
            self.append_output(
                text,
                error=True,
            )

    # ============================================================
    # הצגת פלט
    # ============================================================

    def append_output(
        self,
        text: str,
        error: bool = False,
    ):
        cursor = self.output.textCursor()

        cursor.movePosition(
            QTextCursor.End
        )

        self.output.setTextCursor(cursor)

        if error:
            self.output.insertPlainText(
                f"[ERROR] {text}"
            )
        else:
            self.output.insertPlainText(text)

        if not text.endswith("\n"):
            self.output.insertPlainText("\n")

        self.output.ensureCursorVisible()

    # ============================================================
    # עצירת הדוח
    # ============================================================

    def stop_report(self):
        if not self.process:
            return

        if self.process.state() == QProcess.NotRunning:
            return

        answer = QMessageBox.question(
            self,
            "עצירת הדוח",
            "האם לעצור את הדוח עכשיו?\n\n"
            "המידע שכבר נאסף יוצג, אך הסריקה תיפסק.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        self.append_output("")
        self.append_output(
            "בקשת עצירה התקבלה..."
        )

        self.status_label.setText(
            "עוצר את הדוח..."
        )

        self.stop_button.setEnabled(False)

        # קודם מבקשים מהתהליך להסתיים בצורה מסודרת.
        self.process.terminate()

        # מחכים עד 3 שניות.
        if not self.process.waitForFinished(3000):

            self.append_output(
                "התהליך לא הסתיים בזמן — מבצע עצירה כפויה..."
            )

            self.process.kill()
            self.process.waitForFinished(2000)

        self.is_running = False

        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        self.status_label.setText(
            "הדוח נעצר"
        )

        self.append_output("")
        self.append_output(
            "=== הדוח נעצר על ידי המשתמש ==="
        )

    # ============================================================
    # סיום רגיל
    # ============================================================

    def report_finished(
        self,
        exit_code: int,
        exit_status,
    ):
        self.is_running = False

        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        if exit_code == 0:
            self.status_label.setText(
                "הדוח הסתיים בהצלחה"
            )

            self.append_output("")
            self.append_output(
                "=" * 70
            )
            self.append_output(
                "הדוח הסתיים בהצלחה"
            )
            self.append_output(
                "=" * 70
            )

        else:
            self.status_label.setText(
                f"הדוח הסתיים עם שגיאה ({exit_code})"
            )

            self.append_output("")
            self.append_output(
                "=" * 70
            )
            self.append_output(
                f"הדוח הסתיים עם קוד שגיאה: {exit_code}"
            )
            self.append_output(
                "=" * 70
            )

    # ============================================================
    # שגיאת QProcess
    # ============================================================

    def process_error(self, error):
        if not self.process:
            return

        error_text = self.process.errorString()

        self.append_output("")
        self.append_output(
            f"QProcess ERROR: {error_text}",
            error=True,
        )

        self.status_label.setText(
            "שגיאה בהרצת הדוח"
        )

    # ============================================================
    # חזרה לתפריט הראשי
    # ============================================================

    def go_back(self):
        if self.process:
            if self.process.state() != QProcess.NotRunning:

                answer = QMessageBox.question(
                    self,
                    "הדוח עדיין פועל",
                    "הדוח עדיין פועל.\n\n"
                    "האם לעצור אותו ולחזור לתפריט הראשי?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )

                if answer != QMessageBox.Yes:
                    return

                self.process.terminate()

                if not self.process.waitForFinished(3000):
                    self.process.kill()
                    self.process.waitForFinished(2000)

                self.is_running = False

        self.close()

    # ============================================================
    # סגירת החלון
    # ============================================================

    def closeEvent(self, event):
        if self.process:
            if self.process.state() != QProcess.NotRunning:

                answer = QMessageBox.question(
                    self,
                    "הדוח עדיין פועל",
                    "הדוח עדיין פועל.\n\n"
                    "האם לעצור אותו ולסגור את החלון?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )

                if answer != QMessageBox.Yes:
                    event.ignore()
                    return

                self.process.terminate()

                if not self.process.waitForFinished(3000):
                    self.process.kill()
                    self.process.waitForFinished(2000)

        event.accept()