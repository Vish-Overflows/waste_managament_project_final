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
