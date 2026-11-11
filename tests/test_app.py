"""Automated tests. Run with:  python -m unittest discover -s tests -v   (or: pytest)"""
import io
import os
import re
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openpyxl import load_workbook  # noqa: E402

import database  # noqa: E402
from app import create_app  # noqa: E402

TODAY = date.today()


def iso(delta):
    return (TODAY + timedelta(days=delta)).isoformat()


class Base(unittest.TestCase):
    SEED = False

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({"DATABASE": os.path.join(self.tmp, "t.db"), "LOG_DIR": self.tmp, "TESTING": True,
                               "SECRET_KEY": "test-secret", "SEED_DEMO": self.SEED})
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # helpers ---------------------------------------------------------------------------
    def token(self, client=None, path="/login"):
        r = (client or self.client).get(path)
        return re.search(r'name="csrf_token" value="([^"]+)"', r.get_data(as_text=True)).group(1)

    def login(self, username="admin", password="Admin@123", client=None):
        c = client or self.client
        return c.post("/login", data={"username": username, "password": password, "csrf_token": self.token(c)})

    def post(self, url, data=None, client=None, follow=False):
        c = client or self.client
        payload = dict(data or {})
        payload["csrf_token"] = self.token(c, "/guide")
        return c.post(url, data=payload, follow_redirects=follow)

    def q(self, sql, params=()):
        conn = database.connect(self.app.config["DATABASE"])
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def add_team(self, name="Alpha"):
        self.post("/teams/new", {"name": name, "description": "d"})
        return self.q("SELECT id FROM teams WHERE name = ?", (name,))[0]["id"]

    def intern_data(self, **kw):
        d = {"name": "Asha Devi", "dit_id": "DIT001", "email": "asha@example.com", "phone": "9876543210",
             "college": "ABC College", "role": "Developer", "joining_date": iso(-30), "team_id": ""}
        d.update(kw)
        return d

    def add_intern(self, **kw):
        r = self.post("/interns/new", self.intern_data(**kw))
        self.assertIn(r.status_code, (302, 303), r.get_data(as_text=True)[:300])
        return self.q("SELECT id FROM interns WHERE dit_id = ?", (kw.get("dit_id", "DIT001").upper(),))[0]["id"]

    def task_data(self, intern_id, **kw):
        d = {"title": "Build login page", "description": "desc", "intern_id": intern_id, "assigned_date": iso(-10),
             "due_date": iso(5), "submission_date": "", "status": "Not Started", "assessment_status": "Pending",
             "assessment_score": "", "remarks": ""}
        d.update(kw)
        return d

    def add_task(self, intern_id, **kw):
        r = self.post("/tasks/new", self.task_data(intern_id, **kw))
        self.assertIn(r.status_code, (302, 303), r.get_data(as_text=True)[:400])
        return self.q("SELECT id FROM tasks ORDER BY id DESC LIMIT 1")[0]["id"]


