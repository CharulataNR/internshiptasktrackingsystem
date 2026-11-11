# InternTrack - Internship Task Tracking System

A browser-based web application to manage interns, DIT IDs, teams, tasks, deadlines, submissions and assessments, with dashboards, charts and Excel reports.

**Stack:** Python 3 + Flask, SQLite, Bootstrap 5, Chart.js, Pandas + OpenPyXL. No terminal UI; everything runs in the browser.

## Features
| Module | What it does |
|---|---|
| Dashboard | 10 KPI cards, status pipeline bar, 4 interactive charts (status, team completion, intern performance, monthly submissions), overdue and upcoming lists |
| Intern Master | Add / view / edit / delete, search (name, DIT ID, email), filter by college and team, unique DIT ID, email and phone validation |
| Team Management | Create teams, assign leader, add/remove members, per-team progress and completion % |
| Task Tracker | Create/assign/edit tasks, quick status change, dates, automatic **Overdue** detection, filters (team, college, status, assessment, date range), pagination |
| Assessment Management | Approve / reject / review with score 0-100 and remarks, full history |
| Reports | 8 formatted Excel reports + printable Team Lead report |
| Security | Hashed passwords, login/logout, Admin and Team Lead roles, CSRF tokens, secure sessions, login throttling, activity log |

## Quick start on Windows with VS Code
1. Install **Python 3.10 or newer** from python.org (tick *Add python.exe to PATH*) and **VS Code** with the *Python* extension.
2. Unzip the project, then in VS Code choose **File > Open Folder** and select `internship_tracker`.
3. Open a terminal in VS Code (**Terminal > New Terminal**) and run:
```powershell
python -m pip install --user -r requirements.txt
python app.py
```
   (Use `py` instead of `python` if `python` is not recognised.) A virtual environment is optional: on PCs where *Device Guard* / company policy blocks `venv\Scripts\pip.exe` or `python.exe`, skip `venv` and use the commands above.
4. Open **http://127.0.0.1:5000** in your browser.

Shortcut: double-click `run.bat` - it installs the packages and starts the site for you (no venv needed).

The first start creates `instance/tracker.db` and loads synthetic demo data (25 interns, 5 teams, about 100 tasks). To start empty set `SEED_DEMO=0` before the first run. To reset, stop the app and delete the `instance` folder.

## Demo accounts
| Role | Username | Password |
|---|---|---|
| Administrator | `admin` | `Admin@123` |
| Team Lead (one per team) | `lead_web`, `lead_data`, `lead_cloud`, `lead_ai`, `lead_ui` | `Lead@1234` |

**Change these passwords (Settings page) before sharing the site publicly.**

## Run the tests
```powershell
python -m unittest discover -s tests -v
```
40 automated tests cover registration, duplicate DIT IDs, validation, teams, task assignment, status updates, overdue detection, score validation, Excel generation, dashboard figures, login, roles and CSRF. See `docs/TEST_CASES.md`.

## Deploy to the internet (Render, free HTTPS link)
Full steps are in `docs/DEPLOYMENT.md`. Short version: push the folder to GitHub, create a Render *Web Service* (or *Blueprint* using `render.yaml`), set `APP_ENV=production`, `SECRET_KEY`, `ADMIN_PASSWORD`; Render gives you `https://<name>.onrender.com`.
Note: Render's free plan has an ephemeral disk, so the SQLite file resets on each redeploy/restart. That is fine for a demo (demo data reloads automatically); use a paid persistent disk for permanent data (see the guide).

## Configuration (environment variables)
`APP_ENV` (development|production), `SECRET_KEY`, `DATABASE_PATH`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SEED_DEMO` (1|0), `APP_TIMEZONE` (default Asia/Kolkata, decides when a task becomes overdue), `PAGE_SIZE`, `LOG_DIR`.

## Project layout
```
app.py            Flask app factory, routes, auth, exports
config.py         settings from environment variables
database.py       SQLite helpers      schema.sql   table definitions
queries.py        SQL: tasks view with overdue logic, filters, statistics
validators.py     server-side validation rules
reports.py        Excel report builder (Pandas + OpenPyXL)
security.py       CSRF, login_required, role checks
seed.py           synthetic demo data
templates/ static/   Jinja2 pages, CSS, JavaScript (Chart.js dashboard)
tests/            unittest suite       docs/   project documentation
Procfile render.yaml requirements.txt runtime.txt wsgi.py   deployment files
```

## Business rules worth knowing
* A task is **Overdue** automatically when it is *Not Started* or *In Progress* and its due date is before today.
* Dashboard **Pending** = *Not Started*. The "Pending Tasks" Excel report lists all open work (everything not yet Completed).
* **Assessment pending** = submitted/under-review/completed/rejected tasks whose assessment status is still Pending.
* Approving an assessment completes the task; rejecting it marks the task Rejected; re-submitting a rejected task resets the assessment to Pending.
* Team Leads work only inside their own team; Admins manage interns, teams and users.
* Phone numbers are validated as 10-digit Indian mobiles (change `PHONE_RE` in `validators.py` for other regions).
