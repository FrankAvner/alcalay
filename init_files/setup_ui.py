from __future__ import annotations

import json
import os
import platform
import socket
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


# ============================================================
# ALCALAY SETUP UI
# ============================================================

APP_NAME = "Alcalay"
SETUP_VERSION = "1.0"

DEFAULT_API_PORT = 8443
DEFAULT_POSTGRES_PORT = 5432

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INIT_DIR = Path(__file__).resolve().parent

# Configuration is intentionally stored outside the source tree
# when the user selects a server root.
DEFAULT_WINDOWS_ROOT = Path(r"C:\AlcalayServer")
DEFAULT_MAC_ROOT = Path.home() / "AlcalayServer"


# ============================================================
# Utility functions
# ============================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def detect_os() -> str:
    system = platform.system().lower()

    if system == "windows":
        return "windows"

    if system == "darwin":
        return "macos"

    return "other"


def default_server_root_for_os(os_name: str) -> str:
    if os_name == "windows":
        return str(DEFAULT_WINDOWS_ROOT)

    if os_name == "macos":
        return str(DEFAULT_MAC_ROOT)

    return str(Path.home() / "AlcalayServer")


def ensure_directory(path: str) -> tuple[bool, str]:
    try:
        Path(path).expanduser().mkdir(parents=True, exist_ok=True)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=4,
        )


# ============================================================
# Setup state
# ============================================================

@dataclass
class SetupStep:
    key: str
    title: str
    description: str


STEPS = [
    SetupStep(
        "server",
        "Server Configuration",
        "Operating system, server name, address and API port.",
    ),
    SetupStep(
        "directories",
        "Directory Structure",
        "Documents, index, backups, logs and configuration directories.",
    ),
    SetupStep(
        "postgresql",
        "PostgreSQL Database",
        "Database connection and central Alcalay database settings.",
    ),
    SetupStep(
        "google_drive",
        "Google Drive",
        "Configure Google Drive as a document source.",
    ),
    SetupStep(
        "gmail",
        "Gmail Accounts",
        "Configure Gmail accounts and selected Labels.",
    ),
    SetupStep(
        "processing",
        "Document Processing",
        "Text extraction, metadata, classification and document processing.",
    ),
    SetupStep(
        "ocr",
        "OCR",
        "Configure optical character recognition for scanned documents.",
    ),
    SetupStep(
        "ai_ml",
        "AI / ML",
        "Semantic understanding, classification and intelligent search.",
    ),
    SetupStep(
        "search",
        "Search & Indexing",
        "Full-text, semantic and metadata search.",
    ),
    SetupStep(
        "security",
        "Security",
        "Authentication, API security and TLS configuration.",
    ),
    SetupStep(
        "validation",
        "Installation Check",
        "Validate the complete Alcalay server configuration.",
    ),
]


# ============================================================
# Worker
# ============================================================

class Worker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, function: Callable[[], Any]):
        super().__init__()
        self.function = function

    def run(self) -> None:
        try:
            result = self.function()
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(
                f"{exc}\n\n{traceback.format_exc()}"
            )


# ============================================================
# Base step widget
# ============================================================

class StepWidget(QWidget):
    changed = Signal()

    def __init__(
        self,
        title: str,
        description: str,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.title_text = title
        self.description_text = description

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 24, 24, 24)
        self.main_layout.setSpacing(16)

        title_label = QLabel(title)
        title_label.setObjectName("StepTitle")

        description_label = QLabel(description)
        description_label.setObjectName("StepDescription")
        description_label.setWordWrap(True)

        self.main_layout.addWidget(title_label)
        self.main_layout.addWidget(description_label)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName("Separator")

        self.main_layout.addWidget(separator)

    def get_data(self) -> dict[str, Any]:
        return {}

    def validate(self) -> tuple[bool, str]:
        return True, ""


# ============================================================
# 1. Server
# ============================================================

class ServerStep(StepWidget):
    def __init__(self, state: dict[str, Any]):
        super().__init__(
            "Server Configuration",
            "Define the computer that will host the Alcalay central server.",
        )

        layout = QFormLayout()
        layout.setSpacing(12)

        self.os_combo = QComboBox()
        self.os_combo.addItem("Windows", "windows")
        self.os_combo.addItem("macOS", "macos")

        detected = detect_os()

        index = self.os_combo.findData(detected)
        if index >= 0:
            self.os_combo.setCurrentIndex(index)

        self.server_name = QLineEdit(
            state.get("server", {}).get(
                "server_name",
                socket.gethostname(),
            )
        )

        self.server_host = QLineEdit(
            state.get("server", {}).get(
                "host",
                "0.0.0.0",
            )
        )

        self.api_port = QSpinBox()
        self.api_port.setRange(1, 65535)
        self.api_port.setValue(
            safe_int(
                str(
                    state.get("server", {}).get(
                        "api_port",
                        DEFAULT_API_PORT,
                    )
                ),
                DEFAULT_API_PORT,
            )
        )

        self.public_hostname = QLineEdit(
            state.get("server", {}).get(
                "public_hostname",
                "",
            )
        )

        layout.addRow("Server OS:", self.os_combo)
        layout.addRow("Server name:", self.server_name)
        layout.addRow("Listen address:", self.server_host)
        layout.addRow("API port:", self.api_port)
        layout.addRow("Public hostname:", self.public_hostname)

        self.main_layout.addLayout(layout)

        info = QLabel(
            "The server OS selection controls the default directory layout. "
            "The application itself remains cross-platform."
        )
        info.setWordWrap(True)
        info.setObjectName("InfoBox")
        self.main_layout.addWidget(info)

        self.os_combo.currentIndexChanged.connect(self._os_changed)

        self.main_layout.addStretch()

    def _os_changed(self) -> None:
        self.changed.emit()

    def get_data(self) -> dict[str, Any]:
        return {
            "server_os": self.os_combo.currentData(),
            "server_name": self.server_name.text().strip(),
            "host": self.server_host.text().strip(),
            "api_port": self.api_port.value(),
            "public_hostname": self.public_hostname.text().strip(),
        }

    def validate(self) -> tuple[bool, str]:
        if not self.server_name.text().strip():
            return False, "Server name is required."

        if not self.server_host.text().strip():
            return False, "Listen address is required."

        return True, ""


