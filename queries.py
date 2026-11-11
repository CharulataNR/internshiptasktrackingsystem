"""Read-side SQL: task base query (with automatic overdue detection), filters and statistics."""
from datetime import date, timedelta

from validators import ASSESSMENT_STATUSES, TASK_STATUSES, parse_date

# Tasks that have reached the assessment stage.
ASSESSABLE = ("Submitted", "Under Review", "Completed", "Rejected")
ASSESSABLE_SQL = ",".join(f"'{s}'" for s in ASSESSABLE)

# A task is automatically "Overdue" when it is still Not Started / In Progress after its due date.
BASE_TASK_SQL = """
SELECT t.id, t.task_code, t.title, t.description, t.intern_id, t.assigned_date, t.due_date,
       t.submission_date, t.status, t.assessment_status, t.assessment_score, t.remarks,
       t.created_by, t.created_at, t.updated_at,
       i.name AS intern_name, i.dit_id AS dit_id, i.college AS college,
       tm.team_id AS team_id, tg.name AS team_name,
       CASE WHEN t.status IN ('Not Started','In Progress') AND t.due_date < :today
            THEN 'Overdue' ELSE t.status END AS eff_status,
       CASE WHEN t.status IN ('Not Started','In Progress','Overdue') AND t.due_date < :today
            THEN CAST(julianday(:today) - julianday(t.due_date) AS INTEGER) ELSE 0 END AS days_overdue
FROM tasks t
JOIN interns i ON i.id = t.intern_id
LEFT JOIN team_members tm ON tm.intern_id = i.id
LEFT JOIN teams tg ON tg.id = tm.team_id
"""

DATE_FIELDS = {"assigned_date", "due_date", "submission_date"}
SORTS = {
    "newest": "id DESC",
    "due": "due_date ASC, id ASC",
    "due_desc": "due_date DESC, id DESC",
    "intern": "intern_name COLLATE NOCASE ASC, due_date ASC",
    "status": "eff_status ASC, due_date ASC",
}


def _like(text):
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def build_task_filters(args, scope_team=None):
    """Translate query-string filters into a WHERE clause. Returns (sql, params, warnings)."""
    where, params, warnings = [], {}, []
    if scope_team is not None:
        where.append("team_id = :scope_team")
        params["scope_team"] = scope_team
    q = (args.get("q") or "").strip()
    if q:
        where.append("(dit_id LIKE :q ESCAPE '\\' OR intern_name LIKE :q ESCAPE '\\' OR title LIKE :q ESCAPE '\\' OR task_code LIKE :q ESCAPE '\\')")
        params["q"] = _like(q)
    team = (args.get("team") or "").strip()
    if team.isdigit():
        where.append("team_id = :team")
        params["team"] = int(team)
    intern = (args.get("intern") or "").strip()
    if intern.isdigit():
        where.append("intern_id = :intern")
        params["intern"] = int(intern)
    college = (args.get("college") or "").strip()
    if college:
        where.append("college = :college")
        params["college"] = college
    status = (args.get("status") or "").strip()
    if status in TASK_STATUSES:
        where.append("eff_status = :status")
        params["status"] = status
    assessment = (args.get("assessment") or "").strip()
    if assessment in ASSESSMENT_STATUSES:
        where.append("assessment_status = :assessment")
        params["assessment"] = assessment
    field = args.get("date_field") if args.get("date_field") in DATE_FIELDS else "due_date"
    for key, op in (("date_from", ">="), ("date_to", "<=")):
        raw = (args.get(key) or "").strip()
        if raw:
            try:
                parse_date(raw)
                where.append(f"{field} {op} :{key}")
                params[key] = raw
            except ValueError:
                warnings.append(f"Ignored invalid '{key.replace('_', ' ')}' value.")
    return (" WHERE " + " AND ".join(where)) if where else "", params, warnings


