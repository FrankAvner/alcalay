from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from .alcalay_server_setup import (
        APP_NAME,
        build_configuration,
        create_server_directories,
        default_server_root,
        validate_configuration,
    )
except ImportError:
    INIT_DIR = Path(__file__).resolve().parent

    if str(INIT_DIR) not in sys.path:
        sys.path.insert(0, str(INIT_DIR))

    from alcalay_server_setup import (
        APP_NAME,
        build_configuration,
        create_server_directories,
        default_server_root,
        validate_configuration,
    )


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_bool(
    value: Any,
    default: bool = False,
) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
            "כן",
        }

    return bool(value)


class ValidationWorker(QObject):

    progress = Signal(int)
    stage_started = Signal(int, str)
    activity = Signal(str)
    stage_finished = Signal(int, str, bool, str)

    completed = Signal(object)
    stopped = Signal()
    failed = Signal(str)

    def __init__(
        self,
        configuration: Dict[str, Any],
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)

        self.configuration = configuration
        self._stop_requested = False

    @Slot()
    def request_stop(self) -> None:
        self._stop_requested = True

        self.activity.emit(
            f"{timestamp()}  בקשת עצירה התקבלה."
        )

    def should_stop(self) -> bool:
        return self._stop_requested

    def check_structure(self) -> tuple[bool, str]:

        configuration = self.configuration

        if not isinstance(configuration, dict):
            return (
                False,
                "התצורה אינה מסוג dictionary.",
            )

        required_sections = [
            "application",
            "server",
            "paths",
            "postgresql",
            "sources",
            "processing",
            "ocr",
            "ai_ml",
            "search",
            "security",
        ]

        missing = [
            section
            for section in required_sections
            if section not in configuration
        ]

        if missing:
            return (
                False,
                "חסרים חלקים בתצורה: "
                + ", ".join(missing),
            )

        sources = configuration.get(
            "sources",
            {},
        )

        if not isinstance(sources, dict):
            return (
                False,
                "חלק sources אינו תקין.",
            )

        if "gmail" not in sources:
            return (
                False,
                "חלק sources.gmail חסר.",
            )

        if "google_drive" not in sources:
            return (
                False,
                "חלק sources.google_drive חסר.",
            )

        return (
            True,
            "מבנה התצורה תקין.",
        )

    def check_paths(self) -> tuple[bool, str]:

        paths = self.configuration.get(
            "paths",
            {},
        )

        if not isinstance(paths, dict):
            return (
                False,
                "חלק paths אינו תקין.",
            )

        required_paths = [
            "app_root",
            "documents",
            "search_index",
            "backups",
            "logs",
            "config",
            "data",
            "runtime",
        ]

        missing = [
            name
            for name in required_paths
            if not paths.get(name)
        ]

        if missing:
            return (
                False,
                "חסרים נתיבים: "
                + ", ".join(missing),
            )

        errors = []

        for name in required_paths:

            value = paths.get(name)

            try:
                path = Path(value).expanduser()

                if path.exists() and not path.is_dir():
                    errors.append(
                        f"{name}: אינו תיקייה"
                    )

            except Exception as exc:
                errors.append(
                    f"{name}: {exc}"
                )

        if errors:
            return (
                False,
                "; ".join(errors),
            )

        return (
            True,
            "כל הנתיבים תקינים.",
        )

    def check_postgresql(self) -> tuple[bool, str]:

        try:

            setup_database_path = (
                Path(__file__).resolve().parent
                / "setup_database.py"
            )

            if not setup_database_path.exists():
                return (
                    False,
                    "setup_database.py לא נמצא.",
                )

            import importlib.util

            module_name = "alcalay_setup_database"

            spec = importlib.util.spec_from_file_location(
                module_name,
                setup_database_path,
            )

            if spec is None or spec.loader is None:
                return (
                    False,
                    "לא ניתן לטעון את מודול בדיקת PostgreSQL.",
                )

            module = importlib.util.module_from_spec(
                spec
            )

            # חשוב:
            # dataclass ב-setup_database.py מסתמך על כך
            # שהמודול כבר רשום ב-sys.modules בזמן exec_module().
            sys.modules[module_name] = module

            spec.loader.exec_module(module)

            check_function = getattr(
                module,
                "check_postgresql_dict",
                None,
            )

            if check_function is None:
                return (
                    False,
                    "check_postgresql_dict אינה זמינה.",
                )

            result = check_function(
                self.configuration
            )

            if not isinstance(result, dict):
                return (
                    False,
                    "בדיקת PostgreSQL החזירה תוצאה שאינה dictionary.",
                )

            success = bool(
                result.get(
                    "success",
                    False,
                )
            )

            message = str(
                result.get(
                    "message",
                    "בדיקת PostgreSQL הסתיימה.",
                )
            )

            details = []

            if result.get(
                "psql_available"
            ):
                details.append(
                    "psql זמין"
                )
            else:
                details.append(
                    "psql אינו זמין"
                )

            if result.get(
                "connection_ok"
            ):
                details.append(
                    "חיבור TCP תקין"
                )
            else:
                details.append(
                    "חיבור TCP אינו תקין"
                )

            return (
                success,
                f"{message} ({', '.join(details)})",
            )

        except Exception as exc:

            self.activity.emit(
                f"{timestamp()}  "
                "שגיאה פנימית בבדיקת PostgreSQL:"
            )

            for line in traceback.format_exc().splitlines():

                self.activity.emit(
                    f"{timestamp()}  {line}"
                )

            return (
                False,
                f"בדיקת PostgreSQL נכשלה: {exc}",
            )

    def check_google_drive(self) -> tuple[bool, str]:

        sources = self.configuration.get(
            "sources",
            {},
        )

        if not isinstance(sources, dict):
            return (
                False,
                "חלק sources אינו תקין.",
            )

        drive = sources.get(
            "google_drive",
            {},
        )

        if not isinstance(drive, dict):
            return (
                False,
                "הגדרות Google Drive אינן תקינות.",
            )

        enabled = safe_bool(
            drive.get("enabled"),
            False,
        )

        if not enabled:
            return (
                True,
                "Google Drive אינו מופעל.",
            )

        root = (
            drive.get("local_root")
            or drive.get("documents_root")
            or drive.get("root")
        )

        if not root:
            return (
                False,
                "Google Drive מופעל אך לא הוגדר נתיב מקומי.",
            )

        try:

            path = Path(root).expanduser()

            path.mkdir(
                parents=True,
                exist_ok=True,
            )

            return (
                True,
                f"נתיב Google Drive תקין: {path}",
            )

        except Exception as exc:

            return (
                False,
                f"לא ניתן להכין את נתיב Google Drive: {exc}",
            )

    def check_gmail(self) -> tuple[bool, str]:

        sources = self.configuration.get(
            "sources",
            {},
        )

        if not isinstance(sources, dict):
            return (
                False,
                "חלק sources אינו תקין.",
            )

        gmail = sources.get(
            "gmail",
            {},
        )

        if not isinstance(gmail, dict):
            return (
                False,
                "הגדרות Gmail אינן תקינות.",
            )

        accounts = gmail.get(
            "accounts",
            [],
        )

        if not isinstance(accounts, list):
            return (
                False,
                "רשימת חשבונות Gmail אינה תקינה.",
            )

        if not accounts:
            return (
                True,
                "Gmail מופעל אך עדיין לא חובר חשבון.",
            )

        enabled_accounts = [
            account
            for account in accounts
            if isinstance(account, dict)
            and safe_bool(
                account.get("enabled"),
                False,
            )
        ]

        if not enabled_accounts:
            return (
                True,
                "Gmail מוגדר אך אין חשבון פעיל.",
            )

        invalid = []

        for account in enabled_accounts:

            email = str(
                account.get(
                    "email",
                    "",
                )
            ).strip()

            if not email:

                invalid.append(
                    str(
                        account.get(
                            "account_id",
                            "חשבון ללא מזהה",
                        )
                    )
                )

        if invalid:
            return (
                False,
                "חשבונות Gmail פעילים ללא כתובת: "
                + ", ".join(invalid),
            )

        return (
            True,
            f"נמצאו {len(enabled_accounts)} חשבונות Gmail פעילים.",
        )

    def check_processing(self) -> tuple[bool, str]:

        processing = self.configuration.get(
            "processing",
            {},
        )

        if not isinstance(processing, dict):
            return (
                False,
                "הגדרות עיבוד המסמכים אינן תקינות.",
            )

        return (
            True,
            "הגדרות עיבוד המסמכים תקינות.",
        )

    def check_ocr(self) -> tuple[bool, str]:

        ocr = self.configuration.get(
            "ocr",
            {},
        )

        if not isinstance(ocr, dict):
            return (
                False,
                "הגדרות OCR אינן תקינות.",
            )

        enabled = safe_bool(
            ocr.get("enabled"),
            False,
        )

        if not enabled:
            return (
                True,
                "OCR אינו מופעל.",
            )

        language = str(
            ocr.get(
                "language",
                "",
            )
        ).strip()

        if not language:
            return (
                False,
                "OCR מופעל אך לא הוגדרה שפה.",
            )

        return (
            True,
            f"OCR מופעל. שפה: {language}",
        )

    def check_ai_ml(self) -> tuple[bool, str]:

        ai_ml = self.configuration.get(
            "ai_ml",
            {},
        )

        if not isinstance(ai_ml, dict):
            return (
                False,
                "הגדרות AI / ML אינן תקינות.",
            )

        enabled = safe_bool(
            ai_ml.get("enabled"),
            False,
        )

        if not enabled:
            return (
                True,
                "AI / ML אינו מופעל.",
            )

        return (
            True,
            "הגדרות AI / ML תקינות.",
        )

    def check_search(self) -> tuple[bool, str]:

        search = self.configuration.get(
            "search",
            {},
        )

        if not isinstance(search, dict):
            return (
                False,
                "הגדרות החיפוש אינן תקינות.",
            )

        return (
            True,
            "הגדרות מנגנון החיפוש תקינות.",
        )

    def check_security(self) -> tuple[bool, str]:

        security = self.configuration.get(
            "security",
            {},
        )

        if not isinstance(security, dict):
            return (
                False,
                "הגדרות האבטחה אינן תקינות.",
            )

        tls_required = safe_bool(
            security.get(
                "tls_required",
                False,
            ),
            False,
        )

        if not tls_required:
            return (
                False,
                "TLS אינו מוגדר כחובה.",
            )

        return (
            True,
            "הגדרות האבטחה תקינות.",
        )

    def check_full_configuration(self) -> tuple[bool, str]:

        try:

            result = validate_configuration(
                self.configuration
            )

            if isinstance(result, tuple):

                if len(result) >= 2:

                    is_valid = bool(
                        result[0]
                    )

                    errors = result[1]

                    if is_valid and not errors:
                        return (
                            True,
                            "התצורה תקינה — לא נמצאו שגיאות.",
                        )

                    if is_valid:
                        return (
                            True,
                            "התצורה תקינה.",
                        )

                    if isinstance(errors, list):

                        if not errors:
                            return (
                                False,
                                "ולידציה דיווחה על תצורה לא תקינה "
                                "אך ללא פירוט שגיאות.",
                            )

                        message = "; ".join(
                            str(error)
                            for error in errors
                        )

                        return (
                            False,
                            f"נמצאו שגיאות: {message}",
                        )

                    return (
                        False,
                        str(errors),
                    )

                if len(result) == 1:

                    return (
                        bool(result[0]),
                        "ולידציה מלאה הסתיימה.",
                    )

            if isinstance(result, list):

                if not result:
                    return (
                        True,
                        "התצורה תקינה — לא נמצאו שגיאות.",
                    )

                message = "; ".join(
                    str(error)
                    for error in result
                )

                return (
                    False,
                    f"נמצאו שגיאות: {message}",
                )

            if isinstance(result, bool):

                return (
                    result,
                    "ולידציה מלאה תקינה."
                    if result
                    else "ולידציה מלאה נכשלה.",
                )

            return (
                True,
                "ולידציה מלאה הסתיימה.",
            )

        except Exception as exc:

            return (
                False,
                f"ולידציה מלאה נכשלה: {exc}",
            )

    @Slot()
    def run(self) -> None:

        stages = [
            (
                "מבנה התצורה",
                self.check_structure,
            ),
            (
                "בדיקת תיקיות ונתיבים",
                self.check_paths,
            ),
            (
                "בדיקת PostgreSQL",
                self.check_postgresql,
            ),
            (
                "בדיקת Google Drive",
                self.check_google_drive,
            ),
            (
                "בדיקת Gmail",
                self.check_gmail,
            ),
            (
                "בדיקת עיבוד מסמכים",
                self.check_processing,
            ),
            (
                "בדיקת OCR",
                self.check_ocr,
            ),
            (
                "בדיקת AI / ML",
                self.check_ai_ml,
            ),
            (
                "בדיקת מנגנון החיפוש",
                self.check_search,
            ),
            (
                "בדיקת אבטחה",
                self.check_security,
            ),
            (
                "ולידציה מלאה של התצורה",
                self.check_full_configuration,
            ),
        ]

        results = []

        total = len(stages)

        try:

            for index, (
                name,
                function,
            ) in enumerate(
                stages,
                start=1,
            ):

                if self.should_stop():

                    self.activity.emit(
                        f"{timestamp()}  "
                        "הבדיקה הופסקה על ידי המשתמש."
                    )

                    self.stopped.emit()
                    return

                self.stage_started.emit(
                    index,
                    name,
                )

                self.activity.emit(
                    f"{timestamp()}  מתחיל: {name}"
                )

                try:

                    ok, message = function()

                except Exception as exc:

                    ok = False

                    message = (
                        f"שגיאה: {exc}"
                    )

                    self.activity.emit(
                        f"{timestamp()}  "
                        f"Traceback עבור {name}:"
                    )

                    for line in traceback.format_exc().splitlines():

                        self.activity.emit(
                            f"{timestamp()}  {line}"
                        )

                results.append(
                    {
                        "stage": name,
                        "ok": bool(ok),
                        "message": str(message),
                    }
                )

                self.stage_finished.emit(
                    index,
                    name,
                    bool(ok),
                    str(message),
                )

                self.activity.emit(
                    f"{timestamp()}  "
                    f"{'OK' if ok else 'FAILED'}: "
                    f"{name} — {message}"
                )

                self.progress.emit(
                    int(
                        index
                        * 100
                        / total
                    )
                )

            overall_ok = all(
                result["ok"]
                for result in results
            )

            self.activity.emit(
                f"{timestamp()}  "
                "הולידציה הסתיימה: "
                f"{'תקינה' if overall_ok else 'נמצאו בעיות'}."
            )

            self.completed.emit(
                {
                    "ok": overall_ok,
                    "results": results,
                    "configuration": self.configuration,
                }
            )

        except Exception as exc:

            error = (
                f"שגיאה כללית בתהליך הולידציה: {exc}"
            )

            self.activity.emit(
                f"{timestamp()}  {error}"
            )

            self.failed.emit(
                error
            )


