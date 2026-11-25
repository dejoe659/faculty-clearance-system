from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import mimetypes
import os
from pathlib import Path
import secrets
import sqlite3
from typing import Iterator
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
import psycopg
from psycopg.rows import dict_row

BASE_DIR = Path(__file__).parent
DATABASE_PATH = Path(os.getenv("CLEARANCE_DATABASE_PATH", str(BASE_DIR / "clearance.db")))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
UPLOAD_DIR = Path(os.getenv("CLEARANCE_UPLOAD_DIR", str(BASE_DIR / "clearance_uploads")))
MAX_FILE_BYTES = 10 * 1024 * 1024
ROLES = {"student", "departmental_officer", "faculty_officer", "faculty_admin", "super_admin"}
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
DEMO_MODE = os.getenv("CLEARANCE_DEMO_MODE", "false").lower() == "true"
INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg.IntegrityError)

app = FastAPI(title="Faculty Clearance API", description="Faculty clearance applications and review workflow.", version="1.0.0")
origins = [
    origin.strip()
    for origin in os.getenv(
        "CLEARANCE_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)
bearer = HTTPBearer(auto_error=False)


class DatabaseConnection:
    def __init__(self) -> None:
        self.postgres = bool(DATABASE_URL)
        if self.postgres:
            self.connection = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        else:
            DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(DATABASE_PATH)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys = ON")

    @staticmethod
    def _postgres_sql(statement: str) -> str:
        return statement.replace("?", "%s")

    def execute(self, statement: str, params: tuple = ()):
        if self.postgres:
            statement = self._postgres_sql(statement)
        return self.connection.execute(statement, params)

    def executemany(self, statement: str, params):
        if self.postgres:
            statement = self._postgres_sql(statement)
        cursor = self.connection.cursor()
        cursor.executemany(statement, params)
        return cursor

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()

    def close(self) -> None:
        self.connection.close()


@contextmanager
def connect() -> Iterator[DatabaseConnection]:
    db = DatabaseConnection()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}:{digest.hex()}"


def _password_matches(password: str, stored: str) -> bool:
    salt_hex, digest_hex = stored.split(":", 1)
    actual = _password_hash(password, bytes.fromhex(salt_hex)).split(":", 1)[1]
    return secrets.compare_digest(actual, digest_hex)


def _initialize_database() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, role TEXT NOT NULL, full_name TEXT NOT NULL,
                matric_no TEXT UNIQUE, email TEXT NOT NULL UNIQUE, phone TEXT NOT NULL DEFAULT '',
                faculty TEXT NOT NULL DEFAULT 'Faculty of Science',
                department TEXT NOT NULL DEFAULT 'Computer Science',
                programme TEXT NOT NULL DEFAULT 'B.Sc. Computer Science',
                level TEXT NOT NULL DEFAULT '400', admission_year TEXT NOT NULL DEFAULT '2022',
                graduation_year TEXT NOT NULL DEFAULT '2026', password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS requirements (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL, department TEXT NOT NULL DEFAULT '',
                assigned_role TEXT NOT NULL DEFAULT 'departmental_officer',
                mandatory INTEGER NOT NULL DEFAULT 1, position INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY, student_id TEXT NOT NULL REFERENCES users(id),
                session TEXT NOT NULL DEFAULT '2025/2026', status TEXT NOT NULL DEFAULT 'in_progress',
                verification_code TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS submissions (
                id TEXT PRIMARY KEY, application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                requirement_id TEXT NOT NULL REFERENCES requirements(id), status TEXT NOT NULL DEFAULT 'outstanding',
                filename TEXT, original_filename TEXT, comment TEXT NOT NULL DEFAULT '',
                reviewed_by TEXT REFERENCES users(id), submitted_at TEXT, reviewed_at TEXT,
                UNIQUE(application_id, requirement_id)
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                message TEXT NOT NULL, created_at TEXT NOT NULL, is_read INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS activity_log (
                id TEXT PRIMARY KEY, actor_id TEXT REFERENCES users(id), action TEXT NOT NULL,
                target_id TEXT, created_at TEXT NOT NULL
            );
            """
        )
        if db.postgres:
            columns = {
                row["column_name"] for row in db.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema=current_schema() AND table_name='notifications'"
                ).fetchall()
            }
        else:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(notifications)").fetchall()}
        if "is_read" not in columns:
            db.execute("ALTER TABLE notifications ADD COLUMN is_read INTEGER NOT NULL DEFAULT 0")
            if "read" in columns:
                db.execute('UPDATE notifications SET is_read="read"')
        if not db.execute("SELECT 1 FROM requirements LIMIT 1").fetchone():
            samples = [
                ("Departmental clearance", "Confirm departmental records and return of borrowed items.", "Department", "Computer Science", "departmental_officer"),
                ("Faculty office clearance", "Verify faculty records and student profile.", "Faculty", "", "faculty_officer"),
                ("Examination and records", "Confirm examination results and academic records.", "Records", "", "faculty_officer"),
                ("Library clearance", "Return borrowed books and settle library obligations.", "Library", "Computer Science", "departmental_officer"),
                ("Laboratory or workshop", "Confirm equipment return and laboratory access.", "Laboratory", "Computer Science", "departmental_officer"),
                ("Financial clearance", "Confirm outstanding balances are resolved.", "Finance", "", "faculty_officer"),
                ("Student affairs", "Complete student affairs clearance.", "Student affairs", "", "faculty_officer"),
                ("Project or final-year", "Submit and verify final-year project requirements.", "Final year", "Computer Science", "departmental_officer"),
            ]
            db.executemany(
                "INSERT INTO requirements (id,title,description,category,department,assigned_role,position) VALUES (?,?,?,?,?,?,?)",
                [(str(uuid4()), *row, index) for index, row in enumerate(samples)],
            )
        bootstrap_email = os.getenv("CLEARANCE_BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
        bootstrap_password = os.getenv("CLEARANCE_BOOTSTRAP_ADMIN_PASSWORD", "")
        if bool(bootstrap_email) != bool(bootstrap_password) or (
            bootstrap_password and len(bootstrap_password) < 10
        ):
            logging.getLogger(__name__).error(
                "Bootstrap admin not created: set both bootstrap variables and use a password of at least 10 characters."
            )
        elif bootstrap_email and bootstrap_password:
            has_super_admin = db.execute("SELECT 1 FROM users WHERE role='super_admin' LIMIT 1").fetchone()
            if not has_super_admin:
                existing_user = db.execute(
                    "SELECT id FROM users WHERE lower(email)=?", (bootstrap_email,)
                ).fetchone()
                if existing_user:
                    db.execute(
                        "UPDATE users SET role='super_admin',password_hash=? WHERE id=?",
                        (_password_hash(bootstrap_password), existing_user["id"]),
                    )
                else:
                    db.execute(
                        """INSERT INTO users (id,role,full_name,email,department,password_hash,created_at)
                        VALUES (?,'super_admin','System Administrator',?,'',?,?)""",
                        (str(uuid4()), bootstrap_email, _password_hash(bootstrap_password), now()),
                    )
        if DEMO_MODE and not db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            accounts = [
                ("Amina Yusuf", "student", "CSC/22/0418", "amina.student@northstar.edu", "Computer Science"),
                ("Dr. Evelyn Okoro", "departmental_officer", None, "evelyn.officer@northstar.edu", "Computer Science"),
                ("Prof. Daniel Mensah", "faculty_officer", None, "daniel.faculty@northstar.edu", ""),
                ("Grace Nwosu", "faculty_admin", None, "grace.admin@northstar.edu", ""),
                ("System Administrator", "super_admin", None, "admin@northstar.edu", ""),
            ]
            ids: dict[str, str] = {}
            for name, role, matric, email, department in accounts:
                user_id = str(uuid4())
                ids[role] = user_id
                db.execute(
                    """INSERT INTO users (id,role,full_name,matric_no,email,department,password_hash,created_at)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (user_id, role, name, matric, email, department or "Computer Science", _password_hash("Clearance123!"), now()),
                )
            application_id = str(uuid4())
            db.execute(
                "INSERT INTO applications (id,student_id,session,status,verification_code,created_at) VALUES (?,?,?,'in_progress',?,?)",
                (application_id, ids["student"], "2025/2026", "FC-2026-7A31C9", now()),
            )
            requirements = db.execute("SELECT id FROM requirements ORDER BY position LIMIT 8").fetchall()
            for index, requirement in enumerate(requirements):
                state = "approved" if index == 0 else ("submitted" if index < 3 else "outstanding")
                db.execute(
                    "INSERT INTO submissions (id,application_id,requirement_id,status,submitted_at) VALUES (?,?,?,?,?)",
                    (str(uuid4()), application_id, requirement["id"], state, now() if state != "outstanding" else None),
                )
            db.execute(
                "INSERT INTO notifications (id,user_id,message,created_at) VALUES (?,?,?,?)",
                (str(uuid4()), ids["student"], "Your departmental clearance has been approved.", now()),
            )


@app.on_event("startup")
def startup() -> None:
    _initialize_database()


class RegisterPayload(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    matric_no: str = Field(min_length=3, max_length=40)
    email: str = Field(min_length=5, max_length=160)
    password: str = Field(min_length=10, max_length=128)
    phone: str = Field(default="", max_length=40)
    faculty: str = Field(default="Faculty of Science", max_length=120)
    department: str = Field(default="Computer Science", max_length=120)
    programme: str = Field(default="B.Sc. Computer Science", max_length=120)
    level: str = Field(default="400", max_length=20)
    admission_year: str = Field(default="2022", max_length=4)
    graduation_year: str = Field(default="2026", max_length=4)


class LoginPayload(BaseModel):
    identifier: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=1, max_length=128)


class RequirementPayload(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)
    category: str = Field(min_length=2, max_length=80)
    department: str = Field(default="", max_length=120)
    assigned_role: str = Field(default="departmental_officer")
    mandatory: bool = True
    position: int = Field(default=0, ge=0)
    active: bool = True


class ReviewPayload(BaseModel):
    decision: str = Field(pattern="^(approved|rejected|changes_requested)$")
    comment: str = Field(default="", max_length=2000)


class StaffCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    role: str = Field(pattern="^(departmental_officer|faculty_officer|faculty_admin|super_admin)$")
    email: str = Field(min_length=5, max_length=160)
    password: str = Field(min_length=10, max_length=128)
    department: str = Field(default="", max_length=120)
    faculty: str = Field(default="Faculty of Science", max_length=120)


class StaffUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role: str | None = Field(default=None, pattern="^(departmental_officer|faculty_officer|faculty_admin|super_admin)$")
    email: str | None = Field(default=None, min_length=5, max_length=160)
    password: str | None = Field(default=None, min_length=10, max_length=128)
    department: str | None = Field(default=None, max_length=120)
    faculty: str | None = Field(default=None, max_length=120)


def _public_user(row) -> dict:
    return {key: row[key] for key in row.keys() if key != "password_hash"}


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    with connect() as db:
        row = db.execute(
            """SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>?""", (token_hash, now())
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    return _public_user(row)


def require_roles(user: dict, *roles: str) -> None:
    if user["role"] not in roles:
        raise HTTPException(status_code=403, detail="You are not authorised to perform this action.")


def _add_notification(db: DatabaseConnection, user_id: str, message: str) -> None:
    db.execute(
        "INSERT INTO notifications (id,user_id,message,created_at) VALUES (?,?,?,?)",
        (str(uuid4()), user_id, message, now()),
    )


def _application_rows(db: DatabaseConnection, student_id: str | None = None) -> list[dict]:
    query = """SELECT a.*,u.full_name,u.matric_no,u.department,u.faculty,u.level,
        COUNT(s.id) AS total,
        SUM(CASE WHEN s.status='approved' THEN 1 ELSE 0 END) AS approved,
        SUM(CASE WHEN r.mandatory=1 THEN 1 ELSE 0 END) AS mandatory_total,
        SUM(CASE WHEN r.mandatory=1 AND s.status='approved' THEN 1 ELSE 0 END) AS mandatory_approved,
        SUM(CASE WHEN s.status='submitted' THEN 1 ELSE 0 END) AS pending,
        SUM(CASE WHEN s.status IN ('rejected','changes_requested') THEN 1 ELSE 0 END) AS needs_action
        FROM applications a JOIN users u ON u.id=a.student_id
        LEFT JOIN submissions s ON s.application_id=a.id
        LEFT JOIN requirements r ON r.id=s.requirement_id"""
    params: tuple = ()
    if student_id:
        query += " WHERE a.student_id=?"
        params = (student_id,)
    query += (
        " GROUP BY a.id,u.full_name,u.matric_no,u.department,u.faculty,u.level"
        " ORDER BY a.created_at DESC"
    )
    result = []
    for row in db.execute(query, params).fetchall():
        item = dict(row)
        item["total"] = item["total"] or 0
        item["approved"] = item["approved"] or 0
        item["mandatory_total"] = item["mandatory_total"] or 0
        item["mandatory_approved"] = item["mandatory_approved"] or 0
        item["pending"] = item["pending"] or 0
        item["needs_action"] = item["needs_action"] or 0
        item["progress"] = round(item["mandatory_approved"] / item["mandatory_total"] * 100) if item["mandatory_total"] else 100
        item["status"] = "fully_cleared" if item["mandatory_approved"] == item["mandatory_total"] else "in_progress"
        result.append(item)
    return result


def _submission_rows(db: DatabaseConnection, application_id: str | None = None) -> list[dict]:
    query = """SELECT s.*,r.title,r.description,r.category,r.department,r.assigned_role,r.mandatory,
        a.student_id,a.session,u.full_name,u.matric_no,u.email,u.level
        FROM submissions s JOIN requirements r ON r.id=s.requirement_id
        JOIN applications a ON a.id=s.application_id JOIN users u ON u.id=a.student_id"""
    params: tuple = ()
    if application_id:
        query += " WHERE s.application_id=?"
        params = (application_id,)
    query += " ORDER BY r.position,s.submitted_at DESC"
    return [dict(row) for row in db.execute(query, params).fetchall()]


def _can_review(user: dict, submission: dict) -> bool:
    if user["role"] in {"faculty_admin", "super_admin"}:
        return True
    if user["role"] == "faculty_officer":
        return submission["assigned_role"] == "faculty_officer"
    return (
        user["role"] == "departmental_officer"
        and submission["assigned_role"] == "departmental_officer"
        and user["department"] == submission["department"]
    )


@app.get("/")
def root():
    return {"message": "Faculty Clearance API is running", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/api/auth/register", status_code=201)
def register(payload: RegisterPayload):
    matric_no = payload.matric_no.strip().upper()
    email = payload.email.strip().lower()
    user_id = str(uuid4())
    with connect() as db:
        try:
            db.execute(
                """INSERT INTO users (id,role,full_name,matric_no,email,phone,faculty,department,programme,
                level,admission_year,graduation_year,password_hash,created_at)
                VALUES (?,'student',?,?,?,?,?,?,?,?,?,?,?,?)""",
                (user_id, payload.full_name.strip(), matric_no, email, payload.phone.strip(),
                 payload.faculty.strip(), payload.department.strip(), payload.programme.strip(),
                 payload.level.strip(), payload.admission_year.strip(), payload.graduation_year.strip(),
                 _password_hash(payload.password), now()),
            )
        except INTEGRITY_ERRORS as exc:
            raise HTTPException(status_code=409, detail="That matriculation number or email is already registered.") from exc
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return _public_user(row)


@app.post("/api/auth/login")
def login(payload: LoginPayload):
    identifier = payload.identifier.strip().lower()
    with connect() as db:
        row = db.execute(
            "SELECT * FROM users WHERE lower(email)=? OR lower(matric_no)=?", (identifier, identifier)
        ).fetchone()
        if not row or not _password_matches(payload.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="The sign-in details are incorrect.")
        token = secrets.token_urlsafe(36)
        expires = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        db.execute(
            "INSERT INTO sessions (token_hash,user_id,expires_at) VALUES (?,?,?)",
            (hashlib.sha256(token.encode()).hexdigest(), row["id"], expires),
        )
    return {"token": token, "user": _public_user(row), "expires_at": expires}


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return user


@app.post("/api/auth/logout")
def logout(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), user: dict = Depends(current_user)):
    token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    with connect() as db:
        db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
    return {"ok": True}


@app.get("/api/dashboard")
def dashboard(user: dict = Depends(current_user)):
    with connect() as db:
        apps = _application_rows(db, user["id"]) if user["role"] == "student" else _application_rows(db)
        if user["role"] == "student":
            own_app = apps[0] if apps else None
            subs = _submission_rows(db, own_app["id"]) if own_app else []
            counts = {state: sum(item["status"] == state for item in subs) for state in
                      ("approved", "submitted", "rejected", "changes_requested", "outstanding")}
            notices = [dict(row) for row in db.execute(
                "SELECT id,message,created_at,is_read AS read FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 5",
                (user["id"],),
            ).fetchall()]
            return {"role": user["role"], "application": own_app, "counts": counts, "notifications": notices}
        submissions = [item for item in _submission_rows(db) if _can_review(user, item)]
        if user["role"] == "departmental_officer":
            apps = [item for item in apps if item["department"] == user["department"]]
        if user["role"] == "faculty_officer":
            pass
        all_apps = _application_rows(db)
        staff_count = db.execute("SELECT COUNT(*) AS count FROM users WHERE role!='student'").fetchone()["count"]
        students_count = db.execute("SELECT COUNT(*) AS count FROM users WHERE role='student'").fetchone()["count"]
        return {
            "role": user["role"],
            "counts": {
                "students": students_count, "staff": staff_count, "applications": len(all_apps),
                "fully_cleared": sum(item["status"] == "fully_cleared" for item in all_apps),
                "pending": sum(item["status"] == "submitted" for item in submissions),
                "approved": sum(item["status"] == "approved" for item in submissions),
                "rejected": sum(item["status"] in {"rejected", "changes_requested"} for item in submissions),
            },
            "applications": apps[:8], "submissions": submissions[:10],
        }


@app.get("/api/requirements")
def list_requirements(user: dict = Depends(current_user)):
    with connect() as db:
        rows = db.execute("SELECT * FROM requirements WHERE active=1 ORDER BY position,id").fetchall()
        return [dict(row) for row in rows]


@app.post("/api/requirements", status_code=201)
def create_requirement(payload: RequirementPayload, user: dict = Depends(current_user)):
    require_roles(user, "faculty_admin", "super_admin")
    if payload.assigned_role not in {"departmental_officer", "faculty_officer"}:
        raise HTTPException(status_code=422, detail="Choose a valid clearance officer role.")
    if payload.assigned_role == "departmental_officer" and not payload.department.strip():
        raise HTTPException(status_code=422, detail="A department is required for departmental officer assignment.")
    requirement_id = str(uuid4())
    with connect() as db:
        db.execute(
            """INSERT INTO requirements (id,title,description,category,department,assigned_role,mandatory,position,active)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (requirement_id, payload.title.strip(), payload.description.strip(), payload.category.strip(),
             payload.department.strip(), payload.assigned_role, int(payload.mandatory), payload.position, int(payload.active)),
        )
    return {"id": requirement_id, **payload.model_dump()}


@app.patch("/api/requirements/{requirement_id}")
def update_requirement(requirement_id: str, payload: RequirementPayload, user: dict = Depends(current_user)):
    require_roles(user, "faculty_admin", "super_admin")
    if payload.assigned_role not in {"departmental_officer", "faculty_officer"}:
        raise HTTPException(status_code=422, detail="Choose a valid clearance officer role.")
    if payload.assigned_role == "departmental_officer" and not payload.department.strip():
        raise HTTPException(status_code=422, detail="A department is required for departmental officer assignment.")
    with connect() as db:
        if not db.execute("SELECT 1 FROM requirements WHERE id=?", (requirement_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Requirement not found.")
        db.execute(
            """UPDATE requirements SET title=?,description=?,category=?,department=?,assigned_role=?,
            mandatory=?,position=?,active=? WHERE id=?""",
            (payload.title.strip(), payload.description.strip(), payload.category.strip(), payload.department.strip(),
             payload.assigned_role, int(payload.mandatory), payload.position, int(payload.active), requirement_id),
        )
    return {"id": requirement_id, **payload.model_dump()}


@app.delete("/api/requirements/{requirement_id}")
def delete_requirement(requirement_id: str, user: dict = Depends(current_user)):
    require_roles(user, "faculty_admin", "super_admin")
    with connect() as db:
        if db.execute("SELECT 1 FROM submissions WHERE requirement_id=?", (requirement_id,)).fetchone():
            db.execute("UPDATE requirements SET active=0 WHERE id=?", (requirement_id,))
        elif db.execute("DELETE FROM requirements WHERE id=?", (requirement_id,)).rowcount == 0:
            raise HTTPException(status_code=404, detail="Requirement not found.")
    return {"ok": True}


@app.get("/api/applications")
def list_applications(user: dict = Depends(current_user)):
    with connect() as db:
        rows = _application_rows(db, user["id"] if user["role"] == "student" else None)
    if user["role"] == "departmental_officer":
        rows = [row for row in rows if row["department"] == user["department"]]
    return rows


@app.post("/api/applications", status_code=201)
def create_application(user: dict = Depends(current_user)):
    require_roles(user, "student")
    with connect() as db:
        if db.execute("SELECT 1 FROM applications WHERE student_id=?", (user["id"],)).fetchone():
            raise HTTPException(status_code=409, detail="You already have a clearance application.")
        active = db.execute("SELECT id,department FROM requirements WHERE active=1 ORDER BY position").fetchall()
        if not active:
            raise HTTPException(status_code=409, detail="No clearance requirements are configured yet.")
        application_id = str(uuid4())
        code = f"FC-{datetime.now().year}-{secrets.token_hex(3).upper()}"
        db.execute(
            "INSERT INTO applications (id,student_id,session,status,verification_code,created_at) VALUES (?,?,?,'in_progress',?,?)",
            (application_id, user["id"], f"{datetime.now().year}/{datetime.now().year + 1}", code, now()),
        )
        db.executemany(
            "INSERT INTO submissions (id,application_id,requirement_id) VALUES (?,?,?)",
            [(str(uuid4()), application_id, item["id"]) for item in active],
        )
        _add_notification(db, user["id"], "Your clearance application is ready. Submit the required documents to begin.")
        return next(item for item in _application_rows(db, user["id"]) if item["id"] == application_id)


@app.get("/api/applications/{application_id}/submissions")
def application_submissions(application_id: str, user: dict = Depends(current_user)):
    with connect() as db:
        application = db.execute("SELECT * FROM applications WHERE id=?", (application_id,)).fetchone()
        if not application:
            raise HTTPException(status_code=404, detail="Application not found.")
        if user["role"] == "student" and application["student_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="You cannot view another student's application.")
        result = _submission_rows(db, application_id)
    if user["role"] == "departmental_officer":
        result = [item for item in result if item["department"] == user["department"]]
    return result


@app.post("/api/submissions/{submission_id}/upload")
async def upload_submission(
    submission_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(current_user),
):
    require_roles(user, "student")
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Upload a PDF, PNG or JPG file.")
    content = await file.read(MAX_FILE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="The selected file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Maximum upload size is 10 MB.")
    valid_signature = (
        (extension == ".pdf" and content.startswith(b"%PDF-"))
        or (extension == ".png" and content.startswith(b"\x89PNG\r\n\x1a\n"))
        or (extension in {".jpg", ".jpeg"} and content.startswith(b"\xff\xd8\xff"))
    )
    if not valid_signature:
        raise HTTPException(status_code=400, detail="The file content does not match its extension.")
    with connect() as db:
        row = db.execute(
            """SELECT s.*,a.student_id,r.title FROM submissions s JOIN applications a ON a.id=s.application_id
            JOIN requirements r ON r.id=s.requirement_id WHERE s.id=?""", (submission_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Clearance requirement not found.")
        if row["student_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="You cannot submit documents for another student.")
        if row["status"] == "approved":
            raise HTTPException(status_code=409, detail="This requirement has already been approved.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{extension}"
    (UPLOAD_DIR / stored_name).write_bytes(content)
    with connect() as db:
        db.execute(
            """UPDATE submissions SET status='submitted',filename=?,original_filename=?,comment='',submitted_at=?,
            reviewed_by=NULL,reviewed_at=NULL WHERE id=?""",
            (stored_name, Path(file.filename or "document").name[:180], now(), submission_id),
        )
        _add_notification(db, user["id"], f"Your document for {row['title']} was submitted for review.")
        return next(item for item in _submission_rows(db, row["application_id"]) if item["id"] == submission_id)


@app.get("/api/submissions/{submission_id}/file")
def get_submission_file(submission_id: str, preview: bool = False, user: dict = Depends(current_user)):
    with connect() as db:
        row = db.execute(
            """SELECT s.*,a.student_id,r.department,r.assigned_role FROM submissions s JOIN applications a ON a.id=s.application_id
            JOIN requirements r ON r.id=s.requirement_id WHERE s.id=?""", (submission_id,)
        ).fetchone()
    if not row or not row["filename"]:
        raise HTTPException(status_code=404, detail="No document is available for this requirement.")
    if user["role"] == "student" and row["student_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="You cannot access another student's document.")
    if user["role"] == "departmental_officer" and (
        row["assigned_role"] != "departmental_officer" or user["department"] != row["department"]
    ):
        raise HTTPException(status_code=403, detail="You are not assigned to this department.")
    if user["role"] == "faculty_officer" and row["assigned_role"] != "faculty_officer":
        raise HTTPException(status_code=403, detail="This document is assigned to another office.")
    path = UPLOAD_DIR / row["filename"]
    if not path.is_file() or path.parent.resolve() != UPLOAD_DIR.resolve():
        raise HTTPException(status_code=404, detail="The uploaded document is no longer available.")
    from fastapi.responses import FileResponse
    media_type = mimetypes.guess_type(row["original_filename"])[0] or "application/octet-stream"
    return FileResponse(
        path, filename=row["original_filename"], media_type=media_type,
        content_disposition_type="inline" if preview else "attachment",
    )


@app.patch("/api/submissions/{submission_id}/review")
def review_submission(submission_id: str, payload: ReviewPayload, user: dict = Depends(current_user)):
    require_roles(user, "departmental_officer", "faculty_officer", "faculty_admin", "super_admin")
    if payload.decision in {"rejected", "changes_requested"} and not payload.comment.strip():
        raise HTTPException(status_code=422, detail="Provide a reason or correction request.")
    with connect() as db:
        row = db.execute(
            """SELECT s.*,a.student_id,r.title,r.department,r.assigned_role FROM submissions s JOIN applications a ON a.id=s.application_id
            JOIN requirements r ON r.id=s.requirement_id WHERE s.id=?""", (submission_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Clearance submission not found.")
        item = dict(row)
        if not _can_review(user, item):
            raise HTTPException(status_code=403, detail="This requirement is assigned to another office.")
        if row["status"] not in {"submitted", "rejected", "changes_requested"}:
            raise HTTPException(status_code=409, detail="Only a submitted document can be reviewed.")
        if payload.decision == "approved" and not row["filename"]:
            raise HTTPException(status_code=409, detail="A submitted document is required before approval.")
        if user["role"] == "faculty_officer":
            outstanding_departmental = db.execute(
                """SELECT 1 FROM submissions s JOIN requirements r ON r.id=s.requirement_id
                WHERE s.application_id=? AND r.mandatory=1 AND r.assigned_role='departmental_officer'
                AND s.status!='approved' LIMIT 1""",
                (row["application_id"],),
            ).fetchone()
            if outstanding_departmental:
                raise HTTPException(status_code=409, detail="Departmental clearance must be completed before faculty review.")
        db.execute(
            "UPDATE submissions SET status=?,comment=?,reviewed_by=?,reviewed_at=? WHERE id=?",
            (payload.decision, payload.comment.strip(), user["id"], now(), submission_id),
        )
        message = {
            "approved": f"Your {row['title']} clearance was approved.",
            "rejected": f"Your {row['title']} clearance was rejected: {payload.comment.strip()}",
            "changes_requested": f"Please update your {row['title']} submission: {payload.comment.strip()}",
        }[payload.decision]
        _add_notification(db, row["student_id"], message)
        db.execute(
            "INSERT INTO activity_log (id,actor_id,action,target_id,created_at) VALUES (?,?,?,?,?)",
            (str(uuid4()), user["id"], payload.decision, submission_id, now()),
        )
        return next(item for item in _submission_rows(db, row["application_id"]) if item["id"] == submission_id)


@app.get("/api/notifications")
def notifications(user: dict = Depends(current_user)):
    with connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT id,message,created_at,is_read AS read FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 30",
            (user["id"],),
        ).fetchall()]


@app.patch("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str, user: dict = Depends(current_user)):
    with connect() as db:
        if not db.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?", (notification_id, user["id"])).rowcount:
            raise HTTPException(status_code=404, detail="Notification not found.")
    return {"ok": True}


@app.get("/api/applications/{application_id}/certificate")
def certificate(application_id: str, user: dict = Depends(current_user)):
    with connect() as db:
        row = db.execute(
            """SELECT a.*,u.full_name,u.matric_no,u.faculty,u.department,u.programme,u.level,
            SUM(CASE WHEN r.mandatory=1 THEN 1 ELSE 0 END) AS total,
            SUM(CASE WHEN r.mandatory=1 AND s.status='approved' THEN 1 ELSE 0 END) AS approved
            FROM applications a JOIN users u ON u.id=a.student_id
            LEFT JOIN submissions s ON s.application_id=a.id
            LEFT JOIN requirements r ON r.id=s.requirement_id WHERE a.id=? GROUP BY a.id""",
            (application_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Application not found.")
        if user["role"] == "student" and row["student_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="You cannot access another student's certificate.")
        if row["approved"] != row["total"]:
            raise HTTPException(status_code=409, detail="The certificate is available after all requirements are approved.")
    result = dict(row)
    result["status"] = "fully_cleared"
    return result


@app.get("/api/admin/users")
def list_users(user: dict = Depends(current_user)):
    require_roles(user, "faculty_admin", "super_admin")
    with connect() as db:
        return [_public_user(row) for row in db.execute(
            "SELECT * FROM users ORDER BY role,full_name"
        ).fetchall()]


@app.post("/api/admin/users", status_code=201)
def create_staff(payload: StaffCreate, user: dict = Depends(current_user)):
    require_roles(user, "faculty_admin", "super_admin")
    if user["role"] == "faculty_admin" and payload.role in {"faculty_admin", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only a super administrator can create administrator accounts.")
    if payload.role == "departmental_officer" and not payload.department.strip():
        raise HTTPException(status_code=422, detail="A department is required for departmental officers.")
    user_id = str(uuid4())
    with connect() as db:
        try:
            db.execute(
                """INSERT INTO users (id,role,full_name,email,department,faculty,password_hash,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (user_id, payload.role, payload.full_name.strip(), payload.email.strip().lower(),
                 payload.department.strip() or user["department"], payload.faculty.strip(),
                 _password_hash(payload.password), now()),
            )
        except INTEGRITY_ERRORS as exc:
            raise HTTPException(status_code=409, detail="That email address is already in use.") from exc
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        db.execute(
            "INSERT INTO activity_log (id,actor_id,action,target_id,created_at) VALUES (?,?,?,?,?)",
            (str(uuid4()), user["id"], "staff_created", user_id, now()),
        )
    return _public_user(row)


@app.patch("/api/admin/users/{user_id}")
def update_staff(user_id: str, payload: StaffUpdate, user: dict = Depends(current_user)):
    require_roles(user, "super_admin")
    with connect() as db:
        existing = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Staff account not found.")
        if existing["role"] == "student":
            raise HTTPException(status_code=400, detail="Student accounts cannot be changed through staff management.")
        role = payload.role or existing["role"]
        department = payload.department if payload.department is not None else existing["department"]
        if role == "departmental_officer" and not department.strip():
            raise HTTPException(status_code=422, detail="A department is required for departmental officers.")
        if user_id == user["id"] and role != "super_admin":
            raise HTTPException(status_code=409, detail="You cannot remove your own super administrator access.")
        try:
            db.execute(
                """UPDATE users SET role=?,full_name=?,email=?,department=?,faculty=?,password_hash=? WHERE id=?""",
                (
                    role,
                    payload.full_name.strip() if payload.full_name is not None else existing["full_name"],
                    payload.email.strip().lower() if payload.email is not None else existing["email"],
                    department.strip(),
                    payload.faculty.strip() if payload.faculty is not None else existing["faculty"],
                    _password_hash(payload.password) if payload.password else existing["password_hash"],
                    user_id,
                ),
            )
        except INTEGRITY_ERRORS as exc:
            raise HTTPException(status_code=409, detail="That email address is already in use.") from exc
        if payload.password is not None or payload.role is not None or payload.department is not None:
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        db.execute(
            "INSERT INTO activity_log (id,actor_id,action,target_id,created_at) VALUES (?,?,?,?,?)",
            (str(uuid4()), user["id"], "staff_updated", user_id, now()),
        )
    return _public_user(row)


@app.get("/api/admin/activity")
def activity(user: dict = Depends(current_user)):
    require_roles(user, "super_admin")
    with connect() as db:
        return [dict(row) for row in db.execute(
            """SELECT l.*,u.full_name AS actor_name FROM activity_log l
            LEFT JOIN users u ON u.id=l.actor_id ORDER BY l.created_at DESC LIMIT 100"""
        ).fetchall()]


@app.get("/api/admin/report")
def report(user: dict = Depends(current_user)):
    require_roles(user, "faculty_admin", "super_admin")
    with connect() as db:
        applications = _application_rows(db)
        rows = db.execute(
            """SELECT u.department,COUNT(DISTINCT a.id) AS applications,
            SUM(CASE WHEN a.id IS NOT NULL AND NOT EXISTS (
              SELECT 1 FROM submissions s JOIN requirements r ON r.id=s.requirement_id
              WHERE s.application_id=a.id AND r.mandatory=1 AND s.status!='approved'
            ) THEN 1 ELSE 0 END) AS fully_cleared
            FROM users u LEFT JOIN applications a ON a.student_id=u.id
            WHERE u.role='student' GROUP BY u.department ORDER BY u.department"""
        ).fetchall()
        return {"applications": applications, "departments": [dict(row) for row in rows]}
