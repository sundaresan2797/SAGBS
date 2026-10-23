# Employee Management System

> **Full documentation is in the [`docs/`](docs/README.md) folder:** install and run, system overview, roles and
> permissions, business rules, settings reference, a user guide by role, known limitations and a handover checklist.
> Where this README and `docs/` differ, `docs/` is the current one.

A modular-monolith HR platform: FastAPI + PostgreSQL + Redis on the backend, React + TypeScript + Vite on the frontend. Covers employees, departments, designations, attendance, leave, holidays, tasks, documents, notifications, audit logs, and an HR dashboard with Redis-backed caching.

## Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy 2.x (async), Alembic, PostgreSQL, Redis, JWT auth
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, React Router, React Hook Form + Zod, Recharts, Axios

## Architecture

Layered per module: `router → service → repository → database`. No business logic in route handlers, no raw SQL scattered through the app. See `backend/app/` for the module layout (`api/v1/endpoints`, `services`, `repositories`, `models`, `schemas`).

Redis is used only for caching, rate limiting, and other ephemeral data — PostgreSQL is the single source of truth for all business records. Cache keys follow `ems:<domain>:<...>`; every write path that changes cached data explicitly invalidates the relevant keys (see `app/core/redis.py` for `CacheKeys`/`CacheTTL`, and `services/*_service.py` for invalidation calls).

## Prerequisites

- Docker + Docker Compose **or** Python 3.12+, Node.js 20+, PostgreSQL 16, and Redis installed locally
- No other accounts/services are required — everything runs locally

## Option A: Run with Docker Compose (recommended)

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
docker compose up --build
```

This starts Postgres, Redis, the backend (migrations run automatically on container start), and the frontend dev server.

- Frontend: http://localhost:5173
- Backend API docs: http://localhost:8000/docs (Swagger) and http://localhost:8000/redoc
- Health check: http://localhost:8000/api/v1/health

Then seed demo data (roles, departments, leave types, and one demo user per role):

```bash
docker compose exec backend python -m app.seed
```

## Option B: Run locally without Docker

### 1. Database and Redis

Create a Postgres database and user, and make sure Redis is running:

```bash
psql -U postgres -c "CREATE ROLE ems_app WITH LOGIN PASSWORD 'ems_app_password';"
psql -U postgres -c "CREATE DATABASE employee_management OWNER ems_app;"
redis-server &
```

(A `employee_management_test` database, owned by the same role, is needed if you want to run the backend test suite — see Testing below.)

### 2. Backend

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set DATABASE_URL / DATABASE_URL_SYNC to match the role/db you created

alembic upgrade head
python -m app.seed

uvicorn app.main:app --reload
```

Backend runs at http://localhost:8000. Swagger UI at `/docs`, ReDoc at `/redoc`.

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Frontend runs at http://localhost:5173. The browser only ever calls its own `/api/v1`; the frontend dev server forwards that to the backend at `BACKEND_URL` (default `http://127.0.0.1:8000`, set in `frontend/.env`).

## Running on another machine, or opening it from another device

**Open it from a phone or another computer on the same Wi-Fi.** Use this machine's network address or its name, for example `http://192.168.1.4:5173` or `http://<computer-name>.local:5173`. The computer name keeps working when the network (and so the IP address) changes. Nothing needs configuring: the browser calls the frontend's own `/api/v1` and the frontend forwards it to the backend, so there is no IP address anywhere in the code. To open it by a company domain, add it to `ALLOWED_HOSTS` in `frontend/.env`.

**Move the project to a Windows PC or another Mac.**

1. Use Docker Compose (Option A above). It starts Postgres, Redis, the backend and the frontend together, which avoids installing Redis on Windows. In Docker the frontend reaches the backend at `http://backend:8000` (set by `docker-compose.yml`).
2. Without Docker: install Python 3.12+, Node 20+, PostgreSQL 16 and Redis, then create a fresh virtual environment (`python -m venv venv`, `pip install -r requirements.txt`) and run `npm install`. Do not copy `backend/venv` or `frontend/node_modules` between machines: they are specific to the operating system.
3. Copy `backend/.env.example` to `backend/.env` and `frontend/.env.example` to `frontend/.env`, then set your own `JWT_SECRET_KEY` and database password.
4. Run `alembic upgrade head` and `python -m app.seed`. The new machine starts with an empty database. **Your company's data does not travel with the code.** To move it, make a `pg_dump` of the database and restore it there, and copy the `backend/uploads` folder.
5. `backend/.env`, `backend/backups/` (database dumps) and `backend/uploads/` contain secrets and real employee data. They are ignored by git; do not send them by e-mail or zip.
6. `backend/scripts/demo.sh` is a Mac/Linux helper (Git Bash or WSL on Windows) and is only for the optional demo copy.

## Demo accounts

**Development and trial only. Never run the seed on a real installation.** Seeded by `python -m app.seed`. Every demo account shares one known starter password (see `backend/app/seed.py`) and has `must_change_password` set. A real installation must create its first Founder and Admin logins with strong passwords instead (see `docs/08-handover-checklist.md`, step 5).