class TestInterns(Base):
    def setUp(self):
        super().setUp()
        self.login()

    def test_register_intern(self):
        iid = self.add_intern()
        row = self.q("SELECT * FROM interns WHERE id = ?", (iid,))[0]
        self.assertEqual(row["name"], "Asha Devi")
        self.assertEqual(row["phone"], "9876543210")
        self.assertIn("Asha Devi", self.client.get("/interns").get_data(as_text=True))

    def test_duplicate_dit_id_rejected(self):
        self.add_intern()
        r = self.post("/interns/new", self.intern_data(name="Someone Else", email="x@example.com", dit_id="dit001"))
        self.assertEqual(r.status_code, 422)
        self.assertIn("already exists", r.get_data(as_text=True))
        self.assertEqual(len(self.q("SELECT id FROM interns")), 1)

    def test_missing_and_invalid_fields(self):
        r = self.post("/interns/new", self.intern_data(name="", email="not-an-email", phone="12345", college="", joining_date="2026-13-45"))
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 422)
        for msg in ("Intern name is required", "valid email", "valid 10-digit", "College name is required", "valid date"):
            self.assertIn(msg, html)
        self.assertEqual(self.q("SELECT COUNT(*) c FROM interns")[0]["c"], 0)

    def test_phone_with_country_code_is_normalised(self):
        iid = self.add_intern(phone="+91 98765-43210")
        self.assertEqual(self.q("SELECT phone FROM interns WHERE id=?", (iid,))[0]["phone"], "9876543210")

    def test_edit_search_filter_delete(self):
        iid = self.add_intern()
        self.add_intern(name="Ravi K", dit_id="DIT002", email="r@example.com", college="XYZ Institute")
        self.post(f"/interns/{iid}/edit", self.intern_data(name="Asha D Updated"))
        self.assertEqual(self.q("SELECT name FROM interns WHERE id=?", (iid,))[0]["name"], "Asha D Updated")
        html = self.client.get("/interns?q=DIT002").get_data(as_text=True)
        self.assertIn("Ravi K", html)
        self.assertNotIn("Asha D Updated", html)
        html = self.client.get("/interns?college=XYZ Institute").get_data(as_text=True)
        self.assertIn("Ravi K", html)
        self.post(f"/interns/{iid}/delete")
        self.assertEqual(len(self.q("SELECT id FROM interns")), 1)

    def test_duplicate_dit_on_edit_rejected(self):
        a = self.add_intern()
        self.add_intern(name="Bala", dit_id="DIT002", email="b@example.com")
        r = self.post(f"/interns/{a}/edit", self.intern_data(dit_id="DIT002"))
        self.assertEqual(r.status_code, 422)


class TestTeams(Base):
    def setUp(self):
        super().setUp()
        self.login()

    def test_create_team_with_leader_and_members(self):
        a = self.add_intern()
        b = self.add_intern(name="Bala", dit_id="DIT002", email="b@example.com")
        r = self.post("/teams/new", {"name": "Alpha", "description": "x", "leader_id": a})
        self.assertIn(r.status_code, (302, 303))
        tid = self.q("SELECT id FROM teams")[0]["id"]
        self.assertEqual(self.q("SELECT leader_id FROM teams WHERE id=?", (tid,))[0]["leader_id"], a)
        self.post(f"/teams/{tid}/members/add", {"intern_id": b})
        self.assertEqual(len(self.q("SELECT * FROM team_members WHERE team_id=?", (tid,))), 2)
        self.assertIn("Bala", self.client.get(f"/teams/{tid}").get_data(as_text=True))
        self.post(f"/teams/{tid}/members/{a}/remove")
        self.assertIsNone(self.q("SELECT leader_id FROM teams WHERE id=?", (tid,))[0]["leader_id"])  # leader removed -> cleared
        self.assertEqual(len(self.q("SELECT * FROM team_members WHERE team_id=?", (tid,))), 1)

    def test_duplicate_team_name_and_blank_name(self):
        self.add_team("Alpha")
        self.assertEqual(self.post("/teams/new", {"name": "alpha"}).status_code, 422)
        self.assertEqual(self.post("/teams/new", {"name": " "}).status_code, 422)

    def test_intern_belongs_to_one_team(self):
        t1, t2 = self.add_team("A1"), self.add_team("B1")
        a = self.add_intern(team_id=t1)
        self.post(f"/teams/{t2}/members/add", {"intern_id": a})  # already in a team -> refused
        self.assertEqual(self.q("SELECT team_id FROM team_members WHERE intern_id=?", (a,))[0]["team_id"], t1)
        self.post(f"/interns/{a}/edit", self.intern_data(team_id=t2))  # moving via edit works
        self.assertEqual(self.q("SELECT team_id FROM team_members WHERE intern_id=?", (a,))[0]["team_id"], t2)

    def test_team_completion_percentage(self):
        t = self.add_team()
        a = self.add_intern(team_id=t)
        done = self.add_task(a, title="One")
        self.add_task(a, title="Two")
        self.post(f"/tasks/{done}/status", {"status": "Completed"})
        stats = self.client.get(f"/reports/team/{t}").get_data(as_text=True)
        self.assertIn("50.0%", stats)


