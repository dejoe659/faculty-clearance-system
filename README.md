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

Without demo mode, students can register from the sign-in page. For a fresh production database, set `CLEARANCE_BOOTSTRAP_ADMIN_EMAIL` and `CLEARANCE_BOOTSTRAP_ADMIN_PASSWORD` before starting the API to create the initial super administrator. The bootstrap password must be at least 10 characters. Remove these bootstrap variables after the admin account is created.

## Configuration and storage

- `CLEARANCE_DATABASE_PATH`: SQLite file path (defaults to `backend/clearance.db`).
- `CLEARANCE_UPLOAD_DIR`: private document storage directory (defaults to `backend/clearance_uploads`).
- `CLEARANCE_CORS_ORIGINS`: comma-separated allowed frontend origins (defaults to local `localhost` and `127.0.0.1`).
- `CLEARANCE_DEMO_MODE`: seed demo accounts and one sample application on a new database; defaults to `false`.
- `CLEARANCE_BOOTSTRAP_ADMIN_EMAIL` and `CLEARANCE_BOOTSTRAP_ADMIN_PASSWORD`: initial super-admin credentials for an empty database.
- `NEXT_PUBLIC_API_URL`: frontend API origin (defaults to `http://127.0.0.1:8000`).

Uploaded documents are limited to PDF, PNG, and JPEG files (10 MB). The API validates file signatures, stores files under random names, and requires an authenticated, appropriately scoped user to retrieve them. Passwords are stored as scrypt hashes; bearer sessions expire after 12 hours.

## Scope and deployment

This is a functional local-first MVP, not a fully hardened university production deployment. It uses SQLite and local file storage, a single faculty configuration, and an in-app notification feed; it does not yet provide email/SMS delivery, QR-code verification, multi-faculty tenant isolation, password reset/MFA, configurable session deadlines, or a full permissions editor. Before deployment with real student records, use private durable storage, HTTPS, backups, retention controls, institutional identity integration, and a security/privacy review. Do not enable demo mode in a production environment.

### Deploy the current SQLite version

The included `render.yaml` configures the API on Render with a persistent disk for the SQLite database and uploaded documents. Its `0.5c-512mb` compute plan and persistent disk are paid resources; review the current price in Render before creating the Blueprint.

1. In Render, create a Blueprint from `dejoe659/faculty-clearance-system` and approve the `faculty-clearance-api` service. During setup, enter:
   - `CLEARANCE_CORS_ORIGINS`: your deployed Vercel origin, for example `https://faculty-clearance-system.vercel.app` (no trailing slash).
   - `CLEARANCE_BOOTSTRAP_ADMIN_EMAIL`: your own administrator email.
   - `CLEARANCE_BOOTSTRAP_ADMIN_PASSWORD`: a unique password of at least 10 characters. Keep it private.
2. Wait until the API's `/health` endpoint reports `{"status":"healthy"}`. Copy the Render service URL.
3. In Vercel, import the same GitHub repository and set its **Root Directory** to `frontend`. Add `NEXT_PUBLIC_API_URL` with the Render API URL (for example `https://faculty-clearance-api.onrender.com`) and deploy.
4. If Vercel assigns a different production domain, update `CLEARANCE_CORS_ORIGINS` in Render to that exact origin and redeploy the API.
5. Sign in at the Vercel site with the bootstrap admin email and password. Create staff from **Students**. Then remove the bootstrap email/password variables from Render.

The first Render deployment can use the expected `faculty-clearance-system.vercel.app` origin; if that name is unavailable, update CORS after Vercel provides the actual domain. Keep demo mode disabled. This SQLite deployment is suitable for a small pilot with a single API instance. For concurrent production traffic or multiple instances, migrate the backend to PostgreSQL and move uploads to private object storage before scaling. The current backend does not yet support PostgreSQL.
