from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class GmailAccountsManager:
    """
    מנהל חשבונות Gmail והתגיות המקושרות אליהם.

    הקובץ נשמר ב:
        config/gmail/accounts.json

    המבנה:
    {
        "version": 1,
        "accounts": [
            {
                "email": "...",
                "display_name": "",
                "enabled": true,
                "created_at": "...",
                "updated_at": "...",
                "labels": [
                    {
                        "id": "...",
                        "name": "...",
                        "enabled": true,
                        "last_fetch": null,
                        "last_local_save": null,
                        "history_id": null,
                        "destination": "local",
                        "created_at": "...",
                        "updated_at": "..."
                    }
                ]
            }
        ]
    }
    """

    def __init__(self, accounts_file: str | Path | None = None):
        project_root = Path(__file__).resolve().parents[2]

        if accounts_file is None:
            accounts_file = (
                project_root
                / "config"
                / "gmail"
                / "accounts.json"
            )

        self.accounts_file = Path(accounts_file)

        self.data: dict[str, Any] = {
            "version": 1,
            "accounts": [],
        }

        self.load()

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # File handling
    # ------------------------------------------------------------------

    def load(self) -> dict[str, Any]:
        """
        טוען את accounts.json.

        אם הקובץ לא קיים, נוצר מבנה ריק.
        """
        self.accounts_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.accounts_file.exists():
            self.data = {
                "version": 1,
                "accounts": [],
            }
            return self.data

        try:
            with self.accounts_file.open(
                "r",
                encoding="utf-8",
            ) as f:
                loaded = json.load(f)

            if not isinstance(loaded, dict):
                raise ValueError("accounts.json אינו אובייקט JSON תקין")

            if "accounts" not in loaded:
                loaded["accounts"] = []

            if "version" not in loaded:
                loaded["version"] = 1

            self.data = loaded

        except (json.JSONDecodeError, OSError, ValueError):
            # לא מוחקים את הקובץ הפגום.
            # מתחילים ממבנה ריק כדי שהיישום יוכל להמשיך לעבוד.
            self.data = {
                "version": 1,
                "accounts": [],
            }

        return self.data

    def save(self) -> None:
        """
        שומר את הנתונים ל-accounts.json.
        """
        self.accounts_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temp_file = self.accounts_file.with_suffix(".tmp")

        with temp_file.open(
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                self.data,
                f,
                ensure_ascii=False,
                indent=2,
            )

        temp_file.replace(self.accounts_file)

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    def get_accounts(self) -> list[dict[str, Any]]:
        return self.data.setdefault("accounts", [])

    def get_account(
        self,
        email: str,
    ) -> dict[str, Any] | None:
        normalized = self._normalize_email(email)

        for account in self.get_accounts():
            if self._normalize_email(
                str(account.get("email", ""))
            ) == normalized:
                return account

        return None

    def account_exists(self, email: str) -> bool:
        return self.get_account(email) is not None

    def add_account(
        self,
        email: str,
        display_name: str = "",
    ) -> dict[str, Any]:
        normalized = self._normalize_email(email)

        if not normalized:
            raise ValueError("כתובת Gmail אינה יכולה להיות ריקה")

        existing = self.get_account(normalized)

        if existing is not None:
            return existing

        now = self._utc_now()

        account = {
            "email": normalized,
            "display_name": display_name or "",
            "enabled": True,
            "created_at": now,
            "updated_at": now,
            "labels": [],
        }

        self.get_accounts().append(account)
        self.save()

        return account

    def update_account(
        self,
        email: str,
        display_name: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any] | None:
        account = self.get_account(email)

        if account is None:
            return None

        if display_name is not None:
            account["display_name"] = display_name

        if enabled is not None:
            account["enabled"] = bool(enabled)

        account["updated_at"] = self._utc_now()

        self.save()

        return account

    def remove_account(self, email: str) -> bool:
        normalized = self._normalize_email(email)

        accounts = self.get_accounts()

        for index, account in enumerate(accounts):
            if self._normalize_email(
                str(account.get("email", ""))
            ) == normalized:
                accounts.pop(index)
                self.save()
                return True

        return False

    # ------------------------------------------------------------------
    # Labels
    # ------------------------------------------------------------------

    def get_labels(
        self,
        email: str,
    ) -> list[dict[str, Any]]:
        account = self.get_account(email)

        if account is None:
            return []

        return account.setdefault("labels", [])

    def get_label(
        self,
        email: str,
        label_id: str,
    ) -> dict[str, Any] | None:
        for label in self.get_labels(email):
            if str(label.get("id", "")) == str(label_id):
                return label

        return None

    def add_label(
        self,
        email: str,
        label_id: str,
        label_name: str,
    ) -> dict[str, Any]:
        account = self.get_account(email)

        if account is None:
            raise ValueError(
                f"חשבון Gmail אינו קיים: {email}"
            )

        existing = self.get_label(email, label_id)

        if existing is not None:
            existing["name"] = label_name
            existing["updated_at"] = self._utc_now()

            account["updated_at"] = self._utc_now()

            self.save()

            return existing

        now = self._utc_now()

        label = {
            "id": str(label_id),
            "name": label_name,
            "enabled": True,
            "last_fetch": None,
            "last_local_save": None,
            "history_id": None,
            "destination": "local",
            "created_at": now,
            "updated_at": now,
        }

        self.get_labels(email).append(label)

        account["updated_at"] = now

        self.save()

        return label

    def remove_label(
        self,
        email: str,
        label_id: str,
    ) -> bool:
        account = self.get_account(email)

        if account is None:
            return False

        labels = account.setdefault("labels", [])

        for index, label in enumerate(labels):
            if str(label.get("id", "")) == str(label_id):
                labels.pop(index)

                account["updated_at"] = self._utc_now()

                self.save()

                return True

        return False

    def update_label(
        self,
        email: str,
        label_id: str,
        **updates: Any,
    ) -> dict[str, Any] | None:
        """
        מעדכן שדות של תגית.

        לדוגמה:
            update_label(
                email,
                label_id,
                label_name="Inbox",
            )
        """
        account = self.get_account(email)

        if account is None:
            return None

        label = self.get_label(email, label_id)

        if label is None:
            return None

        allowed_fields = {
            "id",
            "name",
            "label_name",
            "enabled",
            "last_fetch",
            "last_local_save",
            "history_id",
            "destination",
            "created_at",
            "updated_at",
        }

        for key, value in updates.items():
            if key not in allowed_fields:
                continue

            if key == "label_name":
                label["name"] = value
            else:
                label[key] = value

        label["updated_at"] = self._utc_now()
        account["updated_at"] = self._utc_now()

        self.save()

        return label

    # ------------------------------------------------------------------
    # Synchronization timestamps
    # ------------------------------------------------------------------

    def mark_fetch(
        self,
        email: str,
        label_id: str,
        history_id: str | None = None,
    ) -> dict[str, Any] | None:
        """
        מסמן שהתרעננות/שליפה מ-Gmail בוצעה.

        last_fetch:
            מועד השליפה האחרון.

        history_id:
            Gmail History ID, אם קיים.
        """
        label = self.get_label(email, label_id)

        if label is None:
            return None

        now = self._utc_now()

        label["last_fetch"] = now

        if history_id is not None:
            label["history_id"] = str(history_id)

        label["updated_at"] = now

        account = self.get_account(email)

        if account is not None:
            account["updated_at"] = now

        self.save()

        return label

    def mark_local_save(
        self,
        email: str,
        label_id: str,
    ) -> dict[str, Any] | None:
        """
        מסמן שהשמירה המקומית האחרונה של מסמכי התגית בוצעה.
        """
        label = self.get_label(email, label_id)

        if label is None:
            return None

        now = self._utc_now()

        label["last_local_save"] = now
        label["updated_at"] = now

        account = self.get_account(email)

        if account is not None:
            account["updated_at"] = now

        self.save()

        return label
