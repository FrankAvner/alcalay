import hashlib
import mimetypes
from datetime import datetime
from pathlib import Path

from src.database.database_manager import DatabaseManager


class DocumentService:

    LOCAL_SOURCE_TYPE_CODE = "LOCAL"
    LOCAL_SOURCE_NAME = "Local Folder"
    LOCAL_SOURCE_LOCATION_TYPE = "FOLDER"

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
            "modified_at": datetime.fromtimestamp(
                stat.st_mtime
            ).astimezone(),
            "content_hash": self.calculate_hash(path),
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
            (content_hash,),
        )

    def find_document_by_hash_cursor(self, cursor, content_hash):
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

        cursor.execute(
            query,
            (content_hash,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "id": row[0],
            "title": row[1],
            "file_name": row[2],
            "content_hash": row[3],
            "status": row[4],
        }

    def find_local_source(self, cursor):
        query = """
            SELECT
                s.id,
                s.source_type_id,
                s.name,
                s.enabled,
                s.description
            FROM sources s
            JOIN source_types st
                ON st.id = s.source_type_id
            WHERE st.code = %s
              AND s.name = %s
            ORDER BY s.id
            LIMIT 1
        """

        cursor.execute(
            query,
            (
                self.LOCAL_SOURCE_TYPE_CODE,
                self.LOCAL_SOURCE_NAME,
            ),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "id": row[0],
            "source_type_id": row[1],
            "name": row[2],
            "enabled": row[3],
            "description": row[4],
        }

    def get_or_create_local_source(self, cursor):
        source = self.find_local_source(cursor)

        if source is not None:
            return source

        source_type_query = """
            SELECT
                id,
                code,
                name
            FROM source_types
            WHERE code = %s
            LIMIT 1
        """

        cursor.execute(
            source_type_query,
            (self.LOCAL_SOURCE_TYPE_CODE,),
        )

        source_type = cursor.fetchone()

        if source_type is None:
            raise ValueError(
                "LOCAL source type does not exist in source_types"
            )

        source_query = """
            INSERT INTO sources (
                source_type_id,
                name,
                enabled,
                description,
                configuration
            )
            VALUES (
                %s,
                %s,
                TRUE,
                %s,
                '{}'::jsonb
            )
            RETURNING
                id,
                source_type_id,
                name,
                enabled,
                description
        """

        cursor.execute(
            source_query,
            (
                source_type[0],
                self.LOCAL_SOURCE_NAME,
                "Local filesystem source",
            ),
        )

        row = cursor.fetchone()

        return {
            "id": row[0],
            "source_type_id": row[1],
            "name": row[2],
            "enabled": row[3],
            "description": row[4],
        }

    def find_local_source_location(
        self,
        cursor,
        source_id,
        local_directory,
    ):
        query = """
            SELECT
                id,
                source_id,
                account_id,
                parent_location_id,
                external_id,
                name,
                location_type,
                local_path,
                selected_for_sync,
                enabled
            FROM source_locations
            WHERE source_id = %s
              AND local_path = %s
            ORDER BY id
            LIMIT 1
        """

        cursor.execute(
            query,
            (
                source_id,
                local_directory,
            ),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "id": row[0],
            "source_id": row[1],
            "account_id": row[2],
            "parent_location_id": row[3],
            "external_id": row[4],
            "name": row[5],
            "location_type": row[6],
            "local_path": row[7],
            "selected_for_sync": row[8],
            "enabled": row[9],
        }

    def get_or_create_local_source_location(
        self,
        cursor,
        source_id,
        local_directory,
    ):
        location = self.find_local_source_location(
            cursor,
            source_id,
            local_directory,
        )

        if location is not None:
            return location

        directory = Path(local_directory)

        query = """
            INSERT INTO source_locations (
                source_id,
                external_id,
                name,
                location_type,
                local_path,
                selected_for_sync,
                enabled,
                metadata
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                TRUE,
                TRUE,
                '{}'::jsonb
            )
            RETURNING
                id,
                source_id,
                account_id,
                parent_location_id,
                external_id,
                name,
                location_type,
                local_path,
                selected_for_sync,
                enabled
        """

        cursor.execute(
            query,
            (
                source_id,
                str(directory),
                directory.name or str(directory),
                self.LOCAL_SOURCE_LOCATION_TYPE,
                str(directory),
            ),
        )

        row = cursor.fetchone()

        return {
            "id": row[0],
            "source_id": row[1],
            "account_id": row[2],
            "parent_location_id": row[3],
            "external_id": row[4],
            "name": row[5],
            "location_type": row[6],
            "local_path": row[7],
            "selected_for_sync": row[8],
            "enabled": row[9],
        }

    def find_local_file(self, cursor, local_path):
        query = """
            SELECT
                id,
                document_id,
                source_location_id,
                local_path,
                file_name,
                file_size,
                content_hash,
                exists_locally
            FROM local_files
            WHERE local_path = %s
            LIMIT 1
        """

        cursor.execute(
            query,
            (local_path,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "id": row[0],
            "document_id": row[1],
            "source_location_id": row[2],
            "local_path": row[3],
            "file_name": row[4],
            "file_size": row[5],
            "content_hash": row[6],
            "exists_locally": row[7],
        }

    def find_document_source(
        self,
        cursor,
        source_id,
        source_item_id,
    ):
        query = """
            SELECT
                id,
                document_id,
                source_id,
                source_location_id,
                source_account_id,
                source_item_id,
                source_path,
                source_name,
                source_hash,
                first_seen_at,
                last_seen_at,
                last_synced_at
            FROM document_sources
            WHERE source_id = %s
              AND source_item_id = %s
            LIMIT 1
        """

        cursor.execute(
            query,
            (
                source_id,
                source_item_id,
            ),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "id": row[0],
            "document_id": row[1],
            "source_id": row[2],
            "source_location_id": row[3],
            "source_account_id": row[4],
            "source_item_id": row[5],
            "source_path": row[6],
            "source_name": row[7],
            "source_hash": row[8],
            "first_seen_at": row[9],
            "last_seen_at": row[10],
            "last_synced_at": row[11],
        }

    def add_document(self, file_path, title=None):
        information = self.get_file_information(file_path)
        local_path = information["path"]

        connection = self.db.database_connection.connect()

        try:
            cursor = connection.cursor()

            try:
                existing_local_file = self.find_local_file(
                    cursor,
                    local_path,
                )

                if (
                    existing_local_file is not None
                    and existing_local_file["content_hash"]
                    == information["content_hash"]
                ):
                    connection.commit()

                    return {
                        "status": "already_exists",
                        "document_id": existing_local_file[
                            "document_id"
                        ],
                        "local_file_id": existing_local_file["id"],
                        "content_hash": information[
                            "content_hash"
                        ],
                    }

                existing_document = self.find_document_by_hash_cursor(
                    cursor,
                    information["content_hash"],
                )

                if existing_document is not None:
                    document_id = existing_document["id"]
                    document_status = "already_exists"
                else:
                    if title is None:
                        title = Path(
                            information["file_name"]
                        ).stem

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
                            information["modified_at"],
                        ),
                    )

                    document_id = cursor.fetchone()[0]
                    document_status = "added"

                local_source = self.get_or_create_local_source(
                    cursor
                )

                local_directory = str(
                    Path(information["path"]).parent
                )

                source_location = (
                    self.get_or_create_local_source_location(
                        cursor,
                        local_source["id"],
                        local_directory,
                    )
                )

                document_source = self.find_document_source(
                    cursor,
                    local_source["id"],
                    local_path,
                )

                if document_source is None:
                    document_source_query = """
                        INSERT INTO document_sources (
                            document_id,
                            source_id,
                            source_location_id,
                            source_item_id,
                            source_path,
                            source_name,
                            source_hash,
                            source_modified_at,
                            first_seen_at,
                            last_seen_at,
                            last_synced_at,
                            metadata
                        )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            NOW(),
                            NOW(),
                            NOW(),
                            '{}'::jsonb
                        )
                        RETURNING id
                    """

                    cursor.execute(
                        document_source_query,
                        (
                            document_id,
                            local_source["id"],
                            source_location["id"],
                            local_path,
                            local_path,
                            information["file_name"],
                            information["content_hash"],
                            information["modified_at"],
                        ),
                    )

                    document_source_id = cursor.fetchone()[0]

                else:
                    document_source_id = document_source["id"]

                    update_source_query = """
                        UPDATE document_sources
                        SET
                            document_id = %s,
                            source_location_id = %s,
                            source_path = %s,
                            source_name = %s,
                            source_hash = %s,
                            source_modified_at = %s,
                            last_seen_at = NOW(),
                            last_synced_at = NOW()
                        WHERE id = %s
                    """

                    cursor.execute(
                        update_source_query,
                        (
                            document_id,
                            source_location["id"],
                            local_path,
                            information["file_name"],
                            information["content_hash"],
                            information["modified_at"],
                            document_source_id,
                        ),
                    )

                local_file = self.find_local_file(
                    cursor,
                    local_path,
                )

                if local_file is None:
                    local_file_query = """
                        INSERT INTO local_files (
                            document_id,
                            source_location_id,
                            local_path,
                            file_name,
                            file_size,
                            content_hash,
                            exists_locally,
                            first_downloaded_at,
                            last_verified_at,
                            metadata
                        )
                        VALUES (
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            %s,
                            TRUE,
                            NOW(),
                            NOW(),
                            '{}'::jsonb
                        )
                        RETURNING id
                    """

                    cursor.execute(
                        local_file_query,
                        (
                            document_id,
                            source_location["id"],
                            local_path,
                            information["file_name"],
                            information["file_size"],
                            information["content_hash"],
                        ),
                    )

                    local_file_id = cursor.fetchone()[0]

                else:
                    local_file_id = local_file["id"]

                    update_local_file_query = """
                        UPDATE local_files
                        SET
                            document_id = %s,
                            source_location_id = %s,
                            file_name = %s,
                            file_size = %s,
                            content_hash = %s,
                            exists_locally = TRUE,
                            last_verified_at = NOW()
                        WHERE id = %s
                    """

                    cursor.execute(
                        update_local_file_query,
                        (
                            document_id,
                            source_location["id"],
                            information["file_name"],
                            information["file_size"],
                            information["content_hash"],
                            local_file_id,
                        ),
                    )

                connection.commit()

            except Exception:
                connection.rollback()
                raise

            finally:
                cursor.close()

        finally:
            connection.close()

        return {
            "status": document_status,
            "document_id": document_id,
            "local_file_id": local_file_id,
            "document_source_id": document_source_id,
            "source_id": local_source["id"],
            "source_location_id": source_location["id"],
            "content_hash": information["content_hash"],
        }