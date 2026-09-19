# -*- coding: utf-8 -*-

"""
Alcalay - Gmail Management Window
=================================

Gmail account and label management UI.

Responsibilities:
    - Manage Gmail accounts
    - Add Gmail accounts through OAuth
    - Remove Gmail accounts from Alcalay
    - Display linked Gmail labels
    - Display last refresh time for each label
    - Add Gmail labels
    - Remove Gmail labels
    - Refresh labels from Gmail

This module does NOT perform message synchronization.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gmail.gmail_connection import GmailConnection
from gmail.gmail_accounts import GmailAccountsManager


# ======================================================================
# Gmail Window
# ======================================================================

class GmailWindow(QMainWindow):
    """
    Main Gmail management window.

    The window manages:
        - Gmail accounts
        - Linked Gmail labels
        - Label refresh information
    """

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle(
            "Alcalay - ניהול Gmail"
        )

        self.setMinimumSize(
            1050,
            700,
        )

        # --------------------------------------------------------------
        # Data
        # --------------------------------------------------------------

        self.accounts_manager = GmailAccountsManager()

        self.connection: Optional[GmailConnection] = None

        self.selected_email = ""

        self.available_labels = []

        # --------------------------------------------------------------
        # UI references
        # --------------------------------------------------------------

        self.accounts_list = None
        self.linked_labels_list = None
        self.available_labels_list = None

        self.account_email_label = None
        self.account_updated_label = None
        self.status_label = None

        self.remove_account_button = None
        self.remove_label_button = None
        self.refresh_labels_button = None

        # --------------------------------------------------------------
        # Build
        # --------------------------------------------------------------

        self._build_ui()
        self._apply_style()
        self._load_accounts()

    # ==================================================================
    # Style
    # ==================================================================

    def _apply_style(self):

        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f6f8;
            }

            QWidget {
                font-size: 13px;
            }

            QLabel {
                color: #202124;
            }

            QLabel#windowTitle {
                font-size: 22px;
                font-weight: bold;
                color: #202124;
            }

            QLabel#sectionTitle {
                font-size: 16px;
                font-weight: bold;
                color: #202124;
            }

            QLabel#sectionInfo {
                color: #6b7280;
                font-size: 12px;
            }

            QLabel#statusLabel {
                color: #5f6368;
                font-size: 12px;
            }

            QLabel#accountEmail {
                font-size: 17px;
                font-weight: bold;
                color: #1a73e8;
            }

            QLabel#accountUpdated {
                color: #6b7280;
                font-size: 12px;
            }

            QFrame#card {
                background-color: white;
                border: 1px solid #d9dce1;
                border-radius: 8px;
            }

            QListWidget {
                background-color: white;
                border: 1px solid #d9dce1;
                border-radius: 5px;
                padding: 4px;
            }

            QListWidget::item {
                padding: 7px;
                border-radius: 4px;
            }

            QListWidget::item:hover {
                background-color: #f1f3f4;
            }

            QListWidget::item:selected {
                background-color: #dbeafe;
                color: #111827;
            }

            QPushButton {
                background-color: white;
                border: 1px solid #c9cdd3;
                border-radius: 5px;
                padding: 7px 12px;
                min-height: 20px;
            }

            QPushButton:hover {
                background-color: #f0f2f5;
            }

            QPushButton:pressed {
                background-color: #e5e7eb;
            }

            QPushButton:disabled {
                color: #9ca3af;
                background-color: #f3f4f6;
            }

            QPushButton#primaryButton {
                background-color: #1a73e8;
                color: white;
                border: 1px solid #1a73e8;
                font-weight: bold;
            }

            QPushButton#primaryButton:hover {
                background-color: #1765cc;
            }

            QPushButton#secondaryButton {
                background-color: #f8f9fa;
            }

            QPushButton#dangerButton {
                color: #b3261e;
            }

            QPushButton#dangerButton:hover {
                background-color: #fce8e6;
            }

            QSplitter::handle {
                background-color: #e5e7eb;
            }
        """)

    # ==================================================================
    # UI
    # ==================================================================

    def _build_ui(self):

        central = QWidget()

        self.setCentralWidget(
            central
        )

        main_layout = QVBoxLayout(
            central
        )

        main_layout.setContentsMargins(
            25,
            25,
            25,
            25,
        )

        main_layout.setSpacing(
            18
        )

        # ==============================================================
        # Header
        # ==============================================================

        header_layout = QHBoxLayout()

        title = QLabel(
            "ניהול חשבונות Gmail"
        )

        title.setObjectName(
            "windowTitle"
        )

        header_layout.addWidget(
            title
        )

        header_layout.addStretch()

        self.status_label = QLabel(
            "מוכן"
        )

        self.status_label.setObjectName(
            "statusLabel"
        )

        header_layout.addWidget(
            self.status_label
        )

        main_layout.addLayout(
            header_layout
        )

        # ==============================================================
        # Main splitter
        # ==============================================================

        splitter = QSplitter(
            Qt.Orientation.Horizontal
        )

        # ==============================================================
        # LEFT - Accounts
        # ==============================================================

        accounts_frame = QFrame()

        accounts_frame.setObjectName(
            "card"
        )

        accounts_layout = QVBoxLayout(
            accounts_frame
        )

        accounts_layout.setContentsMargins(
            20,
            20,
            20,
            20,
        )

        accounts_layout.setSpacing(
            12
        )

        accounts_title = QLabel(
            "חשבונות Gmail"
        )

        accounts_title.setObjectName(
            "sectionTitle"
        )

        accounts_layout.addWidget(
            accounts_title
        )

        accounts_info = QLabel(
            "בחר חשבון לניהול התגיות המקושרות אליו."
        )

        accounts_info.setObjectName(
            "sectionInfo"
        )

        accounts_info.setWordWrap(
            True
        )

        accounts_layout.addWidget(
            accounts_info
        )

        self.accounts_list = QListWidget()

        self.accounts_list.setObjectName(
            "accountsList"
        )

        self.accounts_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )

        self.accounts_list.currentItemChanged.connect(
            self._account_selected
        )

        accounts_layout.addWidget(
            self.accounts_list,
            1,
        )

        # --------------------------------------------------------------
        # Account buttons
        # --------------------------------------------------------------

        account_buttons = QHBoxLayout()

        add_account_button = QPushButton(
            "+ הוסף חשבון Gmail"
        )

        add_account_button.setObjectName(
            "primaryButton"
        )

        add_account_button.clicked.connect(
            self._add_account
        )

        account_buttons.addWidget(
            add_account_button
        )

        self.remove_account_button = QPushButton(
            "הסר חשבון"
        )

        self.remove_account_button.setObjectName(
            "dangerButton"
        )

        self.remove_account_button.setEnabled(
            False
        )

        self.remove_account_button.clicked.connect(
            self._remove_account
        )

        account_buttons.addWidget(
            self.remove_account_button
        )

        accounts_layout.addLayout(
            account_buttons
        )

        splitter.addWidget(
            accounts_frame
        )

        # ==============================================================
        # RIGHT - Account and labels
        # ==============================================================

        right_widget = QWidget()

        right_layout = QVBoxLayout(
            right_widget
        )

        right_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        right_layout.setSpacing(
            15
        )

        # ==============================================================
        # Account information
        # ==============================================================

        account_info_frame = QFrame()

        account_info_frame.setObjectName(
            "card"
        )

        account_info_layout = QVBoxLayout(
            account_info_frame
        )

        account_info_layout.setContentsMargins(
            20,
            18,
            20,
            18,
        )

        account_info_layout.setSpacing(
            8
        )

        account_header = QLabel(
            "חשבון נבחר"
        )

        account_header.setObjectName(
            "sectionTitle"
        )

        account_info_layout.addWidget(
            account_header
        )

        self.account_email_label = QLabel(
            "לא נבחר חשבון"
        )

        self.account_email_label.setObjectName(
            "accountEmail"
        )

        self.account_email_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
        )

        account_info_layout.addWidget(
            self.account_email_label
        )

        self.account_updated_label = QLabel(
            "מועד עדכון אחרון: —"
        )

        self.account_updated_label.setObjectName(
            "accountUpdated"
        )

        self.account_updated_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
        )

        account_info_layout.addWidget(
            self.account_updated_label
        )

        right_layout.addWidget(
            account_info_frame
        )

        # ==============================================================
        # Linked labels
        # ==============================================================

        linked_frame = QFrame()

        linked_frame.setObjectName(
            "card"
        )

        linked_layout = QVBoxLayout(
            linked_frame
        )

        linked_layout.setContentsMargins(
            20,
            20,
            20,
            20,
        )

        linked_layout.setSpacing(
            10
        )

        linked_title = QLabel(
            "תגיות שנבחרו לחשבון"
        )

        linked_title.setObjectName(
            "sectionTitle"
        )

        linked_layout.addWidget(
            linked_title
        )

        linked_info = QLabel(
            "התגיות הבאות מקושרות לחשבון. "
            "לכל תגית מוצג מועד הרענון האחרון."
        )

        linked_info.setObjectName(
            "sectionInfo"
        )

        linked_info.setWordWrap(
            True
        )

        linked_layout.addWidget(
            linked_info
        )

        self.linked_labels_list = QListWidget()

        self.linked_labels_list.setObjectName(
            "labelsList"
        )

        self.linked_labels_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )

        linked_layout.addWidget(
            self.linked_labels_list,
            1,
        )

        # --------------------------------------------------------------
        # Linked label buttons
        # --------------------------------------------------------------

        linked_buttons = QHBoxLayout()

        self.refresh_labels_button = QPushButton(
            "רענן תגיות מ-Gmail"
        )

        self.refresh_labels_button.setObjectName(
            "secondaryButton"
        )

        self.refresh_labels_button.setEnabled(
            False
        )

        self.refresh_labels_button.clicked.connect(
            self._refresh_gmail_labels
        )

        linked_buttons.addWidget(
            self.refresh_labels_button
        )

        linked_buttons.addStretch()

        self.remove_label_button = QPushButton(
            "הסר תגית"
        )

        self.remove_label_button.setObjectName(
            "dangerButton"
        )

        self.remove_label_button.setEnabled(
            False
        )

        self.remove_label_button.clicked.connect(
            self._remove_label
        )

        linked_buttons.addWidget(
            self.remove_label_button
        )

        linked_layout.addLayout(
            linked_buttons
        )

        self.linked_labels_list.currentItemChanged.connect(
            self._linked_label_selected
        )

        right_layout.addWidget(
            linked_frame,
            1,
        )

        # ==============================================================
        # Available labels
        # ==============================================================

        available_frame = QFrame()

        available_frame.setObjectName(
            "card"
        )

        available_layout = QVBoxLayout(
            available_frame
        )

        available_layout.setContentsMargins(
            20,
            20,
            20,
            20,
        )

        available_layout.setSpacing(
            10
        )

        available_title = QLabel(
            "הוספת תגיות"
        )

        available_title.setObjectName(
            "sectionTitle"
        )

        available_layout.addWidget(
            available_title
        )

        available_info = QLabel(
            "רשימת התגיות הקיימות ב-Gmail. "
            "לחיצה כפולה על תגית מוסיפה אותה לחשבון."
        )

        available_info.setObjectName(
            "sectionInfo"
        )

        available_info.setWordWrap(
            True
        )

        available_layout.addWidget(
            available_info
        )

        self.available_labels_list = QListWidget()

        self.available_labels_list.setObjectName(
            "labelsList"
        )

        self.available_labels_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )

        self.available_labels_list.itemDoubleClicked.connect(
            self._add_label_by_double_click
        )

        available_layout.addWidget(
            self.available_labels_list,
            1,
        )

        right_layout.addWidget(
            available_frame,
            1,
        )

        splitter.addWidget(
            right_widget
        )

        splitter.setSizes(
            [330, 720]
        )

        main_layout.addWidget(
            splitter,
            1,
        )

    # ==================================================================
    # Accounts
    # ==================================================================

    def _load_accounts(self):

        self.accounts_list.clear()

        accounts = (
            self.accounts_manager.get_accounts()
        )

        for account in accounts:

            email = account.get(
                "email",
                ""
            )

            if not email:
                continue

            item = QListWidgetItem(
                email
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                email
            )

            self.accounts_list.addItem(
                item
            )

        if self.accounts_list.count() > 0:

            self.accounts_list.setCurrentRow(
                0
            )

        else:

            self._clear_account_view()

    # ------------------------------------------------------------------
    # Account selected
    # ------------------------------------------------------------------

    def _account_selected(
        self,
        current,
        previous,
    ):

        if current is None:

            self._clear_account_view()

            return

        email = current.data(
            Qt.ItemDataRole.UserRole
        )

        if not email:

            self._clear_account_view()

            return

        self.selected_email = email

        self.account_email_label.setText(
            email
        )

        account = (
            self.accounts_manager
            .get_account(email)
        )

        if account:

            updated = account.get(
                "updated_at"
            )

            self.account_updated_label.setText(
                "מועד עדכון אחרון: "
                + self._format_datetime(updated)
            )

        else:

            self.account_updated_label.setText(
                "מועד עדכון אחרון: —"
            )

        self.remove_account_button.setEnabled(
            True
        )

        self.refresh_labels_button.setEnabled(
            True
        )

        self._load_linked_labels()

        self._load_available_labels()

    # ------------------------------------------------------------------
    # Clear account view
    # ------------------------------------------------------------------

    def _clear_account_view(self):

        self.selected_email = ""

        self.account_email_label.setText(
            "לא נבחר חשבון"
        )

        self.account_updated_label.setText(
            "מועד עדכון אחרון: —"
        )

        self.linked_labels_list.clear()

        self.available_labels_list.clear()

        self.remove_account_button.setEnabled(
            False
        )

        self.remove_label_button.setEnabled(
            False
        )

        self.refresh_labels_button.setEnabled(
            False
        )

    # ==================================================================
    # Add account
    # ==================================================================

    def _add_account(self):

        self.status_label.setText(
            "מתחבר לחשבון Gmail..."
        )

        QApplication.processEvents()

        connection = GmailConnection()

        try:

            email = connection.connect()

            existing = (
                self.accounts_manager
                .get_account(email)
            )

            if existing is None:

                self.accounts_manager.add_account(
                    email
                )

            else:

                self.accounts_manager.update_account(
                    email
                )

            if self.connection is not None:

                self.connection.disconnect()

            self.connection = connection

            self._load_accounts()

            for row in range(
                self.accounts_list.count()
            ):

                item = self.accounts_list.item(
                    row
                )

                item_email = item.data(
                    Qt.ItemDataRole.UserRole
                )

                if item_email == email:

                    self.accounts_list.setCurrentRow(
                        row
                    )

                    break

            self._refresh_gmail_labels(
                show_message=False
            )

            self.status_label.setText(
                f"החשבון {email} נוסף בהצלחה"
            )

        except Exception as exc:

            self.status_label.setText(
                "הוספת החשבון נכשלה"
            )

            QMessageBox.critical(
                self,
                "שגיאה בחיבור ל-Gmail",
                (
                    "לא ניתן היה לחבר את חשבון Gmail.\n\n"
                    f"{exc}"
                ),
            )

    # ==================================================================
    # Remove account
    # ==================================================================

    def _remove_account(self):

        if not self.selected_email:
            return

        email = self.selected_email

        answer = QMessageBox.question(
            self,
            "הסרת חשבון",
            (
                f"האם להסיר את החשבון:\n\n"
                f"{email}\n\n"
                "החשבון יוסר מרשימת החשבונות של Alcalay.\n"
                "הודעות ומסמכים שכבר נשמרו מקומית לא יימחקו."
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:

            if (
                self.connection is not None
                and self.connection.get_account_email()
                == email
            ):

                self.connection.disconnect()

                self.connection = None

            self.accounts_manager.remove_account(
                email
            )

            self.selected_email = ""

            self._load_accounts()

            self.status_label.setText(
                f"החשבון {email} הוסר"
            )

        except Exception as exc:

            QMessageBox.critical(
                self,
                "שגיאה",
                f"לא ניתן להסיר את החשבון.\n\n{exc}",
            )

    # ==================================================================
    # Linked labels
    # ==================================================================

    def _load_linked_labels(self):

        self.linked_labels_list.clear()

        if not self.selected_email:
            return

        labels = (
            self.accounts_manager.get_labels(
                self.selected_email
            )
        )

        for label in labels:

            label_id = label.get(
                "id",
                ""
            )

            label_name = label.get(
                "name",
                label_id
            )

            last_fetch = label.get(
                "last_fetch"
            )

            display_text = (
                f"{label_name}"
                f"    |    רענון אחרון: "
                f"{self._format_datetime(last_fetch)}"
            )

            item = QListWidgetItem(
                display_text
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                label_id
            )

            item.setData(
                Qt.ItemDataRole.UserRole + 1,
                label_name
            )

            self.linked_labels_list.addItem(
                item
            )

        self.remove_label_button.setEnabled(
            self.linked_labels_list.currentItem()
            is not None
        )

    # ------------------------------------------------------------------
    # Linked label selected
    # ------------------------------------------------------------------

    def _linked_label_selected(
        self,
        current,
        previous,
    ):

        self.remove_label_button.setEnabled(
            current is not None
        )

    # ==================================================================
    # Available Gmail labels
    # ==================================================================

    def _load_available_labels(self):

        self.available_labels_list.clear()

        if not self.selected_email:
            return

        if (
            self.connection is None
            or not self.connection.is_connected()
            or self.connection.get_account_email()
            != self.selected_email
        ):

            try:

                self.connection = GmailConnection(
                    self.selected_email
                )

                self.connection.connect(
                    self.selected_email
                )

            except Exception as exc:

                self.status_label.setText(
                    "לא ניתן לטעון את תגיות Gmail"
                )

                QMessageBox.warning(
                    self,
                    "חיבור Gmail",
                    (
                        "לא ניתן להתחבר לחשבון לצורך "
                        "טעינת התגיות.\n\n"
                        f"{exc}"
                    ),
                )

                return

        try:

            service = self.connection.get_service()

            response = (
                service.users()
                .labels()
                .list(
                    userId="me"
                )
                .execute()
            )

            labels = response.get(
                "labels",
                []
            )

            self.available_labels = labels

            linked_labels = (
                self.accounts_manager.get_labels(
                    self.selected_email
                )
            )

            linked_ids = {
                label.get("id")
                for label in linked_labels
            }

            system_labels = []
            user_labels = []

            for label in labels:

                label_id = label.get(
                    "id",
                    ""
                )

                label_name = label.get(
                    "name",
                    label_id
                )

                if label_id in linked_ids:
                    continue

                if label.get("type") == "system":

                    system_labels.append(
                        label
                    )

                else:

                    user_labels.append(
                        label
                    )

            system_labels.sort(
                key=lambda item:
                item.get("name", "").lower()
            )

            user_labels.sort(
                key=lambda item:
                item.get("name", "").lower()
            )

            for label in (
                system_labels + user_labels
            ):

                label_id = label.get(
                    "id",
                    ""
                )

                label_name = label.get(
                    "name",
                    label_id
                )

                if label.get("type") == "system":

                    display_name = (
                        f"[מערכת] {label_name}"
                    )

                else:

                    display_name = label_name

                item = QListWidgetItem(
                    display_name
                )

                item.setData(
                    Qt.ItemDataRole.UserRole,
                    label_id
                )

                item.setData(
                    Qt.ItemDataRole.UserRole + 1,
                    label_name
                )

                self.available_labels_list.addItem(
                    item
                )

            self.status_label.setText(
                f"נטענו {len(labels)} תגיות מ-Gmail"
            )

        except Exception as exc:

            self.status_label.setText(
                "טעינת התגיות נכשלה"
            )

            QMessageBox.warning(
                self,
                "שגיאה",
                (
                    "לא ניתן לטעון את תגיות Gmail.\n\n"
                    f"{exc}"
                ),
            )

    # ==================================================================
    # Add label
    # ==================================================================

    def _add_label_by_double_click(
        self,
        item,
    ):

        if item is None:
            return

        if not self.selected_email:
            return

        label_id = item.data(
            Qt.ItemDataRole.UserRole
        )

        label_name = item.data(
            Qt.ItemDataRole.UserRole + 1
        )

        if not label_id:
            return

        try:

            existing = (
                self.accounts_manager.get_label(
                    self.selected_email,
                    label_id
                )
            )

            if existing:
                return

            self.accounts_manager.add_label(
                self.selected_email,
                label_id,
                label_name,
            )

            self._load_linked_labels()

            self._load_available_labels()

            self._refresh_account_display()

            self.status_label.setText(
                f"התגית '{label_name}' נוספה"
            )

        except Exception as exc:

            QMessageBox.critical(
                self,
                "שגיאה בהוספת תגית",
                (
                    "לא ניתן להוסיף את התגית.\n\n"
                    f"{exc}"
                ),
            )

    # ==================================================================
    # Remove label
    # ==================================================================

    def _remove_label(self):

        if not self.selected_email:
            return

        item = (
            self.linked_labels_list.currentItem()
        )

        if item is None:
            return

        label_id = item.data(
            Qt.ItemDataRole.UserRole
        )

        label_name = item.data(
            Qt.ItemDataRole.UserRole + 1
        )

        answer = QMessageBox.question(
            self,
            "הסרת תגית",
            (
                f"האם להסיר את התגית:\n\n"
                f"{label_name}\n\n"
                "התגית לא תימחק מ-Gmail. "
                "היא רק תוסר מרשימת התגיות "
                "המקושרות ב-Alcalay."
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:

            self.accounts_manager.remove_label(
                self.selected_email,
                label_id
            )

            self._load_linked_labels()

            self._load_available_labels()

            self.status_label.setText(
                f"התגית '{label_name}' הוסרה"
            )

        except Exception as exc:

            QMessageBox.critical(
                self,
                "שגיאה בהסרת תגית",
                (
                    "לא ניתן להסיר את התגית.\n\n"
                    f"{exc}"
                ),
            )

    # ==================================================================
    # Refresh labels from Gmail
    # ==================================================================

    def _refresh_gmail_labels(
        self,
        show_message: bool = True,
    ):

        if not self.selected_email:
            return

        self.status_label.setText(
            "מרענן תגיות מ-Gmail..."
        )

        QApplication.processEvents()

        try:

            if (
                self.connection is None
                or not self.connection.is_connected()
                or self.connection.get_account_email()
                != self.selected_email
            ):

                self.connection = GmailConnection(
                    self.selected_email
                )

                self.connection.connect(
                    self.selected_email
                )

            service = self.connection.get_service()

            response = (
                service.users()
                .labels()
                .list(
                    userId="me"
                )
                .execute()
            )

            labels = response.get(
                "labels",
                []
            )

            gmail_labels_by_id = {
                label.get("id"): label
                for label in labels
            }

            linked_labels = (
                self.accounts_manager.get_labels(
                    self.selected_email
                )
            )

            for local_label in linked_labels:

                label_id = local_label.get(
                    "id",
                    ""
                )

                gmail_label = (
                    gmail_labels_by_id.get(
                        label_id
                    )
                )

                if gmail_label:

                    current_name = gmail_label.get(
                        "name",
                        local_label.get(
                            "name",
                            label_id
                        )
                    )

                    self.accounts_manager.update_label(
                        self.selected_email,
                        label_id,
                        label_name=current_name,
                    )

                self.accounts_manager.mark_fetch(
                    self.selected_email,
                    label_id,
                )

            self._load_linked_labels()

            self._load_available_labels()

            self._refresh_account_display()

            self.status_label.setText(
                f"רענון הסתיים — {len(labels)} תגיות נמצאו"
            )

            if show_message:

                QMessageBox.information(
                    self,
                    "רענון תגיות",
                    (
                        f"הרענון הסתיים בהצלחה.\n\n"
                        f"נמצאו {len(labels)} תגיות ב-Gmail."
                    ),
                )

        except Exception as exc:

            self.status_label.setText(
                "רענון התגיות נכשל"
            )

            QMessageBox.critical(
                self,
                "שגיאה ברענון",
                (
                    "לא ניתן לרענן את תגיות Gmail.\n\n"
                    f"{exc}"
                ),
            )

    # ==================================================================
    # Account display refresh
    # ==================================================================

    def _refresh_account_display(self):

        if not self.selected_email:
            return

        account = (
            self.accounts_manager.get_account(
                self.selected_email
            )
        )

        if not account:
            return

        updated = account.get(
            "updated_at"
        )

        self.account_updated_label.setText(
            "מועד עדכון אחרון: "
            + self._format_datetime(updated)
        )

    # ==================================================================
    # Date formatting
    # ==================================================================

    @staticmethod
    def _format_datetime(
        value
    ) -> str:

        if not value:
            return "—"

        try:

            text = str(value)

            dt = datetime.fromisoformat(
                text.replace(
                    "Z",
                    "+00:00"
                )
            )

            return dt.strftime(
                "%d/%m/%Y %H:%M"
            )

        except Exception:

            return str(value)

    # ==================================================================
    # Close
    # ==================================================================

    def closeEvent(
        self,
        event,
    ):

        if self.connection is not None:

            try:

                self.connection.disconnect()

            except Exception:
                pass

            self.connection = None

        event.accept()


# ======================================================================
# Standalone test
# ======================================================================

def main():

    import sys

    app = QApplication(
        sys.argv
    )

    window = GmailWindow()

    window.show()

    return app.exec()


if __name__ == "__main__":

    raise SystemExit(
        main()
    )