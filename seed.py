"""Demo data (all synthetic) + first-run admin creation. Dates are relative to 'today' so charts always look alive."""
import random
from datetime import timedelta

from werkzeug.security import generate_password_hash

TEAMS = {
    "Web Development": ("Full-stack web modules for internal tools.", "Frontend Developer", [
        "Build responsive landing page", "Create login and registration forms", "Integrate REST API with dashboard",
        "Implement form validation", "Optimise page load performance", "Write unit tests for API endpoints"]),
    "Data Analytics": ("Dashboards, reporting and data cleaning.", "Data Analyst", [
        "Clean and merge survey datasets", "Build sales trend dashboard", "Prepare weekly KPI report",
        "Perform exploratory data analysis", "Automate Excel reporting with Pandas", "Document data dictionary"]),
    "Cloud & DevOps": ("Deployment pipelines and monitoring.", "DevOps Intern", [
        "Containerise the application", "Set up CI pipeline", "Configure staging deployment",
        "Write deployment runbook", "Set up log monitoring", "Automate database backups"]),
    "AI/ML Research": ("Applied machine learning prototypes.", "ML Research Intern", [
        "Collect and label training data", "Train baseline classifier", "Evaluate model with cross-validation",
        "Prepare model comparison report", "Build inference API", "Write literature survey"]),
    "UI/UX Design": ("Interface design, prototypes and usability tests.", "UI/UX Designer", [
        "Create wireframes for dashboard", "Design component style guide", "Conduct usability test with 5 users",
        "Prepare clickable prototype", "Redesign onboarding flow", "Audit accessibility of key screens"]),
}
COLLEGES = ["Thiagarajar College of Engineering, Madurai", "PSG College of Technology, Coimbatore", "NIT Tiruchirappalli",
            "Anna University, Chennai", "Kongu Engineering College, Erode", "SASTRA University, Thanjavur",
            "Mepco Schlenk Engineering College, Sivakasi", "Government College of Technology, Coimbatore"]
FIRST = ["Aarav", "Divya", "Karthik", "Meera", "Naveen", "Priya", "Rahul", "Sneha", "Vikram", "Anjali", "Harish", "Lakshmi",
         "Manoj", "Nisha", "Pranav", "Revathi", "Suresh", "Tamil", "Uma", "Yuvan", "Bharathi", "Deepak", "Gayathri", "Ilango", "Janani"]
LAST = ["Kumar", "Raj", "Subramanian", "Nair", "Iyer", "Selvam", "Murugan", "Pillai", "Venkatesh", "Rao"]
ROLE_EXTRA = ["Team Lead", "Intern", "Intern", "Intern", "Intern"]

DEMO_LEAD_PASSWORD = "Lead@1234"


def ensure_admin(db, username, password):
    db.execute("INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, 'admin')",
               (username, generate_password_hash(password), "System Administrator"))
    db.commit()


def seed_demo(db, today, admin_id):
    rnd = random.Random(2026)
    used_names = set()
    intern_no = 0
    for t_idx, (team_name, (desc, base_role, titles)) in enumerate(TEAMS.items()):
        team_id = db.execute("INSERT INTO teams (name, description) VALUES (?, ?)", (team_name, desc)).lastrowid
        member_ids = []
        for k in range(5):
            while True:
                name = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
                if name not in used_names:
                    used_names.add(name)
                    break
            intern_no += 1
            join = today - timedelta(days=rnd.randint(110, 135))
            email = name.lower().replace(" ", ".") + "@example.com"
            phone = str(rnd.choice([6, 7, 8, 9])) + "".join(str(rnd.randint(0, 9)) for _ in range(9))
            role = "Team Lead - " + base_role if k == 0 else base_role
            iid = db.execute(
                "INSERT INTO interns (name, dit_id, email, phone, college, role, joining_date) VALUES (?,?,?,?,?,?,?)",
                (name, f"DIT2026{intern_no:03d}", email, phone, COLLEGES[(intern_no + t_idx) % len(COLLEGES)], role, join.isoformat())).lastrowid
            db.execute("INSERT INTO team_members (team_id, intern_id) VALUES (?, ?)", (team_id, iid))
            member_ids.append((iid, join))
        db.execute("UPDATE teams SET leader_id = ? WHERE id = ?", (member_ids[0][0], team_id))
        slug = "".join(c for c in team_name.split()[0].lower() if c.isalnum())
        db.execute("INSERT INTO users (username, password_hash, full_name, role, team_id) VALUES (?,?,?,?,?)",
                   (f"lead_{slug}", generate_password_hash(DEMO_LEAD_PASSWORD),
                    db.execute("SELECT name FROM interns WHERE id = ?", (member_ids[0][0],)).fetchone()[0], "team_lead", team_id))
        for iid, join in member_ids:
            for title in rnd.sample(titles, rnd.randint(3, 5)):
                _seed_task(db, rnd, today, admin_id, iid, join, title)
    db.commit()


def _seed_task(db, rnd, today, admin_id, intern_id, join, title):
    assigned = join + timedelta(days=rnd.randint(2, max(3, (today - join).days - 3)))
    if rnd.random() < 0.12:
        assigned = today + timedelta(days=rnd.randint(0, 5))
    due = assigned + timedelta(days=rnd.randint(7, 21))
    r = rnd.random()
    if assigned > today:
        status = "Not Started"
    elif due < today - timedelta(days=5):
        status = "Completed" if r < .62 else "Submitted" if r < .70 else "Under Review" if r < .77 else "Rejected" if r < .82 else "In Progress" if r < .91 else "Not Started"
    else:
        status = "In Progress" if r < .38 else "Submitted" if r < .56 else "Under Review" if r < .66 else "Not Started" if r < .86 else "Completed"
    sub = None
    a_status, score, remarks = "Pending", None, None
    if status in ("Submitted", "Under Review", "Completed", "Rejected"):
        latest = min(due + timedelta(days=3), today)
        earliest = min(assigned + timedelta(days=2), latest)
        sub = earliest + timedelta(days=rnd.randint(0, max(0, (latest - earliest).days)))
        if status == "Completed":
            a_status, score, remarks = "Approved", float(rnd.randint(62, 98)), rnd.choice(["Good work, meets requirements.", "Well documented and tested.", "Clean implementation.", "Delivered on time."])
        elif status == "Under Review":
            a_status = "Under Review"
        elif status == "Rejected":
            a_status, score, remarks = "Rejected", float(rnd.randint(30, 55)), rnd.choice(["Requirements not met - please rework.", "Incomplete submission.", "Needs proper testing evidence."])
    elif status == "In Progress":
        remarks = rnd.choice([None, "Work started, first draft in progress.", "Waiting for review comments."])
    tid = db.execute(
        """INSERT INTO tasks (task_code, title, description, intern_id, assigned_date, due_date, submission_date, status,
                              assessment_status, assessment_score, remarks, created_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (f"TMP-{rnd.random()}", title, f"Complete the task '{title}' and submit the deliverables with a short summary.",
         intern_id, assigned.isoformat(), due.isoformat(), sub.isoformat() if sub else None, status, a_status, score, remarks, admin_id)).lastrowid
    db.execute("UPDATE tasks SET task_code = ? WHERE id = ?", (f"TSK-{tid:04d}", tid))
    if a_status != "Pending":
        db.execute("INSERT INTO assessments (task_id, assessor_id, status, score, remarks, assessed_at) VALUES (?,?,?,?,?,?)",
                   (tid, admin_id, a_status, score, remarks, (sub or today).isoformat() + " 10:00:00"))
