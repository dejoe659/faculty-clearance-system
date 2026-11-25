import tempfile
import unittest
from pathlib import Path
import sqlite3
from unittest.mock import patch

import main


class DatabaseConnectionTests(unittest.TestCase):
    def test_postgres_placeholders_are_translated(self):
        self.assertEqual(
            main.DatabaseConnection._postgres_sql("SELECT id FROM users WHERE email=? AND role=?"),
            "SELECT id FROM users WHERE email=%s AND role=%s",
        )

    def test_sqlite_fallback_supports_schema_batch_and_named_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(main, "DATABASE_URL", ""), patch.object(
                main, "DATABASE_PATH", Path(directory) / "clearance.db"
            ):
                with main.connect() as db:
                    db.executescript(
                        """
                        CREATE TABLE users (id TEXT PRIMARY KEY, full_name TEXT NOT NULL);
                        CREATE TABLE sessions (token TEXT PRIMARY KEY);
                        """
                    )
                    db.executemany(
                        "INSERT INTO users (id,full_name) VALUES (?,?)",
                        [("student-1", "Student One"), ("student-2", "Student Two")],
                    )
                    rows = db.execute("SELECT id,full_name FROM users ORDER BY id").fetchall()
                self.assertEqual([row["full_name"] for row in rows], ["Student One", "Student Two"])

    def test_existing_sqlite_notification_read_state_is_migrated(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "legacy.db"
            connection = sqlite3.connect(database_path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE users (id TEXT PRIMARY KEY);
                    CREATE TABLE notifications (
                        id TEXT PRIMARY KEY, user_id TEXT, message TEXT, created_at TEXT, read INTEGER DEFAULT 0
                    );
                    INSERT INTO users (id) VALUES ('user-1');
                    INSERT INTO notifications (id,user_id,message,created_at,read)
                        VALUES ('notice-1','user-1','Reviewed','2025-01-01',1);
                    """
                )
            finally:
                connection.close()
            with patch.object(main, "DATABASE_URL", ""), patch.object(main, "DATABASE_PATH", database_path):
                main._initialize_database()
                with main.connect() as db:
                    notification = db.execute(
                        "SELECT is_read FROM notifications WHERE id=?", ("notice-1",)
                    ).fetchone()
            self.assertEqual(notification["is_read"], 1)


if __name__ == "__main__":
    unittest.main()
