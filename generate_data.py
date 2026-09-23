import sqlite3
import random
from datetime import date, timedelta

DB_PATH = "project_monitor.db"


def create_schema(conn):
    conn.executescript("""
    DROP TABLE IF EXISTS projects;
    DROP TABLE IF EXISTS team_members;
    DROP TABLE IF EXISTS tasks;
    DROP TABLE IF EXISTS risk_scores;
    DROP TABLE IF EXISTS reallocation_suggestions;
    DROP TABLE IF EXISTS assignment_suggestions;

    CREATE TABLE projects (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        start_date TEXT NOT NULL,
        deadline TEXT NOT NULL,
        status TEXT NOT NULL
    );

    CREATE TABLE team_members (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        weekly_capacity_hours REAL NOT NULL,
        current_allocated_hours REAL NOT NULL DEFAULT 0,
        skills TEXT NOT NULL              -- comma-separated tags
    );

    CREATE TABLE tasks (
        id INTEGER PRIMARY KEY,
        project_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        assignee_id INTEGER,
        estimated_hours REAL NOT NULL,
        logged_hours REAL NOT NULL DEFAULT 0,
        due_date TEXT NOT NULL,
        dependency_ids TEXT DEFAULT '',   -- comma-separated task ids
        status TEXT NOT NULL,             -- To Do / In Progress / In Review / Done / Blocked
        comment_text TEXT DEFAULT '',
        required_skills TEXT DEFAULT '',  -- comma-separated tags
        FOREIGN KEY(project_id) REFERENCES projects(id),
        FOREIGN KEY(assignee_id) REFERENCES team_members(id)
    );

    -- Derived tables: filled in by the Day 2 AI scripts, not seeded here.
    CREATE TABLE risk_scores (
        task_id INTEGER PRIMARY KEY,
        score REAL,
        factors TEXT,
        computed_at TEXT
    );

    CREATE TABLE reallocation_suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_member_id INTEGER,
        to_member_id INTEGER,
        task_id INTEGER,
        reason TEXT
    );

    CREATE TABLE assignment_suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER,
        candidate_member_id INTEGER,
        match_score REAL,
        reason TEXT
    );
    """)
    conn.commit()


# (name, weekly_capacity_hours, skills)
TEAM = [
    ("Priya Nair",   40, "python,sql,flask"),
    ("Jonas Weber",  40, "python,power-bi,power-automate"),
    ("Amara Okafor", 32, "scada,iiot,python"),
    ("Liu Chen",     40, "sql,power-bi,excel"),
    ("Marco Rossi",  20, "flask,react,ui-design"),
]

# (title, estimated_hours, required_skills)
TASK_TEMPLATES = [
    ("Design database schema",          6,  "sql,python"),
    ("Build task CRUD API",             10, "python,flask"),
    ("Build team member CRUD API",      6,  "python,flask"),
    ("Generate synthetic dataset",      4,  "python,sql"),
    ("Build dashboard skeleton",        8,  "python,power-bi"),
    ("Build manual entry form UI",      6,  "python,flask,ui-design"),
    ("Build risk-scoring formula",      6,  "python,sql"),
    ("Train risk classifier",           5,  "python"),
    ("Build workload utilization calc", 5,  "python,sql"),
    ("Build reallocation engine",       6,  "python,sql"),
    ("Build skill-matching engine",     5,  "python,sql"),
    ("Wire risk heatmap into UI",       4,  "python,react,ui-design"),
    ("Wire workload chart into UI",     4,  "python,react,ui-design"),
    ("Write integration tests",         4,  "python"),
    ("Write README and demo script",    2,  "python"),
]

COMMENTS_NORMAL = ["", "On track, no issues.", "Started work, looks straightforward.",
                   "Reviewed with the team, good progress.", ""]
COMMENTS_RISK = [
    "Blocked - waiting on the API contract from the backend team.",
    "This is taking longer than expected, might slip.",
    "Blocked on a dependency, can't proceed until it's resolved.",
    "Still waiting on clarification, no progress since yesterday.",
]

# Nudge specific task categories to specific people so the demo has a clear
# story: Priya ends up overloaded, Marco ends up comfortably underloaded.
FORCED_ASSIGNEE = {
    "Design database schema": 1, "Build task CRUD API": 1, "Build team member CRUD API": 1,
    "Build risk-scoring formula": 1, "Train risk classifier": 1,
    "Build manual entry form UI": 5, "Wire risk heatmap into UI": 5, "Wire workload chart into UI": 5,
    "Build workload utilization calc": 3, "Build reallocation engine": 3, "Build skill-matching engine": 4,
}


def seed_data(conn):
    cur = conn.cursor()
    today = date.today()

    cur.execute(
        "INSERT INTO projects (id, name, start_date, deadline, status) VALUES (?,?,?,?,?)",
        (1, "AI Project Monitoring Tool", str(today - timedelta(days=1)),
         str(today + timedelta(days=1)), "active"),
    )

    member_ids = []
    for i, (name, capacity, skills) in enumerate(TEAM, start=1):
        cur.execute(
            "INSERT INTO team_members (id, name, weekly_capacity_hours, current_allocated_hours, skills) "
            "VALUES (?,?,?,?,?)",
            (i, name, capacity, 0, skills),
        )
        member_ids.append(i)

    task_id = 1
    dependency_pool = []
    for title, est_hours, req_skills in TASK_TEMPLATES:
        assignee = FORCED_ASSIGNEE.get(title, random.choice(member_ids))

        logged = round(est_hours * random.uniform(0.3, 1.4), 1)
        overdue = random.random() < 0.25
        due = today - timedelta(days=1) if overdue else today + timedelta(days=random.randint(1, 5))

        is_blocked = random.random() < 0.15
        status = "Blocked" if is_blocked else random.choice(["To Do", "In Progress", "In Review", "Done"])
        comment = random.choice(COMMENTS_RISK) if is_blocked else random.choice(COMMENTS_NORMAL)

        dep_ids = ""
        if dependency_pool and random.random() < 0.3:
            dep_ids = str(random.choice(dependency_pool))
        dependency_pool.append(task_id)

        cur.execute(
            "INSERT INTO tasks (id, project_id, title, assignee_id, estimated_hours, logged_hours, "
            "due_date, dependency_ids, status, comment_text, required_skills) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (task_id, 1, title, assignee, est_hours, logged, str(due), dep_ids, status, comment, req_skills),
        )
        task_id += 1

    # Recompute allocated hours per member from their not-done tasks.
    cur.execute("""
        UPDATE team_members
        SET current_allocated_hours = (
            SELECT COALESCE(SUM(estimated_hours), 0)
            FROM tasks
            WHERE tasks.assignee_id = team_members.id
              AND tasks.status != 'Done'
        )
    """)
    conn.commit()


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    create_schema(conn)
    seed_data(conn)

    cur = conn.cursor()
    print("Team members:")
    for row in cur.execute(
        "SELECT id, name, weekly_capacity_hours, current_allocated_hours, skills FROM team_members"
    ):
        pct = round(100 * row[3] / row[2])
        print(f"  {row[1]:15s} capacity={row[2]:>4} allocated={row[3]:>5} ({pct:>3}%) skills={row[4]}")

    print("\nTasks:")
    for row in cur.execute("SELECT id, title, assignee_id, status, due_date FROM tasks"):
        print(f"  #{row[0]:2d} {row[1]:32s} assignee={row[2]} status={row[3]:12s} due={row[4]}")

    conn.close()
    print(f"\nDone. Database written to {DB_PATH}")
