# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Iterable, Optional, Sequence

from .search_result import SearchResult


@dataclass
class SearchCriteria:
    """
    תנאי חיפוש.

    משמש גם לחיפוש ראשי וגם לחיפוש
    בתוך קבוצת תוצאות קיימת.
    """

    text: str = ""
    exact_phrase: str = ""

    sender: str = ""
    recipient: str = ""

    date_from: Optional[date | datetime] = None
    date_to: Optional[date | datetime] = None

    source: str = ""
    document_type: str = ""

    include_attachments: bool = True
    search_attachment_content: bool = True

    # כאשר קיים, החיפוש מוגבל ל-document IDs אלה.
    result_document_ids: Optional[list[int]] = None

    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResultSet:
    """
    קבוצת תוצאות חיפוש.

    results:
        התוצאות הנוכחיות.

    original_count:
        מספר התוצאות בחיפוש המקורי.
    """

    results: list[SearchResult] = field(default_factory=list)

    original_count: int = 0

    query_description: str = ""

    def __post_init__(self) -> None:
        if self.original_count == 0:
            self.original_count = len(self.results)

    @property
    def current_count(self) -> int:
        return len(self.results)

    @property
    def document_ids(self) -> list[int]:
        return [
            result.document_id
            for result in self.results
        ]

    def filter_ids(
        self,
        ids: Iterable[int],
    ) -> "SearchResultSet":

        allowed = set(ids)

        filtered = [
            result
            for result in self.results
            if result.document_id in allowed
        ]

        return SearchResultSet(
            results=filtered,
            original_count=self.original_count,
            query_description=self.query_description,
        )


