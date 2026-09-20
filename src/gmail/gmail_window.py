# -*- coding: utf-8 -*-

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QGroupBox,
    QLineEdit,
)

try:
    from gmail.gmail_connection import GmailConnection
    from gmail.gmail_accounts import GmailAccountsManager
except ModuleNotFoundError:
    from src.gmail.gmail_connection import GmailConnection
    from src.gmail.gmail_accounts import GmailAccountsManager

try:
    from database.connection import DatabaseConnection
except ModuleNotFoundError:
    from src.database.connection import DatabaseConnection


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class GmailWindow(QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.accounts_manager = GmailAccountsManager()
        self.gmail_connection = None

        self.selected_email = None
        self.selected_label = None

        self.setWindowTitle("Alcalay - ניהול Gmail")
        self.setMinimumSize(1050, 700)
        self.resize(1200, 760)

        self._build_ui()
        self._apply_style()
        self._load_accounts()

    def _build_ui(self):

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        title = QLabel("ניהול Gmail")
        title.setAlignment(Qt.AlignmentFlag.AlignRight)
        title.setStyleSheet(
            "font-size: 26px; font-weight: bold;"
        )

        subtitle = QLabel(
            "ניהול חשבונות Gmail, תגיות והבחירה לסנכרון"
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignRight)
        subtitle.setStyleSheet(
            "font-size: 14px;"
        )

        main_layout.addWidget(title)
        main_layout.addWidget(subtitle)

        account_group = QGroupBox("חשבונות Gmail")
        account_layout = QVBoxLayout(account_group)

        account_buttons = QHBoxLayout()

        self.add_account_button = QPushButton(
            "הוסף חשבון Gmail"
        )
        self.add_account_button.clicked.connect(
            self._add_account
        )

        self.remove_account_button = QPushButton(
            "הסר חשבון"
        )
        self.remove_account_button.clicked.connect(
            self._remove_account
        )

        self.refresh_account_button = QPushButton(
            "רענן חשבונות"
        )
        self.refresh_account_button.clicked.connect(
            self._load_accounts
        )

        account_buttons.addWidget(
            self.add_account_button
        )
        account_buttons.addWidget(
            self.remove_account_button
        )
        account_buttons.addWidget(
            self.refresh_account_button
        )
        account_buttons.addStretch()

        account_layout.addLayout(account_buttons)

        self.accounts_list = QListWidget()
        self.accounts_list.setMinimumHeight(90)
        self.accounts_list.itemSelectionChanged.connect(
            self._account_selected
        )

        account_layout.addWidget(
            self.accounts_list
        )

        main_layout.addWidget(
            account_group
        )

        selected_group = QGroupBox(
            "חשבון נבחר"
        )
        selected_layout = QVBoxLayout(
            selected_group
        )

        self.selected_account_label = QLabel(
            "לא נבחר חשבון"
        )
        self.selected_account_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
        )

        selected_layout.addWidget(
            self.selected_account_label
        )

        main_layout.addWidget(
            selected_group
        )

        labels_layout = QHBoxLayout()
        labels_layout.setSpacing(15)

        linked_group = QGroupBox(
            "תגיות מקושרות"
        )
        linked_layout = QVBoxLayout(
            linked_group
        )

        self.linked_labels_list = QListWidget()
        self.linked_labels_list.itemSelectionChanged.connect(
            self._linked_label_selected
        )

        linked_layout.addWidget(
            self.linked_labels_list
        )

        linked_buttons = QHBoxLayout()

        self.remove_label_button = QPushButton(
            "הסר תגית"
        )
        self.remove_label_button.clicked.connect(
            self._remove_label
        )

        linked_buttons.addWidget(
            self.remove_label_button
        )
        linked_buttons.addStretch()

        linked_layout.addLayout(
            linked_buttons
        )

        available_group = QGroupBox(
            "תגיות זמינות ב-Gmail"
        )
        available_layout = QVBoxLayout(
            available_group
        )

        search_layout = QHBoxLayout()

        search_label = QLabel(
            "חיפוש:"
        )

        self.label_search = QLineEdit()
        self.label_search.setPlaceholderText(
            "חפש תגית..."
        )
        self.label_search.textChanged.connect(
            self._filter_available_labels
        )

        search_layout.addWidget(
            search_label
        )
        search_layout.addWidget(
            self.label_search
        )

        available_layout.addLayout(
            search_layout
        )

        self.available_labels_list = QListWidget()
        self.available_labels_list.itemDoubleClicked.connect(
            self._add_label_by_double_click
        )

        available_layout.addWidget(
            self.available_labels_list
        )

        add_hint = QLabel(
            "לחיצה כפולה על תגית מוסיפה אותה לתגיות המקושרות"
        )
        add_hint.setAlignment(
            Qt.AlignmentFlag.AlignRight
        )

        available_layout.addWidget(
            add_hint
        )

        labels_layout.addWidget(
            linked_group,
            1
        )

        labels_layout.addWidget(
            available_group,
            1
        )

        main_layout.addLayout(
            labels_layout,
            1
        )

        bottom_layout = QHBoxLayout()

        self.refresh_labels_button = QPushButton(
            "רענן תגיות Gmail"
        )
        self.refresh_labels_button.clicked.connect(
            self._refresh_gmail_labels
        )

        self.refresh_display_button = QPushButton(
            "רענן תצוגה"
        )
        self.refresh_display_button.clicked.connect(
            self._refresh_account_display
        )

        bottom_layout.addWidget(
            self.refresh_labels_button
        )

        bottom_layout.addWidget(
            self.refresh_display_button
        )

        bottom_layout.addStretch()

        main_layout.addLayout(
            bottom_layout
        )

        self.status_label = QLabel(
            "מוכן"
        )
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
        )

        main_layout.addWidget(
            self.status_label
        )

    def _apply_style(self):

        self.setStyleSheet(
            """
            QMainWindow {
                background: #f5f6f8;
            }

            QGroupBox {
                background: white;
                border: 1px solid #d7dbe0;
                border-radius: 8px;
                margin-top: 12px;
                padding: 12px;
                font-weight: bold;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                right: 12px;
                padding: 0 6px;
            }

            QListWidget {
                background: white;
                border: 1px solid #d7dbe0;
                border-radius: 5px;
                padding: 4px;
            }

            QListWidget::item {
                padding: 8px;
            }

            QListWidget::item:selected {
                background: #dcecff;
                color: #111111;
            }

            QPushButton {
                min-height: 34px;
                padding-left: 14px;
                padding-right: 14px;
                border-radius: 5px;
                border: 1px solid #c7ccd2;
                background: #ffffff;
            }

            QPushButton:hover {
                background: #eef3f8;
            }

            QLineEdit {
                min-height: 32px;
                border: 1px solid #c7ccd2;
                border-radius: 5px;
                padding-left: 8px;
                padding-right: 8px;
            }
            """
        )

    def _load_accounts(self):

        self.accounts_list.clear()

        try:

            accounts = self.accounts_manager.get_accounts()

            if not accounts:
                self.selected_email = None
                self._clear_account_view()
                self.status_label.setText(
                    "אין חשבונות Gmail מקושרים"
                )
                return

            for account in accounts:

                if isinstance(account, str):
                    email = account

                elif isinstance(account, dict):
                    email = (
                        account.get("email")
                        or account.get("address")
                        or account.get("account_email")
                    )

                else:
                    email = str(account)

                if not email:
                    continue

                item = QListWidgetItem(
                    str(email)
                )

                item.setData(
                    Qt.ItemDataRole.UserRole,
                    str(email)
                )

                self.accounts_list.addItem(
                    item
                )

            if self.accounts_list.count() > 0:
                self.accounts_list.setCurrentRow(0)

            else:
                self.selected_email = None
                self._clear_account_view()

            self.status_label.setText(
                "חשבונות Gmail נטענו"
            )

        except Exception as exc:

            self.status_label.setText(
                "שגיאה בטעינת חשבונות"
            )

            QMessageBox.critical(
                self,
                "שגיאה",
                f"לא ניתן לטעון את חשבונות Gmail:\n\n{exc}"
            )

    def _account_selected(self):

        item = self.accounts_list.currentItem()

        if item is None:
            self.selected_email = None
            self._clear_account_view()
            return

        email = item.data(
            Qt.ItemDataRole.UserRole
        )

        if not email:
            email = item.text()

        self.selected_email = str(
            email
        )

        self.selected_account_label.setText(
            f"חשבון נבחר: {self.selected_email}"
        )

        self._load_linked_labels()
        self._load_available_labels()

    def _add_account(self):

        try:

            connection = GmailConnection()

            result = connection.connect()

            if result is False:
                raise RuntimeError(
                    "חיבור Gmail נכשל."
                )

            email = getattr(
                connection,
                "email",
                None
            )

            if not email:
                email = getattr(
                    connection,
                    "account_email",
                    None
                )

            if not email:
                email = getattr(
                    connection,
                    "user_email",
                    None
                )

            if not email:

                QMessageBox.warning(
                    self,
                    "Gmail",
                    "החיבור הצליח, אך לא ניתן לזהות את כתובת החשבון."
                )
                return

            self.accounts_manager.add_account(
                email
            )

            self.selected_email = email

            self._load_accounts()

            for index in range(
                self.accounts_list.count()
            ):

                item = self.accounts_list.item(
                    index
                )

                if item.data(
                    Qt.ItemDataRole.UserRole
                ) == email:

                    self.accounts_list.setCurrentItem(
                        item
                    )
                    break

            self._refresh_gmail_labels()

        except TypeError:

            try:

                connection = GmailConnection(
                    None
                )

                result = connection.connect()

                if result is False:
                    raise RuntimeError(
                        "חיבור Gmail נכשל."
                    )

                email = getattr(
                    connection,
                    "email",
                    None
                )

                if not email:
                    raise RuntimeError(
                        "לא ניתן לזהות את כתובת Gmail."
                    )

                self.accounts_manager.add_account(
                    email
                )

                self._load_accounts()

            except Exception as exc:

                QMessageBox.critical(
                    self,
                    "שגיאה בחיבור Gmail",
                    str(exc)
                )

        except Exception as exc:

            QMessageBox.critical(
                self,
                "שגיאה בחיבור Gmail",
                str(exc)
            )

    def _remove_account(self):

        if not self.selected_email:
            QMessageBox.information(
                self,
                "Gmail",
                "יש לבחור חשבון להסרה."
            )
            return

        answer = QMessageBox.question(
            self,
            "הסרת חשבון",
            (
                "האם להסיר את חשבון Gmail?\n\n"
                + self.selected_email
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:

            self.accounts_manager.remove_account(
                self.selected_email
            )

            self.selected_email = None
            self._load_accounts()

            self.status_label.setText(
                "החשבון הוסר"
            )

        except Exception as exc:

            QMessageBox.critical(
                self,
                "שגיאה",
                f"לא ניתן להסיר את החשבון:\n\n{exc}"
            )

    def _clear_account_view(self):

        self.selected_account_label.setText(
            "לא נבחר חשבון"
        )

        self.linked_labels_list.clear()
        self.available_labels_list.clear()

        self.label_search.clear()

    def _linked_label_selected(self):

        item = self.linked_labels_list.currentItem()

        if item is None:
            self.selected_label = None
            return

        self.selected_label = item.data(
            Qt.ItemDataRole.UserRole
        )

    def _load_linked_labels(self):

        self.linked_labels_list.clear()

        if not self.selected_email:
            return

        try:

            labels = self.accounts_manager.get_labels(
                self.selected_email
            )

            if not labels:
                return

            for label in labels:

                if isinstance(label, str):

                    label_id = label
                    label_name = label
                    last_fetch = None

                else:

                    label_id = (
                        label.get("id")
                        or label.get("label_id")
                    )

                    label_name = (
                        label.get("name")
                        or label.get("label_name")
                        or label_id
                    )

                    last_fetch = (
                        label.get("last_fetch")
                        or label.get("last_fetched")
                        or label.get("last_refresh")
                    )

                text = str(
                    label_name
                )

                if last_fetch:
                    text += (
                        "    |    "
                        + self._format_datetime(
                            last_fetch
                        )
                    )

                item = QListWidgetItem(
                    text
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

        except Exception as exc:

            self.status_label.setText(
                f"שגיאה בטעינת תגיות מקושרות: {exc}"
            )

    def _load_available_labels(self):

        self.available_labels_list.clear()

        if not self.selected_email:
            return

        try:

            connection = GmailConnection(
                self.selected_email
            )

            result = connection.connect(
                self.selected_email
            )

            if result is False:
                raise RuntimeError(
                    "לא ניתן להתחבר ל-Gmail."
                )

            self.gmail_connection = connection

            all_labels = self._get_all_gmail_labels(
                connection
            )

            linked_ids = set()

            for index in range(
                self.linked_labels_list.count()
            ):

                item = self.linked_labels_list.item(
                    index
                )

                label_id = item.data(
                    Qt.ItemDataRole.UserRole
                )

                if label_id:
                    linked_ids.add(
                        str(label_id)
                    )

            labels = []

            for label in all_labels:

                label_id = label.get(
                    "id"
                )

                label_name = label.get(
                    "name"
                )

                if not label_id or not label_name:
                    continue

                if str(label_id) in linked_ids:
                    continue

                labels.append(
                    label
                )

            labels.sort(
                key=lambda value: (
                    0
                    if value.get("type") == "system"
                    else 1,
                    str(
                        value.get("name", "")
                    ).lower()
                )
            )

            for label in labels:

                item = QListWidgetItem(
                    label.get("name", "")
                )

                item.setData(
                    Qt.ItemDataRole.UserRole,
                    label.get("id")
                )

                item.setData(
                    Qt.ItemDataRole.UserRole + 1,
                    label.get("name")
                )

                item.setData(
                    Qt.ItemDataRole.UserRole + 2,
                    label.get("type")
                )

                self.available_labels_list.addItem(
                    item
                )

            self._filter_available_labels(
                self.label_search.text()
            )

        except Exception as exc:

            self.status_label.setText(
                f"שגיאה בטעינת תגיות Gmail: {exc}"
            )

    def _get_all_gmail_labels(self, connection):

        service = getattr(
            connection,
            "service",
            None
        )

        if service is None:
            raise RuntimeError(
                "שירות Gmail אינו זמין."
            )

        labels = []

        request = service.users().labels().list(
            userId="me"
        )

        response = request.execute()

        if not isinstance(response, dict):
            return labels

        labels.extend(
            response.get(
                "labels",
                []
            )
        )

        page_token = response.get(
            "nextPageToken"
        )

        while page_token:

            try:

                request = service.users().labels().list(
                    userId="me",
                    page_token=page_token
                )

            except TypeError:

                request = service.users().labels().list(
                    userId="me",
                    pageToken=page_token
                )

            response = request.execute()

            if not isinstance(response, dict):
                break

            labels.extend(
                response.get(
                    "labels",
                    []
                )
            )

            page_token = response.get(
                "nextPageToken"
            )

        return labels

    def _add_label_by_double_click(self, item):

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

        if not label_name:
            label_name = item.text()

        try:

            self.accounts_manager.add_label(
                self.selected_email,
                label_id,
                label_name
            )

            self._load_linked_labels()
            self._load_available_labels()

            self.status_label.setText(
                f"התגית '{label_name}' נוספה"
            )

        except TypeError:

            try:

                self.accounts_manager.add_label(
                    self.selected_email,
                    {
                        "id": label_id,
                        "name": label_name
                    }
                )

                self._load_linked_labels()
                self._load_available_labels()

                self.status_label.setText(
                    f"התגית '{label_name}' נוספה"
                )

            except Exception as exc:

                QMessageBox.critical(
                    self,
                    "שגיאה בהוספת תגית",
                    str(exc)
                )

        except Exception as exc:

            QMessageBox.critical(
                self,
                "שגיאה בהוספת תגית",
                str(exc)
            )

    def _remove_label(self):

        if not self.selected_email:
            return

        item = self.linked_labels_list.currentItem()

        if item is None:
            QMessageBox.information(
                self,
                "תגית",
                "יש לבחור תגית להסרה."
            )
            return

        label_id = item.data(
            Qt.ItemDataRole.UserRole
        )

        label_name = item.data(
            Qt.ItemDataRole.UserRole + 1
        )

        if not label_name:
            label_name = item.text()

        answer = QMessageBox.question(
            self,
            "הסרת תגית",
            (
                "להסיר את התגית מניהול Alcalay?\n\n"
                + str(label_name)
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
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

        except TypeError:

            try:

                self.accounts_manager.remove_label(
                    self.selected_email,
                    {
                        "id": label_id,
                        "name": label_name
                    }
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
                    str(exc)
                )

        except Exception as exc:

            QMessageBox.critical(
                self,
                "שגיאה בהסרת תגית",
                str(exc)
            )

    def _filter_available_labels(self, text):

        search_text = str(
            text or ""
        ).strip().lower()

        for index in range(
            self.available_labels_list.count()
        ):

            item = self.available_labels_list.item(
                index
            )

            visible = (
                not search_text
                or search_text in item.text().lower()
            )

            item.setHidden(
                not visible
            )

    def _refresh_gmail_labels(self):

        if not self.selected_email:
            QMessageBox.information(
                self,
                "Gmail",
                "יש לבחור חשבון Gmail."
            )
            return

        try:

            connection = GmailConnection(
                self.selected_email
            )

            result = connection.connect(
                self.selected_email
            )

            if result is False:
                raise RuntimeError(
                    "חיבור Gmail נכשל."
                )

            self.gmail_connection = connection

            all_labels = self._get_all_gmail_labels(
                connection
            )

            local_labels = self.accounts_manager.get_labels(
                self.selected_email
            )

            local_by_id = {}

            for label in local_labels:

                if isinstance(label, str):
                    continue

                label_id = (
                    label.get("id")
                    or label.get("label_id")
                )

                if label_id:
                    local_by_id[
                        str(label_id)
                    ] = label

            for gmail_label in all_labels:

                label_id = gmail_label.get(
                    "id"
                )

                label_name = gmail_label.get(
                    "name"
                )

                if not label_id:
                    continue

                if str(label_id) in local_by_id:

                    local_label = local_by_id[
                        str(label_id)
                    ]

                    if isinstance(
                        local_label,
                        dict
                    ):

                        local_label[
                            "name"
                        ] = label_name

            self._load_linked_labels()
            self._load_available_labels()

            self.status_label.setText(
                f"נמצאו {len(all_labels)} תגיות ב-Gmail"
            )

        except Exception as exc:

            QMessageBox.critical(
                self,
                "שגיאה ברענון תגיות",
                (
                    "לא ניתן לרענן את תגיות Gmail:\n\n"
                    + str(exc)
                )
            )

    def _refresh_account_display(self):

        if not self.selected_email:
            self._load_accounts()
            return

        email = self.selected_email

        self._load_accounts()

        for index in range(
            self.accounts_list.count()
        ):

            item = self.accounts_list.item(
                index
            )

            item_email = item.data(
                Qt.ItemDataRole.UserRole
            )

            if item_email == email:

                self.accounts_list.setCurrentItem(
                    item
                )

                break

        self._load_linked_labels()
        self._load_available_labels()

    def _format_datetime(self, value):

        if not value:
            return ""

        try:

            if isinstance(
                value,
                datetime
            ):
                return value.strftime(
                    "%d/%m/%Y %H:%M"
                )

            text = str(
                value
            )

            text = text.replace(
                "Z",
                "+00:00"
            )

            parsed = datetime.fromisoformat(
                text
            )

            return parsed.strftime(
                "%d/%m/%Y %H:%M"
            )

        except Exception:

            return str(
                value
            )

    def closeEvent(self, event):

        try:

            if self.gmail_connection is not None:

                service = getattr(
                    self.gmail_connection,
                    "service",
                    None
                )

                if service is not None:
                    pass

        except Exception:
            pass

        event.accept()


def main():

    app = QApplication(
        sys.argv
    )

    window = GmailWindow()
    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()