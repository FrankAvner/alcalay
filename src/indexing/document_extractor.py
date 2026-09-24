# -*- coding: utf-8 -*-

"""
Alcalay - Unified Document Text Extractor

Shared extraction layer for the central document index.
The extractor is deliberately independent from Gmail/Drive so that all
repositories can use the same content pipeline.
"""

from __future__ import annotations

import csv
import html
import io
import json
import mimetypes
import re
from email import policy
from email.message import Message
from email.parser import BytesParser
from pathlib import Path
from typing import Any


EXTRACTOR_VERSION = "1.0"

TEXT_EXTENSIONS = {
    ".txt",
    ".text",
    ".md",
    ".csv",
    ".tsv",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".log",
    ".ini",
    ".cfg",
    ".conf",
    ".rtf",
    ".html",
    ".htm",
}

DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".xlsx",
    ".xlsm",
    ".pptx",
    ".eml",
}

SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS


def detect_mime_type(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    return mime_type or "application/octet-stream"


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)
    text = text.replace("\x00", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def decode_bytes(data: bytes) -> str:
    if not data:
        return ""

    candidates = [
        "utf-8",
        "utf-8-sig",
        "cp1255",
        "windows-1255",
        "cp1252",
        "latin-1",
    ]

    for encoding in candidates:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    return data.decode("utf-8", errors="replace")


def strip_html(value: str) -> str:
    if not value:
        return ""

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(value, "html.parser")
        return normalize_text(soup.get_text("\n"))
    except Exception:
        text = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
        text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        return normalize_text(html.unescape(text))


def extract_rtf(value: str) -> str:
    if not value:
        return ""

    # Basic RTF cleanup. It intentionally avoids destructive decoding of
    # non-ASCII text when a dedicated RTF parser is not installed.
    value = re.sub(r"\\'[0-9a-fA-F]{2}", " ", value)
    value = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", value)
    value = value.replace("{", " ").replace("}", " ")
    return normalize_text(value)


def extract_pdf(path: Path) -> tuple[str, str]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []

    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")

    return normalize_text("\n\n".join(pages)), "pypdf"


def extract_docx(path: Path) -> tuple[str, str]:
    from docx import Document

    document = Document(str(path))
    parts = []

    for paragraph in document.paragraphs:
        if paragraph.text:
            parts.append(paragraph.text)

    for table in document.tables:
        for row in table.rows:
            values = [cell.text for cell in row.cells]
            if any(values):
                parts.append(" | ".join(values))

    return normalize_text("\n".join(parts)), "python-docx"


def extract_xlsx(path: Path) -> tuple[str, str]:
    from openpyxl import load_workbook

    workbook = load_workbook(
        filename=str(path),
        read_only=True,
        data_only=True,
    )

    parts = []

    try:
        for worksheet in workbook.worksheets:
            parts.append(f"[SHEET] {worksheet.title}")

            for row in worksheet.iter_rows(values_only=True):
                values = []
                for value in row:
                    if value is not None:
                        values.append(str(value))

                if values:
                    parts.append(" | ".join(values))
    finally:
        workbook.close()

    return normalize_text("\n".join(parts)), "openpyxl"


def extract_pptx(path: Path) -> tuple[str, str]:
    from pptx import Presentation

    presentation = Presentation(str(path))
    parts = []

    for index, slide in enumerate(presentation.slides, start=1):
        parts.append(f"[SLIDE {index}]")

        for shape in slide.shapes:
            text = getattr(shape, "text", None)
            if text:
                parts.append(text)

    return normalize_text("\n".join(parts)), "python-pptx"


def extract_csv(path: Path, delimiter: str) -> tuple[str, str]:
    data = path.read_bytes()
    text = decode_bytes(data)

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = []

    for row in reader:
        rows.append(" | ".join(str(value) for value in row))

    return normalize_text("\n".join(rows)), "python-csv"


def extract_json_like(path: Path) -> tuple[str, str]:
    text = decode_bytes(path.read_bytes())

    try:
        payload = json.loads(text)
        return normalize_text(json.dumps(payload, ensure_ascii=False, indent=2)), "json"
    except Exception:
        return normalize_text(text), "text-fallback"


def extract_plain_text(path: Path) -> tuple[str, str]:
    return normalize_text(decode_bytes(path.read_bytes())), "text"


def extract_generic(path: Path) -> tuple[str, str]:
    mime_type = detect_mime_type(path)

    if mime_type.startswith("text/"):
        return extract_plain_text(path)

    return "", "unsupported"


def extract_eml(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    message = BytesParser(policy=policy.default).parsebytes(raw)

    metadata: dict[str, Any] = {
        "subject": str(message.get("Subject", "") or ""),
        "from": str(message.get("From", "") or ""),
        "to": str(message.get("To", "") or ""),
        "cc": str(message.get("Cc", "") or ""),
        "bcc": str(message.get("Bcc", "") or ""),
        "date": str(message.get("Date", "") or ""),
        "message_id": str(message.get("Message-ID", "") or ""),
        "in_reply_to": str(message.get("In-Reply-To", "") or ""),
        "references": str(message.get("References", "") or ""),
    }

    body_parts = []
    attachments: list[dict[str, Any]] = []

    if message.is_multipart():
        for part_number, part in enumerate(message.walk()):
            if part.is_multipart():
                continue

            content_disposition = str(part.get("Content-Disposition", "") or "").lower()
            filename = part.get_filename()
            content_type = part.get_content_type()

            if filename or "attachment" in content_disposition:
                try:
                    payload = part.get_payload(decode=True) or b""
                except Exception:
                    payload = b""

                attachments.append(
                    {
                        "part_number": part_number,
                        "file_name": str(filename or f"attachment_{part_number}"),
                        "mime_type": content_type,
                        "bytes": payload,
                        "metadata": {
                            "content_type": content_type,
                            "content_disposition": str(part.get("Content-Disposition", "") or ""),
                            "content_id": str(part.get("Content-ID", "") or ""),
                        },
                    }
                )
                continue

            try:
                content = part.get_content()
            except Exception:
                payload = part.get_payload(decode=True) or b""
                content = decode_bytes(payload)

            if content_type == "text/plain":
                body_parts.append(str(content))
            elif content_type == "text/html":
                body_parts.append(strip_html(str(content)))
    else:
        try:
            content = message.get_content()
        except Exception:
            content = decode_bytes(raw)
        body_parts.append(str(content))

    body_text = normalize_text("\n\n".join(body_parts))

    return {
        "message": message,
        "raw_size": len(raw),
        "metadata": metadata,
        "body_text": body_text,
        "attachments": attachments,
        "raw_bytes": raw,
    }


def extract_document(path: Path) -> dict[str, Any]:
    path = Path(path)
    suffix = path.suffix.lower()
    mime_type = detect_mime_type(path)

    if suffix == ".eml":
        email_result = extract_eml(path)
        return {
            "text": normalize_text(
                "\n\n".join(
                    part
                    for part in [
                        email_result["metadata"].get("subject", ""),
                        email_result["body_text"],
                    ]
                    if part
                )
            ),
            "method": "email-mime",
            "status": "SUCCESS",
            "error": None,
            "metadata": email_result["metadata"],
            "email": email_result,
            "mime_type": mime_type or "message/rfc822",
        }

    if suffix == ".pdf":
        text, method = extract_pdf(path)
    elif suffix == ".docx":
        text, method = extract_docx(path)
    elif suffix in {".xlsx", ".xlsm"}:
        text, method = extract_xlsx(path)
    elif suffix == ".pptx":
        text, method = extract_pptx(path)
    elif suffix == ".csv":
        text, method = extract_csv(path, ",")
    elif suffix == ".tsv":
        text, method = extract_csv(path, "\t")
    elif suffix in {".json", ".xml", ".yaml", ".yml"}:
        if suffix == ".json":
            text, method = extract_json_like(path)
        else:
            text, method = extract_plain_text(path)
    elif suffix in {".html", ".htm"}:
        text = strip_html(decode_bytes(path.read_bytes()))
        method = "html"
    elif suffix == ".rtf":
        text = extract_rtf(decode_bytes(path.read_bytes()))
        method = "rtf-basic"
    elif suffix in TEXT_EXTENSIONS:
        text, method = extract_plain_text(path)
    else:
        text, method = extract_generic(path)

    text = normalize_text(text)

    if method == "unsupported":
        return {
            "text": "",
            "method": method,
            "status": "UNSUPPORTED",
            "error": None,
            "metadata": {},
            "email": None,
            "mime_type": mime_type,
        }

    return {
        "text": text,
        "method": method,
        "status": "SUCCESS",
        "error": None,
        "metadata": {},
        "email": None,
        "mime_type": mime_type,
    }
