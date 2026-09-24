# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional


@dataclass
class SearchResult:
    """
    תוצאת חיפוש אחידה עבור כל מקורות Alcalay.

    result_type:
        document
        email
        attachment

    match_location:
        subject
        body
        content
        filename
        metadata
        attachment
    """

    document_id: int

    name: str = ""
    source: str = ""
    source_id: str = ""

    mime_type: str = ""
    extension: str = ""
    local_path: str = ""

    parent_document_id: Optional[int] = None

    result_type: str = "document"
    match_location: str = "content"

    match_count: int = 0
    snippet: str = ""

    document_date: Optional[date | datetime] = None
    indexed_at: Optional[date | datetime] = None

    is_attachment: bool = False
    attachment_name: str = ""

    metadata: dict[str, Any] = field(default_factory=dict)

    def display_source(self) -> str:
        source = (self.source or "").lower()

        return {
            "gmail": "Gmail",
            "drive": "Google Drive",
            "local": "Local",
        }.get(source, self.source or "לא ידוע")

    def display_type(self) -> str:
        if self.result_type == "email":
            return "מייל"

        if self.result_type == "attachment" or self.is_attachment:
            return "צרופה"

        return "מסמך"

    def display_date(self) -> str:
        value = self.document_date

        if value is None:
            return ""

        if isinstance(value, datetime):
            return value.strftime("%d/%m/%Y %H:%M")

        if isinstance(value, date):
            return value.strftime("%d/%m/%Y")

        return str(value)

    def display_name(self) -> str:
        return (
            self.attachment_name
            or self.name
            or f"Document {self.document_id}"
        )

    def icon_text(self) -> str:
        mime = (self.mime_type or "").lower()
        extension = (self.extension or "").lower()

        if (
            self.result_type == "email"
            or mime == "message/rfc822"
            or extension == ".eml"
        ):
            return "📧"

        if mime.startswith("image/"):
            return "🖼"

        if mime == "application/pdf" or extension == ".pdf":
            return "📄"

        if (
            "spreadsheet" in mime
            or extension in {".xls", ".xlsx", ".csv"}
        ):
            return "📊"

        if (
            "word" in mime
            or extension in {".doc", ".docx", ".rtf"}
        ):
            return "📝"

        if (
            "presentation" in mime
            or extension in {".ppt", ".pptx"}
        ):
            return "📑"

        if (
            mime.startswith("text/")
            or extension in {".txt", ".html", ".htm"}
        ):
            return "📃"

        if self.is_attachment:
            return "📎"

        return "📄"