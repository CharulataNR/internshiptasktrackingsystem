# System Architecture and Flowcharts

## Architecture
```mermaid
flowchart LR
    B[Browser<br/>Bootstrap 5 + JS + Chart.js] -->|HTTPS| G[gunicorn]
    G --> F[Flask app<br/>routes + auth + CSRF]
    F --> V[validators.py]
    F --> Q[queries.py<br/>SQL + overdue logic]
    F --> R[reports.py<br/>Pandas + OpenPyXL]
    Q --> D[(SQLite<br/>tracker.db)]
    F --> L[(logs/app.log<br/>activity_logs table)]
    R -->|.xlsx download| B
```
Layers: **presentation** (Jinja2 templates, CSS, JS) - **application** (Flask routes, security, validation) - **data** (SQLite via sqlite3 with foreign keys ON). One connection per request; transactions are committed or rolled back in `write()`.

## Flowchart: task lifecycle
```mermaid
flowchart TD
    A([Admin or Team Lead creates task]) --> B{Valid?<br/>dates, intern, score}
    B -- No --> C[Show field errors] --> A
    B -- Yes --> D[Not Started]
    D -->|work begins| E[In Progress]
    D -->|due date passes| O[Overdue - automatic]
    E -->|due date passes| O
    O -->|intern starts / submits| E
    E -->|intern submits| F[Submitted<br/>submission date recorded]
    F --> G[Under Review]
    G --> H{Assessment}
    H -- Approved + score --> I([Completed])
    H -- Rejected --> J[Rejected] -->|rework| E
```

## Flowchart: request handling and security
```mermaid
flowchart TD
    R([HTTP request]) --> C{POST?}
    C -- Yes --> T{CSRF token valid?}
    T -- No --> X[400 error page]
    T -- Yes --> L
    C -- No --> L{Logged in?}
    L -- No --> LG[Redirect to login]
    L -- Yes --> P{Role allowed and record in scope?}
    P -- No --> E[403 / 404]
    P -- Yes --> V[Validate input] --> W[Database transaction] --> A[Activity log] --> S[Redirect + success toast]
```
