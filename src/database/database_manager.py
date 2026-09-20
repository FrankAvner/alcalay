from src.database.connection import DatabaseConnection


class DatabaseManager:

    def __init__(self, database_connection=None):

        if database_connection is None:
            database_connection = DatabaseConnection()

        self.database_connection = database_connection

    def test_connection(self):

        return self.database_connection.test_connection()

    def execute(self, query, params=None):

        connection = self.database_connection.connect()

        try:
            cursor = connection.cursor()

            try:
                cursor.execute(query, params)
                connection.commit()

            except Exception:
                connection.rollback()
                raise

            finally:
                cursor.close()

        finally:
            connection.close()

    def fetch_one(self, query, params=None):

        connection = self.database_connection.connect()

        try:
            cursor = connection.cursor()

            try:
                cursor.execute(query, params)
                row = cursor.fetchone()

                if row is None:
                    return None

                columns = [description[0] for description in cursor.description]

                return dict(zip(columns, row))

            finally:
                cursor.close()

        finally:
            connection.close()

    def fetch_all(self, query, params=None):

        connection = self.database_connection.connect()

        try:
            cursor = connection.cursor()

            try:
                cursor.execute(query, params)
                rows = cursor.fetchall()

                columns = [description[0] for description in cursor.description]

                return [
                    dict(zip(columns, row))
                    for row in rows
                ]

            finally:
                cursor.close()

        finally:
            connection.close()