class DirectoriesStep(QWidget):

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel(
            "תיקיות ונתיבים"
        )

        title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )

        layout.addWidget(title)

        form = QFormLayout()

        self.server_root = QLineEdit()
        self.documents = QLineEdit()
        self.search_index = QLineEdit()
        self.backups = QLineEdit()
        self.logs = QLineEdit()
        self.config = QLineEdit()

        form.addRow(
            "Server Root:",
            self.server_root,
        )

        form.addRow(
            "Documents:",
            self.documents,
        )

        form.addRow(
            "Search Index:",
            self.search_index,
        )

        form.addRow(
            "Backups:",
            self.backups,
        )

        form.addRow(
            "Logs:",
            self.logs,
        )

        form.addRow(
            "Config:",
            self.config,
        )

        layout.addLayout(form)

        self.load_defaults()

    def load_defaults(self):

        root = Path(
            default_server_root()
        ).expanduser()

        self.server_root.setText(
            str(root)
        )

        self.documents.setText(
            str(root / "documents")
        )

        self.search_index.setText(
            str(root / "search_index")
        )

        self.backups.setText(
            str(root / "backups")
        )

        self.logs.setText(
            str(root / "logs")
        )

        self.config.setText(
            str(root / "config")
        )


class PostgreSQLStep(QWidget):

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel(
            "PostgreSQL"
        )

        title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )

        layout.addWidget(title)

        form = QFormLayout()

        self.host = QLineEdit(
            "127.0.0.1"
        )

        self.port = QSpinBox()

        self.port.setRange(
            1,
            65535,
        )

        self.port.setValue(
            5432
        )

        self.database = QLineEdit(
            "alcalay"
        )

        self.user = QLineEdit(
            "alcalay"
        )

        self.password = QLineEdit()

        self.password.setEchoMode(
            QLineEdit.Password
        )

        form.addRow(
            "Host:",
            self.host,
        )

        form.addRow(
            "Port:",
            self.port,
        )

        form.addRow(
            "Database:",
            self.database,
        )

        form.addRow(
            "User:",
            self.user,
        )

        form.addRow(
            "Password:",
            self.password,
        )

        layout.addLayout(form)

        note = QLabel(
            "הסיסמה אינה נשמרת בתצורה. "
            "בדיקת PostgreSQL משתמשת במנגנון "
            "ALCALAY_POSTGRES_PASSWORD כאשר הוא מוגדר."
        )

        note.setWordWrap(True)

        layout.addWidget(
            note
        )

        layout.addStretch()