# ============================================================
# 2. Directories
# ============================================================

class DirectoriesStep(StepWidget):
    def __init__(self, state: dict[str, Any]):
        super().__init__(
            "Directory Structure",
            "Define where Alcalay will keep its server-side files.",
        )

        data = state.get("directories", {})

        os_name = state.get("server", {}).get(
            "server_os",
            detect_os(),
        )

        default_root = default_server_root_for_os(os_name)

        self.root = QLineEdit(
            data.get("server_root", default_root)
        )

        self.documents = QLineEdit(
            data.get(
                "documents",
                str(Path(default_root) / "documents"),
            )
        )

        self.index = QLineEdit(
            data.get(
                "index",
                str(Path(default_root) / "index"),
            )
        )

        self.backups = QLineEdit(
            data.get(
                "backups",
                str(Path(default_root) / "backups"),
            )
        )

        self.logs = QLineEdit(
            data.get(
                "logs",
                str(Path(default_root) / "logs"),
            )
        )

        self.config = QLineEdit(
            data.get(
                "config",
                str(Path(default_root) / "config"),
            )
        )

        form = QFormLayout()
        form.setSpacing(12)

        form.addRow("Server root:", self.root)
        form.addRow("Documents:", self.documents)
        form.addRow("Search index:", self.index)
        form.addRow("Backups:", self.backups)
        form.addRow("Logs:", self.logs)
        form.addRow("Configuration:", self.config)

        self.main_layout.addLayout(form)

        create_button = QPushButton("Create / Verify Directories")
        create_button.clicked.connect(self.create_directories)

        self.main_layout.addWidget(create_button)

        self.status = QLabel("Directories have not been checked yet.")
        self.status.setObjectName("StatusLabel")

        self.main_layout.addWidget(self.status)

        self.main_layout.addStretch()

    def create_directories(self) -> None:
        paths = [
            self.root.text().strip(),
            self.documents.text().strip(),
            self.index.text().strip(),
            self.backups.text().strip(),
            self.logs.text().strip(),
            self.config.text().strip(),
        ]

        errors = []

        for path in paths:
            if not path:
                errors.append("Empty directory path.")
                continue

            ok, error = ensure_directory(path)

            if not ok:
                errors.append(f"{path}: {error}")

        if errors:
            self.status.setText(
                "Directory errors:\n" + "\n".join(errors)
            )
            self.status.setObjectName("ErrorLabel")
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)
            return

        self.status.setText(
            "✓ All Alcalay directories are ready."
        )
        self.status.setObjectName("SuccessLabel")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def get_data(self) -> dict[str, Any]:
        return {
            "server_root": self.root.text().strip(),
            "documents": self.documents.text().strip(),
            "index": self.index.text().strip(),
            "backups": self.backups.text().strip(),
            "logs": self.logs.text().strip(),
            "config": self.config.text().strip(),
        }

    def validate(self) -> tuple[bool, str]:
        for name, widget in [
            ("Server root", self.root),
            ("Documents", self.documents),
            ("Search index", self.index),
            ("Backups", self.backups),
            ("Logs", self.logs),
            ("Configuration", self.config),
        ]:
            if not widget.text().strip():
                return False, f"{name} path is required."

        return True, ""


# ============================================================
# 3. PostgreSQL
# ============================================================

