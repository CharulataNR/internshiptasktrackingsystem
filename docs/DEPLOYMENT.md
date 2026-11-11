# Deployment Guide - Render (public HTTPS link)

## 1. Put the code on GitHub
1. Create a free account at github.com and a **new empty repository** (for example `intern-task-tracker`).
2. In VS Code open a terminal in the project folder:
```powershell
git init
git add .
git commit -m "Internship Task Tracking System"
git branch -M main
git remote add origin https://github.com/<your-username>/intern-task-tracker.git
git push -u origin main
```
(`.gitignore` already excludes the local database, logs and `venv`.)

## 2. Create the web service on Render
1. Sign in at render.com with GitHub.
2. **New > Web Service** > select your repository.
3. Settings:
   * Runtime: **Python 3**
   * Build command: `pip install -r requirements.txt`
   * Start command: `gunicorn wsgi:app --workers 1 --threads 4 --timeout 60`
   * Health check path: `/healthz`
4. Environment variables:
   | Key | Value |
   |---|---|
   | `APP_ENV` | `production` |
   | `SECRET_KEY` | any long random string (Render can generate one) |
   | `ADMIN_PASSWORD` | a strong password for the `admin` account |
   | `PYTHON_VERSION` | `3.12.3` |
   | `SEED_DEMO` | `1` for demo data, `0` for an empty system |
5. Click **Create Web Service**. After the build finishes (2-4 minutes) Render shows your link, e.g. `https://intern-task-tracker.onrender.com`. It is served over HTTPS automatically.

Alternative: **New > Blueprint** and pick the repository; `render.yaml` fills in all of the above.

## 3. Share with the internship coordinator
Send the link and a login (for example the `admin` account, or create a Team Lead account in **Settings > Add user**). Change the demo Team Lead passwords first (Settings > reset password) or delete those accounts.

## Things to know
* **Free plan sleeps** after ~15 minutes without visits; the first request afterwards takes about 30-60 seconds.
* **Free plan disk is temporary.** The SQLite database is recreated (and demo data re-seeded) whenever the service restarts or redeploys. For data that must survive, add a Render **Persistent Disk** (paid plan), mount it at `/var/data` and set `DATABASE_PATH=/var/data/tracker.db`.
* Keep **one worker** (as configured). SQLite is a single-file database and this avoids write contention.
* Logs are visible in the Render dashboard (the app logs to the console as well as `logs/app.log`).
* After deploying, test: log in, open the dashboard, add an intern, download an Excel report.

## Troubleshooting
| Symptom | Fix |
|---|---|
| Build fails on `pandas` | Make sure `PYTHON_VERSION` is 3.12.3 (set in the dashboard) |
| Login works but you are logged out immediately | `APP_ENV=production` requires HTTPS cookies; use the https:// link, not http:// |
| Charts blank | The browser must reach cdn.jsdelivr.net (Chart.js/Bootstrap load from CDN) |
| Overdue dates off by a day | Set `APP_TIMEZONE` (default `Asia/Kolkata`) |
