# Campus Waste Management Portal

Internal waste-management data entry application for campus sanitation staff.

## Features

- Session-based login with demo users
- Separate workflows for dry, wet, and hazardous waste
- Wet waste weekly compost/biogas update that uses total wet waste logged so far
- SQLite-backed storage for entries and weekly wet processing updates
- Admin dashboard with totals, recent entries, and wet processing status

## Demo Credentials

- `worker1 / password`
- `worker2 / password`
- `admin / password`

## Run Locally

```bash
python3 server.py
```

Open `http://127.0.0.1:8000`

## Run Tests

```bash
python3 -m unittest test_app.py
```

## Production Upgrade Branch

The `production-upgrade` branch keeps `main` frozen as the working baseline and builds the production system alongside it.

### Upgraded Stack

- `backend/`
  FastAPI API, SQLAlchemy ORM, JWT authentication, PostgreSQL-ready persistence, role-based access
- `frontend/`
  React + TypeScript + Vite + Tailwind interface with separate staff, operator, and admin workflows
- `docker-compose.yml`
  local production-style stack for `frontend + backend + postgres + nginx`

### Why This Upgrade Is Safer

- Postgres stores records durably across days and weeks instead of relying on a local SQLite file
- Gunicorn + Uvicorn workers give the API a more reliable production server path than Python's built-in server
- The admin dashboard now includes trend, block, and operator analytics
- Staff, operator, and admin flows are separated cleanly instead of sharing one form

### Local Production-Style Run

```bash
docker compose up --build
```

Expected services:

- frontend served behind Nginx
- backend API on FastAPI
- PostgreSQL for durable records
- reverse proxy for a single entry point on `http://127.0.0.1`

### Demo Users On The Upgrade Branch

- `staff1 / password`
- `staff2 / password`
- `operator1 / password`
- `admin / password`

### Railway Deployment For `production-upgrade`

Deploy the upgraded branch as three Railway services in the same project:

1. `PostgreSQL`
   Add Railway's PostgreSQL template. Railway exposes `DATABASE_URL` and related `PG*` variables to connect services.

2. `backend`
   Connect the same GitHub repository, but set the branch to `production-upgrade`.

   Required variables:

   - `RAILWAY_DOCKERFILE_PATH=railway/backend.Dockerfile`
   - `DATABASE_URL=${{Postgres.DATABASE_URL}}`
   - `SECRET_KEY=<long-random-secret>`
   - `WEB_CONCURRENCY=2`
   - `SECURE_COOKIES=false`
   - `CORS_ORIGINS=https://<your-frontend-service>.up.railway.app`

3. `frontend`
   Connect the same GitHub repository, again using the `production-upgrade` branch.

   Required variables:

   - `RAILWAY_DOCKERFILE_PATH=railway/frontend.Dockerfile`
   - `VITE_API_BASE_URL=https://<your-backend-service>.up.railway.app/api`

Why the frontend needs an API variable:

- the production-upgrade frontend is deployed as a separate service from the backend
- it uses bearer tokens in the browser and must know the backend public URL at build time
- `frontend/.env.example` shows the same setting for local development

Recommended deployment order:

1. create the PostgreSQL service
2. deploy the backend and confirm `/healthz` works
3. deploy the frontend with `VITE_API_BASE_URL` pointing to the backend URL
4. open the frontend domain and test all 3 roles

Railway docs used for this setup:

- Services: https://docs.railway.com/services
- Dockerfile paths: https://docs.railway.com/deploy/dockerfiles
- Variables: https://docs.railway.com/variables
- PostgreSQL: https://docs.railway.com/guides/postgresql

## Stable Public Deployment

The exact same app can be deployed as a public website on Render using the included [Dockerfile](/Users/vishnusinha/Documents/project_sushoban/Dockerfile:1).

Recommended setup:

- Create a new Render `Web Service`
- Choose the `Docker` runtime
- Deploy this repository
- Attach a persistent disk
- Set `DB_PATH=/app/data/waste_management.db`

Why the disk matters:

- this app stores data in `SQLite`
- without a persistent disk, Render's filesystem is ephemeral and your saved entries can be lost on restart or redeploy

Suggested disk mount path:

- `/app/data`

Suggested Render URL outcome:

- `https://your-service-name.onrender.com`