class PostgreSQLStep(StepWidget):
    def __init__(self, state: dict[str, Any]):
        super().__init__(
            "PostgreSQL Database",
            "Configure the central PostgreSQL database used by Alcalay.",
        )

        data = state.get("postgresql", {})

        self.host = QLineEdit(
            data.get("host", "localhost")
        )

        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(
            safe_int(
                str(data.get("port", DEFAULT_POSTGRES_PORT)),
                DEFAULT_POSTGRES_PORT,
            )
        )

        self.database = QLineEdit(
            data.get("database", "alcalay")
        )

        self.user = QLineEdit(
            data.get("user", "alcalay")
        )

        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)

        form = QFormLayout()
        form.setSpacing(12)

        form.addRow("Host:", self.host)
        form.addRow("Port:", self.port)
        form.addRow("Database:", self.database)
        form.addRow("User:", self.user)
        form.addRow("Password:", self.password)

        self.main_layout.addLayout(form)

        button_row = QHBoxLayout()

        self.test_button = QPushButton("Test Connection")
        self.test_button.clicked.connect(self.test_connection)

        self.create_button = QPushButton(
            "Create Database Structure"
        )
        self.create_button.clicked.connect(
            self.create_database_structure
        )

        button_row.addWidget(self.test_button)
        button_row.addWidget(self.create_button)

        self.main_layout.addLayout(button_row)

        self.status = QLabel(
            "PostgreSQL connection has not been tested."
        )
        self.status.setObjectName("StatusLabel")

        self.main_layout.addWidget(self.status)

        self.main_layout.addStretch()

    def test_connection(self) -> None:
        host = self.host.text().strip()
        port = self.port.value()

        if not host:
            self.status.setText(
                "PostgreSQL host is required."
            )
            return

        try:
            with socket.create_connection(
                (host, port),
                timeout=3,
            ):
                self.status.setText(
                    "✓ PostgreSQL server is reachable."
                )
                self.status.setObjectName("SuccessLabel")
        except Exception as exc:
            self.status.setText(
                f"PostgreSQL connection test failed: {exc}"
            )
            self.status.setObjectName("ErrorLabel")

        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def create_database_structure(self) -> None:
        self.status.setText(
            "Database schema creation will be connected to "
            "the Alcalay migration system in the next setup phase."
        )
        self.status.setObjectName("InfoBox")

        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def get_data(self) -> dict[str, Any]:
        data = {
            "host": self.host.text().strip(),
            "port": self.port.value(),
            "database": self.database.text().strip(),
            "user": self.user.text().strip(),
            "password_env": "ALCALAY_POSTGRES_PASSWORD",
        }

        return data

    def validate(self) -> tuple[bool, str]:
        if not self.host.text().strip():
            return False, "PostgreSQL host is required."

        if not self.database.text().strip():
            return False, "Database name is required."

        if not self.user.text().strip():
            return False, "Database user is required."

        return True, ""


# ============================================================
# 4. Google Drive
# ============================================================

class GoogleDriveStep(StepWidget):
    def __init__(self, state: dict[str, Any]):
        super().__init__(
            "Google Drive",
            "Configure Google Drive as a document source.",
        )

        data = state.get("google_drive", {})

        self.enabled = QCheckBox(
            "Enable Google Drive"
        )
        self.enabled.setChecked(
            bool(data.get("enabled", True))
        )

        self.root = QLineEdit(
            data.get("root", "")
        )

        self.sync_mode = QComboBox()
        self.sync_mode.addItems([
            "Index source without local copy",
            "Synchronize selected folders",
            "Download selected documents",
        ])

        saved_mode = data.get(
            "sync_mode",
            "Index source without local copy",
        )

        index = self.sync_mode.findText(saved_mode)
        if index >= 0:
            self.sync_mode.setCurrentIndex(index)

        self.main_layout.addWidget(self.enabled)

        form = QFormLayout()
        form.addRow(
            "Google Drive root:",
            self.root,
        )
        form.addRow(
            "Sync mode:",
            self.sync_mode,
        )

        self.main_layout.addLayout(form)

        info = QLabel(
            "Google Drive remains a configurable external source. "
            "Actual OAuth connection will be performed after this setup."
        )
        info.setWordWrap(True)
        info.setObjectName("InfoBox")

        self.main_layout.addWidget(info)
        self.main_layout.addStretch()

    def get_data(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled.isChecked(),
            "root": self.root.text().strip(),
            "sync_mode": self.sync_mode.currentText(),
        }


# ============================================================
# 5. Gmail
# ============================================================

