import json
import os
from pathlib import Path

import psycopg


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = PROJECT_ROOT / "config" / "alcalay_config.json"


class DatabaseConnection:

    def __init__(self, config_file=None):
        if config_file is None:
            config_file = CONFIG_FILE

        self.config_file = config_file
        self.config = self.load_config()

    def load_config(self):

        if not self.config_file.exists():
            raise FileNotFoundError(
                "Database configuration not found: "
                + str(self.config_file)
            )

        with self.config_file.open("r", encoding="utf-8") as file:
            config = json.load(file)

        database = config.get("database")

        if not isinstance(database, dict):
            raise ValueError(
                "Missing database section in alcalay_config.json"
            )

        required = [
            "host",
            "port",
            "name",
            "user"
        ]

        for key in required:
            if key not in database or database[key] in (None, ""):
                raise ValueError(
                    "Missing database configuration: " + key
                )

        return database

    def get_password(self):

        return os.environ.get("ALCALAY_DB_PASSWORD")

    def connect(self):

        return psycopg.connect(
            host=str(self.config["host"]),
            port=int(self.config["port"]),
            dbname=str(self.config["name"]),
            user=str(self.config["user"]),
            password=self.get_password()
        )

    def test_connection(self):

        try:
            connection = self.connect()

            try:
                cursor = connection.cursor()

                try:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    return result == (1,)

                finally:
                    cursor.close()

            finally:
                connection.close()

        except psycopg.Error:
            return False