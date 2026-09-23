import sqlite3
import time
from datetime import date

import pandas as pd
import streamlit as st

DB_PATH = "project_monitor.db"

st.set_page_config(page_title="Project Monitor", layout="wide")


def get_conn():
    return sqlite3.connect(DB_PATH)


def load_tables():
    conn = get_conn()
    tasks = pd.read_sql("SELECT * FROM tasks", conn)
    members = pd.read_sql("SELECT * FROM team_members", conn)
    conn.close()
    return tasks, members


st.title("Project monitor")

auto = st.checkbox("Auto-refresh every 15s")

tasks, members = load_tables()

# ---------- Snapshot metrics (stand-in for a full burndown until history exists) ----------
col1, col2, col3, col4 = st.columns(4)
total = len(tasks)
done = (tasks["status"] == "Done").sum()
blocked = (tasks["status"] == "Blocked").sum()
overdue = (pd.to_datetime(tasks["due_date"]).dt.date < date.today()).sum()
col1.metric("Total tasks", total)
col2.metric("Done", f"{done}/{total}")
col3.metric("Blocked", blocked)
col4.metric("Overdue", overdue)

# ---------- Status breakdown ----------
st.subheader("Status breakdown")
status_counts = tasks["status"].value_counts()
st.bar_chart(status_counts)

# ---------- Workload ----------
st.subheader("Workload by team member")
members["utilization_pct"] = (
    100 * members["current_allocated_hours"] / members["weekly_capacity_hours"]
).round(0)
st.bar_chart(members.set_index("name")["utilization_pct"])
overloaded = members[members["utilization_pct"] > 90]
for _, m in overloaded.iterrows():
    st.warning(f"{m['name']} is at {int(m['utilization_pct'])}% capacity — consider reassigning a task.")

# ---------- Task table ----------
st.subheader("Tasks")


def highlight_status(row):
    color = ""
    if row["status"] == "Blocked":
        color = "background-color: #f8d7da"
    elif row["status"] == "Done":
        color = "background-color: #d4edda"
    return [color] * len(row)


member_lookup = members.set_index("id")["name"].to_dict()
display = tasks.copy()
display["assignee"] = display["assignee_id"].map(member_lookup)
cols = ["id", "title", "assignee", "status", "due_date", "estimated_hours",
        "logged_hours", "required_skills", "comment_text"]
st.dataframe(display[cols].style.apply(highlight_status, axis=1), use_container_width=True)

# ---------- Create / update task (Jira-style manual entry) ----------
st.subheader("Create or update a task")

with st.form("task_form", clear_on_submit=True):
    mode = st.radio("Mode", ["Create new", "Update existing"], horizontal=True)
    task_id = None
    if mode == "Update existing":
        task_id = st.selectbox("Task", tasks["id"].tolist(),
                                format_func=lambda i: f"#{i} {tasks.loc[tasks.id == i, 'title'].values[0]}")

    title = st.text_input("Title")
    assignee_name = st.selectbox("Assignee", members["name"].tolist())
    estimated_hours = st.number_input("Estimated hours", min_value=0.0, value=4.0, step=0.5)
    logged_hours = st.number_input("Logged hours", min_value=0.0, value=0.0, step=0.5)
    due = st.date_input("Due date")
    status = st.selectbox("Status", ["To Do", "In Progress", "In Review", "Blocked", "Done"])
    required_skills = st.text_input("Required skills (comma-separated)")
    dependency_id = st.selectbox("Depends on (optional)", [None] + tasks["id"].tolist())
    comment = st.text_area("Comment")

    submitted = st.form_submit_button("Save task")

    if submitted:
        if not title.strip():
            st.error("Title is required.")
        else:
            assignee_id = int(members.loc[members.name == assignee_name, "id"].values[0])
            dep_str = str(dependency_id) if dependency_id else ""
            conn = get_conn()
            cur = conn.cursor()
            if mode == "Create new":
                new_id = int(tasks["id"].max()) + 1 if len(tasks) else 1
                cur.execute(
                    "INSERT INTO tasks (id, project_id, title, assignee_id, estimated_hours, "
                    "logged_hours, due_date, dependency_ids, status, comment_text, required_skills) "
                    "VALUES (?,1,?,?,?,?,?,?,?,?,?)",
                    (new_id, title, assignee_id, estimated_hours, logged_hours,
                     str(due), dep_str, status, comment, required_skills),
                )
            else:
                cur.execute(
                    "UPDATE tasks SET title=?, assignee_id=?, estimated_hours=?, logged_hours=?, "
                    "due_date=?, dependency_ids=?, status=?, comment_text=?, required_skills=? "
                    "WHERE id=?",
                    (title, assignee_id, estimated_hours, logged_hours,
                     str(due), dep_str, status, comment, required_skills, task_id),
                )
            # Recompute allocated hours for the affected member
            cur.execute("""
                UPDATE team_members
                SET current_allocated_hours = (
                    SELECT COALESCE(SUM(estimated_hours), 0) FROM tasks
                    WHERE tasks.assignee_id = team_members.id AND tasks.status != 'Done'
                )
            """)
            conn.commit()
            conn.close()
            st.success("Saved.")
            st.rerun()

if auto:
    time.sleep(15)
    st.rerun()
