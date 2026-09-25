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
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from database.connection import DatabaseConnection
from gmail.gmail_connection import GmailConnection


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

DEFAULT_GMAIL_ACCOUNT = "frank.avner@gmail.com"


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

        QTimer.singleShot(150, self.start)

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

        self.stop_button = QPushButton("עצור COPY")
        self.stop_button.clicked.connect(self.stop_copy)
        self.stop_button.setEnabled(False)
        button_row.addWidget(self.stop_button)

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
            "continue to copy",
            "copy? yes",
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

        if (
            self.process.state()
            == QProcess.ProcessState.NotRunning
        ):
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

            self._append_output(
                "\n[GUI] זוהתה בקשת בחירת תגיות.\n"
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

            self._append_output(
                "\n[GUI] זוהתה בקשת אישור COPY.\n"
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

        if (
            self.process.state()
            == QProcess.ProcessState.NotRunning
        ):
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

            QTimer.singleShot(
                100,
                self._check_for_input_prompt,
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

        if (
            self.process.state()
            == QProcess.ProcessState.NotRunning
        ):
            return

        self._append_output(
            f"\n[GUI INPUT] {text}\n"
        )

        data = (text + "\n").encode("utf-8")

        self.process.write(data)
        self.process.waitForBytesWritten(2000)

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

        if (
            self.process is not None
            and self.process.state()
            != QProcess.ProcessState.NotRunning
        ):
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
        self.stop_button.setEnabled(True)
        self.refresh_counts_button.setEnabled(False)

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

            self.stop_button.setEnabled(False)
            self.close_button.setEnabled(True)
            self.refresh_counts_button.setEnabled(True)

    def stop_copy(self):
        if self.process is None:
            self.status_label.setText(
                "אין תהליך Gmail COPY פעיל."
            )
            return

        if (
            self.process.state()
            == QProcess.ProcessState.NotRunning
        ):
            self.stop_button.setEnabled(False)
            return

        self.status_label.setText(
            "עוצר את Gmail COPY..."
        )

        self._append_output(
            "\n[GUI] בקשת עצירה של Gmail COPY...\n"
        )

        self.awaiting_label_input = False
        self.awaiting_copy_confirmation = False
        self._disable_input_controls()

        self.stop_button.setEnabled(False)

        self.process.terminate()

        if not self.process.waitForFinished(1500):
            self._append_output(
                "[GUI] Gmail COPY לא נעצר ב-terminate. "
                "מפעיל kill...\n"
            )

            self.process.kill()
            self.process.waitForFinished(1000)

        self.status_label.setText(
            "Gmail COPY נעצר."
        )

        self.close_button.setEnabled(True)
        self.refresh_counts_button.setEnabled(True)

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

        self.stop_button.setEnabled(False)
        self.close_button.setEnabled(True)
        self.refresh_counts_button.setEnabled(True)

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
            if self.status_label.text() != "Gmail COPY נעצר.":
                self.status_label.setText(
                    "Gmail COPY הסתיים עם שגיאה. "
                    f"קוד: {exit_code}"
                )

        self.stop_button.setEnabled(False)
        self.close_button.setEnabled(True)
        self.refresh_counts_button.setEnabled(True)

    def closeEvent(self, event):
        if (
            self.process is not None
            and self.process.state()
            != QProcess.ProcessState.NotRunning
        ):
            self.stop_copy()

        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = GmailImportWindow()
    window.show()

    sys.exit(app.exec())