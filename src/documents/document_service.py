import hashlib
import mimetypes
from datetime import datetime
from pathlib import Path

from src.database.database_manager import DatabaseManager


class DocumentService:

    def __init__(self, database_manager=None):

        if database_manager is None:
            database_manager = DatabaseManager()

        self.db = database_manager

    def calculate_hash(self, file_path):

        sha256 = hashlib.sha256()

        with open(file_path, "rb") as file:

            while True:
                data = file.read(1024 * 1024)

                if not data:
                    break

                sha256.update(data)

        return sha256.hexdigest()

    def get_file_information(self, file_path):

        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(str(path))

        if not path.is_file():
            raise ValueError("Path is not a file")

        stat = path.stat()

        mime_type, _ = mimetypes.guess_type(path.name)

        return {
            "path": str(path.resolve()),
            "file_name": path.name,
            "extension": path.suffix.lower(),
            "file_size": stat.st_size,
            "mime_type": mime_type or "application/octet-stream",
            "modified_at": datetime.fromtimestamp(stat.st_mtime),
            "content_hash": self.calculate_hash(path)
        }

    def find_by_hash(self, content_hash):

        query = """
            SELECT
                id,
                title,
                file_name,
                content_hash,
                status
            FROM documents
            WHERE content_hash = %s
            AND status <> 'DELETED'
            ORDER BY id
            LIMIT 1
        """

        return self.db.fetch_one(
            query,
            (content_hash,)
        )

    def add_document(self, file_path, title=None):

        information = self.get_file_information(file_path)

        existing = self.find_by_hash(
            information["content_hash"]
        )

        if existing is not None:
            return {
                "status": "already_exists",
                "document": existing
            }

        if title is None:
            title = Path(
                information["file_name"]
            ).stem

        connection = self.db.database_connection.connect()

        try:

            cursor = connection.cursor()

            try:

                document_query = """
                    INSERT INTO documents (
                        title,
                        file_name,
                        mime_type,
                        file_extension,
                        file_size,
                        content_hash,
                        modified_at_source,
                        status
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        'ACTIVE'
                    )
                    RETURNING id
                """

                cursor.execute(
                    document_query,
                    (
                        title,
                        information["file_name"],
                        information["mime_type"],
                        information["extension"],
                        information["file_size"],
                        information["content_hash"],
                        information["modified_at"]
                    )
                )

                document_id = cursor.fetchone()[0]

                local_file_query = """
                    INSERT INTO local_files (
                        document_id,
                        local_path,
                        file_name,
                        file_size,
                        content_hash,
                        exists_locally,
                        first_downloaded_at,
                        last_verified_at
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        TRUE,
                        NOW(),
                        NOW()
                    )
                    RETURNING id
                """

                cursor.execute(
                    local_file_query,
                    (
                        document_id,
                        information["path"],
                        information["file_name"],
                        information["file_size"],
                        information["content_hash"]
                    )
                )

                local_file_id = cursor.fetchone()[0]

                connection.commit()

            except Exception:

                connection.rollback()
                raise

            finally:

                cursor.close()

        finally:

            connection.close()

        return {
            "status": "added",
            "document_id": document_id,
            "local_file_id": local_file_id,
            "content_hash": information["content_hash"]
        }