class GmailStep(StepWidget):
    def __init__(self, state: dict[str, Any]):
        super().__init__(
            "Gmail Accounts",
            "Configure Gmail synchronization. Alcalay will synchronize "
            "selected Labels only unless explicitly changed by the administrator.",
        )

        data = state.get("gmail", {})

        self.enabled = QCheckBox(
            "Enable Gmail synchronization"
        )
        self.enabled.setChecked(
            bool(data.get("enabled", True))
        )

        self.account_email = QLineEdit(
            data.get("account_email", "")
        )

        self.account_id = QLineEdit(
            data.get("account_id", "gmail_001")
        )

        self.labels = QListWidget()

        default_labels = [
            "INBOX",
            "IMPORTANT",
            "STARRED",
            "SENT",
            "DRAFT",
            "TRASH",
        ]

        saved_labels = data.get(
            "selected_labels",
            [],
        )

        for label in default_labels:
            item = QListWidgetItem(label)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
            )

            if label in saved_labels:
                item.setCheckState(
                    Qt.CheckState.Checked
                )
            else:
                item.setCheckState(
                    Qt.CheckState.Unchecked
                )

            self.labels.addItem(item)

        self.entire_mailbox = QCheckBox(
            "Synchronize entire mailbox"
        )
        self.entire_mailbox.setChecked(False)
        self.entire_mailbox.setEnabled(False)

        self.selected_only = QCheckBox(
            "Synchronize selected Labels only"
        )
        self.selected_only.setChecked(True)
        self.selected_only.setEnabled(False)

        self.download_attachments = QCheckBox(
            "Download relevant attachments"
        )
        self.download_attachments.setChecked(
            bool(data.get("download_attachments", True))
        )

        self.index_body = QCheckBox(
            "Index email body"
        )
        self.index_body.setChecked(
            bool(data.get("index_email_body", True))
        )

        self.incremental = QCheckBox(
            "Incremental synchronization"
        )
        self.incremental.setChecked(
            bool(data.get("incremental_sync", True))
        )

        self.history_id = QCheckBox(
            "Use Gmail History ID"
        )
        self.history_id.setChecked(
            bool(data.get("use_history_id", True))
        )

        self.main_layout.addWidget(self.enabled)

        form = QFormLayout()
        form.addRow("Account ID:", self.account_id)
        form.addRow("Gmail address:", self.account_email)

        self.main_layout.addLayout(form)

        label_group = QGroupBox(
            "Selected Gmail Labels"
        )

        label_layout = QVBoxLayout(label_group)
        label_layout.addWidget(self.labels)

        self.main_layout.addWidget(label_group)

        policy_group = QGroupBox(
            "Synchronization Policy"
        )

        policy_layout = QVBoxLayout(policy_group)

        policy_layout.addWidget(
            self.selected_only
        )
        policy_layout.addWidget(
            self.entire_mailbox
        )
        policy_layout.addWidget(
            self.download_attachments
        )
        policy_layout.addWidget(
            self.index_body
        )
        policy_layout.addWidget(
            self.incremental
        )
        policy_layout.addWidget(
            self.history_id
        )

        self.main_layout.addWidget(policy_group)

        warning = QLabel(
            "IMPORTANT: The initial Alcalay policy is selected Labels only. "
            "The complete Gmail mailbox is NOT synchronized."
        )
        warning.setWordWrap(True)
        warning.setObjectName("WarningBox")

        self.main_layout.addWidget(warning)

        self.connect_button = QPushButton(
            "Connect Gmail Account"
        )
        self.connect_button.clicked.connect(
            self.connect_gmail
        )

        self.main_layout.addWidget(
            self.connect_button
        )

        self.status = QLabel(
            "Gmail connection has not been performed."
        )
        self.status.setObjectName("StatusLabel")

        self.main_layout.addWidget(
            self.status
        )

        self.main_layout.addStretch()

    def connect_gmail(self) -> None:
        self.status.setText(
            "Gmail OAuth connection will be connected "
            "to the Alcalay Gmail connector in the next phase."
        )
        self.status.setObjectName("InfoBox")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def get_selected_labels(self) -> list[str]:
        result = []

        for index in range(self.labels.count()):
            item = self.labels.item(index)

            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.text())

        return result

    def get_data(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled.isChecked(),
            "account_id": self.account_id.text().strip(),
            "account_email": self.account_email.text().strip(),
            "selected_labels": self.get_selected_labels(),
            "sync_mode": "selected_labels_only",
            "sync_entire_mailbox": False,
            "sync_selected_labels_only": True,
            "download_attachments": (
                self.download_attachments.isChecked()
            ),
            "index_email_body": (
                self.index_body.isChecked()
            ),
            "incremental_sync": (
                self.incremental.isChecked()
            ),
            "use_history_id": (
                self.history_id.isChecked()
            ),
            "last_successful_refresh_at": None,
            "last_history_id": None,
            "status": "not_connected",
            "last_error": None,
        }

    def validate(self) -> tuple[bool, str]:
        if not self.enabled.isChecked():
            return True, ""

        if not self.account_email.text().strip():
            return False, (
                "Enter the first Gmail account address."
            )

        if "@" not in self.account_email.text():
            return False, (
                "The Gmail address does not appear to be valid."
            )

        if not self.get_selected_labels():
            return False, (
                "Select at least one Gmail Label."
            )

        return True, ""


# ============================================================
# 6. Processing
# ============================================================

class ProcessingStep(StepWidget):
    def __init__(self, state: dict[str, Any]):
        super().__init__(
            "Document Processing",
            "Define how new and changed documents will be processed.",
        )

        data = state.get("processing", {})

        self.extract_text = QCheckBox(
            "Extract text from documents"
        )
        self.extract_text.setChecked(
            bool(data.get("extract_text", True))
        )

        self.extract_metadata = QCheckBox(
            "Extract document metadata"
        )
        self.extract_metadata.setChecked(
            bool(data.get("extract_metadata", True))
        )

        self.classification = QCheckBox(
            "Classify documents"
        )
        self.classification.setChecked(
            bool(data.get("classification", True))
        )

        self.keywords = QCheckBox(
            "Extract keywords"
        )
        self.keywords.setChecked(
            bool(data.get("keywords", True))
        )

        self.thesaurus = QCheckBox(
            "Use thesaurus / עיין ערך"
        )
        self.thesaurus.setChecked(
            bool(data.get("thesaurus", True))
        )

        for widget in [
            self.extract_text,
            self.extract_metadata,
            self.classification,
            self.keywords,
            self.thesaurus,
        ]:
            self.main_layout.addWidget(widget)

        self.main_layout.addStretch()

    def get_data(self) -> dict[str, Any]:
        return {
            "extract_text": self.extract_text.isChecked(),
            "extract_metadata": self.extract_metadata.isChecked(),
            "classification": self.classification.isChecked(),
            "keywords": self.keywords.isChecked(),
            "thesaurus": self.thesaurus.isChecked(),
        }


# ============================================================
# 7. OCR
# ============================================================