class GoogleDriveStep(QWidget):

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel(
            "Google Drive"
        )

        title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )

        layout.addWidget(title)

        self.enabled = QCheckBox(
            "הפעל Google Drive"
        )

        layout.addWidget(
            self.enabled
        )

        form = QFormLayout()

        self.local_root = QLineEdit()

        form.addRow(
            "נתיב מקומי:",
            self.local_root,
        )

        layout.addLayout(form)

        note = QLabel(
            "בשלב זה מוגדר נתיב האחסון המקומי. "
            "חיבור Google Drive עצמו יתווסף למנגנון הסנכרון."
        )

        note.setWordWrap(True)

        layout.addWidget(
            note
        )

        layout.addStretch()


class GmailStep(QWidget):

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel(
            "Gmail"
        )

        title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )

        layout.addWidget(title)

        self.enabled = QCheckBox(
            "הפעל Gmail"
        )

        self.enabled.setChecked(
            True
        )

        layout.addWidget(
            self.enabled
        )

        form = QFormLayout()

        self.account_id = QLineEdit(
            "gmail_001"
        )

        self.email = QLineEdit()

        form.addRow(
            "Account ID:",
            self.account_id,
        )

        form.addRow(
            "כתובת Gmail:",
            self.email,
        )

        layout.addLayout(form)

        self.download_attachments = QCheckBox(
            "הורד קבצים מצורפים"
        )

        self.download_attachments.setChecked(
            True
        )

        self.index_message_body = QCheckBox(
            "אינדקס את תוכן ההודעות"
        )

        self.index_message_body.setChecked(
            True
        )

        self.incremental_sync = QCheckBox(
            "סנכרון Incremental"
        )

        self.incremental_sync.setChecked(
            True
        )

        layout.addWidget(
            self.download_attachments
        )

        layout.addWidget(
            self.index_message_body
        )

        layout.addWidget(
            self.incremental_sync
        )

        labels_box = QGroupBox(
            "Labels לסנכרון"
        )

        labels_layout = QVBoxLayout(
            labels_box
        )

        self.labels = QListWidget()

        default_labels = [
            "INBOX",
            "SENT",
            "STARRED",
            "IMPORTANT",
        ]

        for label in default_labels:

            item = QListWidgetItem(
                label
            )

            item.setCheckState(
                Qt.Checked
            )

            self.labels.addItem(
                item
            )

        labels_layout.addWidget(
            self.labels
        )

        layout.addWidget(
            labels_box
        )

        layout.addStretch()

    def selected_labels(
        self,
    ) -> list[str]:

        result = []

        for index in range(
            self.labels.count()
        ):

            item = self.labels.item(
                index
            )

            if item.checkState() == Qt.Checked:

                result.append(
                    item.text()
                )

        return result


