"""Excel report generation (Pandas + OpenPyXL) with professional formatting."""
from datetime import datetime
from io import BytesIO

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import queries as Q

HEADER_FILL = PatternFill("solid", fgColor="16324F")
BAND_FILL = PatternFill("solid", fgColor="F3F6F9")
THIN = Side(style="thin", color="C9D3DD")
STATUS_FILLS = {
    "Completed": "CDEBD5", "Approved": "CDEBD5", "In Progress": "D4E6F7", "Submitted": "E4DCF5",
    "Under Review": "FBE9BE", "Not Started": "E7EAEE", "Pending": "E7EAEE", "Rejected": "F6CFCF", "Overdue": "F4B9B9",
}
WRAP_COLUMNS = {"Description", "Remarks", "Task Title"}

REPORTS = {
    "intern_master": ("Intern Master", "Complete list of interns with team allocation and task counts."),
    "team_allocation": ("Team Allocation", "Team-wise allocation of interns, including team leaders."),
    "task_tracker": ("Complete Task Tracker", "All tasks with status, deadlines and assessment details."),
    "completed_tasks": ("Completed Tasks", "Tasks that have been completed."),
    "pending_tasks": ("Pending Tasks", "Open work: every task that is not yet Completed (Not Started, In Progress, Submitted, Under Review, Rejected, Overdue)."),
    "overdue_tasks": ("Overdue Tasks", "Tasks past their due date that are still Not Started / In Progress."),
    "assessment_report": ("Assessment Report", "Assessment status and scores for tasks that reached the assessment stage."),
    "team_lead_report": ("Team Lead Report", "Team-wise summary for team leaders: members, task progress, overdue work and assessments."),
}

TASK_COLUMNS = ["task_code", "title", "description", "intern_name", "dit_id", "team_name", "college", "assigned_date",
                "due_date", "submission_date", "eff_status", "days_overdue", "assessment_status", "assessment_score", "remarks"]
TASK_HEADERS = ["Task ID", "Task Title", "Description", "Intern Name", "DIT ID", "Team", "College", "Assigned Date",
                "Due Date", "Submission Date", "Task Status", "Days Overdue", "Assessment Status", "Assessment Score", "Remarks"]


def _tasks_df(rows):
    df = pd.DataFrame([{k: r[k] for k in TASK_COLUMNS} for r in rows], columns=TASK_COLUMNS)
    df.columns = TASK_HEADERS
    df["Team"] = df["Team"].fillna("Unassigned")
    return df.fillna("")


