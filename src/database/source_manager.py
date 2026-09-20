from __future__ import annotations

from typing import Any, Optional

from src.database.database_manager import DatabaseManager


class SourceManager:

    def __init__(
        self,
        database_manager: Optional[DatabaseManager] = None,
    ):
        self.database_manager = database_manager or DatabaseManager()

    # ------------------------------------------------------------
    # Source types
    # ------------------------------------------------------------

    def get_source_type(
        self,
        code: str,
    ) -> Optional[dict[str, Any]]:

        query = """
            SELECT
                id,
                code,
                name,
                description,
                created_at
            FROM source_types
            WHERE code = %s
            LIMIT 1
        """

        return self.database_manager.fetch_one(
            query,
            (code,),
        )

    def get_source_types(
        self,
    ) -> list[dict[str, Any]]:

        query = """
            SELECT
                id,
                code,
                name,
                description,
                created_at
            FROM source_types
            ORDER BY id
        """

        return self.database_manager.fetch_all(query)

    # ------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------

    def get_source(
        self,
        source_id: int,
    ) -> Optional[dict[str, Any]]:

        query = """
            SELECT
                s.id,
                s.source_type_id,
                st.code AS source_type_code,
                st.name AS source_type_name,
                s.name,
                s.enabled,
                s.description,
                s.configuration,
                s.created_at,
                s.updated_at
            FROM sources s
            JOIN source_types st
                ON st.id = s.source_type_id
            WHERE s.id = %s
            LIMIT 1
        """

        return self.database_manager.fetch_one(
            query,
            (source_id,),
        )

    def get_source_by_name(
        self,
        source_type_code: str,
        name: str,
    ) -> Optional[dict[str, Any]]:

        query = """
            SELECT
                s.id,
                s.source_type_id,
                st.code AS source_type_code,
                st.name AS source_type_name,
                s.name,
                s.enabled,
                s.description,
                s.configuration,
                s.created_at,
                s.updated_at
            FROM sources s
            JOIN source_types st
                ON st.id = s.source_type_id
            WHERE st.code = %s
              AND s.name = %s
            LIMIT 1
        """

        return self.database_manager.fetch_one(
            query,
            (source_type_code, name),
        )

    def get_sources(
        self,
        source_type_code: Optional[str] = None,
        enabled_only: bool = False,
    ) -> list[dict[str, Any]]:

        conditions = []
        params: list[Any] = []

        if source_type_code:
            conditions.append("st.code = %s")
            params.append(source_type_code)

        if enabled_only:
            conditions.append("s.enabled = TRUE")

        where_clause = ""

        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT
                s.id,
                s.source_type_id,
                st.code AS source_type_code,
                st.name AS source_type_name,
                s.name,
                s.enabled,
                s.description,
                s.configuration,
                s.created_at,
                s.updated_at
            FROM sources s
            JOIN source_types st
                ON st.id = s.source_type_id
            {where_clause}
            ORDER BY s.id
        """

        return self.database_manager.fetch_all(
            query,
            tuple(params),
        )

    def create_source(
        self,
        source_type_code: str,
        name: str,
        description: Optional[str] = None,
        configuration: Optional[dict[str, Any]] = None,
        enabled: bool = True,
    ) -> dict[str, Any]:

        existing = self.get_source_by_name(
            source_type_code,
            name,
        )

        if existing is not None:
            return existing

        source_type = self.get_source_type(
            source_type_code,
        )

        if source_type is None:
            raise ValueError(
                f"Unknown source type: {source_type_code}"
            )

        import json

        configuration_json = json.dumps(
            configuration or {},
            ensure_ascii=False,
        )

        query = """
            INSERT INTO sources (
                source_type_id,
                name,
                enabled,
                description,
                configuration
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """

        connection = (
            self.database_manager
            .database_connection
            .connect()
        )

        try:
            cursor = connection.cursor()

            try:
                cursor.execute(
                    query,
                    (
                        source_type["id"],
                        name,
                        enabled,
                        description,
                        configuration_json,
                    ),
                )

                row = cursor.fetchone()

                if row is None:
                    raise RuntimeError(
                        "Source was inserted but no ID was returned."
                    )

                source_id = row[0]

                connection.commit()

            except Exception:
                connection.rollback()
                raise

            finally:
                cursor.close()

        finally:
            connection.close()

        result = self.get_source(source_id)

        if result is None:
            raise RuntimeError(
                f"Source {source_id} was created "
                "but could not be loaded."
            )

        return result

    def set_source_enabled(
        self,
        source_id: int,
        enabled: bool,
    ) -> None:

        query = """
            UPDATE sources
            SET
                enabled = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """

        self.database_manager.execute(
            query,
            (enabled, source_id),
        )

    # ------------------------------------------------------------
    # Source accounts
    # ------------------------------------------------------------

    def get_source_account(
        self,
        source_account_id: int,
    ) -> Optional[dict[str, Any]]:

        query = """
            SELECT
                sa.id,
                sa.source_id,
                s.name AS source_name,
                st.code AS source_type_code,
                sa.external_account_id,
                sa.account_name,
                sa.account_email,
                sa.enabled,
                sa.metadata,
                sa.created_at,
                sa.updated_at
            FROM source_accounts sa
            JOIN sources s
                ON s.id = sa.source_id
            JOIN source_types st
                ON st.id = s.source_type_id
            WHERE sa.id = %s
            LIMIT 1
        """

        return self.database_manager.fetch_one(
            query,
            (source_account_id,),
        )

    def get_source_account_by_email(
        self,
        source_type_code: str,
        account_email: str,
    ) -> Optional[dict[str, Any]]:

        query = """
            SELECT
                sa.id,
                sa.source_id,
                s.name AS source_name,
                st.code AS source_type_code,
                sa.external_account_id,
                sa.account_name,
                sa.account_email,
                sa.enabled,
                sa.metadata,
                sa.created_at,
                sa.updated_at
            FROM source_accounts sa
            JOIN sources s
                ON s.id = sa.source_id
            JOIN source_types st
                ON st.id = s.source_type_id
            WHERE st.code = %s
              AND LOWER(sa.account_email) = LOWER(%s)
            LIMIT 1
        """

        return self.database_manager.fetch_one(
            query,
            (
                source_type_code,
                account_email,
            ),
        )

    def get_source_accounts(
        self,
        source_id: Optional[int] = None,
        enabled_only: bool = False,
    ) -> list[dict[str, Any]]:

        conditions = []
        params: list[Any] = []

        if source_id is not None:
            conditions.append("sa.source_id = %s")
            params.append(source_id)

        if enabled_only:
            conditions.append("sa.enabled = TRUE")

        where_clause = ""

        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT
                sa.id,
                sa.source_id,
                s.name AS source_name,
                st.code AS source_type_code,
                sa.external_account_id,
                sa.account_name,
                sa.account_email,
                sa.enabled,
                sa.metadata,
                sa.created_at,
                sa.updated_at
            FROM source_accounts sa
            JOIN sources s
                ON s.id = sa.source_id
            JOIN source_types st
                ON st.id = s.source_type_id
            {where_clause}
            ORDER BY sa.id
        """

        return self.database_manager.fetch_all(
            query,
            tuple(params),
        )

    def create_source_account(
        self,
        source_id: int,
        account_name: str,
        account_email: Optional[str] = None,
        external_account_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        enabled: bool = True,
    ) -> dict[str, Any]:

        if account_email:

            query = """
                SELECT
                    sa.id,
                    sa.source_id,
                    s.name AS source_name,
                    st.code AS source_type_code,
                    sa.external_account_id,
                    sa.account_name,
                    sa.account_email,
                    sa.enabled,
                    sa.metadata,
                    sa.created_at,
                    sa.updated_at
                FROM source_accounts sa
                JOIN sources s
                    ON s.id = sa.source_id
                JOIN source_types st
                    ON st.id = s.source_type_id
                WHERE sa.source_id = %s
                  AND LOWER(sa.account_email) = LOWER(%s)
                LIMIT 1
            """

            existing = self.database_manager.fetch_one(
                query,
                (
                    source_id,
                    account_email,
                ),
            )

            if existing is not None:
                return existing

        import json

        metadata_json = json.dumps(
            metadata or {},
            ensure_ascii=False,
        )

        query = """
            INSERT INTO source_accounts (
                source_id,
                external_account_id,
                account_name,
                account_email,
                enabled,
                metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """

        connection = (
            self.database_manager
            .database_connection
            .connect()
        )

        try:
            cursor = connection.cursor()

            try:
                cursor.execute(
                    query,
                    (
                        source_id,
                        external_account_id,
                        account_name,
                        account_email,
                        enabled,
                        metadata_json,
                    ),
                )

                row = cursor.fetchone()

                if row is None:
                    raise RuntimeError(
                        "Source account was inserted "
                        "but no ID was returned."
                    )

                source_account_id = row[0]

                connection.commit()

            except Exception:
                connection.rollback()
                raise

            finally:
                cursor.close()

        finally:
            connection.close()

        result = self.get_source_account(
            source_account_id,
        )

        if result is None:
            raise RuntimeError(
                f"Source account {source_account_id} "
                "was created but could not be loaded."
            )

        return result

    def set_source_account_enabled(
        self,
        source_account_id: int,
        enabled: bool,
    ) -> None:

        query = """
            UPDATE source_accounts
            SET
                enabled = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """

        self.database_manager.execute(
            query,
            (
                enabled,
                source_account_id,
            ),
        )

    # ------------------------------------------------------------
    # Source locations
    # ------------------------------------------------------------

    def get_source_location(
        self,
        source_location_id: int,
    ) -> Optional[dict[str, Any]]:

        query = """
            SELECT
                sl.id,
                sl.source_id,
                s.name AS source_name,
                st.code AS source_type_code,
                sl.account_id,
                sl.parent_location_id,
                sl.external_id,
                sl.name,
                sl.location_type,
                sl.local_path,
                sl.selected_for_sync,
                sl.enabled,
                sl.metadata,
                sl.created_at,
                sl.updated_at
            FROM source_locations sl
            JOIN sources s
                ON s.id = sl.source_id
            JOIN source_types st
                ON st.id = s.source_type_id
            WHERE sl.id = %s
            LIMIT 1
        """

        return self.database_manager.fetch_one(
            query,
            (source_location_id,),
        )

    def get_source_locations(
        self,
        source_id: Optional[int] = None,
        account_id: Optional[int] = None,
        selected_only: bool = False,
        enabled_only: bool = False,
    ) -> list[dict[str, Any]]:

        conditions = []
        params: list[Any] = []

        if source_id is not None:
            conditions.append("sl.source_id = %s")
            params.append(source_id)

        if account_id is not None:
            conditions.append("sl.account_id = %s")
            params.append(account_id)

        if selected_only:
            conditions.append(
                "sl.selected_for_sync = TRUE"
            )

        if enabled_only:
            conditions.append(
                "sl.enabled = TRUE"
            )

        where_clause = ""

        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT
                sl.id,
                sl.source_id,
                s.name AS source_name,
                st.code AS source_type_code,
                sl.account_id,
                sl.parent_location_id,
                sl.external_id,
                sl.name,
                sl.location_type,
                sl.local_path,
                sl.selected_for_sync,
                sl.enabled,
                sl.metadata,
                sl.created_at,
                sl.updated_at
            FROM source_locations sl
            JOIN sources s
                ON s.id = sl.source_id
            JOIN source_types st
                ON st.id = s.source_type_id
            {where_clause}
            ORDER BY sl.id
        """

        return self.database_manager.fetch_all(
            query,
            tuple(params),
        )

    def create_source_location(
        self,
        source_id: int,
        name: str,
        location_type: str,
        account_id: Optional[int] = None,
        parent_location_id: Optional[int] = None,
        external_id: Optional[str] = None,
        local_path: Optional[str] = None,
        selected_for_sync: bool = True,
        enabled: bool = True,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:

        if external_id is not None:

            query = """
                SELECT
                    sl.id,
                    sl.source_id,
                    s.name AS source_name,
                    st.code AS source_type_code,
                    sl.account_id,
                    sl.parent_location_id,
                    sl.external_id,
                    sl.name,
                    sl.location_type,
                    sl.local_path,
                    sl.selected_for_sync,
                    sl.enabled,
                    sl.metadata,
                    sl.created_at,
                    sl.updated_at
                FROM source_locations sl
                JOIN sources s
                    ON s.id = sl.source_id
                JOIN source_types st
                    ON st.id = s.source_type_id
                WHERE sl.source_id = %s
                  AND sl.account_id IS NOT DISTINCT FROM %s
                  AND sl.external_id = %s
                LIMIT 1
            """

            existing = self.database_manager.fetch_one(
                query,
                (
                    source_id,
                    account_id,
                    external_id,
                ),
            )

            if existing is not None:
                return existing

        import json

        metadata_json = json.dumps(
            metadata or {},
            ensure_ascii=False,
        )

        query = """
            INSERT INTO source_locations (
                source_id,
                account_id,
                parent_location_id,
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
                %s,
                %s,
                %s,
                %s,
                %s
            )
            RETURNING id
        """

        connection = (
            self.database_manager
            .database_connection
            .connect()
        )

        try:
            cursor = connection.cursor()

            try:
                cursor.execute(
                    query,
                    (
                        source_id,
                        account_id,
                        parent_location_id,
                        external_id,
                        name,
                        location_type,
                        local_path,
                        selected_for_sync,
                        enabled,
                        metadata_json,
                    ),
                )

                row = cursor.fetchone()

                if row is None:
                    raise RuntimeError(
                        "Source location was inserted "
                        "but no ID was returned."
                    )

                source_location_id = row[0]

                connection.commit()

            except Exception:
                connection.rollback()
                raise

            finally:
                cursor.close()

        finally:
            connection.close()

        result = self.get_source_location(
            source_location_id,
        )

        if result is None:
            raise RuntimeError(
                f"Source location {source_location_id} "
                "was created but could not be loaded."
            )

        return result

    def set_source_location_selection(
        self,
        source_location_id: int,
        selected_for_sync: bool,
    ) -> None:

        query = """
            UPDATE source_locations
            SET
                selected_for_sync = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """

        self.database_manager.execute(
            query,
            (
                selected_for_sync,
                source_location_id,
            ),
        )

    def set_source_location_enabled(
        self,
        source_location_id: int,
        enabled: bool,
    ) -> None:

        query = """
            UPDATE source_locations
            SET
                enabled = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """

        self.database_manager.execute(
            query,
            (
                enabled,
                source_location_id,
            ),
        )


__all__ = ["SourceManager"]