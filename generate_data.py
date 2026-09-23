import sqlite3
import random
from datetime import date, timedelta

DB_PATH = "project_monitor.db"

NUM_EMPLOYEES = 50
NUM_TASKS = 150


def create_schema(conn):
    conn.executescript("""
    DROP TABLE IF EXISTS projects;
    DROP TABLE IF EXISTS team_members;
    DROP TABLE IF EXISTS tasks;
    DROP TABLE IF EXISTS risk_scores;
    DROP TABLE IF EXISTS reallocation_suggestions;
    DROP TABLE IF EXISTS assignment_suggestions;
    DROP TABLE IF EXISTS project_forecast;

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
        skills TEXT NOT NULL
    );

    CREATE TABLE tasks (
        id INTEGER PRIMARY KEY,
        project_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        assignee_id INTEGER,
        estimated_hours REAL NOT NULL,
        logged_hours REAL NOT NULL DEFAULT 0,
        due_date TEXT NOT NULL,
        dependency_ids TEXT DEFAULT '',
        status TEXT NOT NULL,
        comment_text TEXT DEFAULT '',
        required_skills TEXT DEFAULT '',
        FOREIGN KEY(project_id) REFERENCES projects(id),
        FOREIGN KEY(assignee_id) REFERENCES team_members(id)
    );

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

    CREATE TABLE project_forecast (
        project_id INTEGER PRIMARY KEY,
        remaining_hours REAL,
        predicted_completion_date TEXT,
        project_deadline TEXT,
        days_ahead_or_behind INTEGER,
        on_track INTEGER,
        computed_at TEXT
    );
    """)
    conn.commit()


FIRST_NAMES = [
    "Priya", "Jonas", "Amara", "Liu", "Marco", "Sofia", "Ahmed", "Elena", "Kwame", "Yuki",
    "Diego", "Fatima", "Lars", "Ingrid", "Chen", "Aisha", "Mateo", "Nadia", "Oleg", "Hana",
    "Ravi", "Camila", "Sven", "Zara", "Tariq", "Mei", "Anton", "Layla", "Bjorn", "Nia",
    "Rohan", "Freya", "Kai", "Amina", "Pavel", "Sana", "Erik", "Leila", "Dmitri", "Yara",
    "Arjun", "Maria", "Felix", "Noor", "Viktor", "Dara", "Omar", "Ines", "Tomas", "Zoe",
]
LAST_NAMES = [
    "Nair", "Weber", "Okafor", "Chen", "Rossi", "Garcia", "Khan", "Novak", "Mensah", "Sato",
    "Fernandez", "Hussain", "Larsen", "Johansson", "Wang", "Ali", "Silva", "Petrov", "Kowalski",
    "Park", "Patel", "Costa", "Andersen", "Ahmed", "Yusuf", "Lin", "Ivanov", "Haddad", "Nilsson",
    "Diallo",
]

SKILLS_POOL = [
    "python", "sql", "flask", "react", "ui-design", "power-bi", "power-automate",
    "scada", "iiot", "excel", "devops", "testing", "docs", "project-management",
    "javascript", "aws", "docker", "java", "c-sharp", "kubernetes", "tableau", "node",
]

VERBS = ["Design", "Build", "Implement", "Test", "Review", "Deploy", "Document",
         "Refactor", "Optimize", "Debug", "Integrate", "Migrate", "Configure",
         "Analyze", "Automate"]
COMPONENTS = [
    "database schema", "REST API", "dashboard UI", "authentication module",
    "risk scoring model", "reporting pipeline", "caching layer", "notification service",
    "user profile page", "search feature", "payment integration", "logging system",
    "test suite", "CI/CD pipeline", "data export tool", "admin panel", "email service",
    "analytics module", "file upload feature", "permission system",
]

COMMENTS_NORMAL = ["", "On track, no issues.", "Started work, looks straightforward.",
                   "Reviewed with the team, good progress.", ""]
COMMENTS_RISK = [
    "Blocked - waiting on the API contract from the backend team.",
    "This is taking longer than expected, might slip.",
    "Blocked on a dependency, can't proceed until it's resolved.",
    "Still waiting on clarification, no progress since yesterday.",
]


def generate_team(n):
    used_names = set()
    team = []
    while len(team) < n:
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        if name in used_names:
            continue
        used_names.add(name)
        capacity = random.choices([20, 30, 40], weights=[0.1, 0.2, 0.7])[0]
        skills = ",".join(random.sample(SKILLS_POOL, k=random.randint(2, 4)))
        team.append((name, capacity, skills))
    return team