class ProcessingStep(QWidget):

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel(
            "עיבוד מסמכים"
        )

        title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )

        layout.addWidget(title)

        self.extract_text = QCheckBox(
            "חילוץ טקסט"
        )

        self.extract_text.setChecked(
            True
        )

        self.extract_metadata = QCheckBox(
            "חילוץ Metadata"
        )

        self.extract_metadata.setChecked(
            True
        )

        self.classification = QCheckBox(
            "סיווג מסמכים"
        )

        self.classification.setChecked(
            True
        )

        self.keywords = QCheckBox(
            "חילוץ מילות מפתח"
        )

        self.keywords.setChecked(
            True
        )

        self.thesaurus = QCheckBox(
            "שימוש ב-Thesaurus"
        )

        self.thesaurus.setChecked(
            True
        )

        for widget in [
            self.extract_text,
            self.extract_metadata,
            self.classification,
            self.keywords,
            self.thesaurus,
        ]:

            layout.addWidget(
                widget
            )

        layout.addStretch()


class OCRStep(QWidget):

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel(
            "OCR"
        )

        title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )

        layout.addWidget(title)

        self.enabled = QCheckBox(
            "הפעל OCR"
        )

        self.enabled.setChecked(
            False
        )

        self.automatic = QCheckBox(
            "OCR אוטומטי"
        )

        self.automatic.setChecked(
            True
        )

        form = QFormLayout()

        self.language = QLineEdit(
            "heb+eng"
        )

        form.addRow(
            "שפה:",
            self.language,
        )

        layout.addWidget(
            self.enabled
        )

        layout.addWidget(
            self.automatic
        )

        layout.addLayout(
            form
        )

        layout.addStretch()


class AIMLStep(QWidget):

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel(
            "AI / ML"
        )

        title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )

        layout.addWidget(title)

        self.enabled = QCheckBox(
            "הפעל AI / ML"
        )

        self.enabled.setChecked(
            False
        )

        self.semantic_understanding = QCheckBox(
            "Semantic Understanding"
        )

        self.semantic_understanding.setChecked(
            True
        )

        self.classification = QCheckBox(
            "Classification"
        )

        self.classification.setChecked(
            True
        )

        self.similar_documents = QCheckBox(
            "Similar Documents"
        )

        self.similar_documents.setChecked(
            True
        )

        for widget in [
            self.enabled,
            self.semantic_understanding,
            self.classification,
            self.similar_documents,
        ]:

            layout.addWidget(
                widget
            )

        layout.addStretch()


