# -*- coding: utf-8 -*-

"""
Alcalay - Unified Indexer

One central indexing engine for:
    * Gmail messages and their embedded attachments
    * local/Drive documents already present in local storage
    * optional semantic/AI embeddings

Every processed item is checkpointed in PostgreSQL. A stopped or interrupted
run does not mark the current item as completed, so the next run naturally
continues from the first item that is still missing or changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from psycopg2.extras import Json
except Exception:
    Json = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import DatabaseConnection
from src.indexing.document_extractor import (
    EXTRACTOR_VERSION,
    SUPPORTED_EXTENSIONS,
    extract_document,
    normalize_text,
)


INDEXER_VERSION = "1.0"
REPOSITORY_DOCUMENT_ROOTS = (
    PROJECT_ROOT / "storage" / "drive",
    PROJECT_ROOT / "storage" / "office",
    PROJECT_ROOT / "storage" / "documents",
    PROJECT_ROOT / "storage" / "local",
)
GMAIL_ROOT = PROJECT_ROOT / "storage" / "gmail"

STOP_WORDS = {"STOP", "QUIT", "EXIT", "עצור"}


class UnifiedIndexer:
    def __init__(self, stages: list[str]) -> None:
        normalized = []
        for stage in stages:
            stage = str(stage).strip().lower()
            if stage in {"mail", "mails", "gmail"}:
                stage = "mails"
            elif stage in {"document", "documents", "docs"}:
                stage = "documents"
            elif stage in {"ai", "semantic", "semantic_ai"}:
                stage = "ai"
            else:
                raise ValueError(f"Unsupported index stage: {stage}")
            if stage not in normalized:
                normalized.append(stage)

        self.stages = normalized
        self.db = DatabaseConnection()
        self.connection = None
        self.stop_event = threading.Event()
        self.input_thread: threading.Thread | None = None
        self.run_id: int | None = None
        self.run_uuid: str | None = None
        self.current_stage = None
        self.current_item_key = None
        self.current_item_name = None
        self.current_item_path = None

        self.stage_stats: dict[str, dict[str, int]] = {
            stage: {
                "total": 0,
                "processed": 0,
                "skipped": 0,
                "errors": 0,
                "remaining": 0,
            }
            for stage in self.stages
        }

    # ------------------------------------------------------------------
    # Output protocol
    # ------------------------------------------------------------------

    def emit(self, event: str, **data: Any) -> None:
        payload = {
            "event": event,
            "timestamp": self.now_iso(),
            **data,
        }
        print(
            "[INDEX_EVENT] "
            + json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
            ),
            flush=True,
        )

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def now_iso(self) -> str:
        return self.now().isoformat()

    def log(self, message: str) -> None:
        print(message, flush=True)

    # ------------------------------------------------------------------
    # Stop listener
    # ------------------------------------------------------------------

    def start_stop_listener(self) -> None:
        def reader() -> None:
            try:
                for line in sys.stdin:
                    if line.strip().upper() in STOP_WORDS:
                        self.stop_event.set()
                        self.emit(
                            "STOP_REQUESTED",
                            message="בקשת עצירה התקבלה.",
                            current_item_key=self.current_item_key,
                            current_item_name=self.current_item_name,
                            current_item_path=self.current_item_path,
                        )
                        break
            except Exception:
                pass

        self.input_thread = threading.Thread(
            target=reader,
            daemon=True,
        )
        self.input_thread.start()

    # ------------------------------------------------------------------
    # Database schema / checkpoints
    # ------------------------------------------------------------------

    def connect_database(self) -> None:
        self.connection = self.db.connect()
        self.ensure_schema()
        self.recover_stale_runs()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params)
        self.connection.commit()

    def ensure_schema(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS document_index (
                id BIGSERIAL PRIMARY KEY,
                source_type TEXT NOT NULL,
                source_key TEXT NOT NULL UNIQUE,
                parent_source_key TEXT,
                name TEXT,
                file_path TEXT,
                mime_type TEXT,
                extension TEXT,
                size_bytes BIGINT,
                modified_at TIMESTAMPTZ,
                source_hash TEXT,
                content_hash TEXT,
                content_text TEXT,
                search_vector TSVECTOR,
                extraction_status TEXT,
                extraction_method TEXT,
                extraction_error TEXT,
                extractor_version TEXT,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                indexed_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ,
                ai_status TEXT,
                ai_indexed_at TIMESTAMPTZ,
                ai_content_hash TEXT,
                ai_provider TEXT,
                ai_model TEXT,
                ai_text TEXT,
                ai_embedding JSONB
            )
            """,
            """
            ALTER TABLE document_index
                ADD COLUMN IF NOT EXISTS parent_source_key TEXT,
                ADD COLUMN IF NOT EXISTS search_vector TSVECTOR,
                ADD COLUMN IF NOT EXISTS extractor_version TEXT,
                ADD COLUMN IF NOT EXISTS ai_status TEXT,
                ADD COLUMN IF NOT EXISTS ai_indexed_at TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS ai_content_hash TEXT,
                ADD COLUMN IF NOT EXISTS ai_provider TEXT,
                ADD COLUMN IF NOT EXISTS ai_model TEXT,
                ADD COLUMN IF NOT EXISTS ai_text TEXT,
                ADD COLUMN IF NOT EXISTS ai_embedding JSONB
            """,
            "CREATE INDEX IF NOT EXISTS idx_document_index_source_type ON document_index(source_type)",
            "CREATE INDEX IF NOT EXISTS idx_document_index_source_hash ON document_index(source_hash)",
            "CREATE INDEX IF NOT EXISTS idx_document_index_content_hash ON document_index(content_hash)",
            "CREATE INDEX IF NOT EXISTS idx_document_index_search_vector ON document_index USING GIN(search_vector)",
            "CREATE INDEX IF NOT EXISTS idx_document_index_ai_status ON document_index(ai_status)",
            """
            CREATE TABLE IF NOT EXISTS index_runs (
                id BIGSERIAL PRIMARY KEY,
                run_uuid TEXT NOT NULL UNIQUE,
                started_at TIMESTAMPTZ NOT NULL,
                finished_at TIMESTAMPTZ,
                status TEXT NOT NULL,
                selected_stages JSONB NOT NULL DEFAULT '[]'::jsonb,
                current_stage TEXT,
                current_item_key TEXT,
                current_item_name TEXT,
                current_item_path TEXT,
                current_item_started_at TIMESTAMPTZ,
                total_items BIGINT DEFAULT 0,
                completed_items BIGINT DEFAULT 0,
                skipped_items BIGINT DEFAULT 0,
                error_count BIGINT DEFAULT 0,
                remaining_items BIGINT DEFAULT 0,
                stop_requested BOOLEAN DEFAULT FALSE,
                stop_reason TEXT,
                last_error TEXT
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_index_runs_status ON index_runs(status)",
            "CREATE INDEX IF NOT EXISTS idx_index_runs_started_at ON index_runs(started_at DESC)",
        ]

        for sql in statements:
            with self.connection.cursor() as cursor:
                cursor.execute(sql)

        self.connection.commit()

    def recover_stale_runs(self) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE index_runs
                   SET status = 'INTERRUPTED',
                       finished_at = COALESCE(finished_at, NOW()),
                       stop_reason = COALESCE(stop_reason, 'process interrupted or application closed'),
                       remaining_items = GREATEST(
                           COALESCE(total_items, 0) - COALESCE(completed_items, 0) - COALESCE(skipped_items, 0),
                           0
                       )
                 WHERE status = 'RUNNING'
                """
            )
        self.connection.commit()

    def create_run(self) -> None:
        import uuid

        self.run_uuid = str(uuid.uuid4())
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO index_runs (
                    run_uuid,
                    started_at,
                    status,
                    selected_stages
                )
                VALUES (%s, %s, 'RUNNING', %s)
                RETURNING id
                """,
                (
                    self.run_uuid,
                    self.now(),
                    self.json_value(self.stages),
                ),
            )
            self.run_id = cursor.fetchone()[0]
        self.connection.commit()

    def update_run(self, **fields: Any) -> None:
        if not fields or self.run_id is None:
            return

        allowed = {
            "status",
            "finished_at",
            "current_stage",
            "current_item_key",
            "current_item_name",
            "current_item_path",
            "current_item_started_at",
            "total_items",
            "completed_items",
            "skipped_items",
            "error_count",
            "remaining_items",
            "stop_requested",
            "stop_reason",
            "last_error",
        }

        fields = {
            key: value
            for key, value in fields.items()
            if key in allowed
        }

        if not fields:
            return

        assignments = []
        params: list[Any] = []
        for key, value in fields.items():
            assignments.append(f"{key} = %s")
            params.append(value)

        params.append(self.run_id)

        with self.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE index_runs SET "
                + ", ".join(assignments)
                + " WHERE id = %s",
                tuple(params),
            )

        self.connection.commit()

    def finish_run(self, status: str, stop_reason: str | None = None) -> None:
        self.update_run(
            status=status,
            finished_at=self.now(),
            stop_reason=stop_reason,
            current_item_key=self.current_item_key,
            current_item_name=self.current_item_name,
            current_item_path=self.current_item_path,
        )

    # ------------------------------------------------------------------
    # Candidate discovery
    # ------------------------------------------------------------------

    def relative_key(self, path: Path) -> str:
        try:
            relative = path.resolve().relative_to(PROJECT_ROOT.resolve())
            return relative.as_posix()
        except Exception:
            return str(path.resolve())

    def iter_gmail_messages(self) -> Iterable[Path]:
        if not GMAIL_ROOT.exists():
            return []

        return (
            path
            for path in GMAIL_ROOT.rglob("*.eml")
            if path.is_file()
            and not any(part.startswith(".") for part in path.parts)
        )

    def iter_document_files(self) -> Iterable[Path]:
        seen: set[str] = set()
        files: list[Path] = []

        for root in REPOSITORY_DOCUMENT_ROOTS:
            if not root.exists():
                continue

            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if any(part.startswith(".") for part in path.parts):
                    continue
                if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue

                resolved = str(path.resolve())
                if resolved in seen:
                    continue
                seen.add(resolved)
                files.append(path)

        files.sort(key=lambda item: str(item).lower())
        return files

    def sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def stat_metadata(self, path: Path) -> dict[str, Any]:
        stat = path.stat()
        return {
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(
                stat.st_mtime,
                timezone.utc,
            ),
            "created_at": datetime.fromtimestamp(
                stat.st_ctime,
                timezone.utc,
            ),
        }

    # ------------------------------------------------------------------
    # DB lookup / upsert
    # ------------------------------------------------------------------

    def json_value(self, value: Any) -> Any:
        if Json is not None:
            return Json(value, dumps=lambda data: json.dumps(data, ensure_ascii=False, default=str))
        return json.dumps(value, ensure_ascii=False, default=str)

    def get_existing(self, source_key: str) -> dict[str, Any] | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    source_hash,
                    content_hash,
                    extraction_status,
                    extractor_version,
                    ai_content_hash,
                    ai_status
                FROM document_index
                WHERE source_key = %s
                LIMIT 1
                """,
                (source_key,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "source_hash": row[1],
            "content_hash": row[2],
            "extraction_status": row[3],
            "extractor_version": row[4],
            "ai_content_hash": row[5],
            "ai_status": row[6],
        }

    def upsert_document(
        self,
        *,
        source_type: str,
        source_key: str,
        parent_source_key: str | None,
        name: str,
        file_path: str,
        mime_type: str,
        extension: str,
        size_bytes: int,
        modified_at: datetime,
        source_hash: str,
        content_text: str,
        extraction_status: str,
        extraction_method: str,
        extraction_error: str | None,
        metadata: dict[str, Any],
    ) -> None:
        content_hash = hashlib.sha256(
            content_text.encode("utf-8")
        ).hexdigest()

        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO document_index (
                    source_type,
                    source_key,
                    parent_source_key,
                    name,
                    file_path,
                    mime_type,
                    extension,
                    size_bytes,
                    modified_at,
                    source_hash,
                    content_hash,
                    content_text,
                    search_vector,
                    extraction_status,
                    extraction_method,
                    extraction_error,
                    extractor_version,
                    metadata,
                    indexed_at,
                    updated_at,
                    ai_status,
                    ai_indexed_at,
                    ai_content_hash,
                    ai_provider,
                    ai_model,
                    ai_text,
                    ai_embedding
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s,
                    to_tsvector(
                        'simple',
                        COALESCE(%s, '') || ' ' ||
                        COALESCE(%s, '')
                    ),
                    %s, %s, %s, %s, %s,
                    NOW(), NOW(),
                    'PENDING', NULL, NULL, NULL, NULL, NULL, NULL
                )
                ON CONFLICT (source_key)
                DO UPDATE SET
                    parent_source_key = EXCLUDED.parent_source_key,
                    name = EXCLUDED.name,
                    file_path = EXCLUDED.file_path,
                    mime_type = EXCLUDED.mime_type,
                    extension = EXCLUDED.extension,
                    size_bytes = EXCLUDED.size_bytes,
                    modified_at = EXCLUDED.modified_at,
                    source_hash = EXCLUDED.source_hash,
                    content_hash = EXCLUDED.content_hash,
                    content_text = EXCLUDED.content_text,
                    search_vector = EXCLUDED.search_vector,
                    extraction_status = EXCLUDED.extraction_status,
                    extraction_method = EXCLUDED.extraction_method,
                    extraction_error = EXCLUDED.extraction_error,
                    extractor_version = EXCLUDED.extractor_version,
                    metadata = EXCLUDED.metadata,
                    indexed_at = NOW(),
                    updated_at = NOW(),
                    ai_status = CASE
                        WHEN document_index.content_hash IS DISTINCT FROM EXCLUDED.content_hash
                            THEN 'PENDING'
                        ELSE document_index.ai_status
                    END,
                    ai_indexed_at = CASE
                        WHEN document_index.content_hash IS DISTINCT FROM EXCLUDED.content_hash
                            THEN NULL
                        ELSE document_index.ai_indexed_at
                    END,
                    ai_content_hash = CASE
                        WHEN document_index.content_hash IS DISTINCT FROM EXCLUDED.content_hash
                            THEN NULL
                        ELSE document_index.ai_content_hash
                    END,
                    ai_provider = CASE
                        WHEN document_index.content_hash IS DISTINCT FROM EXCLUDED.content_hash
                            THEN NULL
                        ELSE document_index.ai_provider
                    END,
                    ai_model = CASE
                        WHEN document_index.content_hash IS DISTINCT FROM EXCLUDED.content_hash
                            THEN NULL
                        ELSE document_index.ai_model
                    END,
                    ai_text = CASE
                        WHEN document_index.content_hash IS DISTINCT FROM EXCLUDED.content_hash
                            THEN NULL
                        ELSE document_index.ai_text
                    END,
                    ai_embedding = CASE
                        WHEN document_index.content_hash IS DISTINCT FROM EXCLUDED.content_hash
                            THEN NULL
                        ELSE document_index.ai_embedding
                    END
                """,
                (
                    source_type,
                    source_key,
                    parent_source_key,
                    name,
                    file_path,
                    mime_type,
                    extension,
                    size_bytes,
                    modified_at,
                    source_hash,
                    content_hash,
                    content_text,
                    name,
                    content_text,
                    extraction_status,
                    extraction_method,
                    extraction_error,
                    EXTRACTOR_VERSION,
                    self.json_value(metadata),
                ),
            )

        self.connection.commit()

    def mark_ai_result(
        self,
        document_id: int,
        content_hash: str,
        provider: str,
        model: str,
        ai_text: str,
        embedding: list[float],
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE document_index
                   SET ai_status = 'COMPLETED',
                       ai_indexed_at = NOW(),
                       ai_content_hash = %s,
                       ai_provider = %s,
                       ai_model = %s,
                       ai_text = %s,
                       ai_embedding = %s,
                       updated_at = NOW()
                 WHERE id = %s
                """,
                (
                    content_hash,
                    provider,
                    model,
                    ai_text,
                    self.json_value(embedding),
                    document_id,
                ),
            )
        self.connection.commit()

    def mark_ai_error(
        self,
        document_id: int,
        error_message: str,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE document_index
                   SET ai_status = 'ERROR',
                       ai_indexed_at = NULL,
                       updated_at = NOW()
                 WHERE id = %s
                """,
                (document_id,),
            )
        self.connection.commit()

        self.update_run(last_error=error_message)

    # ------------------------------------------------------------------
    # Mail indexing
    # ------------------------------------------------------------------

    def index_mail_file(self, path: Path) -> str:
        source_key = "gmail:message:" + self.relative_key(path)
        source_hash = self.sha256_file(path)
        existing = self.get_existing(source_key)

        if (
            existing
            and existing["source_hash"] == source_hash
            and existing["extractor_version"] == EXTRACTOR_VERSION
            and existing["extraction_status"] == "SUCCESS"
        ):
            self.stage_stats["mails"]["skipped"] += 1
            return "SKIPPED"

        stat = self.stat_metadata(path)
        extracted = extract_document(path)
        email = extracted.get("email") or {}
        metadata = dict(extracted.get("metadata") or {})
        metadata["repository"] = "Gmail"
        metadata["storage_relative_path"] = self.relative_key(path)
        metadata["raw_size"] = email.get("raw_size", stat["size_bytes"])

        self.upsert_document(
            source_type="GMAIL_MESSAGE",
            source_key=source_key,
            parent_source_key=None,
            name=path.name,
            file_path=str(path.resolve()),
            mime_type=extracted.get("mime_type") or "message/rfc822",
            extension=path.suffix.lower(),
            size_bytes=stat["size_bytes"],
            modified_at=stat["modified_at"],
            source_hash=source_hash,
            content_text=extracted.get("text") or "",
            extraction_status=extracted.get("status") or "SUCCESS",
            extraction_method=extracted.get("method") or "email-mime",
            extraction_error=extracted.get("error"),
            metadata=metadata,
        )

        for attachment in email.get("attachments", []):
            self.index_mail_attachment(
                parent_source_key=source_key,
                message_path=path,
                attachment=attachment,
            )

        self.stage_stats["mails"]["processed"] += 1
        return "INDEXED"

    def index_mail_attachment(
        self,
        *,
        parent_source_key: str,
        message_path: Path,
        attachment: dict[str, Any],
    ) -> None:
        data = attachment.get("bytes") or b""
        file_name = str(attachment.get("file_name") or "attachment")
        attachment_hash = hashlib.sha256(data).hexdigest()
        source_key = (
            parent_source_key
            + ":attachment:"
            + str(attachment.get("part_number", 0))
            + ":"
            + file_name
            + ":"
            + attachment_hash
        )

        existing = self.get_existing(source_key)
        if (
            existing
            and existing["source_hash"] == attachment_hash
            and existing["extractor_version"] == EXTRACTOR_VERSION
            and existing["extraction_status"] in {"SUCCESS", "UNSUPPORTED"}
        ):
            return

        suffix = Path(file_name).suffix.lower()
        temp_root = PROJECT_ROOT / "storage" / ".index_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        temp_path = temp_root / (attachment_hash + (suffix or ".bin"))

        try:
            temp_path.write_bytes(data)
            extracted = extract_document(temp_path)

            metadata = dict(attachment.get("metadata") or {})
            metadata.update(
                {
                    "repository": "Gmail",
                    "parent_message": str(message_path.resolve()),
                    "attachment_hash": attachment_hash,
                }
            )

            self.upsert_document(
                source_type="GMAIL_ATTACHMENT",
                source_key=source_key,
                parent_source_key=parent_source_key,
                name=file_name,
                file_path=str(message_path.resolve()),
                mime_type=str(attachment.get("mime_type") or mimetypes.guess_type(file_name)[0] or "application/octet-stream"),
                extension=suffix,
                size_bytes=len(data),
                modified_at=self.stat_metadata(message_path)["modified_at"],
                source_hash=attachment_hash,
                content_text=extracted.get("text") or "",
                extraction_status=extracted.get("status") or "SUCCESS",
                extraction_method=extracted.get("method") or "attachment",
                extraction_error=extracted.get("error"),
                metadata=metadata,
            )
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Generic document indexing
    # ------------------------------------------------------------------

    def document_source_type(self, path: Path) -> str:
        try:
            relative = path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix().lower()
        except Exception:
            relative = str(path).lower()

        if relative.startswith("storage/drive/"):
            return "GOOGLE_DRIVE_DOCUMENT"
        if relative.startswith("storage/office/"):
            return "LOCAL_OFFICE_DOCUMENT"
        if relative.startswith("storage/documents/"):
            return "LOCAL_DOCUMENT"
        return "LOCAL_DOCUMENT"

    def index_document_file(self, path: Path) -> str:
        source_key = "document:" + self.relative_key(path)
        source_hash = self.sha256_file(path)
        existing = self.get_existing(source_key)

        if (
            existing
            and existing["source_hash"] == source_hash
            and existing["extractor_version"] == EXTRACTOR_VERSION
            and existing["extraction_status"] in {"SUCCESS", "UNSUPPORTED"}
        ):
            self.stage_stats["documents"]["skipped"] += 1
            return "SKIPPED"

        stat = self.stat_metadata(path)
        extracted = extract_document(path)

        metadata = dict(extracted.get("metadata") or {})
        metadata["repository"] = self.document_source_type(path)
        metadata["storage_relative_path"] = self.relative_key(path)
        metadata["name"] = path.name
        metadata["extension"] = path.suffix.lower()

        self.upsert_document(
            source_type=self.document_source_type(path),
            source_key=source_key,
            parent_source_key=None,
            name=path.name,
            file_path=str(path.resolve()),
            mime_type=extracted.get("mime_type") or mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            extension=path.suffix.lower(),
            size_bytes=stat["size_bytes"],
            modified_at=stat["modified_at"],
            source_hash=source_hash,
            content_text=extracted.get("text") or "",
            extraction_status=extracted.get("status") or "SUCCESS",
            extraction_method=extracted.get("method") or "unknown",
            extraction_error=extracted.get("error"),
            metadata=metadata,
        )

        self.stage_stats["documents"]["processed"] += 1
        return "INDEXED"

    # ------------------------------------------------------------------
    # AI / semantic indexing
    # ------------------------------------------------------------------

    def load_ai_engine(self):
        provider = os.environ.get("ALCALAY_AI_PROVIDER", "auto").strip().lower()
        model = os.environ.get("ALCALAY_AI_MODEL", "nomic-embed-text").strip()

        if provider in {"auto", "ollama"}:
            try:
                engine = OllamaEmbeddingEngine(model)
                engine.probe()
                return engine
            except Exception:
                if provider == "ollama":
                    raise

        if provider in {"auto", "sentence-transformers", "sentence_transformers", "st"}:
            try:
                engine = SentenceTransformerEmbeddingEngine(model)
                engine.probe()
                return engine
            except Exception:
                if provider != "auto":
                    raise

        raise RuntimeError(
            "לא נמצא מנוע AI סמנטי זמין. "
            "הגדר ALCALAY_AI_PROVIDER=ollama והפעל מודל embedding מקומי, "
            "או התקן sentence-transformers ומודל מקומי."
        )

    def iter_ai_documents(self) -> list[dict[str, Any]]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    source_key,
                    name,
                    file_path,
                    content_hash,
                    content_text
                FROM document_index
                WHERE extraction_status = 'SUCCESS'
                  AND content_text IS NOT NULL
                  AND LENGTH(BTRIM(content_text)) > 0
                  AND (
                      ai_indexed_at IS NULL
                      OR ai_content_hash IS DISTINCT FROM content_hash
                      OR ai_status <> 'COMPLETED'
                  )
                ORDER BY id
                """
            )
            rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "source_key": row[1],
                "name": row[2],
                "file_path": row[3],
                "content_hash": row[4],
                "content_text": row[5],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Stage execution
    # ------------------------------------------------------------------

    def run_file_stage(
        self,
        stage: str,
        candidates: list[Path],
        handler,
    ) -> bool:
        stats = self.stage_stats[stage]
        stats["total"] = len(candidates)
        stats["remaining"] = len(candidates)

        self.current_stage = stage
        self.update_run(
            current_stage=stage,
            total_items=stats["total"],
            completed_items=0,
            skipped_items=0,
            error_count=0,
            remaining_items=stats["remaining"],
        )

        self.emit(
            "STAGE_START",
            stage=stage,
            total=stats["total"],
            completed=0,
            skipped=0,
            remaining=stats["remaining"],
        )

        for index, path in enumerate(candidates, start=1):
            if self.stop_event.is_set():
                self.update_run(
                    status="STOPPED",
                    stop_requested=True,
                    stop_reason="user requested stop",
                    remaining_items=stats["remaining"],
                )
                self.emit(
                    "STOPPED",
                    stage=stage,
                    current_item_key=self.current_item_key,
                    current_item_name=self.current_item_name,
                    current_item_path=self.current_item_path,
                    completed=stats["processed"],
                    skipped=stats["skipped"],
                    remaining=stats["remaining"],
                )
                return False

            source_key = (
                ("gmail:message:" if stage == "mails" else "document:")
                + self.relative_key(path)
            )
            self.current_item_key = source_key
            self.current_item_name = path.name
            self.current_item_path = str(path.resolve())

            self.update_run(
                current_stage=stage,
                current_item_key=source_key,
                current_item_name=path.name,
                current_item_path=str(path.resolve()),
                current_item_started_at=self.now(),
                remaining_items=stats["remaining"],
            )

            self.emit(
                "ITEM_START",
                stage=stage,
                index=index,
                total=stats["total"],
                source_key=source_key,
                name=path.name,
                path=str(path.resolve()),
                completed=stats["processed"],
                skipped=stats["skipped"],
                remaining=stats["remaining"],
            )

            try:
                result = handler(path)
                if result == "SKIPPED":
                    stats["skipped"] += 1
                else:
                    stats["processed"] += 1

                stats["remaining"] = max(
                    0,
                    stats["total"] - stats["processed"] - stats["skipped"],
                )

                # Advance the durable checkpoint to the next unprocessed file.
                next_path = candidates[index] if index < len(candidates) else None
                if next_path is None:
                    self.current_item_key = None
                    self.current_item_name = None
                    self.current_item_path = None
                else:
                    self.current_item_key = (
                        ("gmail:message:" if stage == "mails" else "document:")
                        + self.relative_key(next_path)
                    )
                    self.current_item_name = next_path.name
                    self.current_item_path = str(next_path.resolve())

                self.update_run(
                    current_stage=stage,
                    current_item_key=self.current_item_key,
                    current_item_name=self.current_item_name,
                    current_item_path=self.current_item_path,
                    completed_items=stats["processed"],
                    skipped_items=stats["skipped"],
                    remaining_items=stats["remaining"],
                )

                self.emit(
                    "ITEM_FINISH",
                    stage=stage,
                    index=index,
                    total=stats["total"],
                    result=result,
                    source_key=source_key,
                    name=path.name,
                    completed=stats["processed"],
                    skipped=stats["skipped"],
                    remaining=stats["remaining"],
                )

            except Exception as exc:
                stats["errors"] += 1
                stats["remaining"] = max(
                    0,
                    stats["total"] - stats["processed"] - stats["skipped"],
                )
                self.update_run(
                    current_stage=stage,
                    current_item_key=source_key,
                    current_item_name=path.name,
                    current_item_path=str(path.resolve()),
                    completed_items=stats["processed"],
                    skipped_items=stats["skipped"],
                    error_count=stats["errors"],
                    remaining_items=stats["remaining"],
                    last_error=f"{type(exc).__name__}: {exc}",
                )

                self.emit(
                    "ITEM_ERROR",
                    stage=stage,
                    index=index,
                    total=stats["total"],
                    source_key=source_key,
                    name=path.name,
                    path=str(path.resolve()),
                    error=f"{type(exc).__name__}: {exc}",
                    error_count=stats["errors"],
                    completed=stats["processed"],
                    skipped=stats["skipped"],
                    remaining=stats["remaining"],
                )

                # Continue with the next file. The failed file remains
                # eligible for retry because its extraction status is ERROR
                # or it has no successful checkpoint.

        self.emit(
            "STAGE_FINISH",
            stage=stage,
            total=stats["total"],
            completed=stats["processed"],
            skipped=stats["skipped"],
            errors=stats["errors"],
            remaining=stats["remaining"],
        )
        return True

    def run_ai_stage(self) -> bool:
        rows = self.iter_ai_documents()
        stats = self.stage_stats["ai"]
        stats["total"] = len(rows)
        stats["remaining"] = len(rows)

        self.current_stage = "ai"
        self.update_run(
            current_stage="ai",
            total_items=stats["total"],
            completed_items=0,
            skipped_items=0,
            error_count=0,
            remaining_items=stats["remaining"],
        )

        self.emit(
            "STAGE_START",
            stage="ai",
            total=stats["total"],
            completed=0,
            skipped=0,
            remaining=stats["remaining"],
        )

        if not rows:
            self.emit(
                "STAGE_FINISH",
                stage="ai",
                total=0,
                completed=0,
                skipped=0,
                errors=0,
                remaining=0,
            )
            return True

        engine = self.load_ai_engine()

        for index, row in enumerate(rows, start=1):
            if self.stop_event.is_set():
                self.update_run(
                    status="STOPPED",
                    stop_requested=True,
                    stop_reason="user requested stop",
                    remaining_items=stats["remaining"],
                )
                self.emit(
                    "STOPPED",
                    stage="ai",
                    current_item_key=self.current_item_key,
                    current_item_name=self.current_item_name,
                    current_item_path=self.current_item_path,
                    completed=stats["processed"],
                    skipped=stats["skipped"],
                    remaining=stats["remaining"],
                )
                return False

            self.current_item_key = row["source_key"]
            self.current_item_name = row["name"] or ""
            self.current_item_path = row["file_path"] or ""

            self.update_run(
                current_stage="ai",
                current_item_key=self.current_item_key,
                current_item_name=self.current_item_name,
                current_item_path=self.current_item_path,
                current_item_started_at=self.now(),
                remaining_items=stats["remaining"],
            )

            self.emit(
                "ITEM_START",
                stage="ai",
                index=index,
                total=stats["total"],
                source_key=row["source_key"],
                name=row["name"] or "",
                path=row["file_path"] or "",
                completed=stats["processed"],
                skipped=stats["skipped"],
                remaining=stats["remaining"],
            )

            try:
                embedding = engine.embed(row["content_text"])
                ai_text = engine.describe(row["content_text"])
                self.mark_ai_result(
                    document_id=row["id"],
                    content_hash=row["content_hash"],
                    provider=engine.provider,
                    model=engine.model,
                    ai_text=ai_text,
                    embedding=embedding,
                )

                stats["processed"] += 1
                stats["remaining"] = max(
                    0,
                    stats["total"] - stats["processed"] - stats["skipped"],
                )

                self.current_item_key = None
                self.current_item_name = None
                self.current_item_path = None
                if index < len(rows):
                    next_row = rows[index]
                    self.current_item_key = next_row["source_key"]
                    self.current_item_name = next_row["name"] or ""
                    self.current_item_path = next_row["file_path"] or ""

                self.update_run(
                    current_stage="ai",
                    current_item_key=self.current_item_key,
                    current_item_name=self.current_item_name,
                    current_item_path=self.current_item_path,
                    completed_items=stats["processed"],
                    skipped_items=stats["skipped"],
                    remaining_items=stats["remaining"],
                )

                self.emit(
                    "ITEM_FINISH",
                    stage="ai",
                    index=index,
                    total=stats["total"],
                    result="AI_INDEXED",
                    source_key=row["source_key"],
                    name=row["name"] or "",
                    completed=stats["processed"],
                    skipped=stats["skipped"],
                    remaining=stats["remaining"],
                    provider=engine.provider,
                    model=engine.model,
                )

            except Exception as exc:
                stats["errors"] += 1
                stats["remaining"] = max(
                    0,
                    stats["total"] - stats["processed"] - stats["skipped"],
                )
                self.mark_ai_error(row["id"], f"{type(exc).__name__}: {exc}")

                self.update_run(
                    current_stage="ai",
                    current_item_key=row["source_key"],
                    current_item_name=row["name"] or "",
                    current_item_path=row["file_path"] or "",
                    error_count=stats["errors"],
                    remaining_items=stats["remaining"],
                    last_error=f"{type(exc).__name__}: {exc}",
                )

                self.emit(
                    "ITEM_ERROR",
                    stage="ai",
                    index=index,
                    total=stats["total"],
                    source_key=row["source_key"],
                    name=row["name"] or "",
                    path=row["file_path"] or "",
                    error=f"{type(exc).__name__}: {exc}",
                    error_count=stats["errors"],
                    completed=stats["processed"],
                    skipped=stats["skipped"],
                    remaining=stats["remaining"],
                )

        self.emit(
            "STAGE_FINISH",
            stage="ai",
            total=stats["total"],
            completed=stats["processed"],
            skipped=stats["skipped"],
            errors=stats["errors"],
            remaining=stats["remaining"],
        )
        return True

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(self) -> int:
        if not self.stages:
            raise ValueError("No indexing stages selected.")

        try:
            self.connect_database()
            self.create_run()
            self.start_stop_listener()

            self.emit(
                "RUN_START",
                run_id=self.run_id,
                run_uuid=self.run_uuid,
                stages=self.stages,
            )

            for stage in self.stages:
                if self.stop_event.is_set():
                    self.finish_run(
                        "STOPPED",
                        "user requested stop",
                    )
                    self.emit(
                        "RUN_FINISH",
                        status="STOPPED",
                        run_id=self.run_id,
                        current_stage=self.current_stage,
                        current_item_key=self.current_item_key,
                        current_item_name=self.current_item_name,
                        current_item_path=self.current_item_path,
                    )
                    return 0

                if stage == "mails":
                    candidates = sorted(
                        list(self.iter_gmail_messages()),
                        key=lambda item: str(item).lower(),
                    )
                    ok = self.run_file_stage(
                        "mails",
                        candidates,
                        self.index_mail_file,
                    )
                elif stage == "documents":
                    candidates = list(self.iter_document_files())
                    ok = self.run_file_stage(
                        "documents",
                        candidates,
                        self.index_document_file,
                    )
                else:
                    ok = self.run_ai_stage()

                if not ok:
                    self.finish_run(
                        "STOPPED",
                        "user requested stop",
                    )
                    self.emit(
                        "RUN_FINISH",
                        status="STOPPED",
                        run_id=self.run_id,
                        current_stage=self.current_stage,
                        current_item_key=self.current_item_key,
                        current_item_name=self.current_item_name,
                        current_item_path=self.current_item_path,
                    )
                    return 0

            total_processed = sum(
                item["processed"]
                for item in self.stage_stats.values()
            )
            total_skipped = sum(
                item["skipped"]
                for item in self.stage_stats.values()
            )
            total_errors = sum(
                item["errors"]
                for item in self.stage_stats.values()
            )
            total_remaining = sum(
                item["remaining"]
                for item in self.stage_stats.values()
            )

            status = "COMPLETED" if total_errors == 0 else "COMPLETED_WITH_ERRORS"
            self.update_run(
                status=status,
                finished_at=self.now(),
                current_stage=None,
                current_item_key=None,
                current_item_name=None,
                current_item_path=None,
                total_items=total_processed + total_skipped + total_remaining,
                completed_items=total_processed,
                skipped_items=total_skipped,
                error_count=total_errors,
                remaining_items=total_remaining,
            )

            self.emit(
                "RUN_FINISH",
                status=status,
                run_id=self.run_id,
                processed=total_processed,
                skipped=total_skipped,
                errors=total_errors,
                remaining=total_remaining,
            )
            return 0 if total_errors == 0 else 1

        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
            try:
                if self.connection is not None:
                    self.connection.rollback()
                    self.update_run(
                        status="ERROR",
                        finished_at=self.now(),
                        last_error=error_message,
                        current_stage=self.current_stage,
                        current_item_key=self.current_item_key,
                        current_item_name=self.current_item_name,
                        current_item_path=self.current_item_path,
                    )
            except Exception:
                pass

            self.emit(
                "RUN_ERROR",
                status="ERROR",
                run_id=self.run_id,
                error=error_message,
                current_stage=self.current_stage,
                current_item_key=self.current_item_key,
                current_item_name=self.current_item_name,
                current_item_path=self.current_item_path,
            )
            return 1
        finally:
            if self.connection is not None:
                self.connection.close()
                self.connection = None