def _style_sheet(ws, df, title, subtitle):
    ncols = max(len(df.columns), 1)
    last = get_column_letter(ncols)
    ws["A1"] = title
    ws["A1"].font = Font(name="Calibri", size=16, bold=True, color="16324F")
    ws["A2"] = subtitle
    ws["A2"].font = Font(name="Calibri", size=10, italic=True, color="5B6B7B")
    header_row = 4
    for c in range(1, ncols + 1):
        cell = ws.cell(row=header_row, column=c)
        cell.fill = HEADER_FILL
        cell.font = Font(name="Calibri", bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
    ws.row_dimensions[header_row].height = 24
    for idx, col in enumerate(df.columns, start=1):
        letter = get_column_letter(idx)
        longest = max([len(str(col))] + [len(str(v)) for v in df[col].tolist()[:500]]) if len(df) else len(str(col))
        ws.column_dimensions[letter].width = min(max(longest + 3, 11), 60 if col in WRAP_COLUMNS else 42)
    for r in range(header_row + 1, header_row + 1 + len(df)):
        for c, col in enumerate(df.columns, start=1):
            cell = ws.cell(row=r, column=c)
            cell.border = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
            cell.alignment = Alignment(vertical="top", wrap_text=col in WRAP_COLUMNS)
            if (r - header_row) % 2 == 0:
                cell.fill = BAND_FILL
            if "Status" in col and str(cell.value) in STATUS_FILLS:
                cell.fill = PatternFill("solid", fgColor=STATUS_FILLS[str(cell.value)])
                cell.alignment = Alignment(horizontal="center", vertical="top")
            if "%" in col or col.endswith("Score") or col.startswith("Total") or col.endswith("Tasks") or col in ("Members", "Days Overdue"):
                cell.alignment = Alignment(horizontal="center", vertical="top")
    ws.auto_filter.ref = f"A{header_row}:{last}{header_row + max(len(df), 1)}"
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{header_row}:{header_row}"


def _write(writer, sheet, df, title, subtitle):
    df.to_excel(writer, sheet_name=sheet, index=False, startrow=3)
    _style_sheet(writer.sheets[sheet], df, title, subtitle)


def _intern_master_df(db, scope_team):
    rows, _ = Q.list_interns(db, {}, scope_team)
    df = pd.DataFrame([{
        "Intern Name": r["name"], "DIT ID": r["dit_id"], "Email": r["email"], "Phone": r["phone"], "College": r["college"],
        "Team": r["team_name"] or "Unassigned", "Assigned Role": r["role"], "Joining Date": r["joining_date"],
        "Total Tasks": r["task_count"], "Completed Tasks": r["completed_count"]} for r in rows],
        columns=["Intern Name", "DIT ID", "Email", "Phone", "College", "Team", "Assigned Role", "Joining Date", "Total Tasks", "Completed Tasks"])
    return df


def _team_allocation_df(db, scope_team):
    cond, params = "", {}
    if scope_team is not None:
        cond, params = " WHERE tg.id = :t", {"t": scope_team}
    rows = db.execute(f"""SELECT tg.name team, (tg.leader_id = i.id) AS is_leader, i.name, i.dit_id, i.role, i.college, i.email, i.joining_date
                          FROM teams tg JOIN team_members m ON m.team_id = tg.id JOIN interns i ON i.id = m.intern_id{cond}
                          ORDER BY tg.name COLLATE NOCASE, is_leader DESC, i.name COLLATE NOCASE""", params).fetchall()
    return pd.DataFrame([{
        "Team": r["team"], "Team Leader": "Yes" if r["is_leader"] else "No", "Intern Name": r["name"], "DIT ID": r["dit_id"],
        "Assigned Role": r["role"], "College": r["college"], "Email": r["email"], "Joining Date": r["joining_date"]} for r in rows],
        columns=["Team", "Team Leader", "Intern Name", "DIT ID", "Assigned Role", "College", "Email", "Joining Date"])


def _team_summary_df(db, today, scope_team):
    stats = Q.team_stats(db, today, scope_team)
    cols = ["Team", "Team Leader", "Leader DIT ID", "Leader Email", "Members", "Total Tasks", "Completed Tasks",
            "Pending (Not Started)", "In Progress", "Submitted / Under Review", "Rejected", "Overdue Tasks",
            "Assessment Pending", "Assessment Approved", "Assessment Rejected", "Average Score", "Completion %"]
    return pd.DataFrame([{
        "Team": t["name"], "Team Leader": t["leader_name"] or "Not assigned", "Leader DIT ID": t["leader_dit_id"] or "",
        "Leader Email": t["leader_email"] or "", "Members": t["members"], "Total Tasks": t["total"],
        "Completed Tasks": t["completed"], "Pending (Not Started)": t["not_started"], "In Progress": t["in_progress"],
        "Submitted / Under Review": t["submitted"] + t["under_review"], "Rejected": t["rejected"],
        "Overdue Tasks": t["overdue"], "Assessment Pending": t["assess_pending"], "Assessment Approved": t["assess_approved"],
        "Assessment Rejected": t["assess_rejected"], "Average Score": t["avg_score"] if t["avg_score"] is not None else "",
        "Completion %": t["completion_pct"]} for t in stats], columns=cols)


def build_report(kind, db, today, scope_team=None, args=None):
    """Return (BytesIO, filename) for the requested report kind. Raises KeyError for unknown kinds."""
    title, description = REPORTS[kind]
    args = args or {}
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    subtitle = f"{description}   |   Generated: {stamp}"
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        if kind == "intern_master":
            _write(writer, "Intern Master", _intern_master_df(db, scope_team), title, subtitle)
        elif kind == "team_allocation":
            _write(writer, "Team Allocation", _team_allocation_df(db, scope_team), title, subtitle)
        elif kind == "team_lead_report":
            _write(writer, "Team Summary", _team_summary_df(db, today, scope_team), title, subtitle)
            rows = Q.task_rows(db, today, scope_team=scope_team, order="team_name COLLATE NOCASE, due_date")
            _write(writer, "Team Tasks", _tasks_df(rows), title + " - Task Detail", subtitle)
        else:
            if kind == "task_tracker":
                rows, _t, _w = Q.list_tasks(db, today, args, scope_team)
                rows = list(rows)
                if args.get("sort") not in Q.SORTS:
                    rows.sort(key=lambda r: r["id"])
            elif kind == "completed_tasks":
                rows = Q.task_rows(db, today, "eff_status = 'Completed'", scope_team=scope_team, order="team_name, intern_name")
            elif kind == "pending_tasks":
                rows = Q.task_rows(db, today, "eff_status != 'Completed'", scope_team=scope_team, order="due_date, intern_name")
            elif kind == "overdue_tasks":
                rows = Q.task_rows(db, today, "eff_status = 'Overdue'", scope_team=scope_team, order="days_overdue DESC, intern_name")
            else:  # assessment_report
                rows = Q.task_rows(db, today, f"status IN ({Q.ASSESSABLE_SQL})", scope_team=scope_team, order="assessment_status, intern_name")
            _write(writer, title[:31], _tasks_df(rows), title, subtitle)
    buf.seek(0)
    return buf, f"{kind}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