class SearchService:
    """
    שירות החיפוש של Alcalay.

    השירות אינו מניח כאן סכמת PostgreSQL ספציפית.

    executor הוא פונקציה שמקבלת:

        sql
        params

    ומחזירה רשימת dictionaries.

    לאחר שנבדוק את PostgreSQL הקיים,
    נחבר את executor לסכמה האמיתית.
    """

    def __init__(
        self,
        executor: Optional[
            Callable[[str, list[Any]], list[dict[str, Any]]]
        ] = None,
    ) -> None:

        self.executor = executor

    # ==================================================================
    # Public search API
    # ==================================================================

    def search(
        self,
        criteria: SearchCriteria,
        *,
        base_result_ids: Optional[Sequence[int]] = None,
    ) -> SearchResultSet:

        if self.executor is None:
            raise RuntimeError(
                "SearchService אינו מחובר עדיין ל-PostgreSQL."
            )

        sql, params = self.build_query(
            criteria,
            base_result_ids=base_result_ids,
        )

        rows = self.executor(
            sql,
            params,
        )

        results = [
            self.row_to_result(row)
            for row in rows
        ]

        return SearchResultSet(
            results=results,
            original_count=len(results),
            query_description=self.describe(criteria),
        )

    def search_within_results(
        self,
        current_results: SearchResultSet,
        criteria: SearchCriteria,
    ) -> SearchResultSet:
        """
        חיפוש בתוך תוצאות קיימות.

        החיפוש החדש מוגבל ל-document IDs
        של קבוצת התוצאות הנוכחית.
        """

        ids = current_results.document_ids

        criteria.result_document_ids = list(ids)

        return self.search(
            criteria,
            base_result_ids=ids,
        )

    # ==================================================================
    # SQL builder
    # ==================================================================

    def build_query(
        self,
        criteria: SearchCriteria,
        *,
        base_result_ids: Optional[Sequence[int]] = None,
    ) -> tuple[str, list[Any]]:
        """
        בונה SQL ו-parameters.

        כל placeholder שמתווסף ל-SQL
        מקבל parameter מתאים אחד.

        כך נמנעת התקלה:

            query has 18 placeholders
            but 19 parameters were passed
        """

        where: list[str] = []
        params: list[Any] = []

        # --------------------------------------------------------------
        # Text
        # --------------------------------------------------------------

        text = criteria.text.strip()

        if text:
            terms = self._split_terms(text)

            for term in terms:

                where.append(
                    "searchable_text ILIKE %s"
                )

                params.append(
                    f"%{term}%"
                )

        # --------------------------------------------------------------
        # Exact phrase
        # --------------------------------------------------------------

        exact_phrase = criteria.exact_phrase.strip()

        if exact_phrase:

            where.append(
                "searchable_text ILIKE %s"
            )

            params.append(
                f"%{exact_phrase}%"
            )

        # --------------------------------------------------------------
        # Sender
        # --------------------------------------------------------------

        sender = criteria.sender.strip()

        if sender:

            where.append(
                "sender ILIKE %s"
            )

            params.append(
                f"%{sender}%"
            )

        # --------------------------------------------------------------
        # Recipient
        # --------------------------------------------------------------

        recipient = criteria.recipient.strip()

        if recipient:

            where.append(
                "recipient ILIKE %s"
            )

            params.append(
                f"%{recipient}%"
            )

        # --------------------------------------------------------------
        # Date range
        # --------------------------------------------------------------

        if criteria.date_from is not None:

            where.append(
                "document_date >= %s"
            )

            params.append(
                criteria.date_from
            )

        if criteria.date_to is not None:

            where.append(
                "document_date <= %s"
            )

            params.append(
                criteria.date_to
            )

        # --------------------------------------------------------------
        # Source
        # --------------------------------------------------------------

        source = criteria.source.strip()

        if source:

            where.append(
                "source = %s"
            )

            params.append(
                source
            )

        # --------------------------------------------------------------
        # MIME type
        # --------------------------------------------------------------

        document_type = criteria.document_type.strip()

        if document_type:

            if document_type.endswith("/"):

                where.append(
                    "mime_type ILIKE %s"
                )

                params.append(
                    document_type + "%"
                )

            else:

                where.append(
                    "mime_type = %s"
                )

                params.append(
                    document_type
                )

        # --------------------------------------------------------------
        # Attachments
        # --------------------------------------------------------------

        if not criteria.include_attachments:

            where.append(
                "COALESCE(is_attachment, FALSE) = FALSE"
            )

        # --------------------------------------------------------------
        # Existing result set
        # --------------------------------------------------------------

        ids = (
            list(base_result_ids)
            if base_result_ids is not None
            else criteria.result_document_ids
        )

        if ids:

            placeholders = ", ".join(
                ["%s"] * len(ids)
            )

            where.append(
                f"document_id IN ({placeholders})"
            )

            params.extend(
                ids
            )

        # --------------------------------------------------------------
        # Temporary generic table/view
        # --------------------------------------------------------------
        #
        # לא לחבר למסד הנתונים האמיתי לפני בדיקת הסכמה.
        #
        # --------------------------------------------------------------

        sql = """
SELECT
    document_id,
    name,
    source,
    source_id,
    mime_type,
    extension,
    local_path,
    parent_document_id,
    document_date,
    indexed_at,
    is_attachment,
    attachment_name,
    result_type,
    match_location,
    match_count,
    snippet
FROM alcalay_search_documents
"""

        if where:

            sql += "\nWHERE "

            sql += "\n  AND ".join(
                where
            )

        sql += """
ORDER BY
    document_date DESC NULLS LAST,
    document_id DESC
"""

        return sql, params

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _split_terms(
        text: str,
    ) -> list[str]:
        """
        חיפוש בסיסי לפי מילים.

        AND / OR / NOT מלאים יתווספו
        לאחר חיבור המנוע לסכמת PostgreSQL.
        """

        return [
            part.strip()
            for part in text.split()
            if part.strip()
        ]

    @staticmethod
    def row_to_result(
        row: dict[str, Any],
    ) -> SearchResult:

        return SearchResult(
            document_id=int(
                row["document_id"]
            ),

            name=row.get("name") or "",

            source=row.get("source") or "",

            source_id=row.get("source_id") or "",

            mime_type=row.get("mime_type") or "",

            extension=row.get("extension") or "",

            local_path=row.get("local_path") or "",

            parent_document_id=row.get(
                "parent_document_id"
            ),

            result_type=row.get(
                "result_type"
            ) or "document",

            match_location=row.get(
                "match_location"
            ) or "content",

            match_count=int(
                row.get("match_count") or 0
            ),

            snippet=row.get(
                "snippet"
            ) or "",

            document_date=row.get(
                "document_date"
            ),

            indexed_at=row.get(
                "indexed_at"
            ),

            is_attachment=bool(
                row.get("is_attachment")
            ),

            attachment_name=row.get(
                "attachment_name"
            ) or "",

            metadata=dict(row),
        )

    @staticmethod
    def describe(
        criteria: SearchCriteria,
    ) -> str:

        parts: list[str] = []

        if criteria.text.strip():

            parts.append(
                criteria.text.strip()
            )

        if criteria.exact_phrase.strip():

            parts.append(
                f'"{criteria.exact_phrase.strip()}"'
            )

        if criteria.sender.strip():

            parts.append(
                f"שולח={criteria.sender.strip()}"
            )

        if criteria.recipient.strip():

            parts.append(
                f"נמען={criteria.recipient.strip()}"
            )

        if criteria.date_from is not None:

            parts.append(
                f"מתאריך={criteria.date_from}"
            )

        if criteria.date_to is not None:

            parts.append(
                f"עד={criteria.date_to}"
            )

        if criteria.source.strip():

            parts.append(
                f"מקור={criteria.source.strip()}"
            )

        if criteria.document_type.strip():

            parts.append(
                f"סוג={criteria.document_type.strip()}"
            )

        return " | ".join(parts)