class OllamaEmbeddingEngine:
    provider = "ollama"

    def __init__(self, model: str) -> None:
        self.model = model or "nomic-embed-text"
        self.base_url = os.environ.get(
            "ALCALAY_OLLAMA_URL",
            "http://127.0.0.1:11434",
        ).rstrip("/")

    def _request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))

    def probe(self) -> None:
        self.embed("health check")

    def embed(self, text: str) -> list[float]:
        payload = {
            "model": self.model,
            "input": text[:12000],
        }

        try:
            response = self._request("/api/embed", payload)
            embeddings = response.get("embeddings")
            if embeddings and embeddings[0]:
                return [float(value) for value in embeddings[0]]
        except Exception:
            pass

        response = self._request(
            "/api/embeddings",
            {
                "model": self.model,
                "prompt": text[:12000],
            },
        )
        embedding = response.get("embedding")
        if not embedding:
            raise RuntimeError("Ollama returned no embedding.")
        return [float(value) for value in embedding]

    def describe(self, text: str) -> str:
        # Keep AI text compact; the semantic signal is stored in the embedding.
        words = normalize_text(text).split()
        return " ".join(words[:120])


class SentenceTransformerEmbeddingEngine:
    provider = "sentence-transformers"

    def __init__(self, model: str) -> None:
        self.model = model or "all-MiniLM-L6-v2"
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model)
        return self._model

    def probe(self) -> None:
        self.embed("health check")

    def embed(self, text: str) -> list[float]:
        model = self._load()
        vector = model.encode(
            text[:12000],
            normalize_embeddings=True,
        )
        return [float(value) for value in vector.tolist()]

    def describe(self, text: str) -> str:
        words = normalize_text(text).split()
        return " ".join(words[:120])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Alcalay unified document indexer")
    parser.add_argument(
        "--stages",
        nargs="+",
        required=True,
        choices=["mails", "documents", "ai"],
        help="Index stages to execute",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return UnifiedIndexer(args.stages).run()


if __name__ == "__main__":
    raise SystemExit(main())