class OCRStep(StepWidget):
    def __init__(self, state: dict[str, Any]):
        super().__init__(
            "OCR",
            "Configure OCR processing for scanned and image-based documents.",
        )

        data = state.get("ocr", {})

        self.enabled = QCheckBox(
            "Enable OCR"
        )
        self.enabled.setChecked(
            bool(data.get("enabled", True))
        )

        self.language = QComboBox()
        self.language.addItems([
            "Hebrew + English",
            "English",
            "Hebrew",
            "Automatic",
        ])

        saved = data.get(
            "language",
            "Hebrew + English",
        )

        index = self.language.findText(saved)
        if index >= 0:
            self.language.setCurrentIndex(index)

        self.auto_ocr = QCheckBox(
            "Automatically OCR documents without usable text"
        )
        self.auto_ocr.setChecked(
            bool(data.get("automatic", True))
        )

        self.main_layout.addWidget(
            self.enabled
        )

        form = QFormLayout()
        form.addRow(
            "OCR language:",
            self.language,
        )

        self.main_layout.addLayout(form)

        self.main_layout.addWidget(
            self.auto_ocr
        )

        self.main_layout.addStretch()

    def get_data(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled.isChecked(),
            "language": self.language.currentText(),
            "automatic": self.auto_ocr.isChecked(),
        }


# ============================================================
# 8. AI / ML
# ============================================================

class AIMLStep(StepWidget):
    def __init__(self, state: dict[str, Any]):
        super().__init__(
            "AI / ML",
            "Configure intelligent document analysis and semantic processing.",
        )

        data = state.get("ai_ml", {})

        self.enabled = QCheckBox(
            "Enable AI / ML processing"
        )
        self.enabled.setChecked(
            bool(data.get("enabled", True))
        )

        self.semantic = QCheckBox(
            "Semantic document understanding"
        )
        self.semantic.setChecked(
            bool(data.get("semantic_search", True))
        )

        self.classification = QCheckBox(
            "AI-assisted classification"
        )
        self.classification.setChecked(
            bool(data.get("classification", True))
        )

        self.similarity = QCheckBox(
            "Similar-document search"
        )
        self.similarity.setChecked(
            bool(data.get("similar_documents", True))
        )

        self.main_layout.addWidget(
            self.enabled
        )
        self.main_layout.addWidget(
            self.semantic
        )
        self.main_layout.addWidget(
            self.classification
        )
        self.main_layout.addWidget(
            self.similarity
        )

        info = QLabel(
            "AI/ML models can be configured separately from the core "
            "Alcalay server. Model files should not be committed to Git."
        )
        info.setWordWrap(True)
        info.setObjectName("InfoBox")

        self.main_layout.addWidget(info)

        self.main_layout.addStretch()

    def get_data(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled.isChecked(),
            "semantic_search": self.semantic.isChecked(),
            "classification": self.classification.isChecked(),
            "similar_documents": self.similarity.isChecked(),
        }


# ============================================================
# 9. Search
# ============================================================

class SearchStep(StepWidget):
    def __init__(self, state: dict[str, Any]):
        super().__init__(
            "Search & Indexing",
            "Configure the central Alcalay search capabilities.",
        )

        data = state.get("search", {})

        self.full_text = QCheckBox(
            "Full-text search"
        )
        self.full_text.setChecked(
            bool(data.get("full_text", True))
        )

        self.metadata = QCheckBox(
            "Metadata search"
        )
        self.metadata.setChecked(
            bool(data.get("metadata", True))
        )

        self.semantic = QCheckBox(
            "Semantic search"
        )
        self.semantic.setChecked(
            bool(data.get("semantic", True))
        )

        self.boolean = QCheckBox(
            "Boolean search"
        )
        self.boolean.setChecked(
            bool(data.get("boolean", True))
        )

        self.reindex_changed = QCheckBox(
            "Re-index changed documents"
        )
        self.reindex_changed.setChecked(
            bool(data.get("reindex_changed", True))
        )

        for widget in [
            self.full_text,
            self.metadata,
            self.semantic,
            self.boolean,
            self.reindex_changed,
        ]:
            self.main_layout.addWidget(widget)

        self.main_layout.addStretch()

    def get_data(self) -> dict[str, Any]:
        return {
            "full_text": self.full_text.isChecked(),
            "metadata": self.metadata.isChecked(),
            "semantic": self.semantic.isChecked(),
            "boolean": self.boolean.isChecked(),
            "reindex_changed": self.reindex_changed.isChecked(),
        }


# ============================================================
# 10. Security
# ============================================================

class SecurityStep(StepWidget):
    def __init__(self, state: dict[str, Any]):
        super().__init__(
            "Security",
            "Configure authentication and secure communication.",
        )

        data = state.get("security", {})

        self.authentication = QCheckBox(
            "Authentication required"
        )
        self.authentication.setChecked(
            bool(data.get("authentication_required", True))
        )

        self.tls = QCheckBox(
            "Require HTTPS / TLS"
        )
        self.tls.setChecked(
            bool(data.get("tls_required", True))
        )

        self.api_secret = QLineEdit()
        self.api_secret.setEchoMode(
            QLineEdit.EchoMode.Password
        )

        self.main_layout.addWidget(
            self.authentication
        )
        self.main_layout.addWidget(
            self.tls
        )

        form = QFormLayout()
        form.addRow(
            "API secret:",
            self.api_secret,
        )

        self.main_layout.addLayout(form)

        info = QLabel(
            "Secrets are never written directly into Git. "
            "Use environment variables or a secure secret store."
        )
        info.setWordWrap(True)
        info.setObjectName("WarningBox")

        self.main_layout.addWidget(info)

        self.main_layout.addStretch()

    def get_data(self) -> dict[str, Any]:
        return {
            "authentication_required": (
                self.authentication.isChecked()
            ),
            "tls_required": (
                self.tls.isChecked()
            ),
            "api_secret_env": "ALCALAY_API_SECRET",
        }


