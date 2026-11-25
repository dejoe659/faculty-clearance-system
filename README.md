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

Open http://localhost:3000. The backend API documentation is at http://localhost:8000/docs. The local backend uses SQLite by default. To run it against PostgreSQL, set `DATABASE_URL` to a PostgreSQL connection URL before starting the API.

### Demo accounts

Demo data is seeded only when `CLEARANCE_DEMO_MODE=true` and the database has no users. All demo accounts use `Clearance123!`.

| Role | Sign-in |
| --- | --- |
| Student | `CSC/22/0418` |
| Departmental officer | `evelyn.officer@northstar.edu` |
| Faculty officer | `daniel.faculty@northstar.edu` |
| Faculty administrator | `grace.admin@northstar.edu` |
| Super administrator | `admin@northstar.edu` |

Without demo mode, students can register from the sign-in page. For a fresh production database, set `CLEARANCE_BOOTSTRAP_ADMIN_EMAIL` and `CLEARANCE_BOOTSTRAP_ADMIN_PASSWORD` before starting the API to create the initial super administrator. The bootstrap password must be at least 10 characters. Remove these bootstrap variables after the admin account is created.

## Configuration and storage

- `DATABASE_URL`: PostgreSQL connection URL. When set, the API uses PostgreSQL; otherwise, local development uses SQLite.
- `CLEARANCE_DATABASE_PATH`: local SQLite file path (defaults to `backend/clearance.db`).
- `CLEARANCE_UPLOAD_DIR`: private document storage directory (defaults to `backend/clearance_uploads`).
- `CLEARANCE_CORS_ORIGINS`: comma-separated allowed frontend origins (defaults to local `localhost` and `127.0.0.1`).
- `CLEARANCE_DEMO_MODE`: seed demo accounts and one sample application on a new database; defaults to `false`.
- `CLEARANCE_BOOTSTRAP_ADMIN_EMAIL` and `CLEARANCE_BOOTSTRAP_ADMIN_PASSWORD`: initial super-admin credentials for an empty database.
- `NEXT_PUBLIC_API_URL`: frontend API origin (defaults to `http://127.0.0.1:8000`).

Uploaded documents are limited to PDF, PNG, and JPEG files (10 MB). The API validates file signatures, stores files under random names, and requires an authenticated, appropriately scoped user to retrieve them. Passwords are stored as scrypt hashes; bearer sessions expire after 12 hours.

## Deploy to Railway and Vercel

The API uses Railway PostgreSQL whenever `DATABASE_URL` is configured. `backend/Dockerfile` packages the API and its PostgreSQL driver for Railway.

1. In Railway, create a project and add a service from the GitHub repository `dejoe659/faculty-clearance-system`. Set the API service's **Root Directory** to `/backend`; Railway will build `backend/Dockerfile`.
2. Add a PostgreSQL service to the project. Set the API service's `DATABASE_URL` variable to a Railway reference to the database service's `DATABASE_URL` (select the reference in Railway's variable editor; do not copy credentials into source code).
3. Configure the API service's variables:
   - `CLEARANCE_DEMO_MODE=false`
   - `CLEARANCE_CORS_ORIGINS=https://<your-vercel-domain>`
   - `CLEARANCE_BOOTSTRAP_ADMIN_EMAIL=<your-admin-email>`
   - `CLEARANCE_BOOTSTRAP_ADMIN_PASSWORD=<unique-password-of-at-least-10-characters>`
   - `CLEARANCE_UPLOAD_DIR=/data/clearance_uploads`
4. Attach a Railway volume to the API service at `/data`. This persists uploaded documents; PostgreSQL stores the application records. Keep the API as a single instance while using local-volume document storage.
5. Set the Railway health check path to `/health`, deploy the API, and confirm its generated Railway domain returns `{"status":"healthy"}`.
6. In Vercel, import the same GitHub repository and set its **Root Directory** to `frontend`. Set `NEXT_PUBLIC_API_URL` to the Railway API's public URL, then deploy.
7. Update `CLEARANCE_CORS_ORIGINS` to the exact Vercel production origin if it differs from the value configured earlier. Sign in with the bootstrap admin account, create staff, then remove the bootstrap email and password variables.

The API creates the PostgreSQL schema on startup. A new Railway PostgreSQL database starts empty; local SQLite accounts, documents, and student records are not automatically copied. The bootstrap admin is created once on an empty database. Never enable demo mode in production or put database URLs or admin credentials into GitHub.

This is not yet a fully hardened university production system. Before using real records, configure backups and retention, review institutional privacy/security requirements, and consider moving uploads to private object storage. Email/SMS delivery, QR verification, multi-faculty tenant isolation, password reset/MFA, and configurable session deadlines are not implemented.
