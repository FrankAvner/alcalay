from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from alcalay_server_setup import (
        build_configuration,
        create_server_directories,
        default_server_root,
        load_configuration,
        validate_configuration,
        write_configuration,
    )
except ImportError:
    from .alcalay_server_setup import (
        build_configuration,
        create_server_directories,
        default_server_root,
        load_configuration,
        validate_configuration,
        write_configuration,
    )

try:
    from setup_detector import detect_server
    from setup_installer import prepare_server
    from setup_orchestrator import (
        run_full_setup,
        run_setup_checks,
    )
except ImportError:
    from .setup_detector import detect_server
    from .setup_installer import prepare_server
    from .setup_orchestrator import (
        run_full_setup,
        run_setup_checks,
    )


APP_NAME = "Alcalay"
SETUP_VERSION = "1.0"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INIT_DIR = Path(__file__).resolve().parent

DEFAULT_API_PORT = 8443
DEFAULT_POSTGRES_PORT = 5432


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def detect_os() -> str:
    system = platform.system()

    if system == "Windows":
        return "Windows"

    if system == "Darwin":
        return "macOS"

    if system == "Linux":
        return "Linux"

    return system


def default_server_root_for_os() -> Path:
    system = detect_os()

    try:
        return Path(
            default_server_root(system)
        ).expanduser()
    except Exception:
        if system == "Windows":
            return Path(r"C:\AlcalayServer")

        return Path.home() / "AlcalayServer"


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def choose_ui_font() -> QFont:
    application = QApplication.instance()

    if application is None:
        return QFont("Arial", 10)

    database = application.fontDatabase()

    preferred = [
        "Segoe UI",
        "SF Pro Display",
        "Helvetica Neue",
        "Arial",
    ]

    families = set(
        database.families()
    )

    for family in preferred:
        if family in families:
            font = QFont(family, 10)
            font.setStyleStrategy(
                QFont.PreferAntialias
            )
            return font

    return QFont("Arial", 10)


def bool_from_value(
    value: Any,
    default: bool = False,
) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "yes",
            "1",
            "on",
        }

    return default


def safe_json(
    value: Any,
) -> str:
    try:
        return json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    except Exception:
        return str(value)


# ---------------------------------------------------------------------------
# Base step
# ---------------------------------------------------------------------------

