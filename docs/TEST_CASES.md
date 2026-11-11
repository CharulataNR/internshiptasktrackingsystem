# Test Cases

Automated: `python -m unittest discover -s tests -v` (file `tests/test_app.py`). **Result at delivery: 40 tests, all passed.**

| ID | Area | Test case | Expected result | Automated test |
|---|---|---|---|---|
| TC-01 | Intern registration | Add intern with valid data | Intern saved, listed | `test_register_intern` |
| TC-02 | Duplicate DIT ID | Add intern with an existing DIT ID (any letter case) | Rejected with "already exists" | `test_duplicate_dit_id_rejected` |
| TC-03 | Validation | Empty name/college, bad email, 5-digit phone, impossible date | Each field error shown, nothing saved | `test_missing_and_invalid_fields` |
| TC-04 | Validation | Phone `+91 98765-43210` | Stored as 9876543210 | `test_phone_with_country_code_is_normalised` |
| TC-05 | Intern CRUD | Edit, search by DIT ID, filter by college, delete | Behaves as expected | `test_edit_search_filter_delete` |
| TC-06 | Duplicate DIT on edit | Change DIT ID to another intern's | Rejected | `test_duplicate_dit_on_edit_rejected` |
| TC-07 | Team creation | Create team with leader, add member, remove leader | Members/leader updated | `test_create_team_with_leader_and_members` |
| TC-08 | Team validation | Duplicate/blank team name | Rejected | `test_duplicate_team_name_and_blank_name` |
| TC-09 | Team membership | Intern in two teams | Blocked; move via edit works | `test_intern_belongs_to_one_team` |
| TC-10 | Team completion % | 1 of 2 tasks completed | 50.0% | `test_team_completion_percentage` |
| TC-11 | Task assignment | Create task | Task ID TSK-000N generated, linked to intern | `test_task_assignment_and_code` |
| TC-12 | Date validation | Due before assigned; invalid dates; future submission | Rejected with messages | `test_due_date_before_assigned_rejected`, `test_invalid_and_missing_dates_rejected`, `test_future_submission_date_rejected` |
| TC-13 | Task status update | Not Started > In Progress > Submitted; invalid status | Saved; submission date auto-set; invalid ignored | `test_status_updates_set_submission_date` |
| TC-14 | Overdue detection | Past-due Not Started/In Progress; on-time; completed-late | Only the first two flagged; clears when due date moves | `test_overdue_detection` |
| TC-15 | Assessment score | Score 101, -5, "abc", Approved without score | Rejected, task unchanged | `test_assessment_score_validation`, `test_score_validation_on_task_form` |
| TC-16 | Assessment flow | Approve 88.5 / reject then resubmit | Completed / Rejected; resubmission resets to Pending | `test_assessment_score_validation`, `test_reject_and_resubmit_resets_assessment` |
| TC-17 | Search and filters | DIT ID, college, status, date range, invalid date | Correct subsets; invalid date warned | `test_filters` |
| TC-18 | Dashboard | All KPI figures vs. direct SQL counts | Equal | `test_dashboard_numbers_match_database`, `test_chart_api_shape` |
| TC-19 | Excel reports | All 8 reports open in OpenPyXL with headings, filter, frozen header, widths; row counts match | Pass | `test_all_excel_reports`, `test_filtered_export_matches_filter` |
| TC-20 | Login/logout | Wrong password, correct password, logout, protected page | Redirect / access as expected | `test_login_logout_and_protected_pages` |
| TC-21 | Password hashing | No plaintext in DB | Hash prefix scrypt/pbkdf2 | `test_passwords_are_hashed` |
| TC-22 | CSRF | POST with no/invalid token; login without token | HTTP 400, nothing saved | `test_csrf_blocks_forged_post`, `test_login_requires_csrf` |
| TC-23 | Role permissions | Team Lead opens admin pages / other team's data | 403 / 404 | `test_team_lead_permissions` |
| TC-24 | Data scoping | Team Lead dashboard, intern list and Excel | Only own team | `test_team_lead_sees_only_own_team_data` |
| TC-25 | Task scoping | Lead assigns to own vs other team's intern | Allowed / rejected | `test_team_lead_cannot_assign_outside_team_but_can_inside` |
| TC-26 | User admin | Lead tries to create user; admin creates; weak password | 403 / created / rejected | `test_admin_only_settings_and_user_creation` |
| TC-27 | Misc security | Open redirect, cookie flags, throttle after 5 failures, password change, activity log | Safe behaviour | `test_open_redirect_blocked`, `test_session_cookie_flags`, `test_login_throttle`, `test_password_change`, `test_activity_log_written` |
| TC-28 | Database | FK, unique DIT ID (nocase), score CHECK | IntegrityError raised | `test_foreign_keys_and_checks` |

## Manual browser checklist (run before the demo)
- [ ] Sign in as admin; every sidebar link opens.
- [ ] Dashboard cards and four charts render; clicking a card opens the filtered task list.
- [ ] Add, edit, delete an intern; try a duplicate DIT ID.
- [ ] Create a team, add a member, set a leader.
- [ ] Create a task, change its status from the table dropdown, open task details.
- [ ] Assess a task in Assessment Management.
- [ ] Download each of the 8 Excel files and open in Excel.
- [ ] Sign in as `lead_web`: only that team is visible; admin pages show "Access denied".
- [ ] Resize the browser to phone width; menu button opens the sidebar.