def generate_task_titles(n):
    used = set()
    titles = []
    all_combos = [(v, c) for v in VERBS for c in COMPONENTS]
    random.shuffle(all_combos)
    for v, c in all_combos:
        if len(titles) >= n:
            break
        title = f"{v} {c}"
        if title not in used:
            used.add(title)
            titles.append(title)
    i = 2
    while len(titles) < n:
        v, c = random.choice(all_combos)
        titles.append(f"{v} {c} ({i})")
        i += 1
    return titles


def seed_data(conn):
    cur = conn.cursor()
    today = date.today()

    cur.execute(
        "INSERT INTO projects (id, name, start_date, deadline, status) VALUES (?,?,?,?,?)",
        (1, "AI Project Monitoring Tool", str(today - timedelta(days=1)),
         str(today + timedelta(days=7)), "active"),
    )

    team = generate_team(NUM_EMPLOYEES)
    member_ids = []
    for i, (name, capacity, skills) in enumerate(team, start=1):
        cur.execute(
            "INSERT INTO team_members (id, name, weekly_capacity_hours, current_allocated_hours, skills) "
            "VALUES (?,?,?,?,?)",
            (i, name, capacity, 0, skills),
        )
        member_ids.append(i)

    overloaded_id = member_ids[0]
    idle_id = member_ids[1]
    normal_pool = [m for m in member_ids if m not in (overloaded_id, idle_id)]

    titles = generate_task_titles(NUM_TASKS)
    task_id = 1
    dependency_pool = []

    for idx, title in enumerate(titles):
        est_hours = random.choice([2, 3, 4, 5, 6, 8, 10, 12, 16])
        req_skills = ",".join(random.sample(SKILLS_POOL, k=random.randint(1, 3)))

        if idx < 10:
            assignee = overloaded_id
        else:
            assignee = random.choice(normal_pool)

        logged = round(est_hours * random.uniform(0.3, 1.4), 1)
        overdue = random.random() < 0.2
        due = today - timedelta(days=1) if overdue else today + timedelta(days=random.randint(1, 10))

        is_blocked = random.random() < 0.1
        if idx < 10:
            status = "Blocked" if is_blocked else random.choice(["To Do", "In Progress", "In Review"])
        else:
            status = "Blocked" if is_blocked else random.choice(
                ["To Do", "In Progress", "In Review", "Done"]
            )
        comment = random.choice(COMMENTS_RISK) if is_blocked else random.choice(COMMENTS_NORMAL)

        dep_ids = ""
        if dependency_pool and random.random() < 0.25:
            dep_ids = str(random.choice(dependency_pool))
        dependency_pool.append(task_id)

        cur.execute(
            "INSERT INTO tasks (id, project_id, title, assignee_id, estimated_hours, logged_hours, "
            "due_date, dependency_ids, status, comment_text, required_skills) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (task_id, 1, title, assignee, est_hours, logged, str(due), dep_ids, status, comment, req_skills),
        )
        task_id += 1

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
    return overloaded_id, idle_id


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    create_schema(conn)
    overloaded_id, idle_id = seed_data(conn)

    cur = conn.cursor()
    total_members = cur.execute("SELECT COUNT(*) FROM team_members").fetchone()[0]
    total_tasks = cur.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    print(f"Team members: {total_members}")
    print(f"Tasks: {total_tasks}")

    print("\nSample of team members (first 5):")
    for row in cur.execute("SELECT id, name, weekly_capacity_hours, current_allocated_hours, skills "
                            "FROM team_members LIMIT 5"):
        pct = round(100 * row[3] / row[2])
        print(f"  {row[1]:20s} capacity={row[2]:>4} allocated={row[3]:>6} ({pct:>3}%) skills={row[4]}")

    print(f"\nDeliberately overloaded: id={overloaded_id}")
    for row in cur.execute("SELECT id, name, weekly_capacity_hours, current_allocated_hours FROM team_members WHERE id=?", (overloaded_id,)):
        pct = round(100 * row[3] / row[2])
        print(f"  {row[1]:20s} capacity={row[2]:>4} allocated={row[3]:>6} ({pct:>3}%)")

    print(f"Deliberately idle: id={idle_id}")
    for row in cur.execute("SELECT id, name, weekly_capacity_hours, current_allocated_hours FROM team_members WHERE id=?", (idle_id,)):
        pct = round(100 * row[3] / row[2])
        print(f"  {row[1]:20s} capacity={row[2]:>4} allocated={row[3]:>6} ({pct:>3}%)")

    conn.close()
    print(f"\nDone. Database written to {DB_PATH}")