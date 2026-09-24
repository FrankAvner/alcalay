
-- coding: utf-8 --

"""
Alcalay - Unified Indexing Package
"""

from .document_extractor import (
EXTRACTOR_VERSION,
SUPPORTED_EXTENSIONS,
detect_mime_type,
normalize_text,
decode_bytes,
strip_html,
extract_document,
extract_eml,
)

from .unified_indexer import UnifiedIndexer

all = [
"EXTRACTOR_VERSION",
"SUPPORTED_EXTENSIONS",
"detect_mime_type",
"normalize_text",
"decode_bytes",
"strip_html",
"extract_document",
"extract_eml",
"UnifiedIndexer",
]
