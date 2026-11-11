"""Server-side validation. Every function returns (clean_data, errors_dict)."""
import re
from datetime import date, datetime

TASK_STATUSES = ["Not Started", "In Progress", "Submitted", "Under Review", "Completed", "Rejected", "Overdue"]
ASSESSMENT_STATUSES = ["Pending", "Under Review", "Approved", "Rejected"]
ROLES = ["admin", "team_lead"]

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^[6-9]\d{9}$")  # Indian mobile numbers; edit here for other regions
DIT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-/]{2,19}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,30}$")


def parse_date(value):
    """'' -> None, 'YYYY-MM-DD' -> date, anything else -> ValueError."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Invalid date")


def normalize_phone(raw):
    digits = re.sub(r"[\s\-()]", "", raw or "")
    if digits.startswith("+91"):
        digits = digits[3:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def validate_intern(form, db, intern_id=None):
    errors = {}
    data = {
        "name": " ".join((form.get("name") or "").split()),
        "dit_id": (form.get("dit_id") or "").strip().upper(),
        "email": (form.get("email") or "").strip().lower(),
        "phone": normalize_phone(form.get("phone")),
        "college": " ".join((form.get("college") or "").split()),
        "role": " ".join((form.get("role") or "").split()),
        "joining_date": (form.get("joining_date") or "").strip(),
        "team_id": None,
    }
    if not data["name"]:
        errors["name"] = "Intern name is required."
    elif len(data["name"]) < 2 or len(data["name"]) > 100:
        errors["name"] = "Name must be 2-100 characters."

    if not data["dit_id"]:
        errors["dit_id"] = "DIT ID is required."
    elif not DIT_RE.match(data["dit_id"]):
        errors["dit_id"] = "DIT ID must be 3-20 characters (letters, digits, - _ /)."
    else:
        dup = db.execute("SELECT id FROM interns WHERE dit_id = ? AND id != ?", (data["dit_id"], intern_id or 0)).fetchone()
        if dup:
            errors["dit_id"] = "This DIT ID already exists. DIT IDs must be unique."

    if not data["email"]:
        errors["email"] = "Email is required."
    elif len(data["email"]) > 120 or not EMAIL_RE.match(data["email"]):
        errors["email"] = "Enter a valid email address (e.g. name@example.com)."

    if not data["phone"]:
        errors["phone"] = "Phone number is required."
    elif not PHONE_RE.match(data["phone"]):
        errors["phone"] = "Enter a valid 10-digit mobile number (optionally with +91)."

    if not data["college"]:
        errors["college"] = "College name is required."
    if not data["role"]:
        errors["role"] = "Assigned role is required."

    if not data["joining_date"]:
        errors["joining_date"] = "Joining date is required."
    else:
        try:
            d = parse_date(data["joining_date"])
            if d < date(2000, 1, 1) or d > date.today().replace(year=date.today().year + 1):
                errors["joining_date"] = "Joining date is out of the acceptable range."
        except ValueError:
            errors["joining_date"] = "Enter a valid date."

    team_raw = (form.get("team_id") or "").strip()
    if team_raw:
        tid = _int(team_raw)
        if tid is None or not db.execute("SELECT 1 FROM teams WHERE id = ?", (tid,)).fetchone():
            errors["team_id"] = "Selected team does not exist."
        else:
            data["team_id"] = tid
    return data, errors


def validate_team(form, db, team_id=None):
    errors = {}
    data = {
        "name": " ".join((form.get("name") or "").split()),
        "description": (form.get("description") or "").strip(),
        "leader_id": None,
    }
    if not data["name"]:
        errors["name"] = "Team name is required."
    elif len(data["name"]) > 80:
        errors["name"] = "Team name must be at most 80 characters."
    elif db.execute("SELECT 1 FROM teams WHERE name = ? AND id != ?", (data["name"], team_id or 0)).fetchone():
        errors["name"] = "A team with this name already exists."
    if len(data["description"]) > 300:
        errors["description"] = "Description must be at most 300 characters."

    leader_raw = (form.get("leader_id") or "").strip()
    if leader_raw:
        lid = _int(leader_raw)
        row = db.execute("SELECT i.id, tm.team_id FROM interns i LEFT JOIN team_members tm ON tm.intern_id = i.id WHERE i.id = ?", (lid,)).fetchone() if lid else None
        if not row:
            errors["leader_id"] = "Selected team leader does not exist."
        elif row["team_id"] is not None and row["team_id"] != team_id:
            errors["leader_id"] = "That intern already belongs to another team."
        else:
            data["leader_id"] = lid
    return data, errors


def validate_score(raw):
    """Return (value|None, error|None). Score must be a number between 0 and 100."""
    raw = (raw or "").strip() if isinstance(raw, str) else raw
    if raw in (None, ""):
        return None, None
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return None, "Assessment score must be a number."
    if score != score or score < 0 or score > 100:
        return None, "Assessment score must be between 0 and 100."
    return round(score, 1), None


def validate_task(form, db, today, allowed_intern_ids=None):
    errors = {}
    data = {
        "title": " ".join((form.get("title") or "").split()),
        "description": (form.get("description") or "").strip(),
        "intern_id": None,
        "assigned_date": (form.get("assigned_date") or "").strip(),
        "due_date": (form.get("due_date") or "").strip(),
        "submission_date": (form.get("submission_date") or "").strip() or None,
        "status": (form.get("status") or "Not Started").strip(),
        "assessment_status": (form.get("assessment_status") or "Pending").strip(),
        "assessment_score": None,
        "remarks": (form.get("remarks") or "").strip(),
    }
    if not data["title"]:
        errors["title"] = "Task title is required."
    elif len(data["title"]) < 3 or len(data["title"]) > 150:
        errors["title"] = "Task title must be 3-150 characters."
    if len(data["description"]) > 2000:
        errors["description"] = "Description must be at most 2000 characters."
    if len(data["remarks"]) > 1000:
        errors["remarks"] = "Remarks must be at most 1000 characters."

    iid = _int(form.get("intern_id"))
    if iid is None:
        errors["intern_id"] = "Please select an intern."
    elif not db.execute("SELECT 1 FROM interns WHERE id = ?", (iid,)).fetchone():
        errors["intern_id"] = "Selected intern does not exist."
    elif allowed_intern_ids is not None and iid not in allowed_intern_ids:
        errors["intern_id"] = "You can only assign tasks to interns in your own team."
    else:
        data["intern_id"] = iid

    if data["status"] not in TASK_STATUSES:
        errors["status"] = "Invalid task status."
    if data["assessment_status"] not in ASSESSMENT_STATUSES:
        errors["assessment_status"] = "Invalid assessment status."

    d_assigned = d_due = d_sub = None
    for key, label, required in (("assigned_date", "Assigned date", True), ("due_date", "Due date", True), ("submission_date", "Submission date", False)):
        raw = data[key]
        if not raw:
            if required:
                errors[key] = f"{label} is required."
            continue
        try:
            parsed = parse_date(raw)
        except ValueError:
            errors[key] = f"{label} is not a valid date."
            continue
        if parsed.year < 2000 or parsed.year > 2100:
            errors[key] = f"{label} is out of the acceptable range."
            continue
        if key == "assigned_date":
            d_assigned = parsed
        elif key == "due_date":
            d_due = parsed
        else:
            d_sub = parsed
    if d_assigned and d_due and d_due < d_assigned:
        errors["due_date"] = "Due date cannot be earlier than the assigned date."
    if d_sub:
        if d_assigned and d_sub < d_assigned:
            errors["submission_date"] = "Submission date cannot be earlier than the assigned date."
        elif d_sub > today:
            errors["submission_date"] = "Submission date cannot be in the future."

    score, score_err = validate_score(form.get("assessment_score"))
    if score_err:
        errors["assessment_score"] = score_err
    else:
        data["assessment_score"] = score
        if data["assessment_status"] == "Approved" and score is None and "assessment_status" not in errors:
            errors["assessment_score"] = "A score (0-100) is required when the assessment is Approved."
    return data, errors


def validate_assessment(form):
    errors = {}
    status = (form.get("status") or "").strip()
    remarks = (form.get("remarks") or "").strip()
    if status not in ASSESSMENT_STATUSES:
        errors["status"] = "Choose a valid assessment status."
    score, err = validate_score(form.get("score"))
    if err:
        errors["score"] = err
    elif status == "Approved" and score is None:
        errors["score"] = "A score (0-100) is required to approve a task."
    if len(remarks) > 1000:
        errors["remarks"] = "Remarks must be at most 1000 characters."
    return {"status": status, "score": score, "remarks": remarks}, errors


def validate_password(pw):
    if not pw or len(pw) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Password must contain both letters and digits."
    return None


def validate_user(form, db):
    errors = {}
    data = {
        "username": (form.get("username") or "").strip(),
        "full_name": " ".join((form.get("full_name") or "").split()),
        "role": (form.get("role") or "").strip(),
        "team_id": None,
        "password": form.get("password") or "",
    }
    if not USERNAME_RE.match(data["username"]):
        errors["username"] = "Username must be 3-30 characters (letters, digits, . _)."
    elif db.execute("SELECT 1 FROM users WHERE username = ?", (data["username"],)).fetchone():
        errors["username"] = "This username is already taken."
    if not data["full_name"]:
        errors["full_name"] = "Full name is required."
    if data["role"] not in ROLES:
        errors["role"] = "Choose a valid role."
    pw_err = validate_password(data["password"])
    if pw_err:
        errors["password"] = pw_err
    tid = _int(form.get("team_id"))
    if data["role"] == "team_lead":
        if tid is None or not db.execute("SELECT 1 FROM teams WHERE id = ?", (tid,)).fetchone():
            errors["team_id"] = "A Team Lead must be linked to an existing team."
        else:
            data["team_id"] = tid
    return data, errors