class TestTasks(Base):
    def setUp(self):
        super().setUp()
        self.login()
        self.team = self.add_team()
        self.intern = self.add_intern(team_id=self.team)

    def test_task_assignment_and_code(self):
        tid = self.add_task(self.intern)
        row = self.q("SELECT * FROM tasks WHERE id=?", (tid,))[0]
        self.assertEqual(row["task_code"], f"TSK-{tid:04d}")
        self.assertEqual(row["intern_id"], self.intern)
        self.assertIn("DIT001", self.client.get(f"/tasks/{tid}").get_data(as_text=True))

    def test_due_date_before_assigned_rejected(self):
        r = self.post("/tasks/new", self.task_data(self.intern, assigned_date=iso(0), due_date=iso(-3)))
        self.assertEqual(r.status_code, 422)
        self.assertIn("Due date cannot be earlier", r.get_data(as_text=True))

    def test_invalid_and_missing_dates_rejected(self):
        r = self.post("/tasks/new", self.task_data(self.intern, assigned_date="2026-02-31", due_date=""))
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 422)
        self.assertIn("not a valid date", html)
        self.assertIn("Due date is required", html)

    def test_future_submission_date_rejected(self):
        r = self.post("/tasks/new", self.task_data(self.intern, submission_date=iso(3)))
        self.assertEqual(r.status_code, 422)

    def test_missing_title_and_intern(self):
        r = self.post("/tasks/new", self.task_data("", title=""))
        html = r.get_data(as_text=True)
        self.assertIn("Task title is required", html)
        self.assertIn("select an intern", html)

    def test_status_updates_set_submission_date(self):
        tid = self.add_task(self.intern)
        self.post(f"/tasks/{tid}/status", {"status": "In Progress"})
        self.assertEqual(self.q("SELECT status FROM tasks WHERE id=?", (tid,))[0]["status"], "In Progress")
        self.post(f"/tasks/{tid}/status", {"status": "Submitted"})
        row = self.q("SELECT * FROM tasks WHERE id=?", (tid,))[0]
        self.assertEqual(row["status"], "Submitted")
        self.assertEqual(row["submission_date"], TODAY.isoformat())
        self.post(f"/tasks/{tid}/status", {"status": "Nonsense"})
        self.assertEqual(self.q("SELECT status FROM tasks WHERE id=?", (tid,))[0]["status"], "Submitted")

    def test_overdue_detection(self):
        late = self.add_task(self.intern, title="Late", assigned_date=iso(-20), due_date=iso(-2), status="In Progress")
        late_ns = self.add_task(self.intern, title="Late not started", assigned_date=iso(-20), due_date=iso(-1))
        ok = self.add_task(self.intern, title="On time", due_date=iso(4), status="In Progress")
        done = self.add_task(self.intern, title="Done late", assigned_date=iso(-20), due_date=iso(-5), status="Completed",
                             submission_date=iso(-6), assessment_status="Approved", assessment_score="80")
        html = self.client.get("/tasks?status=Overdue").get_data(as_text=True)
        self.assertIn("Late", html)
        self.assertIn("Late not started", html)
        self.assertNotIn("On time", html)
        self.assertNotIn("Done late", html)
        stats = self.client.get("/api/dashboard").get_json()["stats"]
        self.assertEqual(stats["overdue"], 2)
        # stored status is untouched; only the effective status changes
        self.assertEqual(self.q("SELECT status FROM tasks WHERE id=?", (late,))[0]["status"], "In Progress")
        # moving the due date into the future clears the overdue flag
        self.post(f"/tasks/{late}/edit", self.task_data(self.intern, title="Late", assigned_date=iso(-20), due_date=iso(3), status="In Progress"))
        self.assertEqual(self.client.get("/api/dashboard").get_json()["stats"]["overdue"], 1)
        self.assertTrue(ok and done)

    def test_assessment_score_validation(self):
        tid = self.add_task(self.intern, status="Submitted", submission_date=iso(-1))
        for bad in ("101", "-5", "abc"):
            r = self.post(f"/assessments/{tid}", {"status": "Approved", "score": bad}, follow=True)
            self.assertIn("Assessment score", r.get_data(as_text=True))
            self.assertEqual(self.q("SELECT assessment_status FROM tasks WHERE id=?", (tid,))[0]["assessment_status"], "Pending")
        r = self.post(f"/assessments/{tid}", {"status": "Approved", "score": ""}, follow=True)
        self.assertIn("score", r.get_data(as_text=True).lower())
        self.assertEqual(self.q("SELECT assessment_status FROM tasks WHERE id=?", (tid,))[0]["assessment_status"], "Pending")
        self.post(f"/assessments/{tid}", {"status": "Approved", "score": "88.5", "remarks": "Great"})
        row = self.q("SELECT * FROM tasks WHERE id=?", (tid,))[0]
        self.assertEqual((row["status"], row["assessment_status"], row["assessment_score"]), ("Completed", "Approved", 88.5))
        self.assertEqual(len(self.q("SELECT * FROM assessments WHERE task_id=?", (tid,))), 1)

    def test_score_validation_on_task_form(self):
        r = self.post("/tasks/new", self.task_data(self.intern, assessment_score="150"))
        self.assertEqual(r.status_code, 422)
        self.assertIn("between 0 and 100", r.get_data(as_text=True))

    def test_reject_and_resubmit_resets_assessment(self):
        tid = self.add_task(self.intern, status="Submitted", submission_date=iso(-1))
        self.post(f"/assessments/{tid}", {"status": "Rejected", "score": "40", "remarks": "Redo"})
        self.assertEqual(self.q("SELECT status FROM tasks WHERE id=?", (tid,))[0]["status"], "Rejected")
        self.post(f"/tasks/{tid}/status", {"status": "In Progress"})
        self.post(f"/tasks/{tid}/status", {"status": "Submitted"})
        row = self.q("SELECT * FROM tasks WHERE id=?", (tid,))[0]
        self.assertEqual((row["assessment_status"], row["assessment_score"]), ("Pending", None))

    def test_filters(self):
        self.add_task(self.intern, title="Alpha job", status="In Progress")
        other = self.add_intern(name="Ravi", dit_id="DIT777", email="r@example.com", college="XYZ")
        self.add_task(other, title="Beta job", assigned_date=iso(-3), due_date=iso(30))
        self.assertNotIn("Beta job", self.client.get("/tasks?q=DIT001").get_data(as_text=True))
        self.assertIn("Beta job", self.client.get("/tasks?college=XYZ").get_data(as_text=True))
        self.assertIn("Alpha job", self.client.get("/tasks?status=In Progress").get_data(as_text=True))
        self.assertNotIn("Alpha job", self.client.get(f"/tasks?date_field=due_date&date_from={iso(20)}").get_data(as_text=True))
        self.assertIn("Beta job", self.client.get(f"/tasks?date_field=due_date&date_from={iso(20)}&date_to={iso(40)}").get_data(as_text=True))
        self.assertIn("Ignored invalid", self.client.get("/tasks?date_from=garbage").get_data(as_text=True))