def list_tasks(db, today, args, scope_team=None, page=None, per_page=15):
    where, params, warnings = build_task_filters(args, scope_team)
    params["today"] = today.isoformat()
    order = SORTS.get(args.get("sort"), SORTS["newest"])
    sql = f"SELECT * FROM ({BASE_TASK_SQL}){where}"
    total = db.execute(f"SELECT COUNT(*) FROM ({BASE_TASK_SQL}){where}", params).fetchone()[0]
    sql += f" ORDER BY {order}"
    if page:
        sql += " LIMIT :limit OFFSET :offset"
        params["limit"] = per_page
        params["offset"] = (page - 1) * per_page
    return db.execute(sql, params).fetchall(), total, warnings


def task_rows(db, today, extra_where="", extra_params=None, scope_team=None, order="id DESC", limit=None):
    """Convenience query used by dashboard widgets and exports."""
    params = {"today": today.isoformat()}
    clauses = []
    if scope_team is not None:
        clauses.append("team_id = :scope_team")
        params["scope_team"] = scope_team
    if extra_where:
        clauses.append(extra_where)
    params.update(extra_params or {})
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM ({BASE_TASK_SQL}){where} ORDER BY {order}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return db.execute(sql, params).fetchall()


def get_task(db, today, task_id):
    return db.execute(f"SELECT * FROM ({BASE_TASK_SQL}) WHERE id = :id", {"today": today.isoformat(), "id": task_id}).fetchone()


# ----------------------------------------------------------------------------- statistics
def dashboard_stats(db, today, scope_team=None):
    params = {"today": today.isoformat()}
    where = ""
    if scope_team is not None:
        where = " WHERE team_id = :scope_team"
        params["scope_team"] = scope_team
    counts = {s: 0 for s in TASK_STATUSES}
    for r in db.execute(f"SELECT eff_status s, COUNT(*) c FROM ({BASE_TASK_SQL}){where} GROUP BY eff_status", params):
        counts[r["s"]] = r["c"]
    total = sum(counts.values())
    conj = " AND " if where else " WHERE "
    assess_pending = db.execute(
        f"SELECT COUNT(*) FROM ({BASE_TASK_SQL}){where}{conj}assessment_status = 'Pending' AND status IN ({ASSESSABLE_SQL})", params
    ).fetchone()[0]
    if scope_team is None:
        interns = db.execute("SELECT COUNT(*) FROM interns").fetchone()[0]
        teams = db.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    else:
        interns = db.execute("SELECT COUNT(*) FROM team_members WHERE team_id = ?", (scope_team,)).fetchone()[0]
        teams = db.execute("SELECT COUNT(*) FROM teams WHERE id = ?", (scope_team,)).fetchone()[0]
    return {
        "interns": interns, "teams": teams, "total_tasks": total,
        "completed": counts["Completed"], "pending": counts["Not Started"], "in_progress": counts["In Progress"],
        "submitted": counts["Submitted"], "under_review": counts["Under Review"], "rejected": counts["Rejected"],
        "overdue": counts["Overdue"], "assessment_pending": assess_pending,
        "completion_pct": round(counts["Completed"] * 100 / total, 1) if total else 0.0,
        "status_counts": counts,
    }


def team_stats(db, today, scope_team=None, team_id=None):
    """One dict per team with membership and task counters. Used by teams page, dashboard, reports."""
    params = {}
    cond = ""
    only = team_id if team_id is not None else scope_team
    if only is not None:
        cond = " WHERE tg.id = :only"
        params["only"] = only
    teams = db.execute(
        f"""SELECT tg.id, tg.name, tg.description, tg.leader_id, tg.created_at,
                   l.name AS leader_name, l.dit_id AS leader_dit_id, l.email AS leader_email, l.phone AS leader_phone,
                   (SELECT COUNT(*) FROM team_members m WHERE m.team_id = tg.id) AS members
            FROM teams tg LEFT JOIN interns l ON l.id = tg.leader_id{cond} ORDER BY tg.name COLLATE NOCASE""", params).fetchall()
    agg = {}
    for r in db.execute(
        f"""SELECT team_id, COUNT(*) total,
                   SUM(eff_status='Completed') completed, SUM(eff_status='In Progress') in_progress,
                   SUM(eff_status='Not Started') not_started, SUM(eff_status='Submitted') submitted,
                   SUM(eff_status='Under Review') under_review, SUM(eff_status='Rejected') rejected,
                   SUM(eff_status='Overdue') overdue,
                   SUM(assessment_status='Pending' AND status IN ({ASSESSABLE_SQL})) assess_pending,
                   SUM(assessment_status='Under Review') assess_review,
                   SUM(assessment_status='Approved') assess_approved,
                   SUM(assessment_status='Rejected') assess_rejected,
                   ROUND(AVG(assessment_score), 1) avg_score
            FROM ({BASE_TASK_SQL}) WHERE team_id IS NOT NULL GROUP BY team_id""", {"today": today.isoformat()}):
        agg[r["team_id"]] = r
    keys = ["total", "completed", "in_progress", "not_started", "submitted", "under_review", "rejected", "overdue",
            "assess_pending", "assess_review", "assess_approved", "assess_rejected"]
    out = []
    for t in teams:
        d = dict(t)
        a = agg.get(t["id"])
        for k in keys:
            d[k] = (a[k] or 0) if a else 0
        d["avg_score"] = a["avg_score"] if a else None
        d["open"] = d["total"] - d["completed"]
        d["completion_pct"] = round(d["completed"] * 100 / d["total"], 1) if d["total"] else 0.0
        out.append(d)
    return out


