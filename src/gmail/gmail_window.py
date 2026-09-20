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

    # ============================================================
    # UI
    # ============================================================

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

    # ============================================================
    # Accounts
    # ============================================================

    def _load_accounts(self):

        current_email = self.selected_email

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

            if self.accounts_list.count() == 0:
                self.selected_email = None
                self._clear_account_view()
                return

            target_row = 0

            if current_email:

                for index in range(
                    self.accounts_list.count()
                ):

                    item = self.accounts_list.item(
                        index
                    )

                    item_email = item.data(
                        Qt.ItemDataRole.UserRole
                    )

                    if str(item_email).lower() == str(
                        current_email
                    ).lower():

                        target_row = index
                        break

            self.accounts_list.setCurrentRow(
                target_row
            )

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

                if str(
                    item.data(
                        Qt.ItemDataRole.UserRole
                    )
                ).lower() == str(
                    email
                ).lower():

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

    # ============================================================
    # Account / Label display
    # ============================================================

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

    # ============================================================
    # PostgreSQL helpers
    # ============================================================

    def _get_database_connection(self):

        return DatabaseConnection().connect()

    def _get_postgres_gmail_account_id(self):

        if not self.selected_email:
            raise RuntimeError(
                "לא נבחר חשבון Gmail."
            )

        conn = self._get_database_connection()

        try:

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT id
                    FROM gmail_accounts
                    WHERE LOWER(email) = LOWER(%s)
                    LIMIT 1
                    """,
                    (
                        self.selected_email,
                    ),
                )

                row = cursor.fetchone()

                if not row:

                    raise RuntimeError(
                        "חשבון Gmail אינו קיים ב-PostgreSQL:\n"
                        + self.selected_email
                    )

                return row[0]

        finally:

            conn.close()

    def _get_postgres_labels(self):

        gmail_account_id = (
            self._get_postgres_gmail_account_id()
        )

        conn = self._get_database_connection()

        try:

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        id,
                        label_id,
                        label_name,
                        label_type,
                        selected_for_sync,
                        enabled,
                        last_history_id,
                        created_at,
                        updated_at
                    FROM gmail_labels
                    WHERE gmail_account_id = %s
                    ORDER BY id
                    """,
                    (
                        gmail_account_id,
                    ),
                )

                rows = cursor.fetchall()

            labels = []

            for row in rows:

                labels.append(
                    {
                        "db_id": row[0],
                        "id": row[1],
                        "name": row[2],
                        "type": row[3],
                        "selected_for_sync": bool(row[4]),
                        "enabled": bool(row[5]),
                        "last_history_id": row[6],
                        "created_at": row[7],
                        "updated_at": row[8],
                    }
                )

            return labels

        finally:

            conn.close()

    def _get_postgres_selected_labels(self):

        labels = self._get_postgres_labels()

        return [
            label
            for label in labels
            if label.get("selected_for_sync")
            and label.get("enabled")
        ]

    def _sync_gmail_labels_to_postgres(
        self,
        all_labels,
    ):

        gmail_account_id = (
            self._get_postgres_gmail_account_id()
        )

        inserted = 0
        updated = 0

        conn = self._get_database_connection()

        try:

            with conn.cursor() as cursor:

                for gmail_label in all_labels:

                    label_id = gmail_label.get(
                        "id"
                    )

                    label_name = gmail_label.get(
                        "name"
                    )

                    label_type = gmail_label.get(
                        "type"
                    )

                    if not label_id or not label_name:
                        continue

                    cursor.execute(
                        """
                        SELECT
                            id,
                            selected_for_sync,
                            enabled
                        FROM gmail_labels
                        WHERE gmail_account_id = %s
                          AND label_id = %s
                        LIMIT 1
                        """,
                        (
                            gmail_account_id,
                            str(label_id),
                        ),
                    )

                    existing = cursor.fetchone()

                    if existing:

                        cursor.execute(
                            """
                            UPDATE gmail_labels
                            SET
                                label_name = %s,
                                label_type = %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE gmail_account_id = %s
                              AND label_id = %s
                            """,
                            (
                                str(label_name),
                                str(label_type or ""),
                                gmail_account_id,
                                str(label_id),
                            ),
                        )

                        updated += 1

                    else:

                        cursor.execute(
                            """
                            INSERT INTO gmail_labels (
                                gmail_account_id,
                                label_id,
                                label_name,
                                label_type,
                                selected_for_sync,
                                enabled
                            )
                            VALUES (
                                %s,
                                %s,
                                %s,
                                %s,
                                FALSE,
                                TRUE
                            )
                            """,
                            (
                                gmail_account_id,
                                str(label_id),
                                str(label_name),
                                str(label_type or ""),
                            ),
                        )

                        inserted += 1

                conn.commit()

        except Exception:

            conn.rollback()
            raise

        finally:

            conn.close()

        return inserted, updated

    def _set_postgres_label_selection(
        self,
        label_id,
        label_name,
        label_type,
        selected,
    ):

        gmail_account_id = (
            self._get_postgres_gmail_account_id()
        )

        conn = self._get_database_connection()

        try:

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    UPDATE gmail_labels
                    SET
                        label_name = %s,
                        label_type = COALESCE(
                            NULLIF(%s, ''),
                            label_type
                        ),
                        selected_for_sync = %s,
                        enabled = TRUE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE gmail_account_id = %s
                      AND label_id = %s
                    """,
                    (
                        str(label_name or ""),
                        str(label_type or ""),
                        bool(selected),
                        gmail_account_id,
                        str(label_id),
                    ),
                )

                if cursor.rowcount == 0:

                    cursor.execute(
                        """
                        INSERT INTO gmail_labels (
                            gmail_account_id,
                            label_id,
                            label_name,
                            label_type,
                            selected_for_sync,
                            enabled
                        )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            TRUE
                        )
                        """,
                        (
                            gmail_account_id,
                            str(label_id),
                            str(label_name or ""),
                            str(label_type or ""),
                            bool(selected),
                        ),
                    )

                conn.commit()

        except Exception:

            conn.rollback()
            raise

        finally:

            conn.close()

    # ============================================================
    # JSON <-> PostgreSQL synchronization
    # ============================================================

    def _sync_json_from_postgres(self):

        if not self.selected_email:
            return 0

        postgres_labels = self._get_postgres_labels()

        accounts = self.accounts_manager.get_accounts()

        target_account = None

        for account in accounts:

            if not isinstance(account, dict):
                continue

            email = (
                account.get("email")
                or account.get("address")
                or account.get("account_email")
            )

            if email and str(email).lower() == str(
                self.selected_email
            ).lower():

                target_account = account
                break

        if target_account is None:
            return 0

        old_labels = target_account.get(
            "labels",
            []
        )

        old_by_id = {}

        for old_label in old_labels:

            if isinstance(old_label, str):

                old_by_id[str(old_label)] = {
                    "id": str(old_label),
                    "name": str(old_label),
                }

                continue

            if not isinstance(old_label, dict):
                continue

            old_id = (
                old_label.get("id")
                or old_label.get("label_id")
            )

            if old_id:

                old_by_id[str(old_id)] = old_label

        new_labels = []

        for pg_label in postgres_labels:

            label_id = pg_label.get(
                "id"
            )

            label_name = pg_label.get(
                "name"
            )

            if not label_id:
                continue

            old = old_by_id.get(
                str(label_id),
                {}
            )

            if not isinstance(old, dict):
                old = {}

            new_label = dict(old)

            new_label["id"] = str(
                label_id
            )

            new_label["name"] = (
                label_name
                or str(label_id)
            )

            new_label["label_id"] = str(
                label_id
            )

            new_label["label_name"] = (
                label_name
                or str(label_id)
            )

            new_label["selected_for_sync"] = bool(
                pg_label.get(
                    "selected_for_sync"
                )
            )

            new_label["enabled"] = bool(
                pg_label.get(
                    "enabled"
                )
            )

            new_label["label_type"] = (
                pg_label.get(
                    "type"
                )
                or ""
            )

            if "last_fetch" not in new_label:
                new_label["last_fetch"] = None

            if "last_local_save" not in new_label:
                new_label["last_local_save"] = None

            if "history_id" not in new_label:
                new_label["history_id"] = (
                    pg_label.get(
                        "last_history_id"
                    )
                )

            if "destination" not in new_label:
                new_label["destination"] = "local"

            new_labels.append(
                new_label
            )

        target_account["labels"] = new_labels

        save_method = getattr(
            self.accounts_manager,
            "save",
            None
        )

        if not callable(save_method):

            raise RuntimeError(
                "GmailAccountsManager אינו מספק save()."
            )

        save_method()

        return len(new_labels)

    # ============================================================
    # Label display
    # ============================================================

    def _load_linked_labels(self):

        self.linked_labels_list.clear()

        if not self.selected_email:
            return

        try:

            # ----------------------------------------------------
            # PostgreSQL הוא מקור הבחירה.
            # לאחר הקריאה ממנו מסנכרנים גם את JSON.
            # ----------------------------------------------------

            selected_labels = (
                self._get_postgres_selected_labels()
            )

            self._sync_json_from_postgres()

            for label in selected_labels:

                label_id = label.get(
                    "id"
                )

                label_name = label.get(
                    "name"
                )

                if not label_id:
                    continue

                text = str(
                    label_name or label_id
                )

                last_fetch = None

                try:

                    json_labels = (
                        self.accounts_manager.get_labels(
                            self.selected_email
                        )
                    )

                    for json_label in json_labels:

                        if not isinstance(
                            json_label,
                            dict
                        ):
                            continue

                        json_id = (
                            json_label.get("id")
                            or json_label.get("label_id")
                        )

                        if str(json_id) == str(
                            label_id
                        ):

                            last_fetch = (
                                json_label.get(
                                    "last_fetch"
                                )
                                or json_label.get(
                                    "last_fetched"
                                )
                                or json_label.get(
                                    "last_refresh"
                                )
                            )

                            break

                except Exception:
                    last_fetch = None

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

                item.setData(
                    Qt.ItemDataRole.UserRole + 2,
                    label.get("type") or ""
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

            # ----------------------------------------------------
            # כל Label שקיים ב-Gmail חייב להיות גם ב-PostgreSQL.
            # זה גם מאפשר לרענן את המאגר במקרה של Label חדש.
            # ----------------------------------------------------

            self._sync_gmail_labels_to_postgres(
                all_labels
            )

            # ----------------------------------------------------
            # לאחר מכן PostgreSQL קובע מי נבחר ומי לא.
            # ----------------------------------------------------

            postgres_labels = self._get_postgres_labels()

            selected_ids = {
                str(label.get("id"))
                for label in postgres_labels
                if label.get("selected_for_sync")
                and label.get("enabled")
            }

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

                if str(label_id) in selected_ids:
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

    # ============================================================
    # Gmail API
    # ============================================================

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

    # ============================================================
    # Label selection
    # ============================================================

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

        label_type = item.data(
            Qt.ItemDataRole.UserRole + 2
        )

        if not label_name:
            label_name = item.text()

        try:

            # ----------------------------------------------------
            # PostgreSQL
            # ----------------------------------------------------

            self._set_postgres_label_selection(
                label_id=label_id,
                label_name=label_name,
                label_type=label_type,
                selected=True,
            )

            # ----------------------------------------------------
            # JSON
            # ----------------------------------------------------

            self._sync_json_from_postgres()

            # ----------------------------------------------------
            # תצוגה
            # ----------------------------------------------------

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

        label_type = item.data(
            Qt.ItemDataRole.UserRole + 2
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

            # ----------------------------------------------------
            # PostgreSQL:
            # לא מוחקים את הרשומה.
            # רק מבטלים את הבחירה.
            # ----------------------------------------------------

            self._set_postgres_label_selection(
                label_id=label_id,
                label_name=label_name,
                label_type=label_type,
                selected=False,
            )

            # ----------------------------------------------------
            # JSON:
            # מקבל בדיוק את אותה בחירה מ-PostgreSQL.
            # ----------------------------------------------------

            self._sync_json_from_postgres()

            # ----------------------------------------------------
            # תצוגה
            # ----------------------------------------------------

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

    # ============================================================
    # Search
    # ============================================================

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

    # ============================================================
    # Refresh Gmail Labels
    # ============================================================

    def _refresh_gmail_labels(self):

        if not self.selected_email:
            QMessageBox.information(
                self,
                "Gmail",
                "יש לבחור חשבון Gmail."
            )
            return

        try:

            self.status_label.setText(
                "מתחבר ל-Gmail ומרענן את רשימת התגיות..."
            )

            QApplication.processEvents()

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

            # ----------------------------------------------------
            # שלב 1:
            # משיכת כל התגיות העדכניות מ-Gmail.
            # ----------------------------------------------------

            all_labels = self._get_all_gmail_labels(
                connection
            )

            if not all_labels:

                self.status_label.setText(
                    "לא נמצאו תגיות ב-Gmail"
                )

                return

            # ----------------------------------------------------
            # שלב 2:
            # הכנסת תגיות חדשות ועדכון שמות קיימים.
            #
            # חשוב:
            # רשומה קיימת שומרת selected_for_sync.
            #
            # רשומה חדשה מתחילה FALSE.
            # ----------------------------------------------------

            inserted, updated = (
                self._sync_gmail_labels_to_postgres(
                    all_labels
                )
            )

            # ----------------------------------------------------
            # שלב 3:
            # PostgreSQL -> accounts.json
            #
            # כאן מתבצע הסנכרון המרכזי.
            # JSON מקבל בדיוק את רשימת ה-Labels ואת
            # selected_for_sync של PostgreSQL.
            # ----------------------------------------------------

            json_count = (
                self._sync_json_from_postgres()
            )

            # ----------------------------------------------------
            # שלב 4:
            # רענון התצוגה.
            # ----------------------------------------------------

            self._load_linked_labels()
            self._load_available_labels()

            selected_count = len(
                self._get_postgres_selected_labels()
            )

            self.status_label.setText(
                (
                    f"נמצאו {len(all_labels)} תגיות ב-Gmail | "
                    f"נוספו {inserted} חדשות | "
                    f"עודכנו {updated} | "
                    f"נבחרו {selected_count} | "
                    f"JSON: {json_count}"
                )
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

            self.status_label.setText(
                "שגיאה ברענון תגיות Gmail"
            )

    # ============================================================
    # Refresh display
    # ============================================================

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

        # קודם מסנכרנים JSON מ-PostgreSQL.
        self._sync_json_from_postgres()

        self._load_linked_labels()
        self._load_available_labels()

    # ============================================================
    # Utilities
    # ============================================================

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