# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.search.search_result import SearchResult
from src.search.search_service import (
    SearchCriteria,
    SearchResultSet,
    SearchService,
)
from src.ui.document_viewer import DocumentViewer


class SearchResultsWidget(QWidget):

    """
    מסך תוצאות החיפוש של Alcalay.

    תומך ב:

    1. הצגת תוצאות חיפוש.
    2. בחירת מסמך.
    3. הצגת המסמך ב-DocumentViewer.
    4. חיפוש נוסף בתוך התוצאות הקיימות.
    5. חיפוש מתקדם בתוך התוצאות.
    6. איפוס לחיפוש המקורי.
    """

    result_selected = Signal(object)

    def __init__(
        self,
        search_service: Optional[SearchService] = None,
        parent=None,
    ):
        super().__init__(
            parent
        )

        self.search_service = (
            search_service
        )

        self.original_result_set = (
            SearchResultSet([])
        )

        self.current_result_set = (
            SearchResultSet([])
        )

        self._build_ui()

    # ==================================================================
    # UI
    # ==================================================================

    def _build_ui(
        self,
    ) -> None:

        root = QVBoxLayout(
            self
        )

        # ==============================================================
        # Top search area
        # ==============================================================

        top_frame = QFrame()

        top_layout = QVBoxLayout(
            top_frame
        )

        row = QHBoxLayout()

        row.addWidget(
            QLabel(
                "חיפוש בתוך התוצאות:"
            )
        )

        self.within_results_edit = (
            QLineEdit()
        )

        self.within_results_edit.setPlaceholderText(
            "חפש רק בתוך התוצאות שכבר נמצאו..."
        )

        self.within_results_edit.returnPressed.connect(
            self._search_within_results
        )

        self.within_search_button = (
            QPushButton(
                "חפש"
            )
        )

        self.within_search_button.clicked.connect(
            self._search_within_results
        )

        self.reset_button = (
            QPushButton(
                "נקה חיפוש פנימי"
            )
        )

        self.reset_button.clicked.connect(
            self._reset_internal_search
        )

        row.addWidget(
            self.within_results_edit,
            1,
        )

        row.addWidget(
            self.within_search_button
        )

        row.addWidget(
            self.reset_button
        )

        top_layout.addLayout(
            row
        )

        # ==============================================================
        # Counter
        # ==============================================================

        self.counter_label = QLabel(
            "אין תוצאות"
        )

        top_layout.addWidget(
            self.counter_label
        )

        # ==============================================================
        # Advanced search
        # ==============================================================

        advanced_frame = QFrame()

        advanced_layout = QFormLayout(
            advanced_frame
        )

        self.exact_edit = QLineEdit()

        self.sender_edit = QLineEdit()

        self.recipient_edit = QLineEdit()

        self.date_from_edit = QLineEdit()

        self.date_from_edit.setPlaceholderText(
            "YYYY-MM-DD"
        )

        self.date_to_edit = QLineEdit()

        self.date_to_edit.setPlaceholderText(
            "YYYY-MM-DD"
        )

        self.source_combo = QComboBox()

        self.source_combo.addItem(
            "כל המקורות",
            "",
        )

        self.source_combo.addItem(
            "Local",
            "local",
        )

        self.source_combo.addItem(
            "Google Drive",
            "drive",
        )

        self.source_combo.addItem(
            "Gmail",
            "gmail",
        )

        self.type_combo = QComboBox()

        self.type_combo.addItem(
            "כל סוגי הקבצים",
            "",
        )

        self.type_combo.addItem(
            "PDF",
            "application/pdf",
        )

        self.type_combo.addItem(
            "תמונה",
            "image/",
        )

        self.type_combo.addItem(
            "EML",
            "message/rfc822",
        )

        self.type_combo.addItem(
            "DOCX",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        advanced_layout.addRow(
            "ביטוי מדויק:",
            self.exact_edit,
        )

        advanced_layout.addRow(
            "שולח:",
            self.sender_edit,
        )

        advanced_layout.addRow(
            "נמען:",
            self.recipient_edit,
        )

        advanced_layout.addRow(
            "מתאריך:",
            self.date_from_edit,
        )

        advanced_layout.addRow(
            "עד תאריך:",
            self.date_to_edit,
        )

        advanced_layout.addRow(
            "מקור:",
            self.source_combo,
        )

        advanced_layout.addRow(
            "סוג:",
            self.type_combo,
        )

        advanced_search_button = (
            QPushButton(
                "חיפוש מתקדם בתוך התוצאות"
            )
        )

        advanced_search_button.clicked.connect(
            self._advanced_search_within_results
        )

        advanced_layout.addRow(
            "",
            advanced_search_button,
        )

        advanced_frame.setVisible(
            False
        )

        toggle_advanced = QPushButton(
            "חיפוש מתקדם"
        )

        toggle_advanced.setCheckable(
            True
        )

        toggle_advanced.toggled.connect(
            advanced_frame.setVisible
        )

        top_layout.addWidget(
            toggle_advanced
        )

        top_layout.addWidget(
            advanced_frame
        )

        root.addWidget(
            top_frame
        )

        # ==============================================================
        # Main splitter
        # ==============================================================

        splitter = QSplitter(
            Qt.Horizontal
        )

        # ==============================================================
        # Left side
        # ==============================================================

        left = QFrame()

        left_layout = QVBoxLayout(
            left
        )

        self.results_list = QListWidget()

        self.results_list.currentItemChanged.connect(
            self._result_changed
        )

        left_layout.addWidget(
            self.results_list,
            1,
        )

        self.result_details = QLabel(
            ""
        )

        self.result_details.setWordWrap(
            True
        )

        self.result_details.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        left_layout.addWidget(
            self.result_details
        )

        # ==============================================================
        # Right side
        # ==============================================================

        self.viewer = DocumentViewer()

        splitter.addWidget(
            left
        )

        splitter.addWidget(
            self.viewer
        )

        splitter.setStretchFactor(
            0,
            0,
        )

        splitter.setStretchFactor(
            1,
            1,
        )

        splitter.setSizes(
            [
                430,
                950,
            ]
        )

        root.addWidget(
            splitter,
            1,
        )

    # ==================================================================
    # Public API
    # ==================================================================

    def set_results(
        self,
        result_set: SearchResultSet,
    ) -> None:

        self.original_result_set = (
            SearchResultSet(
                results=list(
                    result_set.results
                ),
                original_count=(
                    result_set.original_count
                ),
                query_description=(
                    result_set.query_description
                ),
            )
        )

        self.current_result_set = (
            SearchResultSet(
                results=list(
                    result_set.results
                ),
                original_count=(
                    result_set.original_count
                ),
                query_description=(
                    result_set.query_description
                ),
            )
        )

        self._refresh_list()

    def set_results_from_list(
        self,
        results: list[SearchResult],
    ) -> None:

        self.set_results(
            SearchResultSet(
                results=results
            )
        )

    def get_current_results(
        self,
    ) -> SearchResultSet:

        return self.current_result_set

    # ==================================================================
    # Result list
    # ==================================================================

    def _refresh_list(
        self,
    ) -> None:

        self.results_list.blockSignals(
            True
        )

        self.results_list.clear()

        for result in (
            self.current_result_set.results
        ):

            item = QListWidgetItem(
                self._result_text(
                    result
                )
            )

            item.setData(
                Qt.UserRole,
                result,
            )

            self.results_list.addItem(
                item
            )

        self.results_list.blockSignals(
            False
        )

        self.counter_label.setText(
            "מציג "
            + str(
                self.current_result_set.current_count
            )
            + " מתוך "
            + str(
                self.original_result_set.original_count
            )
            + " תוצאות"
        )

        if self.results_list.count():

            self.results_list.setCurrentRow(
                0
            )

        else:

            self.result_details.setText(
                ""
            )

            self.viewer._show_message(
                "אין תוצאות להצגה."
            )

    @staticmethod
    def _result_text(
        result: SearchResult,
    ) -> str:

        lines = [
            (
                f"{result.icon_text()}  "
                f"{result.display_name()}"
            ),
            (
                f"{result.display_type()} | "
                f"{result.display_source()} | "
                f"{result.display_date()}"
            ),
        ]

        if result.match_location:

            lines.append(
                "התאמה: "
                + result.match_location
            )

        if result.snippet:

            snippet = " ".join(
                result.snippet.split()
            )

            if len(snippet) > 180:

                snippet = (
                    snippet[:177]
                    + "..."
                )

            lines.append(
                snippet
            )

        return "\n".join(
            lines
        )

    # ==================================================================
    # Selection
    # ==================================================================

    def _result_changed(
        self,
        current,
        previous,
    ) -> None:

        if current is None:
            return

        result = current.data(
            Qt.UserRole
        )

        if not isinstance(
            result,
            SearchResult,
        ):
            return

        self.result_selected.emit(
            result
        )

        self._show_result(
            result
        )

    def _show_result(
        self,
        result: SearchResult,
    ) -> None:

        details = [
            (
                f"<b>{result.display_name()}</b>"
            ),
            (
                f"מקור: "
                f"{result.display_source()}"
            ),
            (
                f"סוג: "
                f"{result.display_type()}"
            ),
            (
                f"תאריך: "
                f"{result.display_date()}"
            ),
        ]

        if result.match_location:

            details.append(
                "מיקום התאמה: "
                + result.match_location
            )

        if result.match_count:

            details.append(
                f"מספר התאמות: "
                f"{result.match_count}"
            )

        if result.snippet:

            details.append(
                "<br><b>"
                "תצוגה מקדימה:"
                "</b><br>"
                + result.snippet
            )

        self.result_details.setText(
            "<br>".join(
                details
            )
        )

        if result.local_path:

            self.viewer.show_file(
                result.local_path,
                result.display_name(),
            )

        else:

            self.viewer._show_message(
                "לתוצאה הזו עדיין אין "
                "נתיב מקומי להצגה."
            )

    # ==================================================================
    # Search within results
    # ==================================================================

    def _search_within_results(
        self,
    ) -> None:

        text = (
            self.within_results_edit
            .text()
            .strip()
        )

        if not text:

            self._reset_internal_search()

            return

        # --------------------------------------------------------------
        # PostgreSQL
        # --------------------------------------------------------------

        if self.search_service is not None:

            criteria = SearchCriteria(
                text=text
            )

            try:

                result_set = (
                    self.search_service
                    .search_within_results(
                        self.current_result_set,
                        criteria,
                    )
                )

                self.current_result_set = (
                    result_set
                )

                self._refresh_list()

                return

            except Exception as exc:

                self.counter_label.setText(
                    "שגיאה בחיפוש בתוך "
                    "התוצאות: "
                    + str(exc)
                )

                return

        # --------------------------------------------------------------
        # Local fallback
        # --------------------------------------------------------------

        self._local_filter(
            text
        )

    # ==================================================================
    # Advanced search
    # ==================================================================

    def _advanced_search_within_results(
        self,
    ) -> None:

        if self.search_service is None:

            self.counter_label.setText(
                "חיפוש מתקדם יופעל "
                "לאחר חיבור PostgreSQL."
            )

            return

        criteria = SearchCriteria(
            text=(
                self.within_results_edit
                .text()
                .strip()
            ),

            exact_phrase=(
                self.exact_edit
                .text()
                .strip()
            ),

            sender=(
                self.sender_edit
                .text()
                .strip()
            ),

            recipient=(
                self.recipient_edit
                .text()
                .strip()
            ),

            source=(
                self.source_combo
                .currentData()
                or ""
            ),

            document_type=(
                self.type_combo
                .currentData()
                or ""
            ),
        )

        try:

            result_set = (
                self.search_service
                .search_within_results(
                    self.current_result_set,
                    criteria,
                )
            )

            self.current_result_set = (
                result_set
            )

            self._refresh_list()

        except Exception as exc:

            self.counter_label.setText(
                "שגיאה בחיפוש המתקדם: "
                + str(exc)
            )

    # ==================================================================
    # Local fallback
    # ==================================================================

    def _local_filter(
        self,
        text: str,
    ) -> None:

        """
        Fallback זמני בלבד.

        משמש לבדיקת ממשק "חיפוש בתוך התוצאות"
        לפני חיבור PostgreSQL.
        """

        needle = text.casefold()

        filtered = []

        for result in (
            self.current_result_set.results
        ):

            haystack = " ".join(
                [
                    result.name,
                    result.attachment_name,
                    result.snippet,
                    result.source,
                    result.match_location,
                ]
            ).casefold()

            if needle in haystack:

                filtered.append(
                    result
                )

        self.current_result_set = (
            SearchResultSet(
                results=filtered,
                original_count=(
                    self.original_result_set
                    .original_count
                ),
                query_description=(
                    self.original_result_set
                    .query_description
                ),
            )
        )

        self._refresh_list()

    # ==================================================================
    # Reset
    # ==================================================================

    def _reset_internal_search(
        self,
    ) -> None:

        self.within_results_edit.clear()

        self.exact_edit.clear()

        self.sender_edit.clear()

        self.recipient_edit.clear()

        self.date_from_edit.clear()

        self.date_to_edit.clear()

        self.source_combo.setCurrentIndex(
            0
        )

        self.type_combo.setCurrentIndex(
            0
        )

        self.current_result_set = (
            SearchResultSet(
                results=list(
                    self.original_result_set
                    .results
                ),
                original_count=(
                    self.original_result_set
                    .original_count
                ),
                query_description=(
                    self.original_result_set
                    .query_description
                ),
            )
        )

        self._refresh_list()