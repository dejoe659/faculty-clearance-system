# Faculty Clearance Management System

ClearanceHub is a responsive faculty clearance portal with student, departmental officer, faculty officer, faculty administrator, and super administrator workspaces. Students register, create a clearance application, upload documents, follow review decisions, and print a verifiable clearance confirmation. Officers review documents and approve, reject, or request corrections. Administrators manage the configurable checklist, staff accounts, reports, and activity history.

## Run locally

Requirements: Node.js 20+ and Python 3.10+.

In one PowerShell terminal:

```powershell
cd .\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:CLEARANCE_DEMO_MODE = "true"
uvicorn main:app --reload --port 8000
```

In a second terminal:

```powershell
cd .\frontend
npm.cmd install
npm.cmd run dev
```

Open http://localhost:3000. The backend API documentation is at http://localhost:8000/docs.

### Demo accounts

Demo data is seeded only when `CLEARANCE_DEMO_MODE=true` and the database has no users. All demo accounts use `Clearance123!`.

| Role | Sign-in |
| --- | --- |
| Student | `CSC/22/0418` |
| Departmental officer | `evelyn.officer@northstar.edu` |
| Faculty officer | `daniel.faculty@northstar.edu` |
| Faculty administrator | `grace.admin@northstar.edu` |
| Super administrator | `admin@northstar.edu` |

Without demo mode, students can register from the sign-in page. For a fresh production database, set `CLEARANCE_BOOTSTRAP_ADMIN_EMAIL` and `CLEARANCE_BOOTSTRAP_ADMIN_PASSWORD` before starting the API to create the initial super administrator. The bootstrap password must be at least 10 characters.

## Configuration and storage

- `CLEARANCE_DATABASE_PATH`: SQLite file path (defaults to `backend/clearance.db`).
- `CLEARANCE_UPLOAD_DIR`: private document storage directory (defaults to `backend/clearance_uploads`).
- `CLEARANCE_CORS_ORIGINS`: comma-separated allowed frontend origins (defaults to `http://localhost:3000`).
- `CLEARANCE_DEMO_MODE`: seed demo accounts and one sample application on a new database; defaults to `false`.
- `CLEARANCE_BOOTSTRAP_ADMIN_EMAIL` and `CLEARANCE_BOOTSTRAP_ADMIN_PASSWORD`: initial super-admin credentials for an empty database.
- `NEXT_PUBLIC_API_URL`: frontend API origin (defaults to `http://127.0.0.1:8000`).

Uploaded documents are limited to PDF, PNG, and JPEG files (10 MB). The API validates file signatures, stores files under random names, and requires an authenticated, appropriately scoped user to retrieve them. Passwords are stored as scrypt hashes; bearer sessions expire after 12 hours.

## Scope and deployment

This is a functional local-first MVP, not a fully hardened university production deployment. It uses SQLite and local file storage, a single faculty configuration, and an in-app notification feed; it does not yet provide email/SMS delivery, QR-code verification, multi-faculty tenant isolation, password reset/MFA, configurable session deadlines, or a full permissions editor. Before deployment with real student records, use private durable storage, HTTPS, backups, retention controls, institutional identity integration, and a security/privacy review. Do not enable demo mode in a production environment.
