# -*- coding: utf-8 -*-

import os
import sys
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QPushButton,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QFrame,
)

from gmail.gmail_window import GmailWindow
from gmail.gmail_search_window import GmailSearchWindow


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"


MENU_ITEMS = [
    (1, "Google"),
    (2, "מסמכים"),
    (3, "חיפוש"),
    (4, "ניהול משתמשים"),
    (5, "הרשאות"),
    (6, "מסד נתונים"),
    (7, "הורדות"),
    (8, "הגדרות"),
    (9, "מערכת"),
    (10, "רענון והוספת מסמכים מהמייל"),
]


class GoogleLauncherPage(QWidget):
    def __init__(self, main_window):
        super().__init__()

        self.main_window = main_window
        self.setLayoutDirection(Qt.RightToLeft)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        title = QLabel("Google / Gmail")
        title.setObjectName("pageTitle")
        title.setAlignment(Qt.AlignRight)

        subtitle = QLabel(
            "עבודה עם Gmail בשלושה שלבים עצמאיים: "
            "בחירת חשבון ותגיות → ייבוא → אינדוקס"
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setAlignment(Qt.AlignRight)
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(20)

        cards_layout.addWidget(
            self.create_card(
                "1. חשבונות ותגיות",
                "הצגת חשבונות Gmail הקיימים במערכת, "
                "בחירת חשבון והצגת ובחירת התגיות שלו.",
                "חשבונות ותגיות",
                self.main_window.open_gmail_window,
            )
        )

        cards_layout.addWidget(
            self.create_card(
                "2. ייבוא מיילים",
                "ייבוא המיילים מהחשבון והתגיות שנבחרו "
                "לאחסון המקומי של Alcalay.",
                "ייבוא מיילים",
                self.main_window.open_gmail_import,
            )
        )

        cards_layout.addWidget(
            self.create_card(
                "3. אינדוקס מיילים",
                "אינדוקס המיילים שכבר נמצאים באחסון המקומי. "
                "שלב זה אינו מבצע ייבוא נוסף.",
                "אינדוקס מיילים",
                self.main_window.open_gmail_indexer,
            )
        )

        cards_layout.addWidget(
            self.create_card(
                "חיפוש במיילים",
                "חיפוש במידע שנאסף מהמיילים "
                "באמצעות מנגנון החיפוש של Alcalay.",
                "חיפוש במיילים",
                self.main_window.open_gmail_search,
            )
        )

        layout.addLayout(cards_layout)
        layout.addStretch()

    def create_card(
        self,
        title_text,
        description_text,
        button_text,
        callback,
    ):
        card = QFrame()
        card.setObjectName("card")
        card.setMinimumWidth(250)
        card.setMaximumWidth(360)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel(title_text)
        title.setObjectName("cardTitle")
        title.setAlignment(Qt.AlignRight)
        title.setWordWrap(True)

        description = QLabel(description_text)
        description.setObjectName("cardDescription")
        description.setAlignment(Qt.AlignRight)
        description.setWordWrap(True)

        button = QPushButton(button_text)
        button.setObjectName("primaryButton")
        button.clicked.connect(callback)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addStretch()
        layout.addWidget(button)

        return card


class PlaceholderPage(QWidget):
    def __init__(self, title_text, description_text):
        super().__init__()

        self.setLayoutDirection(Qt.RightToLeft)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(15)

        title = QLabel(title_text)
        title.setObjectName("pageTitle")
        title.setAlignment(Qt.AlignRight)

        description = QLabel(description_text)
        description.setObjectName("pageSubtitle")
        description.setAlignment(Qt.AlignRight)
        description.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(description)
        layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Alcalay")
        self.resize(1450, 850)
        self.setLayoutDirection(Qt.RightToLeft)

        self.stack = QStackedWidget()
        self.pages = {}

        self.google_page = GoogleLauncherPage(self)
        self.pages[1] = self.google_page

        self.pages[2] = PlaceholderPage(
            "מסמכים",
            "ניהול מסמכים ומקורות מידע.",
        )

        self.pages[3] = PlaceholderPage(
            "חיפוש",
            "חיפוש במסמכים ובמידע המאונדקס.",
        )

        self.pages[4] = PlaceholderPage(
            "ניהול משתמשים",
            "ניהול משתמשים במערכת.",
        )

        self.pages[5] = PlaceholderPage(
            "הרשאות",
            "ניהול הרשאות וגישה למידע.",
        )

        self.pages[6] = PlaceholderPage(
            "מסד נתונים",
            "חיבור וניהול מסדי הנתונים.",
        )

        self.pages[7] = PlaceholderPage(
            "הורדות",
            "ניהול הורדות ואחסון מקומי.",
        )

        self.pages[8] = PlaceholderPage(
            "הגדרות",
            "הגדרות המערכת.",
        )

        self.pages[9] = PlaceholderPage(
            "מערכת",
            "כלי מערכת ותחזוקה.",
        )

        self.pages[10] = PlaceholderPage(
            "רענון והוספת מסמכים מהמייל",
            "תהליך העבודה עם Gmail: "
            "בחירת חשבון ותגיות → ייבוא → אינדוקס.",
        )

        for page in self.pages.values():
            self.stack.addWidget(page)

        self.menu_buttons = {}

        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        menu = self.create_menu()

        central_layout.addWidget(self.stack, 1)
        central_layout.addWidget(menu)

        self.setCentralWidget(central)

        self.statusBar().showMessage("Alcalay מוכן")
        self.show_page(1)

    def create_menu(self):
        menu = QFrame()
        menu.setObjectName("sideMenu")
        menu.setFixedWidth(260)

        layout = QVBoxLayout(menu)
        layout.setContentsMargins(15, 20, 15, 20)
        layout.setSpacing(8)

        title = QLabel("ALCALAY")
        title.setObjectName("menuTitle")
        title.setAlignment(Qt.AlignCenter)

        layout.addWidget(title)
        layout.addSpacing(15)

        for number, text in MENU_ITEMS:
            button = QPushButton(f"{number}. {text}")
            button.setObjectName("menuButton")
            button.setMinimumHeight(45)

            button.clicked.connect(
                lambda checked=False, page_number=number:
                self.show_page(page_number)
            )

            self.menu_buttons[number] = button
            layout.addWidget(button)

        layout.addStretch()

        return menu

    def show_page(self, page_number):
        if page_number not in self.pages:
            return

        page = self.pages[page_number]
        self.stack.setCurrentWidget(page)

        for number, button in self.menu_buttons.items():
            button.setProperty(
                "selected",
                number == page_number,
            )

            button.style().unpolish(button)
            button.style().polish(button)

        self.statusBar().showMessage(
            MENU_ITEMS[page_number - 1][1]
        )

    def open_gmail_window(self):
        try:
            self.gmail_window = GmailWindow(self)

            self.gmail_window.setWindowModality(
                Qt.ApplicationModal
            )

            self.gmail_window.show()
            self.gmail_window.raise_()
            self.gmail_window.activateWindow()

            self.statusBar().showMessage(
                "שלב 1: חשבונות Gmail ותגיות"
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "שגיאה",
                f"לא ניתן לפתוח את ניהול Gmail:\n\n{exc}",
            )

    def open_gmail_search(self):
        try:
            self.gmail_search_window = GmailSearchWindow(self)

            self.gmail_search_window.setWindowModality(
                Qt.ApplicationModal
            )

            self.gmail_search_window.show()
            self.gmail_search_window.raise_()
            self.gmail_search_window.activateWindow()

            self.statusBar().showMessage(
                "חיפוש במיילים"
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "שגיאה",
                f"לא ניתן לפתוח את חיפוש Gmail:\n\n{exc}",
            )

    def _get_subprocess_environment(self):
        env = os.environ.copy()

        existing_pythonpath = env.get("PYTHONPATH", "")

        python_paths = [
            str(SRC_ROOT),
            str(PROJECT_ROOT),
        ]

        if existing_pythonpath:
            python_paths.append(existing_pythonpath)

        env["PYTHONPATH"] = os.pathsep.join(
            python_paths
        )

        return env

    def open_gmail_import(self):
        script_path = (
            PROJECT_ROOT
            / "src"
            / "gmail"
            / "gmail_copy.py"
        )

        if not script_path.exists():
            QMessageBox.critical(
                self,
                "קובץ חסר",
                f"קובץ הייבוא לא נמצא:\n\n{script_path}",
            )
            return

        answer = QMessageBox.question(
            self,
            "ייבוא מיילים",
            "להפעיל את שלב 2 - ייבוא המיילים "
            "לפי חשבון ותגיות Gmail שהוגדרו?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if answer != QMessageBox.Yes:
            return

        try:
            env = self._get_subprocess_environment()

            process = subprocess.Popen(
                [
                    sys.executable,
                    str(script_path),
                ],
                cwd=str(PROJECT_ROOT),
                env=env,
            )

            self.statusBar().showMessage(
                "שלב 2: ייבוא מיילים הופעל"
            )

            print(
                "[GMAIL IMPORT] Started process "
                f"PID={process.pid}"
            )

            print(
                "[GMAIL IMPORT] PYTHONPATH="
                f"{env.get('PYTHONPATH', '')}"
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "שגיאה",
                f"לא ניתן להפעיל את ייבוא Gmail:\n\n{exc}",
            )

    def open_gmail_indexer(self):
        script_path = (
            PROJECT_ROOT
            / "src"
            / "gmail"
            / "gmail_indexer.py"
        )

        if not script_path.exists():
            QMessageBox.critical(
                self,
                "קובץ חסר",
                f"קובץ האינדוקס לא נמצא:\n\n{script_path}",
            )
            return

        answer = QMessageBox.question(
            self,
            "אינדוקס Gmail",
            "להפעיל את שלב 3 - אינדוקס "
            "המיילים שכבר יובאו?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if answer != QMessageBox.Yes:
            return

        try:
            env = self._get_subprocess_environment()

            process = subprocess.Popen(
                [
                    sys.executable,
                    str(script_path),
                ],
                cwd=str(PROJECT_ROOT),
                env=env,
            )

            self.statusBar().showMessage(
                "שלב 3: אינדוקס Gmail הופעל"
            )

            print(
                "[GMAIL INDEXER] Started process "
                f"PID={process.pid}"
            )

            print(
                "[GMAIL INDEXER] PYTHONPATH="
                f"{env.get('PYTHONPATH', '')}"
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "שגיאה",
                f"לא ניתן להפעיל את אינדוקס Gmail:\n\n{exc}",
            )


def apply_styles(app):
    app.setStyleSheet(
        """
        QMainWindow {
            background: #f4f5f7;
        }

        QWidget {
            font-family: Arial;
            font-size: 14px;
        }

        #sideMenu {
            background: #20242a;
        }

        #menuTitle {
            color: white;
            font-size: 24px;
            font-weight: bold;
            padding: 10px;
        }

        #menuButton {
            background: transparent;
            color: #d9dde3;
            border: none;
            border-radius: 6px;
            padding: 10px;
            text-align: right;
            font-size: 14px;
        }

        #menuButton:hover {
            background: #30363d;
            color: white;
        }

        #menuButton[selected="true"] {
            background: #3b4350;
            color: white;
            font-weight: bold;
        }

        #pageTitle {
            font-size: 30px;
            font-weight: bold;
            color: #20242a;
        }

        #pageSubtitle {
            font-size: 16px;
            color: #606872;
        }

        #card {
            background: white;
            border: 1px solid #d9dde3;
            border-radius: 10px;
        }

        #cardTitle {
            font-size: 19px;
            font-weight: bold;
            color: #20242a;
        }

        #cardDescription {
            color: #606872;
            font-size: 14px;
        }

        #primaryButton {
            background: #2f6fed;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 10px 15px;
            font-weight: bold;
        }

        #primaryButton:hover {
            background: #245dcc;
        }

        #primaryButton:pressed {
            background: #1e4fae;
        }

        QStatusBar {
            background: #e9ebef;
            color: #40464f;
        }
        """
    )


def main():
    app = QApplication(sys.argv)

    app.setApplicationName("Alcalay")
    app.setOrganizationName("Alcalay")

    apply_styles(app)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()