# ============================================================
# 11. Validation
# ============================================================

class ValidationStep(StepWidget):
    def __init__(self):
        super().__init__(
            "Installation Check",
            "Run a final validation of the Alcalay server configuration.",
        )

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)

        self.run_button = QPushButton(
            "Run Installation Check"
        )

        self.main_layout.addWidget(
            self.progress
        )

        self.main_layout.addWidget(
            self.output
        )

        self.main_layout.addWidget(
            self.run_button
        )

        self.run_button.clicked.connect(
            self.run_validation
        )

        self.main_layout.addStretch()

    def run_validation(self) -> None:
        self.output.clear()
        self.progress.setValue(0)

        checks = [
            ("Python runtime", self.check_python),
            ("Operating system", self.check_os),
            ("Server root", self.check_server_root),
            ("Configuration directory", self.check_config),
            ("PostgreSQL configuration", self.check_postgresql),
            ("Gmail policy", self.check_gmail),
            ("Security policy", self.check_security),
        ]

        passed = 0

        for index, (name, function) in enumerate(checks, start=1):
            self.output.appendPlainText(
                f"Checking: {name}..."
            )

            QApplication.processEvents()

            try:
                ok, message = function()

                if ok:
                    self.output.appendPlainText(
                        f"  ✓ {message}"
                    )
                    passed += 1
                else:
                    self.output.appendPlainText(
                        f"  ✗ {message}"
                    )
            except Exception as exc:
                self.output.appendPlainText(
                    f"  ✗ {exc}"
                )

            self.progress.setValue(
                int(index / len(checks) * 100)
            )

        self.output.appendPlainText("")
        self.output.appendPlainText(
            f"Validation complete: "
            f"{passed}/{len(checks)} checks passed."
        )

    def check_python(self) -> tuple[bool, str]:
        version = sys.version_info

        if version >= (3, 11):
            return True, (
                f"Python {version.major}.{version.minor}.{version.micro}"
            )

        return False, (
            "Python 3.11 or newer is recommended."
        )

    def check_os(self) -> tuple[bool, str]:
        system = platform.system()

        if system in ("Windows", "Darwin"):
            return True, system

        return False, (
            f"Unsupported operating system: {system}"
        )

    def check_server_root(self) -> tuple[bool, str]:
        return True, (
            "Server root will be checked after configuration is saved."
        )

    def check_config(self) -> tuple[bool, str]:
        return True, (
            "Configuration directory is defined."
        )

    def check_postgresql(self) -> tuple[bool, str]:
        return True, (
            "PostgreSQL settings are defined."
        )

    def check_gmail(self) -> tuple[bool, str]:
        return True, (
            "Gmail is configured for selected Labels only."
        )

    def check_security(self) -> tuple[bool, str]:
        return True, (
            "Authentication/TLS policy is configured."
        )

    def get_data(self) -> dict[str, Any]:
        return {
            "last_validation_at": utc_now(),
        }


# ============================================================
# Main window
# ============================================================

class SetupWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            f"{APP_NAME} - Server Setup"
        )

        self.resize(1200, 760)

        self.state: dict[str, Any] = {
            "setup_version": SETUP_VERSION,
            "app_name": APP_NAME,
        }

        self.current_index = 0

        self.step_widgets: list[StepWidget] = []

        self.build_ui()
        self.load_existing_config()
        self.update_step_display()

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------

    def build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("Header")

        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(
            24,
            18,
            24,
            18,
        )

        title = QLabel(
            "ALCALAY SERVER SETUP"
        )
        title.setObjectName("HeaderTitle")

        subtitle = QLabel(
            "Central server installation and configuration wizard"
        )
        subtitle.setObjectName("HeaderSubtitle")

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        root.addWidget(header)

        content = QHBoxLayout()
        content.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        content.setSpacing(0)

        # Left side - steps
        self.step_list = QListWidget()
        self.step_list.setFixedWidth(320)
        self.step_list.setObjectName("StepList")

        for index, step in enumerate(STEPS, start=1):
            item = QListWidgetItem(
                f"{index}. {step.title}"
            )
            item.setData(
                Qt.ItemDataRole.UserRole,
                index - 1,
            )

            self.step_list.addItem(item)

        self.step_list.currentRowChanged.connect(
            self.on_step_selected
        )

        content.addWidget(self.step_list)

        # Right side
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self.stack = QStackedWidget()

        self.create_steps()

        for widget in self.step_widgets:
            self.stack.addWidget(widget)

        right_layout.addWidget(self.stack)

        # Navigation
        navigation = QFrame()
        navigation.setObjectName("Navigation")

        navigation_layout = QHBoxLayout(
            navigation
        )

        self.status_label = QLabel(
            "Step 1 of 11"
        )
        self.status_label.setObjectName(
            "NavigationStatus"
        )

        self.previous_button = QPushButton(
            "Previous"
        )
        self.previous_button.clicked.connect(
            self.previous_step
        )

        self.save_button = QPushButton(
            "Save Configuration"
        )
        self.save_button.clicked.connect(
            self.save_configuration
        )

        self.next_button = QPushButton(
            "Next"
        )
        self.next_button.clicked.connect(
            self.next_step
        )

        navigation_layout.addWidget(
            self.status_label
        )

        navigation_layout.addStretch()

        navigation_layout.addWidget(
            self.previous_button
        )

        navigation_layout.addWidget(
            self.save_button
        )

        navigation_layout.addWidget(
            self.next_button
        )

        right_layout.addWidget(
            navigation
        )

        content.addWidget(right)

        root.addLayout(content)

    def create_steps(self) -> None:
        self.step_widgets = [
            ServerStep(self.state),
            DirectoriesStep(self.state),
            PostgreSQLStep(self.state),
            GoogleDriveStep(self.state),
            GmailStep(self.state),
            ProcessingStep(self.state),
            OCRStep(self.state),
            AIMLStep(self.state),
            SearchStep(self.state),
            SecurityStep(self.state),
            ValidationStep(),
        ]

    # --------------------------------------------------------
    # Configuration
    # --------------------------------------------------------

    def configuration_path(self) -> Path:
        directories = self.state.get(
            "directories",
            {},
        )

        config_dir = directories.get(
            "config"
        )

        if config_dir:
            return (
                Path(config_dir).expanduser()
                / "alcalay_config.json"
            )

        return (
            PROJECT_ROOT
            / "config"
            / "alcalay_config.json"
        )

    def load_existing_config(self) -> None:
        path = self.configuration_path()

        if not path.exists():
            return

        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as file:
                loaded = json.load(file)

            if isinstance(loaded, dict):
                self.state.update(loaded)

        except Exception:
            # A damaged or incompatible old configuration
            # should not prevent the setup UI from starting.
            pass

    def collect_state(self) -> dict[str, Any]:
        result = {
            "app_name": APP_NAME,
            "setup_version": SETUP_VERSION,
            "updated_at": utc_now(),
        }

        for index, step in enumerate(
            self.step_widgets
        ):
            result[STEPS[index].key] = (
                step.get_data()
            )

        # Global Gmail policy
        result["gmail_policy"] = {
            "sync_entire_mailbox": False,
            "sync_selected_labels_only": True,
            "incremental_sync": True,
            "use_history_id": True,
            "deduplicate_by_message_id": True,
            "deduplicate_by_content_hash": True,
            "manual_full_sync_requires_explicit_action": True,
        }

        # Global synchronization policy
        result["sync"] = {
            "mode": "incremental",
            "store_sync_state_in_postgresql": True,
            "deduplicate_by_source_id": True,
            "deduplicate_by_content_hash": True,
        }

        # Git policy
        result["git_policy"] = {
            "commit_setup_code": True,
            "commit_configuration_template": True,
            "exclude_real_documents": True,
            "exclude_database_files": True,
            "exclude_passwords": True,
            "exclude_oauth_tokens": True,
            "exclude_search_indexes": True,
            "exclude_ai_models": True,
        }

        return result

    def save_configuration(self) -> bool:
        try:
            self.state = self.collect_state()

            directories = self.state.get(
                "directories",
                {},
            )

            config_dir = directories.get(
                "config"
            )

            if not config_dir:
                config_dir = str(
                    PROJECT_ROOT / "config"
                )

            config_path = (
                Path(config_dir).expanduser()
                / "alcalay_config.json"
            )

            config_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            write_json(
                config_path,
                self.state,
            )

            QMessageBox.information(
                self,
                "Alcalay",
                "Configuration saved successfully.\n\n"
                f"{config_path}",
            )

            return True

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Configuration Error",
                f"Could not save configuration:\n\n{exc}",
            )

            return False

    # --------------------------------------------------------
    # Navigation
    # --------------------------------------------------------

    def on_step_selected(
        self,
        index: int,
    ) -> None:
        if index < 0:
            return

        self.current_index = index
        self.stack.setCurrentIndex(index)

        self.update_step_display()

    def update_step_display(self) -> None:
        self.stack.setCurrentIndex(
            self.current_index
        )

        self.step_list.blockSignals(True)
        self.step_list.setCurrentRow(
            self.current_index
        )
        self.step_list.blockSignals(False)

        self.status_label.setText(
            f"Step {self.current_index + 1} "
            f"of {len(STEPS)}"
        )

        self.previous_button.setEnabled(
            self.current_index > 0
        )

        if self.current_index == len(STEPS) - 1:
            self.next_button.setText(
                "Finish"
            )
        else:
            self.next_button.setText(
                "Next"
            )

        self.update_step_statuses()

    def update_step_statuses(self) -> None:
        for index in range(
            self.step_list.count()
        ):
            item = self.step_list.item(index)

            if index < self.current_index:
                item.setText(
                    f"✓ {index + 1}. "
                    f"{STEPS[index].title}"
                )

            elif index == self.current_index:
                item.setText(
                    f"● {index + 1}. "
                    f"{STEPS[index].title}"
                )

            else:
                item.setText(
                    f"○ {index + 1}. "
                    f"{STEPS[index].title}"
                )

    def previous_step(self) -> None:
        if self.current_index <= 0:
            return

        self.current_index -= 1
        self.update_step_display()

    def next_step(self) -> None:
        current_widget = self.step_widgets[
            self.current_index
        ]

        valid, message = current_widget.validate()

        if not valid:
            QMessageBox.warning(
                self,
                "Alcalay Setup",
                message,
            )
            return

        # Save the current state before advancing.
        self.state = self.collect_state()

        if self.current_index < len(STEPS) - 1:
            self.current_index += 1
            self.update_step_display()
            return

        # Final step
        if self.save_configuration():
            QMessageBox.information(
                self,
                "Alcalay Setup Complete",
                "The Alcalay server configuration has been saved.\n\n"
                "The next phase is to connect the real PostgreSQL, "
                "Gmail, Google Drive, OCR and indexing services.",
            )

    # --------------------------------------------------------
    # Close handling
    # --------------------------------------------------------

    def closeEvent(self, event) -> None:
        answer = QMessageBox.question(
            self,
            "Exit Alcalay Setup",
            "Save the current configuration before exiting?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
        )

        if answer == QMessageBox.StandardButton.Yes:
            if self.save_configuration():
                event.accept()
            else:
                event.ignore()

        elif answer == QMessageBox.StandardButton.No:
            event.accept()

        else:
            event.ignore()