class SetupStep(QWidget):
    def __init__(
        self,
        title: str,
        description: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        self.title = title
        self.description = description

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(
            16,
            16,
            16,
            16,
        )
        self.main_layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName(
            "stepTitle"
        )

        self.main_layout.addWidget(
            title_label
        )

        if description:
            description_label = QLabel(
                description
            )
            description_label.setWordWrap(True)
            description_label.setObjectName(
                "stepDescription"
            )

            self.main_layout.addWidget(
                description_label
            )

        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(10)

        self.main_layout.addLayout(
            self.content_layout
        )

        self.main_layout.addStretch()

    def collect_state(self) -> dict[str, Any]:
        return {}

    def apply_state(
        self,
        state: dict[str, Any],
    ) -> None:
        pass


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class ServerStep(SetupStep):
    def __init__(
        self,
        parent: QWidget | None = None,
    ):
        super().__init__(
            "1. Server",
            "Configure the Alcalay central server.",
            parent,
        )

        group = QGroupBox(
            "Server Configuration"
        )

        form = QFormLayout(group)

        self.os_combo = QComboBox()
        self.os_combo.addItems(
            [
                "Windows",
                "macOS",
                "Linux",
            ]
        )
        self.os_combo.setCurrentText(
            detect_os()
        )

        self.server_name = QLineEdit(
            platform.node() or "AlcalayServer"
        )

        self.host = QLineEdit(
            "0.0.0.0"
        )

        self.api_port = QSpinBox()
        self.api_port.setRange(
            1,
            65535,
        )
        self.api_port.setValue(
            DEFAULT_API_PORT
        )

        self.public_hostname = QLineEdit()

        form.addRow(
            "Operating system:",
            self.os_combo,
        )
        form.addRow(
            "Server name:",
            self.server_name,
        )
        form.addRow(
            "API bind address:",
            self.host,
        )
        form.addRow(
            "API port:",
            self.api_port,
        )
        form.addRow(
            "Public hostname:",
            self.public_hostname,
        )

        self.content_layout.addWidget(
            group
        )

    def collect_state(self):
        return {
            "os": self.os_combo.currentText(),
            "name": self.server_name.text().strip(),
            "host": self.host.text().strip(),
            "api_port": self.api_port.value(),
            "public_hostname": (
                self.public_hostname.text().strip()
            ),
        }

    def apply_state(self, state):
        if not state:
            return

        self.os_combo.setCurrentText(
            state.get(
                "os",
                detect_os(),
            )
        )

        self.server_name.setText(
            state.get(
                "name",
                platform.node(),
            )
        )

        self.host.setText(
            state.get(
                "host",
                "0.0.0.0",
            )
        )

        self.api_port.setValue(
            safe_int(
                state.get(
                    "api_port"
                ),
                DEFAULT_API_PORT,
            )
        )

        self.public_hostname.setText(
            state.get(
                "public_hostname",
                "",
            )
        )


# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------

class DirectoriesStep(SetupStep):
    def __init__(
        self,
        parent: QWidget | None = None,
    ):
        super().__init__(
            "2. Directories",
            "Configure the Alcalay server filesystem.",
            parent,
        )

        group = QGroupBox(
            "Filesystem"
        )

        form = QFormLayout(group)

        self.server_root = QLineEdit(
            str(
                default_server_root_for_os()
            )
        )

        self.documents = QLineEdit()
        self.search_index = QLineEdit()
        self.backups = QLineEdit()
        self.logs = QLineEdit()
        self.config = QLineEdit()

        form.addRow(
            "Server root:",
            self.server_root,
        )
        form.addRow(
            "Documents:",
            self.documents,
        )
        form.addRow(
            "Search index:",
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

        self.content_layout.addWidget(
            group
        )

        buttons = QHBoxLayout()

        self.browse_button = QPushButton(
            "Browse Server Root"
        )

        self.derive_button = QPushButton(
            "Derive Paths"
        )

        self.create_button = QPushButton(
            "Create / Verify Directories"
        )

        buttons.addWidget(
            self.browse_button
        )
        buttons.addWidget(
            self.derive_button
        )
        buttons.addWidget(
            self.create_button
        )
        buttons.addStretch()

        self.content_layout.addLayout(
            buttons
        )

        self.browse_button.clicked.connect(
            self.browse_server_root
        )

        self.derive_button.clicked.connect(
            self.derive_paths
        )

        self.create_button.clicked.connect(
            self.create_directories
        )

        self.derive_paths()

    def browse_server_root(self):
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Alcalay Server Root",
            self.server_root.text(),
        )

        if selected:
            self.server_root.setText(
                selected
            )
            self.derive_paths()

    def derive_paths(self):
        root = Path(
            self.server_root.text()
        ).expanduser()

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

    def create_directories(self):
        try:
            state = self.parent_window().collect_state()

            configuration = build_configuration(
                state
            )

            create_server_directories(
                configuration
            )

            QMessageBox.information(
                self,
                "Directories",
                "Server directories were created/verified.",
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Directory Error",
                str(exc),
            )

    def parent_window(self):
        widget = self.parent()

        while widget is not None:
            if isinstance(
                widget,
                SetupWindow,
            ):
                return widget

            widget = widget.parent()

        raise RuntimeError(
            "SetupWindow parent was not found."
        )

    def collect_state(self):
        return {
            "server_root": self.server_root.text().strip(),
            "documents": self.documents.text().strip(),
            "search_index": self.search_index.text().strip(),
            "backups": self.backups.text().strip(),
            "logs": self.logs.text().strip(),
            "config": self.config.text().strip(),
        }

    def apply_state(self, state):
        if not state:
            return

        root = state.get(
            "server_root"
        )

        if root:
            self.server_root.setText(
                root
            )

        self.documents.setText(
            state.get(
                "documents",
                self.documents.text(),
            )
        )

        self.search_index.setText(
            state.get(
                "search_index",
                self.search_index.text(),
            )
        )

        self.backups.setText(
            state.get(
                "backups",
                self.backups.text(),
            )
        )

        self.logs.setText(
            state.get(
                "logs",
                self.logs.text(),
            )
        )

        self.config.setText(
            state.get(
                "config",
                self.config.text(),
            )
        )


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------

class PostgreSQLStep(SetupStep):
    def __init__(
        self,
        parent=None,
    ):
        super().__init__(
            "3. PostgreSQL",
            "Configure the PostgreSQL endpoint. "
            "Database creation and migrations are separate operations.",
            parent,
        )

        group = QGroupBox(
            "PostgreSQL"
        )

        form = QFormLayout(group)

        self.host = QLineEdit(
            "localhost"
        )

        self.port = QSpinBox()
        self.port.setRange(
            1,
            65535,
        )
        self.port.setValue(
            DEFAULT_POSTGRES_PORT
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

        self.content_layout.addWidget(
            group
        )

        self.status = QLabel(
            "Not tested."
        )

        self.content_layout.addWidget(
            self.status
        )

        button = QPushButton(
            "Test PostgreSQL Endpoint"
        )

        button.clicked.connect(
            self.test_connection
        )

        self.content_layout.addWidget(
            button
        )

        info = QLabel(
            "The password is not written to the Alcalay configuration file."
        )
        info.setWordWrap(True)

        self.content_layout.addWidget(
            info
        )

    def test_connection(self):
        try:
            from setup_database import check_postgresql

            configuration = (
                self.parent_window()
                .build_current_configuration()
            )

            result = check_postgresql(
                configuration
            )

            self.status.setText(
                result.message
            )

        except Exception as exc:
            self.status.setText(
                f"PostgreSQL check failed: {exc}"
            )

    def parent_window(self):
        widget = self.parent()

        while widget is not None:
            if isinstance(
                widget,
                SetupWindow,
            ):
                return widget

            widget = widget.parent()

        raise RuntimeError(
            "SetupWindow parent was not found."
        )

    def collect_state(self):
        return {
            "host": self.host.text().strip(),
            "port": self.port.value(),
            "database": self.database.text().strip(),
            "user": self.user.text().strip(),
            "password": self.password.text(),
        }

    def apply_state(self, state):
        if not state:
            return

        self.host.setText(
            state.get(
                "host",
                "localhost",
            )
        )

        self.port.setValue(
            safe_int(
                state.get("port"),
                DEFAULT_POSTGRES_PORT,
            )
        )

        self.database.setText(
            state.get(
                "database",
                "alcalay",
            )
        )

        self.user.setText(
            state.get(
                "user",
                "alcalay",
            )
        )


# ---------------------------------------------------------------------------
# Google Drive
# ---------------------------------------------------------------------------

class GoogleDriveStep(SetupStep):
    def __init__(self, parent=None):
        super().__init__(
            "4. Google Drive",
            "Configure the Google Drive source.",
            parent,
        )

        self.enabled = QCheckBox(
            "Enable Google Drive"
        )

        self.root = QLineEdit()

        self.sync_mode = QComboBox()
        self.sync_mode.addItems(
            [
                "Configured root",
                "Selected folders",
            ]
        )

        self.content_layout.addWidget(
            self.enabled
        )

        group = QGroupBox(
            "Google Drive"
        )

        form = QFormLayout(group)

        form.addRow(
            "Root / address:",
            self.root,
        )

        form.addRow(
            "Sync mode:",
            self.sync_mode,
        )

        self.content_layout.addWidget(
            group
        )

        self.status = QLabel(
            "OAuth connection has not been performed."
        )

        self.content_layout.addWidget(
            self.status
        )

    def collect_state(self):
        return {
            "enabled": self.enabled.isChecked(),
            "root": self.root.text().strip(),
            "sync_mode": self.sync_mode.currentText(),
        }

    def apply_state(self, state):
        if not state:
            return

        self.enabled.setChecked(
            bool_from_value(
                state.get("enabled")
            )
        )

        self.root.setText(
            state.get(
                "root",
                "",
            )
        )

        self.sync_mode.setCurrentText(
            state.get(
                "sync_mode",
                "Configured root",
            )
        )


# ---------------------------------------------------------------------------
# Gmail
# ---------------------------------------------------------------------------

class GmailStep(SetupStep):
    def __init__(self, parent=None):
        super().__init__(
            "5. Gmail",
            "Configure incremental Gmail synchronization. "
            "The entire mailbox is never synchronized automatically.",
            parent,
        )

        self.enabled = QCheckBox(
            "Enable Gmail"
        )

        self.account_id = QLineEdit(
            "gmail_001"
        )

        self.email = QLineEdit()

        self.labels = QLineEdit(
            "INBOX,IMPORTANT,STARRED,SENT,DRAFT,TRASH"
        )

        self.selected_only = QCheckBox(
            "Selected labels only"
        )
        self.selected_only.setChecked(True)

        self.attachments = QCheckBox(
            "Download relevant attachments"
        )
        self.attachments.setChecked(True)

        self.body_indexing = QCheckBox(
            "Index message body"
        )
        self.body_indexing.setChecked(True)

        self.incremental = QCheckBox(
            "Incremental synchronization"
        )
        self.incremental.setChecked(True)

        self.history_id = QCheckBox(
            "Use Gmail historyId"
        )
        self.history_id.setChecked(True)

        group = QGroupBox(
            "Gmail Account"
        )

        form = QFormLayout(group)

        form.addRow(
            "Account ID:",
            self.account_id,
        )

        form.addRow(
            "Email:",
            self.email,
        )

        form.addRow(
            "Labels:",
            self.labels,
        )

        self.content_layout.addWidget(
            group
        )

        self.content_layout.addWidget(
            self.selected_only
        )
        self.content_layout.addWidget(
            self.attachments
        )
        self.content_layout.addWidget(
            self.body_indexing
        )
        self.content_layout.addWidget(
            self.incremental
        )
        self.content_layout.addWidget(
            self.history_id
        )

        self.status = QLabel(
            "OAuth connection has not been performed."
        )

        self.content_layout.addWidget(
            self.status
        )

    def collect_state(self):
        labels = [
            item.strip()
            for item in self.labels.text().split(",")
            if item.strip()
        ]

        return {
            "enabled": self.enabled.isChecked(),
            "account_id": self.account_id.text().strip(),
            "email": self.email.text().strip(),
            "labels": labels,
            "selected_labels_only": (
                self.selected_only.isChecked()
            ),
            "download_attachments": (
                self.attachments.isChecked()
            ),
            "index_body": (
                self.body_indexing.isChecked()
            ),
            "incremental": (
                self.incremental.isChecked()
            ),
            "history_id": (
                self.history_id.isChecked()
            ),
        }

    def apply_state(self, state):
        if not state:
            return

        self.enabled.setChecked(
            bool_from_value(
                state.get("enabled")
            )
        )

        self.account_id.setText(
            state.get(
                "account_id",
                "gmail_001",
            )
        )

        self.email.setText(
            state.get(
                "email",
                "",
            )
        )

        labels = state.get(
            "labels",
            [],
        )

        if isinstance(labels, list):
            self.labels.setText(
                ",".join(labels)
            )

        self.selected_only.setChecked(
            bool_from_value(
                state.get(
                    "selected_labels_only",
                    True,
                ),
                True,
            )
        )

        self.attachments.setChecked(
            bool_from_value(
                state.get(
                    "download_attachments",
                    True,
                ),
                True,
            )
        )

        self.body_indexing.setChecked(
            bool_from_value(
                state.get(
                    "index_body",
                    True,
                ),
                True,
            )
        )

        self.incremental.setChecked(
            bool_from_value(
                state.get(
                    "incremental",
                    True,
                ),
                True,
            )
        )

        self.history_id.setChecked(
            bool_from_value(
                state.get(
                    "history_id",
                    True,
                ),
                True,
            )
        )


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

class ProcessingStep(SetupStep):
    def __init__(self, parent=None):
        super().__init__(
            "6. Processing",
            "Configure document processing.",
            parent,
        )

        self.text = QCheckBox(
            "Text extraction"
        )
        self.metadata = QCheckBox(
            "Metadata extraction"
        )
        self.classification = QCheckBox(
            "Document classification"
        )
        self.keywords = QCheckBox(
            "Keywords"
        )
        self.thesaurus = QCheckBox(
            "Thesaurus / עיין ערך"
        )

        for checkbox in [
            self.text,
            self.metadata,
            self.classification,
            self.keywords,
            self.thesaurus,
        ]:
            checkbox.setChecked(True)
            self.content_layout.addWidget(
                checkbox
            )

    def collect_state(self):
        return {
            "text_extraction": self.text.isChecked(),
            "metadata_extraction": self.metadata.isChecked(),
            "classification": self.classification.isChecked(),
            "keywords": self.keywords.isChecked(),
            "thesaurus": self.thesaurus.isChecked(),
        }

    def apply_state(self, state):
        if not state:
            return

        self.text.setChecked(
            bool_from_value(
                state.get(
                    "text_extraction",
                    True,
                ),
                True,
            )
        )

        self.metadata.setChecked(
            bool_from_value(
                state.get(
                    "metadata_extraction",
                    True,
                ),
                True,
            )
        )

        self.classification.setChecked(
            bool_from_value(
                state.get(
                    "classification",
                    True,
                ),
                True,
            )
        )

        self.keywords.setChecked(
            bool_from_value(
                state.get(
                    "keywords",
                    True,
                ),
                True,
            )
        )

        self.thesaurus.setChecked(
            bool_from_value(
                state.get(
                    "thesaurus",
                    True,
                ),
                True,
            )
        )


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

class OCRStep(SetupStep):
    def __init__(self, parent=None):
        super().__init__(
            "7. OCR",
            "Configure OCR for scanned/image documents.",
            parent,
        )

        self.enabled = QCheckBox(
            "Enable OCR"
        )
        self.enabled.setChecked(True)

        self.language = QComboBox()
        self.language.addItems(
            [
                "heb+eng",
                "eng",
                "heb",
            ]
        )

        self.automatic = QCheckBox(
            "Automatic OCR"
        )
        self.automatic.setChecked(True)

        form = QFormLayout()

        form.addRow(
            "Language:",
            self.language,
        )

        self.content_layout.addWidget(
            self.enabled
        )
        self.content_layout.addLayout(
            form
        )
        self.content_layout.addWidget(
            self.automatic
        )

    def collect_state(self):
        return {
            "enabled": self.enabled.isChecked(),
            "language": self.language.currentText(),
            "automatic": self.automatic.isChecked(),
        }

    def apply_state(self, state):
        if not state:
            return

        self.enabled.setChecked(
            bool_from_value(
                state.get(
                    "enabled",
                    True,
                ),
                True,
            )
        )

        self.language.setCurrentText(
            state.get(
                "language",
                "heb+eng",
            )
        )

        self.automatic.setChecked(
            bool_from_value(
                state.get(
                    "automatic",
                    True,
                ),
                True,
            )
        )


# ---------------------------------------------------------------------------
# AI / ML
# ---------------------------------------------------------------------------

class AIMLStep(SetupStep):
    def __init__(self, parent=None):
        super().__init__(
            "8. AI / ML",
            "Configure semantic processing and machine learning.",
            parent,
        )

        self.enabled = QCheckBox(
            "Enable AI / ML"
        )
        self.enabled.setChecked(True)

        self.semantic = QCheckBox(
            "Semantic understanding"
        )
        self.semantic.setChecked(True)

        self.classification = QCheckBox(
            "AI classification"
        )
        self.classification.setChecked(True)

        self.similarity = QCheckBox(
            "Similar-document analysis"
        )
        self.similarity.setChecked(True)

        for checkbox in [
            self.enabled,
            self.semantic,
            self.classification,
            self.similarity,
        ]:
            self.content_layout.addWidget(
                checkbox
            )

    def collect_state(self):
        return {
            "enabled": self.enabled.isChecked(),
            "semantic": self.semantic.isChecked(),
            "classification": self.classification.isChecked(),
            "similarity": self.similarity.isChecked(),
        }

    def apply_state(self, state):
        if not state:
            return

        self.enabled.setChecked(
            bool_from_value(
                state.get(
                    "enabled",
                    True,
                ),
                True,
            )
        )

        self.semantic.setChecked(
            bool_from_value(
                state.get(
                    "semantic",
                    True,
                ),
                True,
            )
        )

        self.classification.setChecked(
            bool_from_value(
                state.get(
                    "classification",
                    True,
                ),
                True,
            )
        )

        self.similarity.setChecked(
            bool_from_value(
                state.get(
                    "similarity",
                    True,
                ),
                True,
            )
        )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchStep(SetupStep):
    def __init__(self, parent=None):
        super().__init__(
            "9. Search",
            "Configure unified search.",
            parent,
        )

        self.full_text = QCheckBox(
            "Full-text search"
        )
        self.metadata = QCheckBox(
            "Metadata search"
        )
        self.semantic = QCheckBox(
            "Semantic search"
        )
        self.boolean = QCheckBox(
            "Boolean search"
        )
        self.reindex = QCheckBox(
            "Reindex changed documents"
        )

        for checkbox in [
            self.full_text,
            self.metadata,
            self.semantic,
            self.boolean,
            self.reindex,
        ]:
            checkbox.setChecked(True)
            self.content_layout.addWidget(
                checkbox
            )

    def collect_state(self):
        return {
            "full_text": self.full_text.isChecked(),
            "metadata": self.metadata.isChecked(),
            "semantic": self.semantic.isChecked(),
            "boolean": self.boolean.isChecked(),
            "reindex_changed_documents": (
                self.reindex.isChecked()
            ),
        }

    def apply_state(self, state):
        if not state:
            return

        self.full_text.setChecked(
            bool_from_value(
                state.get(
                    "full_text",
                    True,
                ),
                True,
            )
        )

        self.metadata.setChecked(
            bool_from_value(
                state.get(
                    "metadata",
                    True,
                ),
                True,
            )
        )

        self.semantic.setChecked(
            bool_from_value(
                state.get(
                    "semantic",
                    True,
                ),
                True,
            )
        )

        self.boolean.setChecked(
            bool_from_value(
                state.get(
                    "boolean",
                    True,
                ),
                True,
            )
        )

        self.reindex.setChecked(
            bool_from_value(
                state.get(
                    "reindex_changed_documents",
                    True,
                ),
                True,
            )
        )


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

class SecurityStep(SetupStep):
    def __init__(self, parent=None):
        super().__init__(
            "10. Security",
            "Configure authentication and transport security.",
            parent,
        )

        self.authentication = QCheckBox(
            "Authentication required"
        )
        self.authentication.setChecked(True)

        self.tls = QCheckBox(
            "TLS / HTTPS required"
        )
        self.tls.setChecked(True)

        self.secret = QLineEdit()
        self.secret.setEchoMode(
            QLineEdit.Password
        )

        group = QGroupBox(
            "Security Policy"
        )

        form = QFormLayout(group)

        form.addRow(
            "API secret:",
            self.secret,
        )

        self.content_layout.addWidget(
            self.authentication
        )
        self.content_layout.addWidget(
            self.tls
        )
        self.content_layout.addWidget(
            group
        )

        info = QLabel(
            "The API secret is not written to the JSON configuration."
        )
        info.setWordWrap(True)

        self.content_layout.addWidget(
            info
        )

    def generate_secret(self):
        try:
            from setup_auth import generate_api_secret

            self.secret.setText(
                generate_api_secret()
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Security Error",
                str(exc),
            )

    def collect_state(self):
        return {
            "authentication_required": (
                self.authentication.isChecked()
            ),
            "tls_required": (
                self.tls.isChecked()
            ),
            "api_secret_configured": bool(
                self.secret.text().strip()
            ),
        }

    def apply_state(self, state):
        if not state:
            return

        self.authentication.setChecked(
            bool_from_value(
                state.get(
                    "authentication_required",
                    True,
                ),
                True,
            )
        )

        self.tls.setChecked(
            bool_from_value(
                state.get(
                    "tls_required",
                    True,
                ),
                True,
            )
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class ValidationStep(SetupStep):
    def __init__(self, parent=None):
        super().__init__(
            "11. Validation",
            "Run the complete Alcalay setup checks.",
            parent,
        )

        self.status = QLabel(
            "No validation has been executed."
        )

        self.progress = QProgressBar()
        self.progress.setRange(
            0,
            100,
        )
        self.progress.setValue(
            0
        )

        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setMinimumHeight(
            300
        )

        self.content_layout.addWidget(
            self.status
        )
        self.content_layout.addWidget(
            self.progress
        )
        self.content_layout.addWidget(
            self.report
        )

    def set_running(self):
        self.status.setText(
            "Running setup checks..."
        )
        self.progress.setRange(
            0,
            0,
        )

    def set_result(
        self,
        success: bool,
        message: str,
        report: Any,
    ):
        self.progress.setRange(
            0,
            100,
        )
        self.progress.setValue(
            100 if success else 50
        )

        self.status.setText(
            (
                "Setup checks completed successfully."
                if success
                else
                "Setup checks completed with failures."
            )
        )

        self.report.setPlainText(
            message
            + "\n\n"
            + safe_json(report)
        )


# ---------------------------------------------------------------------------
# Main Setup Window
# ---------------------------------------------------------------------------

class SetupWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            f"{APP_NAME} - Server Setup"
        )

        self.resize(
            1200,
            820,
        )

        self.setMinimumSize(
            1000,
            700,
        )

        self.steps: list[SetupStep] = []

        self.build_ui()
        self.load_existing_config()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def build_ui(self):
        central = QWidget()

        root_layout = QVBoxLayout(
            central
        )

        root_layout.setContentsMargins(
            12,
            12,
            12,
            12,
        )

        # Header
        header = QHBoxLayout()

        title = QLabel(
            "ALCALAY"
        )
        title.setObjectName(
            "appTitle"
        )

        subtitle = QLabel(
            "Central Server Setup"
        )
        subtitle.setObjectName(
            "appSubtitle"
        )

        header.addWidget(
            title
        )
        header.addWidget(
            subtitle
        )
        header.addStretch()

        os_label = QLabel(
            f"OS: {detect_os()}"
        )

        header.addWidget(
            os_label
        )

        root_layout.addLayout(
            header
        )

        # Main area
        main_layout = QHBoxLayout()

        # Left navigation
        self.navigation = QVBoxLayout()
        self.navigation.setSpacing(
            4
        )

        navigation_widget = QWidget()
        navigation_widget.setLayout(
            self.navigation
        )
        navigation_widget.setMaximumWidth(
            240
        )

        self.nav_buttons: list[QPushButton] = []

        # Stack
        self.stack = QStackedWidget()

        # Steps
        self.server_step = ServerStep()
        self.directories_step = DirectoriesStep()
        self.postgres_step = PostgreSQLStep()
        self.drive_step = GoogleDriveStep()
        self.gmail_step = GmailStep()
        self.processing_step = ProcessingStep()
        self.ocr_step = OCRStep()
        self.ai_step = AIMLStep()
        self.search_step = SearchStep()
        self.security_step = SecurityStep()
        self.validation_step = ValidationStep()

        self.steps = [
            self.server_step,
            self.directories_step,
            self.postgres_step,
            self.drive_step,
            self.gmail_step,
            self.processing_step,
            self.ocr_step,
            self.ai_step,
            self.search_step,
            self.security_step,
            self.validation_step,
        ]

        for index, step in enumerate(
            self.steps
        ):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(step)

            self.stack.addWidget(
                scroll
            )

            button = QPushButton(
                f"{index + 1}. {step.title.split('.', 1)[-1].strip()}"
            )

            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False,
                i=index: self.show_step(i)
            )

            self.nav_buttons.append(
                button
            )

            self.navigation.addWidget(
                button
            )

        self.navigation.addStretch()

        main_layout.addWidget(
            navigation_widget
        )

        main_layout.addWidget(
            self.stack,
            1,
        )

        root_layout.addLayout(
            main_layout,
            1,
        )

        # Action buttons
        actions_group = QGroupBox(
            "Setup Actions"
        )

        actions = QHBoxLayout(
            actions_group
        )

        self.detect_button = QPushButton(
            "Auto Detect"
        )

        self.validate_button = QPushButton(
            "Validate"
        )

        self.prepare_button = QPushButton(
            "Prepare Server"
        )

        self.full_setup_button = QPushButton(
            "Run Full Setup"
        )

        self.save_button = QPushButton(
            "Save Configuration"
        )

        self.finish_button = QPushButton(
            "Finish"
        )

        actions.addWidget(
            self.detect_button
        )
        actions.addWidget(
            self.validate_button
        )
        actions.addWidget(
            self.prepare_button
        )
        actions.addWidget(
            self.full_setup_button
        )
        actions.addWidget(
            self.save_button
        )
        actions.addWidget(
            self.finish_button
        )

        root_layout.addWidget(
            actions_group
        )

        self.setCentralWidget(
            central
        )

        # Signals
        self.detect_button.clicked.connect(
            self.auto_detect
        )

        self.validate_button.clicked.connect(
            self.validate_current
        )

        self.prepare_button.clicked.connect(
            self.prepare_current
        )

        self.full_setup_button.clicked.connect(
            self.full_setup
        )

        self.save_button.clicked.connect(
            self.save_configuration
        )

        self.finish_button.clicked.connect(
            self.finish_setup
        )

        self.show_step(
            0
        )

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def show_step(
        self,
        index: int,
    ):
        if index < 0:
            index = 0

        if index >= len(self.steps):
            index = len(self.steps) - 1

        self.stack.setCurrentIndex(
            index
        )

        for i, button in enumerate(
            self.nav_buttons
        ):
            button.setChecked(
                i == index
            )

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def collect_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {}

        server = self.server_step.collect_state()
        directories = (
            self.directories_step.collect_state()
        )
        postgres = (
            self.postgres_step.collect_state()
        )
        drive = (
            self.drive_step.collect_state()
        )
        gmail = (
            self.gmail_step.collect_state()
        )
        processing = (
            self.processing_step.collect_state()
        )
        ocr = (
            self.ocr_step.collect_state()
        )
        ai_ml = (
            self.ai_step.collect_state()
        )
        search = (
            self.search_step.collect_state()
        )
        security = (
            self.security_step.collect_state()
        )

        state.update(
            server
        )

        state["server_root"] = (
            directories.get(
                "server_root",
                "",
            )
        )

        state["paths"] = directories

        state["postgresql"] = postgres

        state["google_drive"] = drive

        state["gmail"] = gmail

        state["processing"] = processing

        state["ocr"] = ocr

        state["ai_ml"] = ai_ml

        state["search"] = search

        state["security"] = security

        # Global synchronization policy.
        state["sync"] = {
            "incremental": True,
            "deduplication": True,
            "changed_documents_only": True,
            "manual_full_sync_only": True,
            "timestamp_tracking": True,
        }

        state["git_policy"] = {
            "store_source_code": True,
            "store_configuration_templates": True,
            "store_schema": True,
            "exclude_runtime_data": True,
            "exclude_documents": True,
            "exclude_credentials": True,
            "exclude_tokens": True,
            "exclude_indexes": True,
            "exclude_models": True,
        }

        return state

    def build_current_configuration(
        self,
    ) -> dict[str, Any]:
        state = self.collect_state()

        return build_configuration(
            state
        )

    # ------------------------------------------------------------------
    # Existing configuration
    # ------------------------------------------------------------------

    def configuration_path(self) -> Path:
        root = Path(
            self.directories_step.server_root.text()
        ).expanduser()

        return (
            root
            / "config"
            / "alcalay_config.json"
        )

    def load_existing_config(self):
        path = self.configuration_path()

        if not path.exists():
            return

        try:
            configuration = load_configuration(
                path
            )

            self.apply_configuration(
                configuration
            )

        except Exception as exc:
            QMessageBox.warning(
                self,
                "Configuration",
                f"Existing configuration could not be loaded:\n{exc}",
            )

    def apply_configuration(
        self,
        configuration: dict[str, Any],
    ):
        server = configuration.get(
            "server",
            {},
        )

        paths = configuration.get(
            "paths",
            {},
        )

        postgres = configuration.get(
            "postgresql",
            {},
        )

        google_drive = (
            configuration
            .get(
                "sources",
                {},
            )
            .get(
                "google_drive",
                {},
            )
        )

        gmail_root = (
            configuration
            .get(
                "sources",
                {},
            )
            .get(
                "gmail",
                {},
            )
        )

        gmail_accounts = gmail_root.get(
            "accounts",
            [],
        )

        gmail = (
            gmail_accounts[0]
            if gmail_accounts
            else {}
        )

        processing = configuration.get(
            "processing",
            {},
        )

        ocr = configuration.get(
            "ocr",
            {},
        )

        ai_ml = configuration.get(
            "ai_ml",
            {},
        )

        search = configuration.get(
            "search",
            {},
        )

        security = configuration.get(
            "security",
            {},
        )

        self.server_step.apply_state(
            server
        )

        self.directories_step.apply_state(
            paths
        )

        self.postgres_step.apply_state(
            postgres
        )

        self.drive_step.apply_state(
            google_drive
        )

        self.gmail_step.apply_state(
            gmail
        )

        self.processing_step.apply_state(
            processing
        )

        self.ocr_step.apply_state(
            ocr
        )

        self.ai_step.apply_state(
            ai_ml
        )

        self.search_step.apply_state(
            search
        )

        self.security_step.apply_state(
            security
        )

    # ------------------------------------------------------------------
    # Auto detection
    # ------------------------------------------------------------------

    def auto_detect(self):
        try:
            configuration = (
                self.build_current_configuration()
            )

            server = configuration.get(
                "server",
                {},
            )

            postgres = configuration.get(
                "postgresql",
                {},
            )

            paths = configuration.get(
                "paths",
                {},
            )

            result = detect_server(
                server_os=server.get(
                    "os",
                    detect_os(),
                ),
                server_root=paths.get(
                    "server_root",
                    str(
                        default_server_root_for_os()
                    ),
                ),
                api_port=safe_int(
                    server.get(
                        "api_port"
                    ),
                    DEFAULT_API_PORT,
                ),
                postgres_host=postgres.get(
                    "host",
                    "localhost",
                ),
                postgres_port=safe_int(
                    postgres.get(
                        "port"
                    ),
                    DEFAULT_POSTGRES_PORT,
                ),
            )

            self.apply_detection(
                result.to_dict()
            )

            self.show_detection_result(
                result.to_dict()
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Auto Detect",
                f"Automatic detection failed:\n{exc}",
            )

    def apply_detection(
        self,
        detection: dict[str, Any],
    ):
        os_name = detection.get(
            "operating_system",
            detect_os(),
        )

        self.server_step.os_combo.setCurrentText(
            os_name
        )

        self.server_step.server_name.setText(
            detection.get(
                "machine_name",
                platform.node(),
            )
        )

        root = detection.get(
            "server_root"
        )

        if root:
            self.directories_step.server_root.setText(
                root
            )
            self.directories_step.derive_paths()

        api_port = detection.get(
            "api_port"
        )

        if api_port:
            self.server_step.api_port.setValue(
                safe_int(
                    api_port,
                    DEFAULT_API_PORT,
                )
            )

        postgres_host = detection.get(
            "postgres_host"
        )

        if postgres_host:
            self.postgres_step.host.setText(
                postgres_host
            )

        postgres_port = detection.get(
            "postgres_port"
        )

        if postgres_port:
            self.postgres_step.port.setValue(
                safe_int(
                    postgres_port,
                    DEFAULT_POSTGRES_PORT,
                )
            )

    def show_detection_result(
        self,
        detection: dict[str, Any],
    ):
        text = (
            "Alcalay automatic detection\n"
            "===========================\n\n"
        )

        text += safe_json(
            detection
        )

        QMessageBox.information(
            self,
            "Auto Detect",
            text,
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_current(
        self,
    ) -> bool:
        try:
            configuration = (
                self.build_current_configuration()
            )

            result = validate_configuration(
                configuration
            )

            success, message = (
                self.interpret_validation_result(
                    result
                )
            )

            self.validation_step.set_result(
                success,
                message,
                result,
            )

            self.show_step(
                10
            )

            return success

        except Exception as exc:
            self.validation_step.set_result(
                False,
                str(exc),
                {},
            )

            self.show_step(
                10
            )

            return False

    def interpret_validation_result(
        self,
        result: Any,
    ) -> tuple[bool, str]:
        if isinstance(
            result,
            bool,
        ):
            return (
                result,
                (
                    "Configuration validation passed."
                    if result
                    else
                    "Configuration validation failed."
                ),
            )

        if isinstance(
            result,
            dict,
        ):
            success = result.get(
                "success"
            )

            if success is None:
                success = result.get(
                    "valid"
                )

            if success is None:
                success = result.get(
                    "ok",
                    False,
                )

            return (
                bool(success),
                safe_json(result),
            )

        return (
            False,
            str(result),
        )

    # ------------------------------------------------------------------
    # Prepare server
    # ------------------------------------------------------------------

    def prepare_current(
        self,
    ):
        answer = QMessageBox.question(
            self,
            "Prepare Server",
            (
                "This will create/verify the Alcalay "
                "server directories and configuration.\n\n"
                "It will NOT install PostgreSQL, perform OAuth, "
                "or start the API service.\n\n"
                "Continue?"
            ),
            QMessageBox.Yes
            | QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        try:
            configuration = (
                self.build_current_configuration()
            )

            result = prepare_server(
                configuration
            )

            if result.success:
                QMessageBox.information(
                    self,
                    "Prepare Server",
                    result.message,
                )
            else:
                QMessageBox.warning(
                    self,
                    "Prepare Server",
                    result.message,
                )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Prepare Server",
                str(exc),
            )

    # ------------------------------------------------------------------
    # Full setup
    # ------------------------------------------------------------------

    def full_setup(
        self,
    ):
        answer = QMessageBox.question(
            self,
            "Run Full Setup",
            (
                "Run the complete Alcalay setup workflow?\n\n"
                "This prepares the local Alcalay filesystem "
                "and executes all setup checks.\n\n"
                "External services are not automatically "
                "installed, authenticated, or started."
            ),
            QMessageBox.Yes
            | QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        self.validation_step.set_running()
        self.show_step(
            10
        )

        QApplication.processEvents()

        try:
            configuration = (
                self.build_current_configuration()
            )

            execution = run_full_setup(
                configuration
            )

            self.validation_step.set_result(
                execution.success,
                execution.message,
                execution.report,
            )

            if execution.success:
                QMessageBox.information(
                    self,
                    "Full Setup",
                    execution.message,
                )
            else:
                QMessageBox.warning(
                    self,
                    "Full Setup",
                    execution.message,
                )

        except Exception as exc:
            self.validation_step.set_result(
                False,
                f"Full setup failed: {exc}",
                {},
            )

            QMessageBox.critical(
                self,
                "Full Setup",
                str(exc),
            )

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_configuration(
        self,
    ) -> bool:
        try:
            configuration = (
                self.build_current_configuration()
            )

            result = validate_configuration(
                configuration
            )

            valid, message = (
                self.interpret_validation_result(
                    result
                )
            )

            if not valid:
                answer = QMessageBox.question(
                    self,
                    "Validation",
                    (
                        "The configuration contains validation "
                        "issues.\n\n"
                        "Do you want to save it anyway?"
                    ),
                    QMessageBox.Yes
                    | QMessageBox.No,
                )

                if answer != QMessageBox.Yes:
                    return False

            create_server_directories(
                configuration
            )

            path = write_configuration(
                configuration
            )

            QMessageBox.information(
                self,
                "Configuration Saved",
                (
                    "Alcalay configuration saved successfully.\n\n"
                    f"{path}"
                ),
            )

            return True

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Configuration",
                str(exc),
            )

            return False

    # ------------------------------------------------------------------
    # Finish
    # ------------------------------------------------------------------

    def finish_setup(
        self,
    ):
        if not self.save_configuration():
            return

        QMessageBox.information(
            self,
            "Alcalay Setup",
            (
                "The Alcalay setup configuration has been saved.\n\n"
                "The next implementation phases are:\n"
                "• PostgreSQL database/user setup\n"
                "• Database migrations\n"
                "• Google Drive OAuth\n"
                "• Gmail OAuth\n"
                "• Document processing\n"
                "• Search indexing\n"
                "• API service management"
            ),
        )

        self.close()

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def closeEvent(
        self,
        event,
    ):
        answer = QMessageBox.question(
            self,
            "Exit Setup",
            (
                "Do you want to save the current "
                "Alcalay configuration before exiting?"
            ),
            QMessageBox.Save
            | QMessageBox.Discard
            | QMessageBox.Cancel,
        )

        if answer == QMessageBox.Save:
            if self.save_configuration():
                event.accept()
            else:
                event.ignore()

        elif answer == QMessageBox.Discard:
            event.accept()

        else:
            event.ignore()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

def apply_style(
    application: QApplication,
):
    font = choose_ui_font()
    application.setFont(
        font
    )

    application.setStyleSheet(
        """
        QWidget {
            font-size: 13px;
        }

        QLabel#appTitle {
            font-size: 26px;
            font-weight: bold;
        }

        QLabel#appSubtitle {
            font-size: 17px;
            margin-left: 10px;
        }

        QLabel#stepTitle {
            font-size: 22px;
            font-weight: bold;
        }

        QLabel#stepDescription {
            font-size: 13px;
        }

        QPushButton {
            min-height: 32px;
            padding-left: 12px;
            padding-right: 12px;
        }

        QPushButton:checked {
            font-weight: bold;
        }

        QLineEdit,
        QComboBox,
        QSpinBox {
            min-height: 30px;
        }

        QGroupBox {
            font-weight: bold;
            margin-top: 10px;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }

        QPlainTextEdit {
            font-family: monospace;
        }
        """
    )


def main():
    application = QApplication(
        sys.argv
    )

    application.setApplicationName(
        APP_NAME
    )

    apply_style(
        application
    )

    window = SetupWindow()
    window.show()

    sys.exit(
        application.exec()
    )


if __name__ == "__main__":
    main()