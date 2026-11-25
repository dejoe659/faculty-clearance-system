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

    def test_bootstrap_admin_is_created_when_student_already_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "clearance.db"
            with patch.object(main, "DATABASE_URL", ""), patch.object(
                main, "DATABASE_PATH", database_path
            ), patch.dict(
                main.os.environ,
                {"CLEARANCE_BOOTSTRAP_ADMIN_EMAIL": "", "CLEARANCE_BOOTSTRAP_ADMIN_PASSWORD": ""},
            ):
                main._initialize_database()
                with main.connect() as db:
                    db.execute(
                        """INSERT INTO users (id,role,full_name,email,password_hash,created_at)
                        VALUES (?,?,?,?,?,?)""",
                        (
                            "student-1",
                            "student",
                            "Student One",
                            "student@example.edu",
                            main._password_hash("StudentPass123!"),
                            "2025-01-01",
                        ),
                    )

                with patch.dict(
                    main.os.environ,
                    {
                        "CLEARANCE_BOOTSTRAP_ADMIN_EMAIL": "admin@example.edu",
                        "CLEARANCE_BOOTSTRAP_ADMIN_PASSWORD": "AdminPass123!",
                    },
                ):
                    main._initialize_database()
                    main._initialize_database()

                with main.connect() as db:
                    admin = db.execute(
                        "SELECT role,password_hash FROM users WHERE lower(email)=?",
                        ("admin@example.edu",),
                    ).fetchone()
                    user_count = db.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]

            self.assertEqual(user_count, 2)
            self.assertEqual(admin["role"], "super_admin")
            self.assertTrue(main._password_matches("AdminPass123!", admin["password_hash"]))

    def test_bootstrap_promotes_matching_existing_user(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "clearance.db"
            with patch.object(main, "DATABASE_URL", ""), patch.object(
                main, "DATABASE_PATH", database_path
            ), patch.dict(
                main.os.environ,
                {"CLEARANCE_BOOTSTRAP_ADMIN_EMAIL": "", "CLEARANCE_BOOTSTRAP_ADMIN_PASSWORD": ""},
            ):
                main._initialize_database()
                with main.connect() as db:
                    db.execute(
                        """INSERT INTO users (id,role,full_name,email,password_hash,created_at)
                        VALUES (?,?,?,?,?,?)""",
                        (
                            "student-1",
                            "student",
                            "Student One",
                            "admin@example.edu",
                            main._password_hash("StudentPass123!"),
                            "2025-01-01",
                        ),
                    )

                with patch.dict(
                    main.os.environ,
                    {
                        "CLEARANCE_BOOTSTRAP_ADMIN_EMAIL": "admin@example.edu",
                        "CLEARANCE_BOOTSTRAP_ADMIN_PASSWORD": "AdminPass123!",
                    },
                ):
                    main._initialize_database()

                with main.connect() as db:
                    users = db.execute("SELECT role,password_hash FROM users").fetchall()

            self.assertEqual(len(users), 1)
            self.assertEqual(users[0]["role"], "super_admin")
            self.assertTrue(main._password_matches("AdminPass123!", users[0]["password_hash"]))

    def test_invalid_bootstrap_settings_do_not_stop_database_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "clearance.db"
            with patch.object(main, "DATABASE_URL", ""), patch.object(
                main, "DATABASE_PATH", database_path
            ), patch.dict(
                main.os.environ,
                {
                    "CLEARANCE_BOOTSTRAP_ADMIN_EMAIL": "admin@example.edu",
                    "CLEARANCE_BOOTSTRAP_ADMIN_PASSWORD": "",
                },
            ):
                with self.assertLogs("main", level="ERROR") as logged:
                    main._initialize_database()
                with main.connect() as db:
                    user_count = db.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]

            self.assertEqual(user_count, 0)
            self.assertIn("Bootstrap admin not created", logged.output[0])


if __name__ == "__main__":
    unittest.main()