class SearchStep(QWidget):

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel(
            "מנגנון חיפוש"
        )

        title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )

        layout.addWidget(title)

        self.full_text = QCheckBox(
            "Full Text Search"
        )

        self.full_text.setChecked(
            True
        )

        self.metadata = QCheckBox(
            "Metadata Search"
        )

        self.metadata.setChecked(
            True
        )

        self.semantic = QCheckBox(
            "Semantic Search"
        )

        self.semantic.setChecked(
            False
        )

        self.boolean = QCheckBox(
            "Boolean Search"
        )

        self.boolean.setChecked(
            True
        )

        self.reindex_changed_documents = QCheckBox(
            "Reindex מסמכים שהשתנו"
        )

        self.reindex_changed_documents.setChecked(
            True
        )

        for widget in [
            self.full_text,
            self.metadata,
            self.semantic,
            self.boolean,
            self.reindex_changed_documents,
        ]:

            layout.addWidget(
                widget
            )

        layout.addStretch()


class SecurityStep(QWidget):

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel(
            "אבטחה"
        )

        title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )

        layout.addWidget(title)

        self.authentication_required = QCheckBox(
            "Authentication נדרש"
        )

        self.authentication_required.setChecked(
            True
        )

        self.tls_required = QCheckBox(
            "TLS נדרש"
        )

        self.tls_required.setChecked(
            True
        )

        form = QFormLayout()

        self.api_secret_env = QLineEdit(
            "ALCALAY_API_SECRET"
        )

        form.addRow(
            "API Secret Environment Variable:",
            self.api_secret_env,
        )

        layout.addWidget(
            self.authentication_required
        )

        layout.addWidget(
            self.tls_required
        )

        layout.addLayout(
            form
        )

        layout.addStretch()


