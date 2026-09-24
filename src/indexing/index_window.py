# -*- coding: utf-8 -*-

"""
Alcalay - Unified Index Control Window
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QProcess, QProcessEnvironment
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from database.connection import DatabaseConnection


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
INDEXER_SCRIPT = PROJECT_ROOT / "src" / "indexing" / "unified_indexer.py"


STAGE_LABELS = {
    "mails": "אינדקס מיילים",
    "documents": "אינדקס מסמכים",
    "ai": "מנוע AI / אינדקס סמנטי",
}


class IndexWindow(QDialog):
    """
    Selection + progress window for all indexing engines.

    Starting any combination of stages automatically skips documents that
    already have a successful checkpoint for the same source hash and
    extractor version. The backend persists the current file in PostgreSQL.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Alcalay - אינדקס")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.resize(1080, 780)
        self.setLayoutDirection(Qt.RightToLeft)

        self.process: QProcess | None = None
        self.output_buffer = ""
        self.stop_requested = False
        self.selected_stages: list[str] = []
        self.current_stage = ""
        self.current_total = 0
        self.current_completed = 0
        self.current_skipped = 0
        self.current_remaining = 0
        self.stage_number = 0
        self.stage_count = 0

        self.checkboxes: dict[str, QCheckBox] = {}

        self._build_ui()
        self._refresh_last_run()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("אינדקס מרכזי")
        title.setStyleSheet("font-size: 26px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel(
            "בחירת כמה מנועי אינדקס תפעיל תהליך אחד. "
            "המערכת שומרת ב-PostgreSQL את הקובץ הנוכחי ואת מצב כל פריט, "
            "ולכן בהרצה הבאה היא ממשיכה רק מפריטים שטרם הושלמו או שהשתנו."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        selection_frame = QFrame()
        selection_frame.setFrameShape(QFrame.StyledPanel)
        selection_layout = QVBoxLayout(selection_frame)
        selection_layout.setContentsMargins(14, 14, 14, 14)
        selection_layout.setSpacing(10)

        selection_title = QLabel("בחר מנועי אינדקס")
        selection_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        selection_layout.addWidget(selection_title)

        descriptions = {
            "mails": "סורק את מיילי ה-Gmail שנשמרו מקומית, כולל תוכן ההודעה והצרופות שבתוך ה-EML.",
            "documents": "סורק מסמכים מקומיים ומסמכי Google Drive שכבר נמצאים ב-storage ומחלץ את תוכנם.",
            "ai": "יוצר embeddings סמנטיים למסמכים שכבר עברו אינדוקס רגיל, כדי לאפשר חיפוש לפי משמעות בהמשך.",
        }

        for key in ("mails", "documents", "ai"):
            row = QHBoxLayout()
            checkbox = QCheckBox(STAGE_LABELS[key])
            checkbox.setMinimumHeight(34)
            self.checkboxes[key] = checkbox
            row.addWidget(checkbox)

            description = QLabel(descriptions[key])
            description.setWordWrap(True)
            description.setStyleSheet("color: #555555;")
            row.addWidget(description, 1)

            selection_layout.addLayout(row)

        layout.addWidget(selection_frame)

        self.resume_label = QLabel("בודק מצב אינדקס קודם...")
        self.resume_label.setWordWrap(True)
        layout.addWidget(self.resume_label)

        self.stage_label = QLabel("שלב: -")
        self.stage_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(self.stage_label)

        self.file_label = QLabel("קובץ נוכחי: -")
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        counter_grid = QGridLayout()
        counter_grid.setHorizontalSpacing(18)
        counter_grid.setVerticalSpacing(6)

        self.counter_processed = QLabel("טופלו: 0")
        self.counter_skipped = QLabel("כבר בוצע: 0")
        self.counter_remaining = QLabel("נשארו: 0")
        self.counter_errors = QLabel("שגיאות: 0")

        for row, widget in enumerate(
            [
                self.counter_processed,
                self.counter_skipped,
                self.counter_remaining,
                self.counter_errors,
            ]
        ):
            widget.setStyleSheet("font-size: 16px; font-weight: bold;")
            counter_grid.addWidget(widget, row // 2, row % 2)

        layout.addLayout(counter_grid)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMinimumHeight(28)
        layout.addWidget(self.progress)

        self.overall_label = QLabel("שלבים כוללים: -")
        layout.addWidget(self.overall_label)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.output, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()

        self.start_button = QPushButton("התחל אינדקס")
        self.start_button.setMinimumWidth(150)
        self.start_button.clicked.connect(self.start_index)
        buttons.addWidget(self.start_button)

        self.stop_button = QPushButton("עצור")
        self.stop_button.setEnabled(False)
        self.stop_button.setMinimumWidth(120)
        self.stop_button.clicked.connect(self.stop_index)
        buttons.addWidget(self.stop_button)

        self.close_button = QPushButton("סגור")
        self.close_button.setMinimumWidth(100)
        self.close_button.clicked.connect(self.close)
        buttons.addWidget(self.close_button)

        layout.addLayout(buttons)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def log(self, value: Any) -> None:
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output.setTextCursor(cursor)
        self.output.insertPlainText(str(value) + "\n")
        self.output.ensureCursorVisible()

    def _create_process_environment(self) -> QProcessEnvironment:
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PROJECT_ROOT", str(PROJECT_ROOT))
        env.insert("SRC_ROOT", str(SRC_ROOT))
        env.insert("PYTHONUNBUFFERED", "1")

        existing = env.value("PYTHONPATH", "")
        paths = [str(PROJECT_ROOT), str(SRC_ROOT)]
        if existing:
            paths.append(existing)
        env.insert("PYTHONPATH", os.pathsep.join(paths))
        return env

    def _refresh_last_run(self) -> None:
        try:
            connection = DatabaseConnection().connect()
        except Exception as exc:
            self.resume_label.setText(
                "מצב אינדקס קודם: לא ניתן להתחבר ל-PostgreSQL — "
                + str(exc)
            )
            return

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        status,
                        started_at,
                        finished_at,
                        selected_stages,
                        current_stage,
                        current_item_name,
                        current_item_path,
                        completed_items,
                        skipped_items,
                        remaining_items,
                        error_count,
                        stop_reason
                    FROM index_runs
                    ORDER BY started_at DESC
                    LIMIT 1
                    """
                )
                row = cursor.fetchone()

            if not row:
                self.resume_label.setText(
                    "מצב אינדקס קודם: אין עדיין הרצות."
                )
                return

            status = row[0]
            started = row[1]
            finished = row[2]
            stage_data = row[3] or []
            if isinstance(stage_data, str):
                try:
                    stage_data = json.loads(stage_data)
                except Exception:
                    stage_data = []

            current_stage = row[4] or "-"
            current_name = row[5] or "-"
            current_path = row[6] or "-"
            completed = row[7] or 0
            skipped = row[8] or 0
            remaining = row[9] or 0
            errors = row[10] or 0
            stop_reason = row[11] or ""

            stages_text = ", ".join(
                STAGE_LABELS.get(str(item), str(item))
                for item in stage_data
            )

            text = (
                f"הרצה אחרונה: {status} | שלבים: {stages_text or '-'} | "
                f"טופלו: {completed} | כבר בוצע: {skipped} | "
                f"נשארו לפי checkpoint: {remaining} | שגיאות: {errors}"
            )

            if current_stage != "-" or current_name != "-":
                text += (
                    f" | נקודת המשך: {current_stage} / {current_name}"
                )

            if current_path != "-":
                text += f" | {current_path}"

            if stop_reason:
                text += f" | סיבת עצירה: {stop_reason}"

            self.resume_label.setText(text)
        except Exception as exc:
            self.resume_label.setText(
                "מצב אינדקס קודם: שגיאה בקריאה מ-PostgreSQL — "
                + str(exc)
            )
        finally:
            connection.close()

    # ------------------------------------------------------------------
    # Process
    # ------------------------------------------------------------------

    def selected_stage_keys(self) -> list[str]:
        return [
            key
            for key, checkbox in self.checkboxes.items()
            if checkbox.isChecked()
        ]

    def start_index(self) -> None:
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            return

        stages = self.selected_stage_keys()
        if not stages:
            QMessageBox.warning(
                self,
                "אינדקס",
                "יש לבחור לפחות מנוע אינדקס אחד.",
            )
            return

        if not INDEXER_SCRIPT.exists():
            QMessageBox.critical(
                self,
                "אינדקס",
                f"קובץ מנוע האינדקס לא נמצא:\n{INDEXER_SCRIPT}",
            )
            return

        self.selected_stages = stages
        self.stage_count = len(stages)
        self.stage_number = 0
        self.stop_requested = False
        self.output.clear()
        self.progress.setValue(0)
        self.stage_label.setText("מכין אינדקס...")
        self.file_label.setText("קובץ נוכחי: -")
        self.counter_processed.setText("טופלו: 0")
        self.counter_skipped.setText("כבר בוצע: 0")
        self.counter_remaining.setText("נשארו: 0")
        self.counter_errors.setText("שגיאות: 0")
        self.overall_label.setText(
            f"שלבים כוללים: 0 / {self.stage_count}"
        )

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.close_button.setEnabled(False)

        self.process = QProcess(self)
        self.process.setProcessEnvironment(self._create_process_environment())
        self.process.setWorkingDirectory(str(PROJECT_ROOT))
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._process_finished)
        self.process.errorOccurred.connect(self._process_error)

        arguments = [
            "-u",
            str(INDEXER_SCRIPT),
            "--stages",
            *stages,
        ]

        self.log("=" * 90)
        self.log("ALCALAY UNIFIED INDEX")
        self.log("Selected: " + ", ".join(STAGE_LABELS[key] for key in stages))
        self.log("Resume is automatic from PostgreSQL checkpoints.")
        self.log("=" * 90)

        self.process.start(sys.executable, arguments)

        if not self.process.waitForStarted(5000):
            self._process_error(QProcess.ProcessError.FailedToStart)

    def _read_output(self) -> None:
        if self.process is None:
            return

        data = bytes(self.process.readAllStandardOutput()).decode(
            "utf-8",
            errors="replace",
        )
        if not data:
            return

        self.output_buffer += data
        while "\n" in self.output_buffer:
            line, self.output_buffer = self.output_buffer.split("\n", 1)
            self._handle_line(line.rstrip("\r"))

    def _handle_line(self, line: str) -> None:
        if not line:
            return

        prefix = "[INDEX_EVENT] "
        if line.startswith(prefix):
            payload = line[len(prefix):]
            try:
                event = json.loads(payload)
                self._handle_event(event)
                return
            except Exception:
                pass

        self.log(line)

    def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("event", "")).upper()
        stage = str(event.get("stage", ""))

        if event_type == "RUN_START":
            self.log(
                "RUN START | "
                + ", ".join(
                    STAGE_LABELS.get(item, item)
                    for item in event.get("stages", self.selected_stages)
                )
            )
            return

        if event_type == "STAGE_START":
            self.current_stage = stage
            self.stage_number = self.selected_stages.index(stage) + 1 if stage in self.selected_stages else self.stage_number
            self.current_total = int(event.get("total", 0) or 0)
            self.current_completed = 0
            self.current_skipped = 0
            self.current_remaining = int(event.get("remaining", self.current_total) or 0)
            self._update_stage_display()
            self.log(
                f"STAGE START: {STAGE_LABELS.get(stage, stage)} | "
                f"total={self.current_total}"
            )
            return

        if event_type == "ITEM_START":
            self.current_completed = int(event.get("completed", self.current_completed) or 0)
            self.current_skipped = int(event.get("skipped", self.current_skipped) or 0)
            self.current_remaining = int(event.get("remaining", self.current_remaining) or 0)
            self.file_label.setText(
                "קובץ נוכחי: "
                + str(event.get("name", "-"))
                + "\n"
                + str(event.get("path", "-"))
            )
            self._update_stage_display()
            return

        if event_type == "ITEM_FINISH":
            self.current_completed = int(event.get("completed", self.current_completed) or 0)
            self.current_skipped = int(event.get("skipped", self.current_skipped) or 0)
            self.current_remaining = int(event.get("remaining", self.current_remaining) or 0)
            self._update_stage_display()
            return

        if event_type == "ITEM_ERROR":
            self.current_completed = int(event.get("completed", self.current_completed) or 0)
            self.current_skipped = int(event.get("skipped", self.current_skipped) or 0)
            self.current_remaining = int(event.get("remaining", self.current_remaining) or 0)
            self.counter_errors.setText(
                "שגיאות: " + str(event.get("error_count", ""))
                if event.get("error_count") is not None
                else "שגיאות: !"
            )
            self._update_stage_display()
            self.log(
                "ERROR: "
                + str(event.get("name", ""))
                + " | "
                + str(event.get("error", ""))
            )
            return

        if event_type == "STAGE_FINISH":
            self.current_completed = int(event.get("completed", self.current_completed) or 0)
            self.current_skipped = int(event.get("skipped", self.current_skipped) or 0)
            self.current_remaining = int(event.get("remaining", 0) or 0)
            self.counter_errors.setText(
                "שגיאות: " + str(event.get("errors", 0) or 0)
            )
            self._update_stage_display()
            self.log(
                f"STAGE FINISH: {STAGE_LABELS.get(stage, stage)}"
            )
            return

        if event_type == "STOP_REQUESTED":
            self.stop_requested = True
            self.stage_label.setText(
                self.stage_label.text() + " | בקשת עצירה התקבלה"
            )
            self.log("STOP REQUESTED")
            return

        if event_type == "STOPPED":
            self.stop_requested = True
            self.current_completed = int(event.get("completed", self.current_completed) or 0)
            self.current_skipped = int(event.get("skipped", self.current_skipped) or 0)
            self.current_remaining = int(event.get("remaining", self.current_remaining) or 0)
            self._update_stage_display()
            self.stage_label.setText(
                "האינדקס נעצר. ניתן להפעיל שוב ולהמשיך מה-checkpoint."
            )
            self.log(
                "STOPPED | next checkpoint: "
                + str(event.get("current_item_path", "-"))
            )
            return

        if event_type == "RUN_FINISH":
            status = str(event.get("status", ""))
            self.progress.setValue(100 if status != "STOPPED" else self.progress.value())
            self.stage_label.setText(
                "האינדקס הסתיים: " + status
            )
            self.log(
                "RUN FINISH | "
                + json.dumps(event, ensure_ascii=False, default=str)
            )
            self._refresh_last_run()
            return

        if event_type == "RUN_ERROR":
            self.stage_label.setText("האינדקס הסתיים בשגיאה.")
            self.log(
                "RUN ERROR: " + str(event.get("error", ""))
            )
            self._refresh_last_run()
            return

        self.log(
            json.dumps(event, ensure_ascii=False, default=str)
        )

    def _update_stage_display(self) -> None:
        stage_text = STAGE_LABELS.get(
            self.current_stage,
            self.current_stage or "-",
        )
        self.stage_label.setText(
            f"שלב {self.stage_number}/{self.stage_count}: {stage_text}"
        )
        self.counter_processed.setText(
            f"טופלו: {self.current_completed}"
        )
        self.counter_skipped.setText(
            f"כבר בוצע: {self.current_skipped}"
        )
        self.counter_remaining.setText(
            f"נשארו: {self.current_remaining}"
        )

        if self.current_total > 0:
            completed_for_percent = (
                self.current_completed + self.current_skipped
            )
            percent = int(
                max(
                    0,
                    min(
                        100,
                        (completed_for_percent / self.current_total) * 100,
                    ),
                )
            )
        else:
            percent = 100

        self.progress.setValue(percent)
        self.overall_label.setText(
            f"שלבים כוללים: {self.stage_number} / {self.stage_count}"
        )

    def stop_index(self) -> None:
        if self.process is None:
            return

        if self.process.state() == QProcess.NotRunning:
            return

        self.stop_requested = True
        self.stop_button.setEnabled(False)
        self.stage_label.setText(
            "נשלחה בקשת עצירה. הקובץ הנוכחי יסיים ואז האינדקס יעצור."
        )
        self.log("Sending STOP to index process...")
        self.process.write(b"STOP\n")
        self.process.waitForBytesWritten(1000)

    def _process_error(self, error: QProcess.ProcessError) -> None:
        self.log(f"QProcess error: {error}")
        if error == QProcess.ProcessError.FailedToStart:
            self.stage_label.setText("לא ניתן להפעיל את מנוע האינדקס.")

    def _process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self.process = None
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.close_button.setEnabled(True)

        if self.output_buffer.strip():
            self._handle_line(self.output_buffer.rstrip("\r\n"))
            self.output_buffer = ""

        if exit_code == 0 and not self.stop_requested:
            self.progress.setValue(100)
            self.stage_label.setText("האינדקס הסתיים בהצלחה.")
        elif self.stop_requested:
            self.stage_label.setText(
                "האינדקס נעצר. ההרצה הבאה תמשיך מהקובץ שנרשם ב-PostgreSQL."
            )
        else:
            self.stage_label.setText(
                f"האינדקס הסתיים עם קוד {exit_code}."
            )

        self._refresh_last_run()

    def closeEvent(self, event) -> None:
        if (
            self.process is not None
            and self.process.state() != QProcess.NotRunning
        ):
            answer = QMessageBox.question(
                self,
                "אינדקס",
                "האינדקס עדיין פועל. לשלוח בקשת עצירה ולסגור?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if answer == QMessageBox.No:
                event.ignore()
                return
            self.stop_index()

        event.accept()
