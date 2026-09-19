# -*- coding: utf-8 -*-

"""
Alcalay - Main Window
======================

Main application menu.

Location:
    src/ui/main_window.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"


MENU_ITEMS = [
    (1, "חיפוש Gmail"),
    (2, "חיפוש מסמכים"),
    (3, "חיפוש מתקדם"),
    (4, "מקורות מידע"),
    (5, "תוצאות ומסמכים"),
    (6, "סנכרון"),
    (7, "עיבוד מסמכים / AI"),
    (8, "משתמשים והרשאות"),
    (9, "הגדרות"),
    (10, "רענון והוספת מסמכים מהמייל"),
]


class PlaceholderPage(QWidget):
    """Temporary page until the actual module is connected."""

    def __init__(
        self,
        title: str,
        description: str = "",
        parent=None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(18)

        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        title_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )

        layout.addWidget(title_label)

        if description:
            description_label = QLabel(description)
            description_label.setObjectName("pageDescription")
            description_label.setWordWrap(True)
            description_label.setAlignment(
                Qt.AlignmentFlag.AlignRight
                | Qt.AlignmentFlag.AlignTop
            )

            layout.addWidget(description_label)

        layout.addStretch()


class MainWindow(QMainWindow):
    """Main Alcalay application window."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Alcalay - מערכת מידע")
        self.setMinimumSize(1100, 700)

        self.menu_list = None
        self.stack = None
        self.page_title = None

        self._build_ui()
        self._apply_style()
        self._select_initial_page()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ==============================================================
        # HEADER
        # ==============================================================

        header = QFrame()
        header.setObjectName("header")

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(
            25,
            15,
            25,
            15,
        )

        system_title = QLabel("ALCALAY")
        system_title.setObjectName("systemTitle")

        system_subtitle = QLabel(
            "מערכת מידע וחיפוש מסמכים"
        )
        system_subtitle.setObjectName("systemSubtitle")

        title_container = QVBoxLayout()
        title_container.setSpacing(2)

        title_container.addWidget(system_title)
        title_container.addWidget(system_subtitle)

        header_layout.addLayout(title_container)
        header_layout.addStretch()

        self.page_title = QLabel("")
        self.page_title.setObjectName(
            "currentPageTitle"
        )

        header_layout.addWidget(self.page_title)

        main_layout.addWidget(header)

        # ==============================================================
        # MAIN CONTENT
        # ==============================================================

        content = QWidget()

        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        content_layout.setSpacing(0)

        # ==============================================================
        # RIGHT MENU
        # ==============================================================

        menu_frame = QFrame()
        menu_frame.setObjectName("menuFrame")
        menu_frame.setMinimumWidth(300)
        menu_frame.setMaximumWidth(340)

        menu_layout = QVBoxLayout(menu_frame)
        menu_layout.setContentsMargins(
            15,
            20,
            15,
            20,
        )
        menu_layout.setSpacing(8)

        menu_title = QLabel("תפריט ראשי")
        menu_title.setObjectName("menuTitle")
        menu_title.setAlignment(
            Qt.AlignmentFlag.AlignRight
        )

        menu_layout.addWidget(menu_title)

        self.menu_list = QListWidget()
        self.menu_list.setObjectName("mainMenu")

        self.menu_list.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft
        )

        self.menu_list.setSpacing(4)

        for number, title in MENU_ITEMS:

            item = QListWidgetItem()

            item.setData(
                Qt.ItemDataRole.UserRole,
                number,
            )

            item.setText(
                f"{number}.  {title}"
            )

            item.setSizeHint(
                QSize(270, 48)
            )

            self.menu_list.addItem(item)

        self.menu_list.currentRowChanged.connect(
            self._menu_changed
        )

        menu_layout.addWidget(
            self.menu_list
        )

        # ==============================================================
        # CONTENT STACK
        # ==============================================================

        self.stack = QStackedWidget()
        self.stack.setObjectName(
            "contentStack"
        )

        for number, title in MENU_ITEMS:

            page = self._create_page(
                number,
                title,
            )

            self.stack.addWidget(page)

        content_layout.addWidget(
            self.stack,
            1,
        )

        content_layout.addWidget(
            menu_frame
        )

        main_layout.addWidget(
            content,
            1,
        )

        # ==============================================================
        # STATUS BAR
        # ==============================================================

        self.statusBar().showMessage(
            "מוכן"
        )

    def _create_page(
        self,
        number: int,
        title: str,
    ) -> QWidget:

        descriptions = {

            1:
                "חיפוש הודעות ומידע "
                "בחשבון Gmail המחובר.",

            2:
                "חיפוש במסמכים ובקבצים "
                "המאוחסנים במקורות המקומיים.",

            3:
                "חיפוש משולב ומתקדם "
                "במספר מקורות מידע.",

            4:
                "ניהול והצגת מקורות "
                "המידע המחוברים למערכת.",

            5:
                "צפייה, מיון וניהול "
                "של תוצאות חיפוש ומסמכים.",

            6:
                "ניהול פעולות סנכרון "
                "בין מקורות המידע למערכת.",

            7:
                "עיבוד מסמכים, חילוץ מידע "
                "ותהליכי AI.",

            8:
                "ניהול משתמשים, תפקידים "
                "והרשאות.",

            9:
                "הגדרות המערכת "
                "והעדפות המשתמש.",

            10:
                (
                    "רענון והוספת מסמכים מהמייל. "
                    "המערכת תאפשר בחירת חשבון Gmail "
                    "ו-Label/תיקייה ותנהל סנכרון "
                    "incremental לכל שילוב בנפרד."
                ),
        }

        return PlaceholderPage(
            title=f"{number}. {title}",
            description=descriptions.get(
                number,
                "",
            ),
        )

    def _menu_changed(
        self,
        row: int,
    ):

        if row < 0:
            return

        if self.stack is None:
            return

        item = self.menu_list.item(row)

        if item is None:
            return

        title = item.text()

        self.stack.setCurrentIndex(
            row
        )

        if self.page_title is not None:
            self.page_title.setText(
                title
            )

        self.statusBar().showMessage(
            f"נבחר: {title}"
        )

    def _select_initial_page(self):

        if self.menu_list is not None:
            self.menu_list.setCurrentRow(
                0
            )

    def _apply_style(self):

        self.setStyleSheet(
            """
            QMainWindow {
                background: #f5f6f8;
            }

            QWidget {
                font-family: Arial, "Segoe UI";
                font-size: 14px;
            }

            #header {
                background: #1f2937;
                min-height: 80px;
                max-height: 80px;
            }

            #systemTitle {
                color: white;
                font-size: 24px;
                font-weight: bold;
            }

            #systemSubtitle {
                color: #d1d5db;
                font-size: 13px;
            }

            #currentPageTitle {
                color: white;
                font-size: 18px;
                font-weight: bold;
            }

            #menuFrame {
                background: #ffffff;
                border-left: 1px solid #d1d5db;
            }

            #menuTitle {
                color: #374151;
                font-size: 18px;
                font-weight: bold;
                padding: 5px;
            }

            #mainMenu {
                border: none;
                background: transparent;
                outline: none;
            }

            #mainMenu::item {
                color: #374151;
                background: transparent;
                border-radius: 6px;
                padding: 8px 12px;
                margin: 2px 0;
            }

            #mainMenu::item:hover {
                background: #eef2f7;
            }

            #mainMenu::item:selected {
                background: #dbeafe;
                color: #1d4ed8;
                font-weight: bold;
            }

            #contentStack {
                background: #f5f6f8;
            }

            #pageTitle {
                color: #1f2937;
                font-size: 26px;
                font-weight: bold;
            }

            #pageDescription {
                color: #4b5563;
                font-size: 16px;
            }

            QStatusBar {
                background: #e5e7eb;
                color: #374151;
            }
            """
        )


def main():

    app = QApplication.instance()

    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName(
        "Alcalay"
    )

    app.setOrganizationName(
        "Alcalay"
    )

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())