def intern_performance(db, today, scope_team=None, limit=10):
    params = {"today": today.isoformat(), "limit": limit}
    where = ""
    if scope_team is not None:
        where = " WHERE team_id = :scope_team"
        params["scope_team"] = scope_team
    return db.execute(
        f"""SELECT intern_id, intern_name, dit_id, COUNT(*) total, SUM(eff_status='Completed') completed,
                   ROUND(AVG(assessment_score), 1) avg_score
            FROM ({BASE_TASK_SQL}){where} GROUP BY intern_id
            ORDER BY completed DESC, avg_score DESC, intern_name LIMIT :limit""", params).fetchall()


def _month_add(d, delta):
    idx = d.year * 12 + (d.month - 1) + delta
    return date(idx // 12, idx % 12 + 1, 1)


def monthly_submissions(db, today, scope_team=None, months=6):
    first = _month_add(today.replace(day=1), -(months - 1))
    params = {"today": today.isoformat(), "start": first.isoformat()}
    scope = ""
    if scope_team is not None:
        scope = " AND team_id = :scope_team"
        params["scope_team"] = scope_team
    sub = {r["m"]: r["c"] for r in db.execute(
        f"""SELECT substr(submission_date, 1, 7) m, COUNT(*) c FROM ({BASE_TASK_SQL})
            WHERE submission_date IS NOT NULL AND submission_date >= :start{scope} GROUP BY m""", params)}
    asg = {r["m"]: r["c"] for r in db.execute(
        f"""SELECT substr(assigned_date, 1, 7) m, COUNT(*) c FROM ({BASE_TASK_SQL})
            WHERE assigned_date >= :start{scope} GROUP BY m""", params)}
    labels, submitted, assigned = [], [], []
    for k in range(months):
        m = _month_add(first, k)
        key = m.strftime("%Y-%m")
        labels.append(m.strftime("%b %Y"))
        submitted.append(sub.get(key, 0))
        assigned.append(asg.get(key, 0))
    return {"labels": labels, "submitted": submitted, "assigned": assigned}


# ----------------------------------------------------------------------------- interns / teams
INTERN_SELECT = """
SELECT i.*, tm.team_id AS team_id, tg.name AS team_name,
       (SELECT COUNT(*) FROM tasks t WHERE t.intern_id = i.id) AS task_count,
       (SELECT COUNT(*) FROM tasks t WHERE t.intern_id = i.id AND t.status = 'Completed') AS completed_count
FROM interns i
LEFT JOIN team_members tm ON tm.intern_id = i.id
LEFT JOIN teams tg ON tg.id = tm.team_id
"""


def build_intern_filters(args, scope_team=None):
    where, params = [], {}
    if scope_team is not None:
        where.append("team_id = :scope_team")
        params["scope_team"] = scope_team
    q = (args.get("q") or "").strip()
    if q:
        where.append("(name LIKE :q ESCAPE '\\' OR dit_id LIKE :q ESCAPE '\\' OR email LIKE :q ESCAPE '\\')")
        params["q"] = _like(q)
    college = (args.get("college") or "").strip()
    if college:
        where.append("college = :college")
        params["college"] = college
    team = (args.get("team") or "").strip()
    if team == "none":
        where.append("team_id IS NULL")
    elif team.isdigit():
        where.append("team_id = :team")
        params["team"] = int(team)
    return (" WHERE " + " AND ".join(where)) if where else "", params


def list_interns(db, args, scope_team=None, page=None, per_page=15):
    where, params = build_intern_filters(args, scope_team)
    total = db.execute(f"SELECT COUNT(*) FROM ({INTERN_SELECT}){where}", params).fetchone()[0]
    sql = f"SELECT * FROM ({INTERN_SELECT}){where} ORDER BY name COLLATE NOCASE"
    if page:
        sql += " LIMIT :limit OFFSET :offset"
        params.update(limit=per_page, offset=(page - 1) * per_page)
    return db.execute(sql, params).fetchall(), total


def get_intern(db, intern_id):
    return db.execute(f"SELECT * FROM ({INTERN_SELECT}) WHERE id = ?", (intern_id,)).fetchone()


def colleges(db, scope_team=None):
    if scope_team is None:
        rows = db.execute("SELECT DISTINCT college FROM interns ORDER BY college COLLATE NOCASE").fetchall()
    else:
        rows = db.execute("""SELECT DISTINCT i.college FROM interns i JOIN team_members m ON m.intern_id = i.id
                             WHERE m.team_id = ? ORDER BY i.college COLLATE NOCASE""", (scope_team,)).fetchall()
    return [r[0] for r in rows]


def team_options(db, scope_team=None):
    if scope_team is None:
        return db.execute("SELECT id, name FROM teams ORDER BY name COLLATE NOCASE").fetchall()
    return db.execute("SELECT id, name FROM teams WHERE id = ?", (scope_team,)).fetchall()


def assignable_interns(db, scope_team=None):
    """Interns a user may assign tasks to."""
    if scope_team is None:
        return db.execute("""SELECT i.id, i.name, i.dit_id, tg.name AS team_name FROM interns i
                             LEFT JOIN team_members m ON m.intern_id = i.id LEFT JOIN teams tg ON tg.id = m.team_id
                             ORDER BY i.name COLLATE NOCASE""").fetchall()
    return db.execute("""SELECT i.id, i.name, i.dit_id, tg.name AS team_name FROM interns i
                         JOIN team_members m ON m.intern_id = i.id JOIN teams tg ON tg.id = m.team_id
                         WHERE m.team_id = ? ORDER BY i.name COLLATE NOCASE""", (scope_team,)).fetchall()


def team_members(db, team_id):
    return db.execute("""SELECT i.*, (SELECT COUNT(*) FROM tasks t WHERE t.intern_id = i.id) AS task_count,
                                (SELECT COUNT(*) FROM tasks t WHERE t.intern_id = i.id AND t.status = 'Completed') AS completed_count
                         FROM team_members m JOIN interns i ON i.id = m.intern_id
                         WHERE m.team_id = ? ORDER BY i.name COLLATE NOCASE""", (team_id,)).fetchall()


def unassigned_interns(db):
    return db.execute("""SELECT i.id, i.name, i.dit_id FROM interns i
                         WHERE i.id NOT IN (SELECT intern_id FROM team_members) ORDER BY i.name COLLATE NOCASE""").fetchall()


def set_intern_team(db, intern_id, team_id):
    """Move an intern to a team (or remove from all teams when team_id is None). Keeps leader links consistent."""
    old = db.execute("SELECT team_id FROM team_members WHERE intern_id = ?", (intern_id,)).fetchone()
    if old and old["team_id"] == team_id:
        return
    if old:
        db.execute("UPDATE teams SET leader_id = NULL WHERE id = ? AND leader_id = ?", (old["team_id"], intern_id))
        db.execute("DELETE FROM team_members WHERE intern_id = ?", (intern_id,))
    if team_id is not None:
        db.execute("INSERT INTO team_members (team_id, intern_id) VALUES (?, ?)", (team_id, intern_id))
