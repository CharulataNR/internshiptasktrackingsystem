"""Internship Task Tracking System - Flask application (routes, auth, exports)."""
import logging
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import (Flask, abort, current_app, flash, g, jsonify, redirect, render_template, request, send_file, session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import database
import queries as Q
import reports
import seed
import validators as V
from config import Config, INSTANCE_DIR
from security import csrf_token, login_required, roles_required, safe_next, verify_csrf

logger = logging.getLogger("tracker")
_FAILED_LOGINS = {}  # (ip, username) -> [timestamps]; simple brute-force throttle
MAX_FAILS, FAIL_WINDOW = 5, 300


def create_app(overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    _FAILED_LOGINS.clear()
    app.config["SECRET_KEY"] = app.config.get("SECRET_KEY") or _load_secret_key(app)
    if app.config["APP_ENV"] == "production":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # Render terminates HTTPS
    _setup_logging(app)

    database.init_db(app.config["DATABASE"])
    _bootstrap_data(app)
    app.teardown_appcontext(database.close_db)
    _register_hooks(app)
    _register_routes(app)
    _register_errors(app)
    logger.info("Application started (env=%s, db=%s)", app.config["APP_ENV"], app.config["DATABASE"])
    return app


# ------------------------------------------------------------------------------------------ setup helpers
def _load_secret_key(app):
    """Use SECRET_KEY env var; otherwise generate one once and persist it next to the database."""
    key_file = os.path.join(os.path.dirname(os.path.abspath(app.config["DATABASE"])), "secret.key")
    os.makedirs(os.path.dirname(key_file), exist_ok=True)
    if os.path.exists(key_file):
        with open(key_file, encoding="utf-8") as fh:
            return fh.read().strip()
    key = secrets.token_hex(32)
    with open(key_file, "w", encoding="utf-8") as fh:
        fh.write(key)
    return key


def _setup_logging(app):
    root = logging.getLogger("tracker")
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)
    try:
        os.makedirs(app.config["LOG_DIR"], exist_ok=True)
        fh = RotatingFileHandler(os.path.join(app.config["LOG_DIR"], "app.log"), maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:  # read-only file systems: console logging is enough
        pass


def _today(app=None):
    tz = (app or current_app).config["TIMEZONE"]
    try:
        return datetime.now(ZoneInfo(tz)).date()
    except ZoneInfoNotFoundError:
        return datetime.now().date()


def _bootstrap_data(app):
    conn = database.connect(app.config["DATABASE"])
    try:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            seed.ensure_admin(conn, app.config["ADMIN_USERNAME"], app.config["ADMIN_PASSWORD"])
            admin_id = conn.execute("SELECT id FROM users WHERE username = ?", (app.config["ADMIN_USERNAME"],)).fetchone()[0]
            if app.config["SEED_DEMO"] and conn.execute("SELECT COUNT(*) FROM interns").fetchone()[0] == 0:
                seed.seed_demo(conn, _today(app), admin_id)
                logger.info("Demo data loaded")
    finally:
        conn.close()


# ------------------------------------------------------------------------------------------ hooks
def _register_hooks(app):
    @app.before_request
    def _security_and_user():
        if request.endpoint == "static":
            return
        verify_csrf()
        g.user = None
        uid = session.get("user_id")
        if uid:
            row = database.get_db().execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (uid,)).fetchone()
            if row:
                g.user = row
            else:
                session.clear()

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if app.config["APP_ENV"] == "production":
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.endpoint != "static":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    app.jinja_env.globals["csrf_token"] = csrf_token  # global so imported macros can use it

    @app.context_processor
    def _inject():
        return {
            "current_user": g.get("user"),
            "TASK_STATUSES": V.TASK_STATUSES, "ASSESSMENT_STATUSES": V.ASSESSMENT_STATUSES,
            "today": _today(app).isoformat(),
        }

    @app.template_filter("fmt_date")
    def fmt_date(value):
        if not value:
            return "-"
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d %b %Y")
        except ValueError:
            return value

    @app.template_filter("fmt_dt")
    def fmt_dt(value):
        try:
            return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").strftime("%d %b %Y, %H:%M")
        except ValueError:
            return value or "-"

    @app.template_filter("slug")
    def slug(value):
        return "".join(c if c.isalnum() else "-" for c in str(value).lower()).strip("-")

    @app.template_global()
    def page_url(page):
        args = request.args.to_dict()
        args["page"] = page
        return url_for(request.endpoint, **request.view_args, **args)


def _register_errors(app):
    def render(code, title, message):
        return render_template("error.html", code=code, title=title, message=message), code

    @app.errorhandler(400)
    def e400(e):
        return render(400, "Request could not be processed", getattr(e, "description", "Bad request."))

    @app.errorhandler(403)
    def e403(_e):
        return render(403, "Access denied", "Your role does not have permission to open this page or perform this action.")

    @app.errorhandler(404)
    def e404(_e):
        return render(404, "Page not found", "The page or record you are looking for does not exist.")

    @app.errorhandler(413)
    def e413(_e):
        return render(413, "Request too large", "The submitted data is too large.")

    @app.errorhandler(sqlite3.Error)
    def edb(e):
        logger.exception("Database error: %s", e)
        return render(500, "Database error", "A database error occurred. The incident has been logged. Please try again.")

    @app.errorhandler(500)
    def e500(e):
        logger.exception("Unhandled error: %s", e)
        return render(500, "Something went wrong", "An unexpected error occurred. It has been logged.")


# ------------------------------------------------------------------------------------------ small utilities
def db():
    return database.get_db()


def today():
    return _today()


def scope_team():
    """None = admin (all data). Team leads are restricted to their own team (-1 = no team linked)."""
    u = g.user
    if u["role"] == "admin":
        return None
    return u["team_id"] if u["team_id"] else -1


def log_activity(action, entity=None, entity_id=None, details=None, user=None):
    u = user or g.get("user")
    try:
        db().execute(
            "INSERT INTO activity_logs (user_id, username, action, entity, entity_id, details, ip_address) VALUES (?,?,?,?,?,?,?)",
            (u["id"] if u else None, u["username"] if u else None, action, entity, entity_id, details, request.remote_addr))
        db().commit()
    except sqlite3.Error:
        logger.exception("Could not write activity log")
    logger.info("%s | user=%s | %s #%s | %s", action, u["username"] if u else "-", entity, entity_id, details or "")


def write(action_fn, ok_message=None):
    """Run DB writes in a transaction with user-friendly error handling. Returns True on success."""
    try:
        action_fn()
        db().commit()
        if ok_message:
            flash(ok_message, "success")
        return True
    except sqlite3.IntegrityError as e:
        db().rollback()
        logger.warning("Integrity error: %s", e)
        flash("The change could not be saved because it conflicts with existing data (duplicate or linked record).", "danger")
    except sqlite3.Error as e:
        db().rollback()
        logger.exception("Database error: %s", e)
        flash("A database error occurred. Nothing was saved. Please try again.", "danger")
    return False


def paginate(total, page, per_page):
    pages = max(1, -(-total // per_page))
    page = min(max(page, 1), pages)
    return {"page": page, "pages": pages, "total": total, "per_page": per_page,
            "start": (page - 1) * per_page + 1 if total else 0, "end": min(page * per_page, total)}


def page_arg():
    try:
        return max(1, int(request.args.get("page", 1)))
    except ValueError:
        return 1


def team_allowed(team_id):
    s = scope_team()
    return s is None or s == team_id


def intern_or_404(intern_id):
    row = Q.get_intern(db(), intern_id)
    if not row or not team_allowed(row["team_id"]):
        abort(404)
    return row


def task_or_404(task_id):
    row = Q.get_task(db(), today(), task_id)
    if not row or (scope_team() is not None and row["team_id"] != scope_team()):
        abort(404)
    return row


def apply_task_rules(old, data):
    """Keep task status and assessment consistent (only reacts to what the user actually changed)."""
    old_assess = old["assessment_status"] if old else "Pending"
    old_status = old["status"] if old else None
    if data["assessment_status"] != old_assess:
        if data["assessment_status"] == "Approved":
            data["status"] = "Completed"
        elif data["assessment_status"] == "Rejected":
            data["status"] = "Rejected"
        elif data["assessment_status"] == "Under Review" and data["status"] == "Submitted":
            data["status"] = "Under Review"
    elif data["status"] == "Submitted" and old_status not in (None, "Submitted") and old_assess in ("Approved", "Rejected"):
        data["assessment_status"], data["assessment_score"] = "Pending", None  # resubmission restarts assessment
    if data["status"] in ("Submitted", "Under Review", "Completed") and not data["submission_date"]:
        data["submission_date"] = today().isoformat()
    return data


def save_task(task_id, data, user_id, old=None):
    d = db()
    if task_id is None:
        cur = d.execute(
            """INSERT INTO tasks (task_code, title, description, intern_id, assigned_date, due_date, submission_date, status,
                                  assessment_status, assessment_score, remarks, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("TMP-" + secrets.token_hex(6), data["title"], data["description"], data["intern_id"], data["assigned_date"],
             data["due_date"], data["submission_date"], data["status"], data["assessment_status"], data["assessment_score"],
             data["remarks"], user_id))
        task_id = cur.lastrowid
        d.execute("UPDATE tasks SET task_code = ? WHERE id = ?", (f"TSK-{task_id:04d}", task_id))
    else:
        d.execute(
            """UPDATE tasks SET title=?, description=?, intern_id=?, assigned_date=?, due_date=?, submission_date=?, status=?,
                                assessment_status=?, assessment_score=?, remarks=?, updated_at=datetime('now') WHERE id=?""",
            (data["title"], data["description"], data["intern_id"], data["assigned_date"], data["due_date"],
             data["submission_date"], data["status"], data["assessment_status"], data["assessment_score"], data["remarks"], task_id))
    changed = old is None and data["assessment_status"] != "Pending" or old is not None and (
        data["assessment_status"] != old["assessment_status"] or data["assessment_score"] != old["assessment_score"])
    if changed:
        d.execute("INSERT INTO assessments (task_id, assessor_id, status, score, remarks) VALUES (?,?,?,?,?)",
                  (task_id, user_id, data["assessment_status"], data["assessment_score"], data["remarks"]))
    return task_id


# ------------------------------------------------------------------------------------------ routes
def _register_routes(app):
    # ---------------------------------------------------------------- auth
    @app.route("/healthz")
    def healthz():
        try:
            db().execute("SELECT 1").fetchone()
            return jsonify(status="ok")
        except sqlite3.Error:
            return jsonify(status="db-error"), 500

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            key = (request.remote_addr, username.lower())
            now = time.time()
            recent = [t for t in _FAILED_LOGINS.get(key, []) if now - t < FAIL_WINDOW]
            _FAILED_LOGINS[key] = recent
            if len(recent) >= MAX_FAILS:
                logger.warning("Login throttled for %s", username)
                flash("Too many failed attempts. Please wait a few minutes and try again.", "danger")
                return render_template("login.html"), 429
            row = db().execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)).fetchone()
            if row and check_password_hash(row["password_hash"], password):
                session.clear()
                session["user_id"] = row["id"]
                session.permanent = True
                _FAILED_LOGINS.pop(key, None)
                g.user = row
                log_activity("LOGIN", "user", row["id"], "Signed in")
                return redirect(safe_next(request.args.get("next")) or url_for("dashboard"))
            recent.append(now)
            logger.warning("Failed login for username=%s ip=%s", username, request.remote_addr)
            flash("Invalid username or password.", "danger")
        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout():
        log_activity("LOGOUT", "user", g.user["id"], "Signed out")
        session.clear()
        flash("You have been signed out.", "info")
        return redirect(url_for("login"))

    # ---------------------------------------------------------------- dashboard
    @app.route("/")
    @login_required
    def dashboard():
        s = scope_team()
        stats = Q.dashboard_stats(db(), today(), s)
        overdue = Q.task_rows(db(), today(), "eff_status = 'Overdue'", scope_team=s, order="days_overdue DESC", limit=6)
        soon = Q.task_rows(db(), today(), "eff_status IN ('Not Started','In Progress') AND due_date BETWEEN :a AND :b",
                           {"a": today().isoformat(), "b": (today() + timedelta(days=7)).isoformat()}, scope_team=s, order="due_date", limit=6)
        return render_template("dashboard.html", stats=stats, overdue=overdue, soon=soon, teams=Q.team_stats(db(), today(), s))

    @app.route("/api/dashboard")
    @login_required
    def api_dashboard():
        s = scope_team()
        stats = Q.dashboard_stats(db(), today(), s)
        teams = Q.team_stats(db(), today(), s)
        perf = Q.intern_performance(db(), today(), s, 10)
        return jsonify(
            stats=stats,
            status=stats["status_counts"],
            teams={"labels": [t["name"] for t in teams], "completion": [t["completion_pct"] for t in teams],
                   "completed": [t["completed"] for t in teams], "total": [t["total"] for t in teams]},
            interns={"labels": [p["intern_name"] for p in perf], "completed": [p["completed"] for p in perf],
                     "avg_score": [p["avg_score"] or 0 for p in perf]},
            monthly=Q.monthly_submissions(db(), today(), s, 6))

    # ---------------------------------------------------------------- interns
    @app.route("/interns")
    @login_required
    def interns():
        s = scope_team()
        page = page_arg()
        per = app.config["PAGE_SIZE"]
        rows, total = Q.list_interns(db(), request.args, s, page, per)
        pg = paginate(total, page, per)
        if pg["page"] != page:
            rows, total = Q.list_interns(db(), request.args, s, pg["page"], per)
        return render_template("interns.html", interns=rows, pg=pg, colleges=Q.colleges(db(), s), teams=Q.team_options(db(), s))

    def _intern_form(intern=None, form=None, errors=None):
        return render_template("intern_form.html", intern=intern, form=form or {}, errors=errors or {}, teams=Q.team_options(db()))

    @app.route("/interns/new", methods=["GET", "POST"])
    @roles_required("admin")
    def intern_new():
        if request.method == "POST":
            data, errors = V.validate_intern(request.form, db())
            if errors:
                flash("Please correct the highlighted fields.", "danger")
                return _intern_form(form=request.form, errors=errors), 422
            def action():
                cur = db().execute("INSERT INTO interns (name, dit_id, email, phone, college, role, joining_date) VALUES (?,?,?,?,?,?,?)",
                                   (data["name"], data["dit_id"], data["email"], data["phone"], data["college"], data["role"], data["joining_date"]))
                data["id"] = cur.lastrowid
                if data["team_id"]:
                    Q.set_intern_team(db(), cur.lastrowid, data["team_id"])
            if write(action, f"Intern {data['name']} ({data['dit_id']}) was added."):
                log_activity("CREATE", "intern", data["id"], f"{data['name']} / {data['dit_id']}")
                return redirect(url_for("intern_detail", intern_id=data["id"]))
            return _intern_form(form=request.form), 500
        return _intern_form()

    @app.route("/interns/<int:intern_id>")
    @login_required
    def intern_detail(intern_id):
        intern = intern_or_404(intern_id)
        tasks, _t, _w = Q.list_tasks(db(), today(), {"intern": str(intern_id), "sort": "due"}, scope_team())
        return render_template("intern_detail.html", intern=intern, tasks=tasks)

    @app.route("/interns/<int:intern_id>/edit", methods=["GET", "POST"])
    @roles_required("admin")
    def intern_edit(intern_id):
        intern = intern_or_404(intern_id)
        if request.method == "POST":
            data, errors = V.validate_intern(request.form, db(), intern_id)
            if errors:
                flash("Please correct the highlighted fields.", "danger")
                return _intern_form(intern, request.form, errors), 422
            def action():
                db().execute("""UPDATE interns SET name=?, dit_id=?, email=?, phone=?, college=?, role=?, joining_date=?,
                                updated_at=datetime('now') WHERE id=?""",
                             (data["name"], data["dit_id"], data["email"], data["phone"], data["college"], data["role"], data["joining_date"], intern_id))
                Q.set_intern_team(db(), intern_id, data["team_id"])
            if write(action, "Intern details updated."):
                log_activity("UPDATE", "intern", intern_id, f"{data['name']} / {data['dit_id']}")
                return redirect(url_for("intern_detail", intern_id=intern_id))
            return _intern_form(intern, request.form), 500
        form = dict(intern)
        form["team_id"] = intern["team_id"] or ""
        return _intern_form(intern, form)

    @app.post("/interns/<int:intern_id>/delete")
    @roles_required("admin")
    def intern_delete(intern_id):
        intern = intern_or_404(intern_id)
        if write(lambda: db().execute("DELETE FROM interns WHERE id = ?", (intern_id,)),
                 f"Intern {intern['name']} and their {intern['task_count']} task(s) were deleted."):
            log_activity("DELETE", "intern", intern_id, f"{intern['name']} / {intern['dit_id']}")
        return redirect(url_for("interns"))

    # ---------------------------------------------------------------- teams
    @app.route("/teams")
    @login_required
    def teams():
        return render_template("teams.html", teams=Q.team_stats(db(), today(), scope_team()))

    def _team_form(team=None, form=None, errors=None):
        tid = team["id"] if team else None
        leaders = list(Q.unassigned_interns(db()))
        if tid:
            leaders = [{"id": m["id"], "name": m["name"], "dit_id": m["dit_id"]} for m in Q.team_members(db(), tid)] + leaders
        return render_template("team_form.html", team=team, form=form or {}, errors=errors or {}, leaders=leaders)

    def _save_team(team_id, data):
        d = db()
        if team_id is None:
            team_id = d.execute("INSERT INTO teams (name, description) VALUES (?, ?)", (data["name"], data["description"])).lastrowid
        else:
            d.execute("UPDATE teams SET name = ?, description = ? WHERE id = ?", (data["name"], data["description"], team_id))
        if data["leader_id"]:
            Q.set_intern_team(d, data["leader_id"], team_id)
        d.execute("UPDATE teams SET leader_id = ? WHERE id = ?", (data["leader_id"], team_id))
        return team_id

    @app.route("/teams/new", methods=["GET", "POST"])
    @roles_required("admin")
    def team_new():
        if request.method == "POST":
            data, errors = V.validate_team(request.form, db())
            if errors:
                flash("Please correct the highlighted fields.", "danger")
                return _team_form(form=request.form, errors=errors), 422
            holder = {}
            if write(lambda: holder.update(id=_save_team(None, data)), f"Team '{data['name']}' was created."):
                log_activity("CREATE", "team", holder["id"], data["name"])
                return redirect(url_for("team_detail", team_id=holder["id"]))
            return _team_form(form=request.form), 500
        return _team_form()

    @app.route("/teams/<int:team_id>")
    @login_required
    def team_detail(team_id):
        if not team_allowed(team_id):
            abort(404)
        stats = Q.team_stats(db(), today(), team_id=team_id)
        if not stats:
            abort(404)
        tasks, _t, _w = Q.list_tasks(db(), today(), {"team": str(team_id), "sort": "due"}, scope_team())
        return render_template("team_detail.html", team=stats[0], members=Q.team_members(db(), team_id),
                               tasks=tasks, free_interns=Q.unassigned_interns(db()))

    @app.route("/teams/<int:team_id>/edit", methods=["GET", "POST"])
    @roles_required("admin")
    def team_edit(team_id):
        row = db().execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
        if not row:
            abort(404)
        if request.method == "POST":
            data, errors = V.validate_team(request.form, db(), team_id)
            if errors:
                flash("Please correct the highlighted fields.", "danger")
                return _team_form(row, request.form, errors), 422
            if write(lambda: _save_team(team_id, data), "Team updated."):
                log_activity("UPDATE", "team", team_id, data["name"])
                return redirect(url_for("team_detail", team_id=team_id))
            return _team_form(row, request.form), 500
        return _team_form(row, {"name": row["name"], "description": row["description"] or "", "leader_id": row["leader_id"] or ""})

    @app.post("/teams/<int:team_id>/delete")
    @roles_required("admin")
    def team_delete(team_id):
        row = db().execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
        if not row:
            abort(404)
        if write(lambda: db().execute("DELETE FROM teams WHERE id = ?", (team_id,)), f"Team '{row['name']}' was deleted. Its interns are now unassigned."):
            log_activity("DELETE", "team", team_id, row["name"])
        return redirect(url_for("teams"))

    @app.post("/teams/<int:team_id>/members/add")
    @roles_required("admin")
    def team_member_add(team_id):
        if not db().execute("SELECT 1 FROM teams WHERE id = ?", (team_id,)).fetchone():
            abort(404)
        raw = request.form.get("intern_id", "")
        intern = db().execute("SELECT i.*, (SELECT team_id FROM team_members WHERE intern_id = i.id) AS team_id FROM interns i WHERE i.id = ?",
                              (raw,)).fetchone() if raw.isdigit() else None
        if not intern:
            flash("Please select an intern to add.", "danger")
        elif intern["team_id"] is not None:
            flash(f"{intern['name']} already belongs to a team. Edit the intern to move them.", "danger")
        elif write(lambda: Q.set_intern_team(db(), intern["id"], team_id), f"{intern['name']} was added to the team."):
            log_activity("ADD_MEMBER", "team", team_id, f"{intern['name']} / {intern['dit_id']}")
        return redirect(url_for("team_detail", team_id=team_id))

    @app.post("/teams/<int:team_id>/members/<int:intern_id>/remove")
    @roles_required("admin")
    def team_member_remove(team_id, intern_id):
        member = db().execute("""SELECT i.name, i.dit_id FROM team_members m JOIN interns i ON i.id = m.intern_id
                                 WHERE m.team_id = ? AND m.intern_id = ?""", (team_id, intern_id)).fetchone()
        if not member:
            abort(404)
        if write(lambda: Q.set_intern_team(db(), intern_id, None), f"{member['name']} was removed from the team."):
            log_activity("REMOVE_MEMBER", "team", team_id, f"{member['name']} / {member['dit_id']}")
        return redirect(url_for("team_detail", team_id=team_id))

    @app.post("/teams/<int:team_id>/leader")
    @roles_required("admin")
    def team_leader(team_id):
        raw = request.form.get("leader_id", "")
        member = db().execute("SELECT i.name FROM team_members m JOIN interns i ON i.id = m.intern_id WHERE m.team_id = ? AND m.intern_id = ?",
                              (team_id, raw)).fetchone() if raw.isdigit() else None
        if raw == "":
            if write(lambda: db().execute("UPDATE teams SET leader_id = NULL WHERE id = ?", (team_id,)), "Team leader cleared."):
                log_activity("SET_LEADER", "team", team_id, "cleared")
        elif not member:
            flash("The team leader must be a member of the team.", "danger")
        elif write(lambda: db().execute("UPDATE teams SET leader_id = ? WHERE id = ?", (int(raw), team_id)), f"{member['name']} is now the team leader."):
            log_activity("SET_LEADER", "team", team_id, member["name"])
        return redirect(url_for("team_detail", team_id=team_id))

    # ---------------------------------------------------------------- tasks
    @app.route("/tasks")
    @login_required
    def tasks():
        s = scope_team()
        page = page_arg()
        per = app.config["PAGE_SIZE"]
        rows, total, warnings = Q.list_tasks(db(), today(), request.args, s, page, per)
        pg = paginate(total, page, per)
        if pg["page"] != page:
            rows, total, _w = Q.list_tasks(db(), today(), request.args, s, pg["page"], per)
        for w in warnings:
            flash(w, "warning")
        return render_template("tasks.html", tasks=rows, pg=pg, colleges=Q.colleges(db(), s), teams=Q.team_options(db(), s),
                               export_args=request.args.to_dict())

    def _task_form(task=None, form=None, errors=None):
        return render_template("task_form.html", task=task, form=form or {}, errors=errors or {},
                               interns=Q.assignable_interns(db(), scope_team()))

    def _allowed_ids():
        s = scope_team()
        return None if s is None else {r["id"] for r in Q.assignable_interns(db(), s)}

    @app.route("/tasks/new", methods=["GET", "POST"])
    @login_required
    def task_new():
        if request.method == "POST":
            data, errors = V.validate_task(request.form, db(), today(), _allowed_ids())
            if errors:
                flash("Please correct the highlighted fields.", "danger")
                return _task_form(form=request.form, errors=errors), 422
            data = apply_task_rules(None, data)
            holder = {}
            if write(lambda: holder.update(id=save_task(None, data, g.user["id"])), "Task created and assigned."):
                log_activity("CREATE", "task", holder["id"], data["title"])
                return redirect(url_for("task_detail", task_id=holder["id"]))
            return _task_form(form=request.form), 500
        form = {"assigned_date": today().isoformat(), "status": "Not Started", "assessment_status": "Pending", "intern_id": request.args.get("intern", "")}
        return _task_form(form=form)

    @app.route("/tasks/<int:task_id>")
    @login_required
    def task_detail(task_id):
        task = task_or_404(task_id)
        history = db().execute("""SELECT a.*, u.full_name AS assessor FROM assessments a LEFT JOIN users u ON u.id = a.assessor_id
                                  WHERE a.task_id = ? ORDER BY a.id DESC""", (task_id,)).fetchall()
        return render_template("task_detail.html", task=task, history=history)

    @app.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
    @login_required
    def task_edit(task_id):
        task = task_or_404(task_id)
        if request.method == "POST":
            data, errors = V.validate_task(request.form, db(), today(), _allowed_ids())
            if errors:
                flash("Please correct the highlighted fields.", "danger")
                return _task_form(task, request.form, errors), 422
            data = apply_task_rules(task, data)
            if write(lambda: save_task(task_id, data, g.user["id"], old=task), "Task updated."):
                log_activity("UPDATE", "task", task_id, f"{task['task_code']} status={data['status']}")
                return redirect(url_for("task_detail", task_id=task_id))
            return _task_form(task, request.form), 500
        form = dict(task)
        form["assessment_score"] = "" if task["assessment_score"] is None else task["assessment_score"]
        return _task_form(task, form)

    @app.post("/tasks/<int:task_id>/status")
    @login_required
    def task_status(task_id):
        task = task_or_404(task_id)
        new = (request.form.get("status") or "").strip()
        target = safe_next(request.form.get("next")) or url_for("tasks")
        if new not in V.TASK_STATUSES:
            flash("Invalid task status.", "danger")
            return redirect(target)
        data = {"status": new, "assessment_status": task["assessment_status"], "assessment_score": task["assessment_score"],
                "submission_date": task["submission_date"]}
        data = apply_task_rules(task, data)
        def action():
            db().execute("""UPDATE tasks SET status=?, submission_date=?, assessment_status=?, assessment_score=?,
                            updated_at=datetime('now') WHERE id=?""",
                         (data["status"], data["submission_date"], data["assessment_status"], data["assessment_score"], task_id))
        if write(action, f"{task['task_code']} marked as {new}."):
            log_activity("STATUS", "task", task_id, f"{task['status']} -> {new}")
        return redirect(target)

    @app.post("/tasks/<int:task_id>/delete")
    @roles_required("admin")
    def task_delete(task_id):
        task = task_or_404(task_id)
        if write(lambda: db().execute("DELETE FROM tasks WHERE id = ?", (task_id,)), f"Task {task['task_code']} was deleted."):
            log_activity("DELETE", "task", task_id, task["title"])
        return redirect(url_for("tasks"))

    # ---------------------------------------------------------------- assessments
    @app.route("/assessments")
    @login_required
    def assessments():
        args = request.args.to_dict()
        if "assessment" not in request.args:
            args["assessment"] = "Pending"  # default view: work waiting for assessment
        s = scope_team()
        where, params, warnings = Q.build_task_filters(args, s)
        status_clause = f"status IN ({Q.ASSESSABLE_SQL})"
        where = (where + " AND " if where else " WHERE ") + status_clause
        params["today"] = today().isoformat()
        page = page_arg()
        per = app.config["PAGE_SIZE"]
        total = db().execute(f"SELECT COUNT(*) FROM ({Q.BASE_TASK_SQL}){where}", params).fetchone()[0]
        pg = paginate(total, page, per)
        params.update(limit=per, offset=(pg["page"] - 1) * per)
        rows = db().execute(f"SELECT * FROM ({Q.BASE_TASK_SQL}){where} ORDER BY due_date ASC, id ASC LIMIT :limit OFFSET :offset", params).fetchall()
        return render_template("assessments.html", tasks=rows, pg=pg, args=args, teams=Q.team_options(db(), s),
                               stats=Q.dashboard_stats(db(), today(), s))

    @app.post("/assessments/<int:task_id>")
    @login_required
    def assess(task_id):
        task = task_or_404(task_id)
        data, errors = V.validate_assessment(request.form)
        target = safe_next(request.form.get("next")) or url_for("assessments")
        if errors:
            flash(" ".join(errors.values()), "danger")
            return redirect(target)
        new_status = task["status"]
        if data["status"] == "Approved":
            new_status = "Completed"
        elif data["status"] == "Rejected":
            new_status = "Rejected"
        elif data["status"] == "Under Review" and task["status"] == "Submitted":
            new_status = "Under Review"
        sub_date = task["submission_date"] or (today().isoformat() if new_status in ("Submitted", "Under Review", "Completed") else None)
        def action():
            db().execute("""UPDATE tasks SET assessment_status=?, assessment_score=?, status=?, submission_date=?,
                            remarks=COALESCE(NULLIF(?, ''), remarks), updated_at=datetime('now') WHERE id=?""",
                         (data["status"], data["score"], new_status, sub_date, data["remarks"], task_id))
            db().execute("INSERT INTO assessments (task_id, assessor_id, status, score, remarks) VALUES (?,?,?,?,?)",
                         (task_id, g.user["id"], data["status"], data["score"], data["remarks"]))
        if write(action, f"Assessment saved for {task['task_code']}: {data['status']}."):
            log_activity("ASSESS", "task", task_id, f"{data['status']} score={data['score']}")
        return redirect(target)

    # ---------------------------------------------------------------- reports
    @app.route("/reports")
    @login_required
    def reports_page():
        return render_template("reports.html", catalog=reports.REPORTS, teams=Q.team_stats(db(), today(), scope_team()))

    @app.route("/reports/team/<int:team_id>")
    @login_required
    def team_report(team_id):
        if not team_allowed(team_id):
            abort(404)
        stats = Q.team_stats(db(), today(), team_id=team_id)
        if not stats:
            abort(404)
        tasks_, _t, _w = Q.list_tasks(db(), today(), {"team": str(team_id), "sort": "due"}, scope_team())
        members = Q.team_members(db(), team_id)
        return render_template("team_report.html", team=stats[0], members=members, tasks=tasks_,
                               generated=datetime.now().strftime("%d %b %Y, %H:%M"))

    @app.route("/export/<kind>.xlsx")
    @login_required
    def export(kind):
        if kind not in reports.REPORTS:
            abort(404)
        try:
            buf, filename = reports.build_report(kind, db(), today(), scope_team(), request.args)
        except Exception as e:  # never leak stack traces to the browser
            logger.exception("Report generation failed: %s", e)
            flash("The report could not be generated. The error has been logged.", "danger")
            return redirect(url_for("reports_page"))
        log_activity("EXPORT", "report", None, kind)
        return send_file(buf, as_attachment=True, download_name=filename,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ---------------------------------------------------------------- guide & settings
    @app.route("/guide")
    @login_required
    def guide():
        return render_template("guide.html")

    @app.route("/settings")
    @login_required
    def settings():
        ctx = {"users": [], "logs": [], "form": {}, "errors": {}}
        if g.user["role"] == "admin":
            ctx["users"] = db().execute("""SELECT u.*, t.name AS team_name FROM users u LEFT JOIN teams t ON t.id = u.team_id
                                           ORDER BY u.role, u.username""").fetchall()
            ctx["logs"] = db().execute("SELECT * FROM activity_logs ORDER BY id DESC LIMIT 60").fetchall()
        return render_template("settings.html", teams=Q.team_options(db()), **ctx)

    @app.post("/settings/password")
    @login_required
    def change_password():
        current, new, confirm = (request.form.get(k) or "" for k in ("current_password", "new_password", "confirm_password"))
        err = None
        if not check_password_hash(g.user["password_hash"], current):
            err = "Your current password is incorrect."
        elif new != confirm:
            err = "New password and confirmation do not match."
        else:
            err = V.validate_password(new)
        if err:
            flash(err, "danger")
        elif write(lambda: db().execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new), g.user["id"])),
                   "Password changed successfully."):
            log_activity("PASSWORD", "user", g.user["id"], "Password changed")
        return redirect(url_for("settings"))

    @app.post("/settings/users/new")
    @roles_required("admin")
    def user_new():
        data, errors = V.validate_user(request.form, db())
        if errors:
            flash("User not created: " + " ".join(errors.values()), "danger")
        elif write(lambda: db().execute("INSERT INTO users (username, password_hash, full_name, role, team_id) VALUES (?,?,?,?,?)",
                                        (data["username"], generate_password_hash(data["password"]), data["full_name"], data["role"], data["team_id"])),
                   f"User '{data['username']}' created."):
            log_activity("CREATE", "user", None, f"{data['username']} ({data['role']})")
        return redirect(url_for("settings"))

    def _other_user_or_flash(user_id):
        row = db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            abort(404)
        if row["id"] == g.user["id"]:
            flash("You cannot perform this action on your own account.", "danger")
            return None
        return row

    @app.post("/settings/users/<int:user_id>/toggle")
    @roles_required("admin")
    def user_toggle(user_id):
        row = _other_user_or_flash(user_id)
        if row and write(lambda: db().execute("UPDATE users SET is_active = 1 - is_active WHERE id = ?", (user_id,)),
                         f"User '{row['username']}' {'deactivated' if row['is_active'] else 'activated'}."):
            log_activity("TOGGLE_USER", "user", user_id, row["username"])
        return redirect(url_for("settings"))

    @app.post("/settings/users/<int:user_id>/reset")
    @roles_required("admin")
    def user_reset(user_id):
        row = _other_user_or_flash(user_id)
        if row:
            pw = request.form.get("password") or ""
            err = V.validate_password(pw)
            if err:
                flash(err, "danger")
            elif write(lambda: db().execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(pw), user_id)),
                       f"Password reset for '{row['username']}'."):
                log_activity("RESET_PASSWORD", "user", user_id, row["username"])
        return redirect(url_for("settings"))

    @app.post("/settings/users/<int:user_id>/delete")
    @roles_required("admin")
    def user_delete(user_id):
        row = _other_user_or_flash(user_id)
        if row and write(lambda: db().execute("DELETE FROM users WHERE id = ?", (user_id,)), f"User '{row['username']}' deleted."):
            log_activity("DELETE", "user", user_id, row["username"])
        return redirect(url_for("settings"))


if __name__ == "__main__":
    application = create_app()
    application.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=application.config["APP_ENV"] != "production")