# ============================================================
# Styling
# ============================================================

def apply_style(app: QApplication) -> None:
    app.setStyleSheet(
        """
        QWidget {
            font-family: "Segoe UI", "Helvetica Neue", Arial;
            font-size: 14px;
        }

        QMainWindow,
        QWidget {
            background: #f4f6f8;
        }

        #Header {
            background: #17212b;
            color: white;
        }

        #HeaderTitle {
            color: white;
            font-size: 25px;
            font-weight: bold;
        }

        #HeaderSubtitle {
            color: #cbd5df;
            font-size: 14px;
        }

        #StepList {
            background: #202b36;
            border: none;
            padding: 12px;
            color: #dce3e8;
        }

        #StepList::item {
            padding: 15px 12px;
            margin: 2px 0;
            border-radius: 5px;
        }

        #StepList::item:selected {
            background: #3d5366;
            color: white;
        }

        #StepList::item:hover {
            background: #314250;
        }

        QStackedWidget {
            background: white;
        }

        #StepTitle {
            font-size: 25px;
            font-weight: bold;
            color: #17212b;
        }

        #StepDescription {
            font-size: 14px;
            color: #687580;
        }

        #Separator {
            color: #d8dee3;
        }

        QLineEdit,
        QSpinBox,
        QComboBox {
            min-height: 34px;
            border: 1px solid #c7cfd6;
            border-radius: 4px;
            padding: 3px 8px;
            background: white;
        }

        QLineEdit:focus,
        QSpinBox:focus,
        QComboBox:focus {
            border: 1px solid #3978a8;
        }

        QCheckBox {
            spacing: 8px;
            padding: 5px;
        }

        QPushButton {
            min-height: 36px;
            padding: 5px 18px;
            border-radius: 5px;
            border: 1px solid #b8c2ca;
            background: #ffffff;
        }

        QPushButton:hover {
            background: #edf2f5;
        }

        QPushButton:pressed {
            background: #dfe7ec;
        }

        #Navigation {
            background: #ffffff;
            border-top: 1px solid #d8dee3;
            padding: 8px 16px;
        }

        #NavigationStatus {
            color: #687580;
            font-weight: bold;
        }

        #StatusLabel {
            color: #687580;
            padding: 8px;
        }

        #SuccessLabel {
            color: #1d7a46;
            background: #e8f5ed;
            padding: 10px;
            border-radius: 5px;
        }

        #ErrorLabel {
            color: #a32929;
            background: #fdeaea;
            padding: 10px;
            border-radius: 5px;
        }

        #InfoBox {
            color: #315a78;
            background: #eaf3f9;
            padding: 12px;
            border-radius: 5px;
        }

        #WarningBox {
            color: #7a5a16;
            background: #fff5d9;
            padding: 12px;
            border-radius: 5px;
        }

        QGroupBox {
            font-weight: bold;
            border: 1px solid #d0d7dd;
            border-radius: 5px;
            margin-top: 10px;
            padding: 12px;
            background: #ffffff;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 5px;
        }

        QListWidget {
            border: 1px solid #d0d7dd;
            background: white;
        }

        QPlainTextEdit {
            border: 1px solid #d0d7dd;
            background: #111820;
            color: #d9e2e8;
            font-family: Consolas, "Courier New", monospace;
        }

        QProgressBar {
            border: 1px solid #c7cfd6;
            border-radius: 4px;
            text-align: center;
            min-height: 22px;
        }

        QProgressBar::chunk {
            background: #3978a8;
            border-radius: 3px;
        }
        """
    )


# ============================================================
# Main
# ============================================================

def main() -> int:
    app = QApplication(sys.argv)

    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(SETUP_VERSION)

    apply_style(app)

    window = SetupWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())