# -*- coding: utf-8 -*-

"""Alcalay - Unified Local Index Control Window."""

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
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Alcalay - אינדקס מקומי")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.resize(1100, 820)
        self.setLayoutDirection(Qt.RightToLeft)

        self.process: QProcess | None = None
        self.output_buffer = ""
        self.stop_requested = False

        self.selected_stages: list[str] = []
        self.current_stage = ""

        self.current_total = 0
        self.current_completed = 0
        self.current_skipped = 0
        self.current_errors = 0
        self.current_remaining = 0
        self.current_item_number: int | None = None

        self.stage_number = 0
        self.stage_count = 0

        self.resumable = False
        self.last_run_status = ""
        self.last_run_stages: list[str] = []

        self.checkboxes: dict[str, QCheckBox] = {}

        self._build_ui()
        self._refresh_last_run()

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(self, message: str) -> None:
        """Display a message in the indexing output window."""
        if not hasattr(self, "output") or self.output is None:
            return

        self.output.appendPlainText(str(message))

        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.output.setTextCursor(cursor)
        self.output.ensureCursorVisible()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("אינדקס מקומי מרכזי")
        title.setStyleSheet("font-size: 26px; font-weight: bold;")
        layout.addWidget(title)

        explanation = QLabel(
            "האינדקס קורא רק מהאחסון המקומי של Alcalay. "
            "גם מיילים שהורדו/סונכרנו מ-Google Drive ונמצאים תחת "
            "storage/gmail ייכללו באינדקס. "
            "אין גישה ל-Google Drive בזמן האינדוקס."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)

        box = QVBoxLayout(frame)
        box.setContentsMargins(14, 14, 14, 14)

        heading = QLabel("בחר מה לאנדקס")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        box.addWidget(heading)

        descriptions = {
            "mails": "כל קובצי EML מקומיים, תוכן המייל והצרופות שבתוכם.",
            "documents": "מסמכים מקומיים, כולל מסמכי Drive שכבר נמצאים מקומית.",
            "ai": "יצירת אינדקס סמנטי עבור תוכן שכבר עבר אינדוקס רגיל.",
        }

        for key in ("mails", "documents", "ai"):
            row = QHBoxLayout()

            check = QCheckBox(STAGE_LABELS[key])
            check.setMinimumHeight(34)
            self.checkboxes[key] = check
            row.addWidget(check)

            desc = QLabel(descriptions[key])
            desc.setWordWrap(True)
            row.addWidget(desc, 1)

            box.addLayout(row)

        layout.addWidget(frame)

        self.resume_label = QLabel("בודק checkpoint אחרון...")
        self.resume_label.setWordWrap(True)
        layout.addWidget(self.resume_label)

        self.stage_label = QLabel("שלב: -")
        self.stage_label.setStyleSheet(
            "font-size: 16px; font-weight: bold;"
        )
        layout.addWidget(self.stage_label)

        self.item_label = QLabel("פריט נוכחי: -")
        self.item_label.setWordWrap(True)
        layout.addWidget(self.item_label)

        counter = QGridLayout()

        self.counter_processed = QLabel("טופלו: 0")
        self.counter_skipped = QLabel("דולגו ללא שינוי: 0")
        self.counter_errors = QLabel("שגיאות: 0")
        self.counter_remaining = QLabel("נשארו: 0")

        for row, widget in enumerate(
            [
                self.counter_processed,
                self.counter_skipped,
                self.counter_errors,
                self.counter_remaining,
            ]
        ):
            widget.setStyleSheet(
                "font-size: 16px; font-weight: bold;"
            )
            counter.addWidget(widget, row // 2, row % 2)

        layout.addLayout(counter)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMinimumHeight(28)
        layout.addWidget(self.progress)

        self.stage_progress_label = QLabel("שלבים: 0 / 0")
        layout.addWidget(self.stage_progress_label)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.output, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()

        self.resume_button = QPushButton("המשך מהנקודה האחרונה")
        self.resume_button.setMinimumWidth(190)
        self.resume_button.clicked.connect(self.start_resume)
        buttons.addWidget(self.resume_button)

        self.fresh_button = QPushButton("התחל מהתחלה")
        self.fresh_button.setMinimumWidth(150)
        self.fresh_button.clicked.connect(self.start_fresh)
        buttons.addWidget(self.fresh_button)

        self.stop_button = QPushButton("עצור")
        self.stop_button.setEnabled(False)
        self.stop_button.setMinimumWidth(110)
        self.stop_button.clicked.connect(self.stop_index)
        buttons.addWidget(self.stop_button)

        self.close_button = QPushButton("סגור")
        self.close_button.setMinimumWidth(90)
        self.close_button.clicked.connect(self.close)
        buttons.addWidget(self.close_button)

        layout.addLayout(buttons)

    # ------------------------------------------------------------------
    # Database checkpoint display
    # ------------------------------------------------------------------

    def _refresh_last_run(self) -> None:
        try:
            connection = DatabaseConnection().connect()
        except Exception as exc:
            self.resume_label.setText(
                "Checkpoint: לא ניתן להתחבר ל-PostgreSQL — " + str(exc)
            )
            self.resumable = False
            self.resume_button.setEnabled(False)
            return

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        id,
                        status,
                        started_at,
                        finished_at,
                        selected_stages,
                        start_mode,
                        resumed_from_run_id,
                        current_stage,
                        current_item_number,
                        current_item_key,
                        current_item_name,
                        current_item_path,
                        completed_items,
                        skipped_items,
                        error_count,
                        remaining_items,
                        stop_reason,
                        last_error
                    FROM index_runs
                    ORDER BY started_at DESC
                    LIMIT 1
                    """
                )
                row = cursor.fetchone()

            if not row:
                self.resume_label.setText(
                    "Checkpoint: אין עדיין הרצות אינדקס."
                )
                self.resumable = False
                self.resume_button.setEnabled(False)
                return

            (
                run_id,
                status,
                started_at,
                finished_at,
                stages,
                start_mode,
                resumed_from,
                current_stage,
                current_item_number,
                current_item_key,
                current_name,
                current_path,
                completed,
                skipped,
                errors,
                remaining,
                stop_reason,
                last_error,
            ) = row

            if isinstance(stages, str):
                try:
                    stages = json.loads(stages)
                except Exception:
                    stages = []

            stages = stages or []

            stage_text = ", ".join(
                STAGE_LABELS.get(str(item), str(item))
                for item in stages
            ) or "-"

            self.last_run_status = str(status)
            self.last_run_stages = [str(item) for item in stages]

            self.resumable = status in {
                "STOPPED",
                "INTERRUPTED",
                "ERROR",
                "COMPLETED_WITH_ERRORS",
            }

            self.resume_button.setEnabled(self.resumable)

            text = (
                f"Checkpoint: run #{run_id} | {status} | "
                f"שלבים: {stage_text} | "
                f"טופלו: {completed or 0} | "
                f"דולגו: {skipped or 0} | "
                f"שגיאות: {errors or 0} | "
                f"נשארו: {remaining or 0}"
            )

            if current_stage:
                text += (
                    f" | נקודה: "
                    f"{STAGE_LABELS.get(current_stage, current_stage)}"
                )

            if current_item_number:
                text += f" | פריט {current_item_number}"

            if current_name:
                text += f" | {current_name}"

            if current_path:
                text += f" | {current_path}"

            if stop_reason:
                text += f" | סיבה: {stop_reason}"

            if last_error:
                text += f" | שגיאה אחרונה: {last_error}"

            self.resume_label.setText(text)

            for key, check in self.checkboxes.items():
                check.setChecked(
                    key in [str(item) for item in stages]
                )

        except Exception as exc:
            self.resume_label.setText(
                "Checkpoint: שגיאה בקריאה מ-PostgreSQL — " + str(exc)
            )
            self.resumable = False
            self.resume_button.setEnabled(False)

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

    def _start_process(
        self,
        stages: list[str],
        start_mode: str,
    ) -> None:
        if (
            self.process is not None
            and self.process.state() != QProcess.NotRunning
        ):
            return

        if not stages:
            QMessageBox.warning(
                self,
                "אינדקס",
                "יש לבחור לפחות שלב אחד.",
            )
            return

        if not INDEXER_SCRIPT.exists():
            QMessageBox.critical(
                self,
                "אינדקס",
                f"מנוע האינדקס לא נמצא:\n{INDEXER_SCRIPT}",
            )
            return

        self.selected_stages = stages
        self.stage_count = len(stages)
        self.stage_number = 0
        self.stop_requested = False
        self.output_buffer = ""

        self.output.clear()
        self.progress.setValue(0)

        self.stage_label.setText("מכין אינדקס מקומי...")
        self.item_label.setText("פריט נוכחי: -")

        self.counter_processed.setText("טופלו: 0")
        self.counter_skipped.setText("דולגו ללא שינוי: 0")
        self.counter_errors.setText("שגיאות: 0")
        self.counter_remaining.setText("נשארו: 0")

        self.stage_progress_label.setText(
            f"שלבים: 0 / {self.stage_count}"
        )

        self.resume_button.setEnabled(False)
        self.fresh_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.close_button.setEnabled(False)

        env = QProcessEnvironment.systemEnvironment()

        env.insert("PROJECT_ROOT", str(PROJECT_ROOT))
        env.insert("SRC_ROOT", str(SRC_ROOT))
        env.insert("PYTHONUNBUFFERED", "1")

        existing = env.value("PYTHONPATH", "")

        paths = [
            str(PROJECT_ROOT),
            str(SRC_ROOT),
        ]

        if existing:
            paths.append(existing)

        env.insert(
            "PYTHONPATH",
            os.pathsep.join(paths),
        )

        self.process = QProcess(self)

        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(str(PROJECT_ROOT))
        self.process.setProcessChannelMode(
            QProcess.MergedChannels
        )

        self.process.readyReadStandardOutput.connect(
            self._read_output
        )

        self.process.finished.connect(
            self._process_finished
        )

        self.process.errorOccurred.connect(
            self._process_error
        )

        arguments = [
            "-u",
            str(INDEXER_SCRIPT),
            "--stages",
            *stages,
            "--start-mode",
            start_mode,
        ]

        mode_text = (
            "RESUME מה-checkpoint"
            if start_mode == "resume"
            else "התחלה מהתחלה"
        )

        self.log("=" * 90)
        self.log("ALCALAY UNIFIED LOCAL INDEX")

        self.log(
            "Selected: "
            + ", ".join(
                STAGE_LABELS[key]
                for key in stages
            )
        )

        self.log("Mode: " + mode_text)
        self.log("Source: LOCAL STORAGE ONLY")
        self.log("Google Drive: NOT ACCESSED BY INDEXER")
        self.log("=" * 90)

        self.process.start(
            sys.executable,
            arguments,
        )

        if not self.process.waitForStarted(5000):
            self._process_error(
                QProcess.ProcessError.FailedToStart
            )

    # ------------------------------------------------------------------
    # Start / Resume
    # ------------------------------------------------------------------

    def start_resume(self) -> None:
        stages = self.selected_stage_keys()

        if not stages:
            QMessageBox.warning(
                self,
                "אינדקס",
                "יש לבחור את שלבי האינדקס להמשך.",
            )
            return

        if not self.resumable:
            QMessageBox.information(
                self,
                "אינדקס",
                "אין כרגע checkpoint שניתן להמשיך ממנו.",
            )
            return

        if (
            self.last_run_stages
            and stages != self.last_run_stages
        ):
            QMessageBox.warning(
                self,
                "אינדקס",
                "כדי להמשיך מה-checkpoint יש לבחור בדיוק "
                "את אותם שלבים שנבחרו בהרצה הקודמת.",
            )
            return

        self._start_process(
            stages,
            "resume",
        )

    def start_fresh(self) -> None:
        stages = self.selected_stage_keys()

        if not stages:
            QMessageBox.warning(
                self,
                "אינדקס",
                "יש לבחור לפחות שלב אחד.",
            )
            return

        answer = QMessageBox.question(
            self,
            "התחלה מהתחלה",
            "להתחיל את האינדקס מהפריט הראשון?\n\n"
            "הקבצים הקיימים לא יימחקו; קבצים שלא השתנו עדיין ידולגו "
            "לפי hash וגרסת extractor.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        self._start_process(
            stages,
            "fresh",
        )

    # ------------------------------------------------------------------
    # Process output
    # ------------------------------------------------------------------

    def _read_output(self) -> None:
        if self.process is None:
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
                self.output_buffer.split("\n", 1)
            )
            self._handle_line(line.rstrip("\r"))

    def _handle_line(self, line: str) -> None:
        if not line:
            return

        prefix = "[INDEX_EVENT] "

        if line.startswith(prefix):
            try:
                event = json.loads(
                    line[len(prefix):]
                )
                self._handle_event(event)
                return
            except Exception:
                pass

        self.log(line)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _handle_event(
        self,
        event: dict[str, Any],
    ) -> None:
        event_type = str(
            event.get("event", "")
        ).upper()

        stage = str(
            event.get("stage", "")
        )

        if event_type == "RUN_START":
            mode = str(
                event.get(
                    "start_mode",
                    "resume",
                )
            )

            self.log(
                "RUN START | "
                + ", ".join(
                    STAGE_LABELS.get(
                        str(item),
                        str(item),
                    )
                    for item in event.get(
                        "stages",
                        self.selected_stages,
                    )
                )
                + f" | mode={mode}"
            )
            return

        if event_type == "STAGE_RESUMED_PAST":
            self.log(
                "STAGE SKIPPED BY RESUME: "
                + STAGE_LABELS.get(stage, stage)
            )
            return

        if event_type == "STAGE_START":
            self.current_stage = stage

            self.stage_number = (
                self.selected_stages.index(stage) + 1
                if stage in self.selected_stages
                else self.stage_number
            )

            self.current_total = int(
                event.get("total", 0) or 0
            )

            self.current_completed = int(
                event.get("completed", 0) or 0
            )

            self.current_skipped = int(
                event.get("skipped", 0) or 0
            )

            self.current_errors = int(
                event.get("errors", 0) or 0
            )

            self.current_remaining = int(
                event.get("remaining", 0) or 0
            )

            self.current_item_number = event.get(
                "resume_item_number"
            )

            self._update_display()

            self.log(
                f"STAGE START: "
                f"{STAGE_LABELS.get(stage, stage)} "
                f"| total={self.current_total} "
                f"| resume_item="
                f"{event.get('resume_item_number') or '-'}"
            )
            return

        if event_type == "ITEM_START":
            self.current_item_number = event.get(
                "index"
            )

            self.current_completed = int(
                event.get(
                    "completed",
                    self.current_completed,
                )
                or 0
            )

            self.current_skipped = int(
                event.get(
                    "skipped",
                    self.current_skipped,
                )
                or 0
            )

            self.current_errors = int(
                event.get(
                    "errors",
                    self.current_errors,
                )
                or 0
            )

            self.current_remaining = int(
                event.get(
                    "remaining",
                    self.current_remaining,
                )
                or 0
            )

            self.item_label.setText(
                f"פריט {event.get('index', '-')} "
                f"מתוך {event.get('total', '-')}\n"
                f"{event.get('name', '-')}\n"
                f"{event.get('path', '-')}"
            )

            self._update_display()
            return

        if event_type == "ITEM_FINISH":
            self.current_completed = int(
                event.get(
                    "completed",
                    self.current_completed,
                )
                or 0
            )

            self.current_skipped = int(
                event.get(
                    "skipped",
                    self.current_skipped,
                )
                or 0
            )

            self.current_errors = int(
                event.get(
                    "errors",
                    self.current_errors,
                )
                or 0
            )

            self.current_remaining = int(
                event.get(
                    "remaining",
                    self.current_remaining,
                )
                or 0
            )

            self._update_display()
            return

        if event_type == "ITEM_ERROR":
            self.current_item_number = event.get(
                "index"
            )

            self.current_completed = int(
                event.get(
                    "completed",
                    self.current_completed,
                )
                or 0
            )

            self.current_skipped = int(
                event.get(
                    "skipped",
                    self.current_skipped,
                )
                or 0
            )

            self.current_errors = int(
                event.get(
                    "error_count",
                    self.current_errors,
                )
                or 0
            )

            self.current_remaining = int(
                event.get(
                    "remaining",
                    self.current_remaining,
                )
                or 0
            )

            self.item_label.setText(
                f"שגיאה בפריט {event.get('index', '-')}"
                f" מתוך {event.get('total', '-')}\n"
                f"{event.get('name', '-')}\n"
                f"{event.get('path', '-')}"
            )

            self._update_display()

            self.log(
                "ERROR: "
                + str(event.get("name", ""))
                + " | "
                + str(event.get("error", ""))
            )
            return

        if event_type == "STAGE_FINISH":
            self.current_completed = int(
                event.get(
                    "completed",
                    self.current_completed,
                )
                or 0
            )

            self.current_skipped = int(
                event.get(
                    "skipped",
                    self.current_skipped,
                )
                or 0
            )

            self.current_errors = int(
                event.get(
                    "errors",
                    self.current_errors,
                )
                or 0
            )

            self.current_remaining = int(
                event.get(
                    "remaining",
                    0,
                )
                or 0
            )

            checkpoint_number = event.get(
                "checkpoint_item_number"
            )

            self.current_item_number = checkpoint_number

            self._update_display()

            self.log(
                f"STAGE FINISH: "
                f"{STAGE_LABELS.get(stage, stage)} "
                f"| checkpoint="
                f"{checkpoint_number or '-'}"
            )
            return

        if event_type == "STOP_REQUESTED":
            self.stop_requested = True

            self.stage_label.setText(
                "נשלחה בקשת עצירה..."
            )

            self.log("STOP REQUESTED")
            return

        if event_type == "STOPPED":
            self.stop_requested = True
            self.current_stage = stage

            self.current_item_number = event.get(
                "current_item_number"
            )

            self.current_completed = int(
                event.get(
                    "completed",
                    self.current_completed,
                )
                or 0
            )

            self.current_skipped = int(
                event.get(
                    "skipped",
                    self.current_skipped,
                )
                or 0
            )

            self.current_errors = int(
                event.get(
                    "errors",
                    self.current_errors,
                )
                or 0
            )

            self.current_remaining = int(
                event.get(
                    "remaining",
                    self.current_remaining,
                )
                or 0
            )

            self.item_label.setText(
                f"נקודת המשך: פריט "
                f"{self.current_item_number or '-'}\n"
                f"{event.get('current_item_name', '-')}\n"
                f"{event.get('current_item_path', '-')}"
            )

            self._update_display()

            self.stage_label.setText(
                "האינדקס נעצר. ניתן להמשיך מה-checkpoint."
            )

            self.log(
                "STOPPED | checkpoint: "
                + str(
                    event.get(
                        "current_item_path",
                        "-",
                    )
                )
            )
            return

        if event_type == "RUN_FINISH":
            status = str(
                event.get(
                    "status",
                    "",
                )
            )

            self._refresh_last_run()

            if status == "COMPLETED":
                self.progress.setValue(100)

                self.stage_label.setText(
                    "האינדקס המקומי הסתיים בהצלחה."
                )

                self.log(
                    "האינדקס המקומי הסתיים בהצלחה. "
                    "יש לבצע כעת סנכרון בין האחסון המקומי "
                    "ל-Google Drive."
                )

                self._ask_for_drive_sync()

            elif status == "STOPPED":
                self.stage_label.setText(
                    "האינדקס נעצר; checkpoint נשמר."
                )

            else:
                self.stage_label.setText(
                    "האינדקס הסתיים: " + status
                )

            self.log(
                "RUN FINISH | "
                + json.dumps(
                    event,
                    ensure_ascii=False,
                    default=str,
                )
            )
            return

        if event_type == "RUN_ERROR":
            self.stage_label.setText(
                "האינדקס הסתיים בשגיאה."
            )

            self.log(
                "RUN ERROR: "
                + str(
                    event.get(
                        "error",
                        "",
                    )
                )
            )

            self._refresh_last_run()
            return

        self.log(
            json.dumps(
                event,
                ensure_ascii=False,
                default=str,
            )
        )

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _update_display(self) -> None:
        stage_text = STAGE_LABELS.get(
            self.current_stage,
            self.current_stage or "-",
        )

        self.stage_label.setText(
            f"שלב {self.stage_number}/{self.stage_count}: "
            f"{stage_text}"
        )

        self.counter_processed.setText(
            f"טופלו: {self.current_completed}"
        )

        self.counter_skipped.setText(
            f"דולגו ללא שינוי: {self.current_skipped}"
        )

        self.counter_errors.setText(
            f"שגיאות: {self.current_errors}"
        )

        self.counter_remaining.setText(
            f"נשארו: {self.current_remaining}"
        )

        if self.current_total > 0:
            done = (
                self.current_completed
                + self.current_skipped
            )

            percent = int(
                max(
                    0,
                    min(
                        100,
                        (done / self.current_total) * 100,
                    ),
                )
            )
        else:
            percent = 0

        self.progress.setValue(percent)

        self.stage_progress_label.setText(
            f"שלבים: {self.stage_number} / "
            f"{self.stage_count}"
        )

    # ------------------------------------------------------------------
    # Google Drive synchronization
    # ------------------------------------------------------------------

    def _ask_for_drive_sync(self) -> None:
        answer = QMessageBox.question(
            self,
            "האינדקס הסתיים",
            "האינדקס המקומי הסתיים בהצלחה.\n\n"
            "יש לבצע כעת סנכרון בין האחסון המקומי "
            "ל-Google Drive.\n\n"
            "האם לפתוח את חלון Google Drive?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if answer != QMessageBox.Yes:
            return

        parent = self.parent()

        callback = getattr(
            parent,
            "open_google_drive_sync",
            None,
        )

        if callable(callback):
            callback()
        else:
            QMessageBox.information(
                self,
                "Google Drive",
                "פתח את Google Drive מהתפריט "
                "ובצע את הסנכרון המבוקש.",
            )

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------

    def stop_index(self) -> None:
        if self.process is None:
            return

        if self.process.state() == QProcess.NotRunning:
            return

        self.stop_requested = True
        self.stop_button.setEnabled(False)

        self.stage_label.setText(
            "נשלחה בקשת עצירה. "
            "ה-checkpoint יישמר ב-PostgreSQL."
        )

        self.log(
            "Sending STOP to index process..."
        )

        self.process.write(b"STOP\n")
        self.process.waitForBytesWritten(1000)

    # ------------------------------------------------------------------
    # QProcess errors
    # ------------------------------------------------------------------

    def _process_error(
        self,
        error: QProcess.ProcessError,
    ) -> None:
        self.log(
            f"QProcess error: {error}"
        )

        if error == QProcess.ProcessError.FailedToStart:
            self.stage_label.setText(
                "לא ניתן להפעיל את מנוע האינדקס."
            )

    # ------------------------------------------------------------------
    # QProcess finished
    # ------------------------------------------------------------------

    def _process_finished(
        self,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
    ) -> None:
        self.process = None

        self.resume_button.setEnabled(
            self.resumable
        )

        self.fresh_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.close_button.setEnabled(True)

        if self.output_buffer.strip():
            self._handle_line(
                self.output_buffer.rstrip("\r\n")
            )
            self.output_buffer = ""

        if exit_code == 0 and not self.stop_requested:
            if not self.stage_label.text().startswith(
                "האינדקס המקומי הסתיים"
            ):
                self.stage_label.setText(
                    "האינדקס הסתיים."
                )

        elif self.stop_requested:
            self.stage_label.setText(
                "האינדקס נעצר. "
                "ה-checkpoint נשמר ב-PostgreSQL."
            )

        else:
            self.stage_label.setText(
                f"האינדקס הסתיים עם קוד {exit_code}."
            )

        self._refresh_last_run()

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        if (
            self.process is not None
            and self.process.state()
            != QProcess.NotRunning
        ):
            answer = QMessageBox.question(
                self,
                "אינדקס",
                "האינדקס עדיין פועל. "
                "לשלוח בקשת עצירה ולסגור?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if answer == QMessageBox.No:
                event.ignore()
                return

            self.stop_index()

        event.accept()