class TestDashboardAndReports(Base):
    SEED = True

    def setUp(self):
        super().setUp()
        self.login()

    def test_dashboard_numbers_match_database(self):
        s = self.client.get("/api/dashboard").get_json()["stats"]
        total = self.q("SELECT COUNT(*) c FROM tasks")[0]["c"]
        self.assertEqual(s["total_tasks"], total)
        self.assertEqual(s["interns"], self.q("SELECT COUNT(*) c FROM interns")[0]["c"])
        self.assertEqual(s["teams"], self.q("SELECT COUNT(*) c FROM teams")[0]["c"])
        self.assertEqual(s["completed"], self.q("SELECT COUNT(*) c FROM tasks WHERE status='Completed'")[0]["c"])
        overdue = self.q("SELECT COUNT(*) c FROM tasks WHERE status IN ('Not Started','In Progress') AND due_date < ?", (TODAY.isoformat(),))[0]["c"]
        self.assertEqual(s["overdue"], overdue)
        self.assertEqual(sum(s["status_counts"].values()), total)
        self.assertEqual(s["completion_pct"], round(s["completed"] * 100 / total, 1))
        pending = self.q("""SELECT COUNT(*) c FROM tasks WHERE assessment_status='Pending'
                            AND status IN ('Submitted','Under Review','Completed','Rejected')""")[0]["c"]
        self.assertEqual(s["assessment_pending"], pending)

    def test_chart_api_shape(self):
        d = self.client.get("/api/dashboard").get_json()
        self.assertEqual(len(d["teams"]["labels"]), 5)
        self.assertEqual(len(d["monthly"]["labels"]), 6)
        self.assertLessEqual(len(d["interns"]["labels"]), 10)
        self.assertGreater(sum(d["monthly"]["submitted"]), 0)

    def test_all_excel_reports(self):
        expected_sheets = {"intern_master": "Intern Master", "team_allocation": "Team Allocation", "task_tracker": "Complete Task Tracker",
                           "completed_tasks": "Completed Tasks", "pending_tasks": "Pending Tasks", "overdue_tasks": "Overdue Tasks",
                           "assessment_report": "Assessment Report", "team_lead_report": "Team Summary"}
        for kind, sheet in expected_sheets.items():
            r = self.client.get(f"/export/{kind}.xlsx")
            self.assertEqual(r.status_code, 200, kind)
            self.assertIn("spreadsheetml", r.mimetype)
            wb = load_workbook(io.BytesIO(r.data))
            ws = wb[sheet]
            self.assertTrue(ws.auto_filter.ref, f"{kind}: filter missing")
            self.assertEqual(ws.freeze_panes, "A5")
            self.assertTrue(ws["A4"].value)
            self.assertGreater(ws.column_dimensions["A"].width, 5)
        wb = load_workbook(io.BytesIO(self.client.get("/export/task_tracker.xlsx").data))
        ws = wb.active
        self.assertEqual(ws.max_row - 4, self.q("SELECT COUNT(*) c FROM tasks")[0]["c"])
        self.assertEqual([c.value for c in ws[4]][:5], ["Task ID", "Task Title", "Description", "Intern Name", "DIT ID"])
        overdue = load_workbook(io.BytesIO(self.client.get("/export/overdue_tasks.xlsx").data)).active
        self.assertEqual(overdue.max_row - 4, self.client.get("/api/dashboard").get_json()["stats"]["overdue"])
        lead = load_workbook(io.BytesIO(self.client.get("/export/team_lead_report.xlsx").data))
        self.assertEqual(lead.sheetnames, ["Team Summary", "Team Tasks"])
        self.assertEqual(lead["Team Summary"].max_row - 4, 5)

    def test_filtered_export_matches_filter(self):
        n = self.q("SELECT COUNT(*) c FROM tasks WHERE status='Completed'")[0]["c"]
        ws = load_workbook(io.BytesIO(self.client.get("/export/task_tracker.xlsx?status=Completed").data)).active
        self.assertEqual(ws.max_row - 4, n)

    def test_unknown_export_404(self):
        self.assertEqual(self.client.get("/export/secrets.xlsx").status_code, 404)


