# Software Requirements Specification - Internship Task Tracking System

## 1. Introduction
**Purpose.** Provide one central, web-based system for an organisation to manage interns, DIT IDs, team allocation, task assignment, deadlines, submissions and assessments, and to produce management reports.
**Scope.** Admin and Team Lead users work in a browser. Data is stored in SQLite. Excel reports are generated on demand.
**Definitions.** *DIT ID* - unique identifier of an intern. *Open task* - any task not yet Completed. *Pending* - Not Started. *Overdue* - Not Started/In Progress after due date.

## 2. Overall description
* **Users:** Administrator (full access); Team Lead (own team only).
* **Environment:** Python 3.10+, any modern browser; deployable on Render (Linux, gunicorn) or run locally on Windows.
* **Constraints:** SQLite single-writer database; Bootstrap, Chart.js and fonts are loaded from CDNs.
* **Assumptions:** an intern belongs to at most one team; dates use the configured time zone (default Asia/Kolkata).

## 3. Functional requirements
| ID | Requirement |
|---|---|
| FR-01 | The system shall authenticate users with username/password and support logout. |
| FR-02 | The system shall provide Admin and Team Lead roles with role-based access control. |
| FR-03 | The system shall let admins add, view, edit and delete interns with name, DIT ID, email, phone, college, team, role, joining date. |
| FR-04 | DIT ID shall be unique (case-insensitive); mandatory fields, email format and phone number shall be validated. |
| FR-05 | The system shall search interns by name/DIT ID/email and filter by college and team. |
| FR-06 | The system shall let admins create/edit/delete teams, assign a leader, add and remove members. |
| FR-07 | The system shall display team members, team-wise task progress and team completion percentage. |
| FR-08 | Admins and the relevant Team Lead shall create tasks with title, description, intern, assigned/due/submission dates, status, assessment status, score and remarks. |
| FR-09 | Task statuses: Not Started, In Progress, Submitted, Under Review, Completed, Rejected, Overdue. |
| FR-10 | Tasks that are Not Started/In Progress after their due date shall be identified as Overdue automatically. |
| FR-11 | The system shall record assessments (Pending, Under Review, Approved, Rejected) with a score 0-100 and keep a history. |
| FR-12 | The dashboard shall show interns, teams, assigned/completed/pending/in-progress/submitted/overdue tasks, assessment pending and overall completion %. |
| FR-13 | The dashboard shall show charts: status distribution, team-wise completion, intern-wise performance, monthly submissions. |
| FR-14 | The system shall filter tasks by DIT ID, intern name, team, college, task status, assessment status and date range. |
| FR-15 | The system shall generate formatted Excel reports: Intern Master, Team Allocation, Complete Task Tracker, Completed, Pending, Overdue, Assessment, Team Lead. |
| FR-16 | The system shall provide a printable Team Lead report per team. |
| FR-17 | The system shall provide a User Guide page and Settings (password change; user management and activity log for admins). |
| FR-18 | The system shall record an activity log of create/update/delete/status/assessment/export/login events. |

## 4. Non-functional requirements
* **Security:** salted password hashes (Werkzeug scrypt), CSRF tokens on every state-changing request, HttpOnly + SameSite cookies (Secure in production), server-side validation, parameterised SQL, login throttling, output auto-escaping, no-store caching for authenticated pages.
* **Usability:** responsive layout (desktop to mobile), confirmation dialogs for deletions, success/error toasts.
* **Reliability:** database errors are caught, rolled back and reported in plain language; errors are logged to console and `logs/app.log`.
* **Performance:** list pages are paginated; typical page response well under one second for thousands of tasks.
* **Maintainability:** modular code (routes, queries, validators, reports), automated tests.
* **Portability:** runs on Windows/Linux/macOS; one-command deployment on Render.

## 5. Use cases (summary)
UC-1 Admin registers an intern; UC-2 Admin creates a team and assigns members; UC-3 Admin/Lead assigns a task; UC-4 Lead updates status; UC-5 Lead/Admin assesses a submission; UC-6 Admin reviews dashboard; UC-7 Admin exports Excel report; UC-8 Admin creates a Team Lead account.

## 6. Acceptance criteria
All 40 automated tests pass; every navigation link, form, chart and export works in a browser; the application is reachable through a public HTTPS URL after deployment.