| Email | Role |
|---|---|
| admin@example.com | ADMIN |
| hr@example.com | HR |
| manager@example.com | MANAGER |
| employee@example.com | EMPLOYEE |

The seed script is idempotent — safe to re-run.

## Testing

Backend tests run against a **real Postgres database** (no SQLite, per design) with full transactional isolation per test (each test runs in a savepoint that's rolled back afterward, so tests never see each other's data). Redis is also cleared between tests since it's a real shared instance.

```bash
cd backend
# one-time: createdb for tests (or let CI/your own tooling do it)
psql -U postgres -c "CREATE DATABASE employee_management_test OWNER ems_app;"

source venv/bin/activate
pytest tests/ -v
```

274 tests cover: authentication (login, refresh, rate limiting, password reset), RBAC and permission scoping, employee CRUD with manager-scoped visibility, attendance business rules (duplicate check-in/out, inactive employees), leave workflow (balance checks, overlap detection, approval authorization), tasks (assignment scoping, status updates, comments), documents (upload validation, download authorization), notifications, audit logging, and dashboard caching/invalidation.

Frontend type-checking and production build:

```bash
cd frontend
npx tsc -b
npm run build
```

## Project structure

```
employee-management-system/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app, middleware, exception handlers
│   │   ├── config/               Settings (pydantic-settings, .env-driven)
│   │   ├── database/              Async engine/session, declarative base
│   │   ├── models/                 SQLAlchemy models + enums
│   │   ├── schemas/                Pydantic request/response schemas
│   │   ├── repositories/            DB query layer (one per aggregate)
│   │   ├── services/                Business logic, cache invalidation, audit logging
│   │   ├── api/v1/endpoints/         FastAPI routers (thin - delegate to services)
│   │   ├── core/                     security (JWT/bcrypt), Redis service, exceptions
│   │   ├── middleware/                Request logging, centralized error handlers
│   │   ├── dependencies/               Auth/permission FastAPI dependencies
│   │   ├── utils/                       Timezone helpers, permission catalog
│   │   └── seed.py                       Idempotent demo-data seed script
│   ├── alembic/                            Migrations
│   ├── tests/                                Pytest suite (real Postgres, no mocks)
│   └── Dockerfile
├── frontend/
│   └── src/
│       ├── pages/                Route-level page components
│       ├── layouts/                AppLayout (sidebar + topbar, role-aware nav)
│       ├── components/ui/           Shared primitives (Button, Modal, Table, forms...)
│       ├── services/                 Axios-based API clients, one per feature
│       ├── hooks/                     useAuth (auth context), useToast
│       ├── routes/                     ProtectedRoute / PermissionRoute guards
│       ├── types/                       Shared TypeScript types mirroring backend schemas
│       └── utils/                        Role-based navigation config, token storage
└── docker-compose.yml
```

## Roles and permissions

Seven roles — `ADMIN`, `FOUNDER`, `HR`, `EXECUTIVE`, `MANAGER`, `ACCOUNTANT`, `EMPLOYEE` — each mapped to a fixed set of permission codes (see `backend/app/utils/permissions.py`), enforced on every protected endpoint via FastAPI dependencies (`require_permission`, `require_roles`). The frontend nav and route guards mirror these permissions but the backend is the actual authority — hidden UI is not a substitute for server-side checks.

Notable scoping rules (all enforced server-side, with test coverage):
- Managers only see/manage their **direct reports** — not the whole org.
- Employees can only view/edit their own attendance, leave, tasks, and documents.
- Deactivating an employee immediately disables their login (their linked user account is deactivated).
- Only an employee's **direct manager** can approve or reject their leave. HR, the Founder and the Admin (`leave:manage_all`) can see every request but cannot approve one unless they are that person's direct manager.

## Security notes

- Passwords hashed with bcrypt (via passlib); JWT access + refresh tokens; secrets read from environment variables only.
- Login and password-reset-request endpoints are rate-limited via Redis (5 attempts / 5 minutes by default).
- Document downloads are streamed through an authenticated/authorized endpoint (`GET /documents/{id}/download`) — uploaded files are never served from a public static path.
- Document uploads are **PDF only**, checked by file content and size (`MAX_UPLOAD_SIZE_MB`, 5 by default). Profile photos (JPG, PNG or WebP) are re-encoded as a clean 400 x 400 JPEG. File names are always generated by the server, never taken from the client, to prevent path traversal.
- All timestamps are stored in UTC; the Postgres session timezone is forced to UTC at connection time so server-side date/time aggregations aren't silently shifted by the host OS's timezone. Calendar-only concerns (leave dates, holidays) use plain `DATE` columns, never timestamps.

## Extending to V2/V3

The architecture is intentionally a modular monolith with clear service boundaries, so the roadmap items called out in the spec — payroll, recruitment, onboarding, email notifications, and eventually AI-assisted features — can be added as new modules (new model + schema + repository + service + router) without restructuring what's here. The document storage layer (`app/services/storage_service.py`) already isolates local-disk I/O behind a small interface so it can be swapped for S3/Azure Blob without touching calling code.