class TestSecurity(Base):
    SEED = True

    def lead_client(self, username="lead_web"):
        c = self.app.test_client()
        r = self.login(username, "Lead@1234", client=c)
        self.assertEqual(r.status_code, 302)
        return c

    def test_login_logout_and_protected_pages(self):
        r = self.client.get("/interns")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])
        self.assertEqual(self.login("admin", "wrong").status_code, 200)
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client.get("/interns").status_code, 200)
        self.post("/logout")
        self.assertEqual(self.client.get("/interns").status_code, 302)

    def test_passwords_are_hashed(self):
        for row in self.q("SELECT password_hash FROM users"):
            self.assertTrue(row["password_hash"].startswith(("scrypt:", "pbkdf2:")))
            self.assertNotIn("Admin@123", row["password_hash"])

    def test_csrf_blocks_forged_post(self):
        self.login()
        r = self.client.post("/teams/new", data={"name": "Evil"})
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/teams/new", data={"name": "Evil", "csrf_token": "bad"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.q("SELECT COUNT(*) c FROM teams WHERE name='Evil'")[0]["c"], 0)

    def test_login_requires_csrf(self):
        self.assertEqual(self.client.post("/login", data={"username": "admin", "password": "Admin@123"}).status_code, 400)

    def test_open_redirect_blocked(self):
        r = self.client.post("/login?next=https://evil.example", data={"username": "admin", "password": "Admin@123", "csrf_token": self.token()})
        self.assertNotIn("evil", r.headers["Location"])

    def test_session_cookie_flags(self):
        r = self.client.get("/login")
        self.assertEqual(self.app.config["SESSION_COOKIE_HTTPONLY"], True)
        self.assertEqual(self.app.config["SESSION_COOKIE_SAMESITE"], "Lax")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")

    def test_team_lead_permissions(self):
        c = self.lead_client()
        for url in ("/interns/new", "/teams/new", "/teams/1/edit"):
            self.assertEqual(c.get(url).status_code, 403, url)
        self.assertEqual(self.post("/interns/1/delete", client=c).status_code, 403)
        self.assertEqual(c.get("/").status_code, 200)
        web_team = self.q("SELECT team_id FROM users WHERE username='lead_web'")[0]["team_id"]
        other_team = self.q("SELECT id FROM teams WHERE id != ? LIMIT 1", (web_team,))[0]["id"]
        self.assertEqual(c.get(f"/teams/{other_team}").status_code, 404)
        self.assertEqual(c.get(f"/teams/{web_team}").status_code, 200)
        other_task = self.q("""SELECT t.id FROM tasks t JOIN team_members m ON m.intern_id = t.intern_id WHERE m.team_id = ? LIMIT 1""", (other_team,))[0]["id"]
        self.assertEqual(c.get(f"/tasks/{other_task}").status_code, 404)
        self.assertEqual(self.post(f"/tasks/{other_task}/status", {"status": "Completed"}, client=c).status_code, 404)
        own_task = self.q("""SELECT t.id FROM tasks t JOIN team_members m ON m.intern_id = t.intern_id WHERE m.team_id = ? LIMIT 1""", (web_team,))[0]["id"]
        self.assertEqual(c.get(f"/tasks/{own_task}").status_code, 200)

    def test_team_lead_sees_only_own_team_data(self):
        c = self.lead_client()
        web_team = self.q("SELECT team_id FROM users WHERE username='lead_web'")[0]["team_id"]
        s = c.get("/api/dashboard").get_json()
        self.assertEqual(s["stats"]["teams"], 1)
        self.assertEqual(s["stats"]["total_tasks"], self.q("""SELECT COUNT(*) c FROM tasks t JOIN team_members m ON m.intern_id=t.intern_id WHERE m.team_id=?""", (web_team,))[0]["c"])
        html = c.get("/interns").get_data(as_text=True)
        other = self.q("SELECT i.name FROM interns i JOIN team_members m ON m.intern_id=i.id WHERE m.team_id != ? LIMIT 1", (web_team,))[0]["name"]
        self.assertNotIn(other, html)
        ws = load_workbook(io.BytesIO(c.get("/export/intern_master.xlsx").data)).active
        self.assertEqual(ws.max_row - 4, 5)

    def test_team_lead_cannot_assign_outside_team_but_can_inside(self):
        c = self.lead_client()
        web_team = self.q("SELECT team_id FROM users WHERE username='lead_web'")[0]["team_id"]
        mine = self.q("SELECT intern_id FROM team_members WHERE team_id=? LIMIT 1", (web_team,))[0]["intern_id"]
        theirs = self.q("SELECT intern_id FROM team_members WHERE team_id!=? LIMIT 1", (web_team,))[0]["intern_id"]
        base = {"title": "Lead task", "intern_id": mine, "assigned_date": iso(-1), "due_date": iso(7), "status": "Not Started", "assessment_status": "Pending"}
        self.assertEqual(self.post("/tasks/new", base, client=c).status_code, 302)
        base.update(intern_id=theirs, title="Sneaky")
        r = self.post("/tasks/new", base, client=c)
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.q("SELECT COUNT(*) c FROM tasks WHERE title='Sneaky'")[0]["c"], 0)

    def test_admin_only_settings_and_user_creation(self):
        c = self.lead_client()
        self.assertEqual(self.post("/settings/users/new", {"username": "x1234", "full_name": "X", "role": "admin", "password": "Passw0rdX"}, client=c).status_code, 403)
        self.login()
        tid = self.q("SELECT id FROM teams LIMIT 1")[0]["id"]
        self.post("/settings/users/new", {"username": "newlead", "full_name": "New Lead", "role": "team_lead", "team_id": tid, "password": "Passw0rd1"})
        self.assertEqual(self.q("SELECT COUNT(*) c FROM users WHERE username='newlead'")[0]["c"], 1)
        self.post("/settings/users/new", {"username": "weak", "full_name": "W", "role": "team_lead", "team_id": tid, "password": "short"})
        self.assertEqual(self.q("SELECT COUNT(*) c FROM users WHERE username='weak'")[0]["c"], 0)

    def test_password_change(self):
        self.login()
        self.post("/settings/password", {"current_password": "bad", "new_password": "NewPass123", "confirm_password": "NewPass123"})
        self.assertEqual(self.login("admin", "NewPass123", client=self.app.test_client()).status_code, 200)
        self.post("/settings/password", {"current_password": "Admin@123", "new_password": "NewPass123", "confirm_password": "NewPass123"})
        self.assertEqual(self.login("admin", "NewPass123", client=self.app.test_client()).status_code, 302)

    def test_activity_log_written(self):
        self.login()
        self.assertGreaterEqual(self.q("SELECT COUNT(*) c FROM activity_logs WHERE action='LOGIN'")[0]["c"], 1)

    def test_login_throttle(self):
        c = self.app.test_client()
        for _ in range(5):
            self.login("lead_web", "bad", client=c)
        self.assertEqual(self.login("lead_web", "Lead@1234", client=c).status_code, 429)


class TestDatabaseConstraints(Base):
    def test_foreign_keys_and_checks(self):
        import sqlite3
        conn = database.connect(self.app.config["DATABASE"])
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO tasks (task_code,title,intern_id,assigned_date,due_date) VALUES ('X','t',999,'2026-01-01','2026-01-02')")
        conn.execute("INSERT INTO interns (name,dit_id,email,phone,college,role,joining_date) VALUES ('a','D1','a@b.co','9876543210','c','r','2026-01-01')")
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO interns (name,dit_id,email,phone,college,role,joining_date) VALUES ('b','d1','b@b.co','9876543210','c','r','2026-01-01')")
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO tasks (task_code,title,intern_id,assigned_date,due_date,assessment_score) VALUES ('Y','t',1,'2026-01-01','2026-01-02',101)")
        conn.close()


if __name__ == "__main__":
    unittest.main()