class ValidationStep(QWidget):

    start_requested = Signal()
    stop_requested = Signal()

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel(
            "Validation — בדיקת המערכת"
        )

        title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )

        layout.addWidget(title)

        self.status_label = QLabel(
            "מוכן לבדיקה."
        )

        self.status_label.setStyleSheet(
            "font-weight: bold;"
        )

        layout.addWidget(
            self.status_label
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

        current_group = QGroupBox(
            "שלב נוכחי"
        )

        current_layout = QVBoxLayout(
            current_group
        )

        self.current_stage = QLabel(
            "טרם התחיל"
        )

        self.current_stage.setStyleSheet(
            "font-weight: bold;"
        )

        current_layout.addWidget(
            self.current_stage
        )

        layout.addWidget(
            current_group
        )

        stages_group = QGroupBox(
            "שלבי Validation"
        )

        stages_layout = QVBoxLayout(
            stages_group
        )

        self.stage_list = QListWidget()

        self.stage_names = [
            "מבנה התצורה",
            "בדיקת תיקיות ונתיבים",
            "בדיקת PostgreSQL",
            "בדיקת Google Drive",
            "בדיקת Gmail",
            "בדיקת עיבוד מסמכים",
            "בדיקת OCR",
            "בדיקת AI / ML",
            "בדיקת מנגנון החיפוש",
            "בדיקת אבטחה",
            "ולידציה מלאה של התצורה",
        ]

        for name in self.stage_names:

            self.stage_list.addItem(
                QListWidgetItem(
                    f"○ {name}"
                )
            )

        stages_layout.addWidget(
            self.stage_list
        )

        layout.addWidget(
            stages_group
        )

        activity_group = QGroupBox(
            "Activity Log"
        )

        activity_layout = QVBoxLayout(
            activity_group
        )

        self.activity_log = QPlainTextEdit()

        self.activity_log.setReadOnly(
            True
        )

        activity_layout.addWidget(
            self.activity_log
        )

        layout.addWidget(
            activity_group
        )

        buttons = QHBoxLayout()

        self.start_button = QPushButton(
            "התחל Validation"
        )

        self.stop_button = QPushButton(
            "עצור"
        )

        self.stop_button.setEnabled(
            False
        )

        self.clear_button = QPushButton(
            "נקה Log"
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

        buttons.addStretch()

        layout.addLayout(
            buttons
        )

        self.start_button.clicked.connect(
            self.start_requested.emit
        )

        self.stop_button.clicked.connect(
            self.stop_requested.emit
        )

        self.clear_button.clicked.connect(
            self.activity_log.clear
        )

    def append_activity(
        self,
        message: str,
    ) -> None:

        self.activity_log.appendPlainText(
            message
        )

    def reset(self) -> None:

        self.progress.setValue(
            0
        )

        self.status_label.setText(
            "מוכן לבדיקה."
        )

        self.status_label.setStyleSheet(
            "font-weight: bold;"
        )

        self.current_stage.setText(
            "טרם התחיל"
        )

        self.stage_list.clear()

        for name in self.stage_names:

            self.stage_list.addItem(
                QListWidgetItem(
                    f"○ {name}"
                )
            )


class SetupWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            f"{APP_NAME} — Server Setup"
        )

        self.resize(
            1100,
            800,
        )

        self.validation_thread: Optional[
            QThread
        ] = None

        self.validation_worker: Optional[
            ValidationWorker
        ] = None

        self.last_configuration: Optional[
            Dict[str, Any]
        ] = None

        self.build_ui()

    def build_ui(self) -> None:

        central = QWidget()

        self.setCentralWidget(
            central
        )

        root_layout = QVBoxLayout(
            central
        )

        title = QLabel(
            f"{APP_NAME} — Server Setup"
        )

        title.setStyleSheet(
            "font-size: 24px; font-weight: bold;"
        )

        root_layout.addWidget(
            title
        )

        self.stack = QStackedWidget()

        self.directories_step = DirectoriesStep()

        self.postgresql_step = PostgreSQLStep()

        self.google_drive_step = GoogleDriveStep()

        self.gmail_step = GmailStep()

        self.processing_step = ProcessingStep()

        self.ocr_step = OCRStep()

        self.ai_ml_step = AIMLStep()

        self.search_step = SearchStep()

        self.security_step = SecurityStep()

        self.validation_step = ValidationStep()

        self.pages = [
            self.directories_step,
            self.postgresql_step,
            self.google_drive_step,
            self.gmail_step,
            self.processing_step,
            self.ocr_step,
            self.ai_ml_step,
            self.search_step,
            self.security_step,
            self.validation_step,
        ]

        for page in self.pages:

            self.stack.addWidget(
                page
            )

        root_layout.addWidget(
            self.stack
        )

        navigation = QHBoxLayout()

        self.previous_button = QPushButton(
            "← הקודם"
        )

        self.next_button = QPushButton(
            "הבא →"
        )

        self.save_button = QPushButton(
            "שמור תצורה"
        )

        self.validate_button = QPushButton(
            "Validation"
        )

        navigation.addWidget(
            self.previous_button
        )

        navigation.addWidget(
            self.next_button
        )

        navigation.addStretch()

        navigation.addWidget(
            self.save_button
        )

        navigation.addWidget(
            self.validate_button
        )

        root_layout.addLayout(
            navigation
        )

        self.previous_button.clicked.connect(
            self.previous_page
        )

        self.next_button.clicked.connect(
            self.next_page
        )

        self.save_button.clicked.connect(
            self.save_configuration
        )

        self.validate_button.clicked.connect(
            self.go_to_validation
        )

        self.validation_step.start_requested.connect(
            self.start_validation
        )

        self.validation_step.stop_requested.connect(
            self.stop_validation
        )

        self.stack.currentChanged.connect(
            self.update_navigation
        )

        self.update_navigation()

    def build_current_configuration(
        self,
    ) -> Dict[str, Any]:

        server_root = Path(
            self.directories_step.server_root.text()
        ).expanduser()

        paths = {
            "app_root": str(server_root),
            "documents": self.directories_step.documents.text().strip(),
            "search_index": self.directories_step.search_index.text().strip(),
            "backups": self.directories_step.backups.text().strip(),
            "logs": self.directories_step.logs.text().strip(),
            "config": self.directories_step.config.text().strip(),
            "data": str(server_root / "data"),
            "runtime": str(server_root / "runtime"),
        }

        gmail_email = (
            self.gmail_step.email.text().strip()
        )

        gmail_account = {
            "account_id": (
                self.gmail_step.account_id.text().strip()
                or "gmail_001"
            ),
            "email": gmail_email,
            "enabled": (
                self.gmail_step.enabled.isChecked()
                and bool(gmail_email)
            ),
            "selected_labels": (
                self.gmail_step.selected_labels()
            ),
            "selected_labels_only": True,
            "download_attachments": (
                self.gmail_step.download_attachments.isChecked()
            ),
            "index_message_body": (
                self.gmail_step.index_message_body.isChecked()
            ),
            "incremental_sync": (
                self.gmail_step.incremental_sync.isChecked()
            ),
            "status": (
                "not_connected"
                if not gmail_email
                else "configured"
            ),
        }

        ui_state = {

            "server": {
                "server_os": sys.platform,
                "server_name": "Alcalay Local Server",
                "api_port": 8443,
            },

            "paths": paths,

            "postgresql": {
                "host": (
                    self.postgresql_step.host.text().strip()
                ),
                "port": (
                    self.postgresql_step.port.value()
                ),
                "database": (
                    self.postgresql_step.database.text().strip()
                ),
                "user": (
                    self.postgresql_step.user.text().strip()
                ),
            },

            "google_drive": {
                "enabled": (
                    self.google_drive_step.enabled.isChecked()
                ),
                "local_root": (
                    self.google_drive_step.local_root.text().strip()
                ),
            },

            "gmail": {
                "account_id": gmail_account[
                    "account_id"
                ],
                "email": gmail_account[
                    "email"
                ],
                "enabled": gmail_account[
                    "enabled"
                ],
                "selected_labels": gmail_account[
                    "selected_labels"
                ],
                "download_attachments": gmail_account[
                    "download_attachments"
                ],
                "index_message_body": gmail_account[
                    "index_message_body"
                ],
                "incremental_sync": gmail_account[
                    "incremental_sync"
                ],
                "status": gmail_account[
                    "status"
                ],
            },

            "processing": {
                "extract_text": (
                    self.processing_step.extract_text.isChecked()
                ),
                "extract_metadata": (
                    self.processing_step.extract_metadata.isChecked()
                ),
                "classification": (
                    self.processing_step.classification.isChecked()
                ),
                "keywords": (
                    self.processing_step.keywords.isChecked()
                ),
                "thesaurus": (
                    self.processing_step.thesaurus.isChecked()
                ),
            },

            "ocr": {
                "enabled": (
                    self.ocr_step.enabled.isChecked()
                ),
                "language": (
                    self.ocr_step.language.text().strip()
                ),
                "automatic": (
                    self.ocr_step.automatic.isChecked()
                ),
            },

            "ai_ml": {
                "enabled": (
                    self.ai_ml_step.enabled.isChecked()
                ),
                "semantic_understanding": (
                    self.ai_ml_step.semantic_understanding.isChecked()
                ),
                "classification": (
                    self.ai_ml_step.classification.isChecked()
                ),
                "similar_documents": (
                    self.ai_ml_step.similar_documents.isChecked()
                ),
            },

            "search": {
                "full_text": (
                    self.search_step.full_text.isChecked()
                ),
                "metadata": (
                    self.search_step.metadata.isChecked()
                ),
                "semantic": (
                    self.search_step.semantic.isChecked()
                ),
                "boolean": (
                    self.search_step.boolean.isChecked()
                ),
                "reindex_changed_documents": (
                    self.search_step.reindex_changed_documents.isChecked()
                ),
            },

            "security": {
                "authentication_required": (
                    self.security_step.authentication_required.isChecked()
                ),
                "tls_required": (
                    self.security_step.tls_required.isChecked()
                ),
                "api_secret_env": (
                    self.security_step.api_secret_env.text().strip()
                ),
            },
        }

        return build_configuration(
            ui_state
        )

    def save_configuration(
        self,
        show_message: bool = True,
        configuration: Optional[
            Dict[str, Any]
        ] = None,
    ) -> bool:

        try:

            if configuration is None:

                configuration = (
                    self.build_current_configuration()
                )

            create_server_directories(
                configuration
            )

            paths = configuration.get(
                "paths",
                {},
            )

            config_dir_value = paths.get(
                "config"
            )

            if not config_dir_value:

                config_dir_value = (
                    self.directories_step.config.text().strip()
                )

            config_dir = Path(
                config_dir_value
            ).expanduser()

            config_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            config_path = (
                config_dir
                / "alcalay_config.json"
            )

            temp_path = (
                config_dir
                / "alcalay_config.json.tmp"
            )

            temp_path.write_text(
                json.dumps(
                    configuration,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            temp_path.replace(
                config_path
            )

            self.last_configuration = (
                configuration
            )

            self.validation_step.append_activity(
                f"{timestamp()}  "
                f"התצורה נשמרה: {config_path}"
            )

            if show_message:

                QMessageBox.information(
                    self,
                    "שמירה",
                    "התצורה נשמרה בהצלחה.\n\n"
                    f"{config_path}",
                )

            return True

        except Exception as exc:

            message = (
                f"שגיאה בשמירת התצורה: {exc}"
            )

            self.validation_step.append_activity(
                f"{timestamp()}  {message}"
            )

            if show_message:

                QMessageBox.critical(
                    self,
                    "שגיאה בשמירה",
                    message,
                )

            return False

    def current_page_index(
        self,
    ) -> int:

        return self.stack.currentIndex()

    def next_page(self) -> None:

        index = self.current_page_index()

        if index < self.stack.count() - 1:

            self.stack.setCurrentIndex(
                index + 1
            )

    def previous_page(self) -> None:

        index = self.current_page_index()

        if index > 0:

            self.stack.setCurrentIndex(
                index - 1
            )

    def go_to_validation(self) -> None:

        self.stack.setCurrentWidget(
            self.validation_step
        )

        self.start_validation()

    def update_navigation(self) -> None:

        index = self.current_page_index()

        last_index = (
            self.stack.count() - 1
        )

        self.previous_button.setEnabled(
            index > 0
        )

        self.next_button.setEnabled(
            index < last_index
        )

        self.validate_button.setEnabled(
            self.validation_thread is None
            or not self.validation_thread.isRunning()
        )

    def start_validation(self) -> None:

        if (
            self.validation_thread is not None
            and self.validation_thread.isRunning()
        ):
            return

        try:

            configuration = (
                self.build_current_configuration()
            )

            self.last_configuration = (
                configuration
            )

        except Exception as exc:

            QMessageBox.critical(
                self,
                "שגיאה",
                "לא ניתן לבנות את התצורה:\n\n"
                f"{exc}",
            )

            return

        self.validation_step.reset()

        self.validation_step.append_activity(
            f"{timestamp()}  "
            "מתחיל תהליך Validation..."
        )

        self.validation_step.start_button.setEnabled(
            False
        )

        self.validation_step.stop_button.setEnabled(
            True
        )

        self.previous_button.setEnabled(
            False
        )

        self.next_button.setEnabled(
            False
        )

        self.validate_button.setEnabled(
            False
        )

        thread = QThread(
            self
        )

        worker = ValidationWorker(
            configuration
        )

        worker.moveToThread(
            thread
        )

        self.validation_thread = (
            thread
        )

        self.validation_worker = (
            worker
        )

        thread.started.connect(
            worker.run
        )

        worker.progress.connect(
            self.on_validation_progress
        )

        worker.stage_started.connect(
            self.on_stage_started
        )

        worker.activity.connect(
            self.validation_step.append_activity
        )

        worker.stage_finished.connect(
            self.on_stage_finished
        )

        worker.completed.connect(
            self.on_validation_completed
        )

        worker.stopped.connect(
            self.on_validation_stopped
        )

        worker.failed.connect(
            self.on_validation_failed
        )

        worker.completed.connect(
            thread.quit
        )

        worker.stopped.connect(
            thread.quit
        )

        worker.failed.connect(
            thread.quit
        )

        thread.finished.connect(
            self.cleanup_validation_thread
        )

        thread.start()

    def stop_validation(self) -> None:

        worker = (
            self.validation_worker
        )

        if worker is None:
            return

        self.validation_step.append_activity(
            f"{timestamp()}  "
            "שולח בקשת עצירה..."
        )

        worker.request_stop()

        self.validation_step.stop_button.setEnabled(
            False
        )

    @Slot(int)
    def on_validation_progress(
        self,
        value: int,
    ) -> None:

        self.validation_step.progress.setValue(
            value
        )

    @Slot(int, str)
    def on_stage_started(
        self,
        index: int,
        name: str,
    ) -> None:

        self.validation_step.current_stage.setText(
            name
        )

        if (
            0 <= index - 1
            < self.validation_step.stage_list.count()
        ):

            item = (
                self.validation_step.stage_list.item(
                    index - 1
                )
            )

            item.setText(
                f"→ {name}"
            )

    @Slot(
        int,
        str,
        bool,
        str,
    )
    def on_stage_finished(
        self,
        index: int,
        name: str,
        ok: bool,
        message: str,
    ) -> None:

        if (
            0 <= index - 1
            < self.validation_step.stage_list.count()
        ):

            item = (
                self.validation_step.stage_list.item(
                    index - 1
                )
            )

            prefix = (
                "✓"
                if ok
                else "✗"
            )

            item.setText(
                f"{prefix} {name} — {message}"
            )

            item.setForeground(
                Qt.darkGreen
                if ok
                else Qt.red
            )

    @Slot(object)
    def on_validation_completed(
        self,
        result: Dict[str, Any],
    ) -> None:

        ok = bool(
            result.get("ok")
        )

        configuration = (
            result.get("configuration")
            or self.last_configuration
        )

        self.last_configuration = (
            configuration
        )

        self.validation_step.progress.setValue(
            100
        )

        self.validation_step.stop_button.setEnabled(
            False
        )

        self.validation_step.start_button.setEnabled(
            True
        )

        if ok:

            self.validation_step.status_label.setText(
                "✓ Validation הסתיים בהצלחה."
            )

            self.validation_step.status_label.setStyleSheet(
                "font-weight: bold; color: green;"
            )

            self.validation_step.append_activity(
                f"{timestamp()}  "
                "כל שלבי ה-Validation עברו בהצלחה."
            )

            saved = self.save_configuration(
                show_message=False,
                configuration=configuration,
            )

            if saved:

                self.validation_step.append_activity(
                    f"{timestamp()}  "
                    "התצורה נשמרה אוטומטית לאחר Validation."
                )

                QMessageBox.information(
                    self,
                    "Validation",
                    "Validation הסתיים בהצלחה.\n\n"
                    "התצורה נשמרה.",
                )

            else:

                QMessageBox.warning(
                    self,
                    "Validation",
                    "Validation הסתיים בהצלחה,\n"
                    "אך שמירת התצורה נכשלה.",
                )

        else:

            self.validation_step.status_label.setText(
                "✗ Validation הסתיים — נמצאו בעיות."
            )

            self.validation_step.status_label.setStyleSheet(
                "font-weight: bold; color: red;"
            )

            self.validation_step.append_activity(
                f"{timestamp()}  "
                "נמצאו בעיות. התצורה לא נשמרה אוטומטית."
            )

            QMessageBox.warning(
                self,
                "Validation",
                "Validation הסתיים.\n\n"
                "נמצאו בעיות שיש לבדוק ב-Activity Log.",
            )

    @Slot()
    def on_validation_stopped(
        self,
    ) -> None:

        self.validation_step.status_label.setText(
            "ה־Validation הופסק."
        )

        self.validation_step.status_label.setStyleSheet(
            "font-weight: bold; color: orange;"
        )

        self.validation_step.stop_button.setEnabled(
            False
        )

        self.validation_step.start_button.setEnabled(
            True
        )

        self.validation_step.append_activity(
            f"{timestamp()}  "
            "תהליך ה-Validation הופסק."
        )

    @Slot(str)
    def on_validation_failed(
        self,
        message: str,
    ) -> None:

        self.validation_step.status_label.setText(
            "✗ שגיאה ב־Validation."
        )

        self.validation_step.status_label.setStyleSheet(
            "font-weight: bold; color: red;"
        )

        self.validation_step.stop_button.setEnabled(
            False
        )

        self.validation_step.start_button.setEnabled(
            True
        )

        self.validation_step.append_activity(
            f"{timestamp()}  {message}"
        )

        QMessageBox.critical(
            self,
            "Validation Error",
            message,
        )

    @Slot()
    def cleanup_validation_thread(
        self,
    ) -> None:

        thread = (
            self.validation_thread
        )

        worker = (
            self.validation_worker
        )

        if worker is not None:
            worker.deleteLater()

        if thread is not None:
            thread.deleteLater()

        self.validation_worker = None

        self.validation_thread = None

        self.validation_step.stop_button.setEnabled(
            False
        )

        self.validation_step.start_button.setEnabled(
            True
        )

        self.validate_button.setEnabled(
            True
        )

        self.update_navigation()

    def closeEvent(
        self,
        event,
    ) -> None:

        if (
            self.validation_thread is not None
            and self.validation_thread.isRunning()
        ):

            answer = QMessageBox.question(
                self,
                "יציאה",
                "Validation עדיין מתבצע.\n\n"
                "האם לעצור את התהליך ולצאת?",
                QMessageBox.Yes
                | QMessageBox.No,
                QMessageBox.No,
            )

            if answer != QMessageBox.Yes:

                event.ignore()
                return

            if self.validation_worker is not None:

                self.validation_worker.request_stop()

            self.validation_thread.quit()

            if not self.validation_thread.wait(
                3000
            ):

                event.ignore()
                return

        event.accept()


def main() -> int:

    app = QApplication(
        sys.argv
    )

    app.setApplicationName(
        APP_NAME
    )

    window = SetupWindow()

    window.show()

    return app.exec()


if __name__ == "__main__":

    raise SystemExit(
        main()
    )