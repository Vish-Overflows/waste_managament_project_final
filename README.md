# Campus Waste Management System

A full-stack campus sanitation operations platform for recording, quantifying, processing, and reviewing waste collection data.

The project was built for a real campus waste-management workflow with separate portals for field staff, waste operators, and administrators.

## Live Deployment

Public Railway deployment:

https://wastemanagementprojectfinal-production.up.railway.app

Health check:

https://wastemanagementprojectfinal-production.up.railway.app/healthz

Expected production health response:

```json
{
  "status": "ok",
  "database": "postgresql",
  "persistent": true
}
```

## Tech Stack

- Frontend: React, TypeScript, Vite, Tailwind CSS
- Backend: FastAPI, SQLAlchemy, Pydantic
- Database: PostgreSQL on Railway, SQLite fallback for local development
- Auth: JWT-based role access
- Deployment: Railway with Docker
- Testing: Python `unittest` API integration tests

## Main Features

- Role-based access for staff, operator, and admin users
- Staff housing collection logging
- Manual housing block entry with validation from `1` to `34`
- Room number recording with current-date locking
- Dry waste quantification by source, subtype, and quantity
- Wet waste intake with mandatory compost/biogas machine allocation
- Compost distribution logging with multiple recipients
- Admin dashboard for operational analytics
- CSV export for last 7 days of analytics
- Admin-only operational data reset
- Persistent PostgreSQL deployment
- API integration tests for core workflows

## User Roles

### Staff

Staff users record collection from housing rooms.

Current flow:

- Enter housing block number from `1` to `34`
- Enter room number
- Date is automatically recorded by the system
- Submit collection record

Example entries:

- `1-202`
- `3-101`
- `4-501`

### Operator

Operators quantify waste and log processing details.

Dry waste flow:

- Select source location
- Select dry waste subtype
- Enter quantity in kg

Dry waste source examples:

- Housing Block
- Sports Complex
- Hostel Area
- Food Outlet
- Academic Area
- Research Park
- Other Public Bin

Wet waste flow:

- Select wet waste type
- Enter wet quantity in kg
- Enter quantity sent to compost machine and/or biogas machine
- Save wet intake record

Compost distribution flow:

- Enter one or more recipients
- Enter quantity issued to each recipient
- System prevents distribution beyond the theoretical maximum based on compost-machine intake

Example distribution:

- Workers: `2 kg`
- Gardeners: `3 kg`

### Admin

Admins can view the complete operational picture.

Admin capabilities:

- View collection counts and waste totals
- View dry/wet waste breakdown
- View source analytics for dry waste
- View operator throughput
- View individual staff collection records
- View individual operator quantification records
- View compost and biogas processing status
- Export last 7 days of analytics as CSV
- Clear operational records when a fresh demo/data reset is needed

The reset action clears operational records only. Login users remain available.

## Demo Credentials

Staff accounts do not require a password.

| Role | Username | Password |
| --- | --- | --- |
| Staff | `staff1` | none |
| Staff | `staff2` | none |
| Staff | `staff3` | none |
| Operator | `operator1` | `op_key` |
| Admin | `admin` | `admins_key` |

## Local Development

### Backend

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend URL:

```text
http://127.0.0.1:8000
```

Health check:

```text
http://127.0.0.1:8000/healthz
```

### Frontend

In a second terminal:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Frontend URL:

```text
http://127.0.0.1:5173
```

## Run Tests

From the repository root:

```bash
PYTHONPATH=backend .venv/bin/python -m unittest backend.tests.test_api
```

Build frontend:

```bash
cd frontend
npm run build
```

## Railway Deployment Notes

This repository is deployed from the `production-upgrade` branch using the root `Dockerfile`.

Railway app service variables:

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
SECRET_KEY=<long-random-secret>
SECURE_COOKIES=false
WEB_CONCURRENCY=1
APP_TIMEZONE=Asia/Kolkata
```

Do not manually set `PORT`. The Docker command listens on Railway's provided port and falls back to `8000` locally.

The app should report PostgreSQL persistence at `/healthz` after deployment:

```json
{
  "status": "ok",
  "database": "postgresql",
  "persistent": true
}
```

## Project Structure

```text
backend/
  app/
    api/            FastAPI route modules
    core/           config and security
    models.py       SQLAlchemy models
    schemas.py      Pydantic schemas
    time_utils.py   campus timezone helpers
  tests/            API integration tests

frontend/
  src/
    App.tsx         main React application
    lib/api.ts      API client helpers
    types.ts        shared frontend types

Dockerfile          production container build
docker-compose.yml  local production-style stack
```

## Resume Summary

Built and deployed a full-stack campus waste management platform with role-based workflows for staff, operators, and admins, using React, FastAPI, PostgreSQL, and Railway. Implemented collection logging, dry/wet waste quantification, compost and biogas processing, compost distribution, admin analytics dashboards, CSV reporting, persistent database deployment, and API integration tests.
