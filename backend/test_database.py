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
                    user = db.execute("SELECT active FROM users WHERE id=?", ("user-1",)).fetchone()
            self.assertEqual(notification["is_read"], 1)
            self.assertEqual(user["active"], 1)

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

    def test_admin_can_manage_student_profiles_accounts_and_access(self):
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
                            "admin-1", "super_admin", "System Administrator",
                            "admin@example.edu", main._password_hash("AdminPass123!"), "2025-01-01",
                        ),
                    )
                    db.execute(
                        """INSERT INTO users (id,role,full_name,matric_no,email,password_hash,created_at)
                        VALUES (?,?,?,?,?,?,?)""",
                        (
                            "student-1", "student", "Student One", "CSC/22/0001",
                            "student@example.edu", main._password_hash("StudentPass123!"), "2025-01-01",
                        ),
                    )

                admin = {"id": "admin-1", "role": "super_admin"}
                updated = main.update_student(
                    "student-1",
                    main.StudentUpdate(full_name="Updated Student", department="Physics"),
                    admin,
                )
                self.assertEqual(updated["full_name"], "Updated Student")
                self.assertEqual(updated["department"], "Physics")

                settings = main.update_admin_settings(
                    main.AdminSettingsUpdate(registration_enabled=False, applications_enabled=False),
                    admin,
                )
                self.assertFalse(settings["registration_enabled"])
                self.assertFalse(settings["applications_enabled"])

                with self.assertRaises(main.HTTPException) as registration_error:
                    main.register(
                        main.RegisterPayload(
                            full_name="New Student", matric_no="CSC/22/0002", email="new@example.edu",
                            password="StudentPass123!",
                        )
                    )
                self.assertEqual(registration_error.exception.status_code, 403)

                with self.assertRaises(main.HTTPException) as application_error:
                    main.create_application({"id": "student-1", "role": "student"})
                self.assertEqual(application_error.exception.status_code, 403)

                with main.connect() as db:
                    db.execute(
                        "INSERT INTO sessions (token_hash,user_id,expires_at) VALUES (?,?,?)",
                        ("token-hash", "student-1", "2099-01-01T00:00:00+00:00"),
                    )

                updated = main.update_student_status(
                    "student-1", main.StudentStatusUpdate(active=False), admin
                )
                self.assertEqual(updated["active"], 0)
                with main.connect() as db:
                    session_count = db.execute(
                        "SELECT COUNT(*) AS count FROM sessions WHERE user_id=?", ("student-1",)
                    ).fetchone()["count"]
                self.assertEqual(session_count, 0)

                with self.assertRaises(main.HTTPException) as login_error:
                    main.login(
                        main.LoginPayload(identifier="student@example.edu", password="StudentPass123!")
                    )
                self.assertEqual(login_error.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
