import math
import sqlite3
import time
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

import ai_engine
from generate_data import SKILLS_POOL

DB_PATH = "project_monitor.db"

st.set_page_config(page_title="Project Monitor", layout="wide", page_icon="📊")

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

LIGHT = dict(bg="#f7f9fc", card="#ffffff", text="#1a1a1a", subtext="#5c5c5c",
             border="#e3e6ec", accent="#3366ff", accent_text="#ffffff")
DARK = dict(bg="#0e1117", card="#1c1f26", text="#f5f5f5", subtext="#a0a0a0",
            border="#2d313a", accent="#6ea8fe", accent_text="#0e1117")


def inject_theme(dark: bool):
    c = DARK if dark else LIGHT
    st.markdown(f"""
        <style>
        [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
            background-color: {c['bg']};
        }}
        [data-testid="stSidebar"] {{
            background-color: {c['card']};
            border-right: 1px solid {c['border']};
        }}
        h1, h2, h3, p, label, span, .stMarkdown {{
            color: {c['text']} !important;
        }}
        [data-testid="stMetric"] {{
            background-color: {c['card']};
        }}
        [data-testid="stMetricLabel"] {{ color: {c['subtext']} !important; }}
        [data-testid="stMetricValue"] {{ color: {c['accent']} !important; }}
        [data-testid="stVerticalBlockBorderWrapper"] {{
            background-color: {c['card']};
            border: 1px solid {c['border']} !important;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        }}
        .stButton > button, [data-testid="stFormSubmitButton"] button,
        [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"] {{
            background-color: {c['accent']} !important;
            color: {c['accent_text']} !important;
            border: none !important;
            border-radius: 8px !important;
        }}
        .stButton > button:hover, [data-testid="stFormSubmitButton"] button:hover {{
            opacity: 0.85;
        }}
        [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input,
        [data-testid="stTextArea"] textarea, [data-testid="stDateInput"] input {{
            background-color: {c['bg']} !important;
            color: {c['text']} !important;
            border: 1px solid {c['border']} !important;
        }}
        </style>
    """, unsafe_allow_html=True)


def get_conn():
    return sqlite3.connect(DB_PATH)


def load_tables():
    conn = get_conn()
    tasks = pd.read_sql("SELECT * FROM tasks", conn)
    members = pd.read_sql("SELECT * FROM team_members", conn)
    conn.close()
    return tasks, members


def load_project():
    conn = get_conn()
    project = pd.read_sql("SELECT * FROM projects LIMIT 1", conn).iloc[0]
    conn.close()
    return project


def load_ai_outputs():
    conn = get_conn()
    try:
        risk = pd.read_sql("SELECT * FROM risk_scores", conn)
    except Exception:
        risk = pd.DataFrame(columns=["task_id", "score", "factors", "computed_at"])
    try:
        realloc = pd.read_sql("SELECT * FROM reallocation_suggestions", conn)
    except Exception:
        realloc = pd.DataFrame(columns=["from_member_id", "to_member_id", "task_id", "reason"])
    try:
        assign = pd.read_sql("SELECT * FROM assignment_suggestions", conn)
    except Exception:
        assign = pd.DataFrame(columns=["task_id", "candidate_member_id", "match_score", "reason"])
    try:
        forecast = pd.read_sql("SELECT * FROM project_forecast LIMIT 1", conn)
    except Exception:
        forecast = pd.DataFrame()
    conn.close()
    return risk, realloc, assign, forecast


title_col, toggle_col = st.columns([6, 1])
with title_col:
    st.title("📊 Project monitor")
with toggle_col:
    st.session_state.dark_mode = st.toggle("🌙 Dark", value=st.session_state.dark_mode)

inject_theme(st.session_state.dark_mode)
THEME = DARK if st.session_state.dark_mode else LIGHT

auto = st.checkbox("Auto-refresh every 15s")

tasks, members = load_tables()
project = load_project()
risk_scores, reallocations, assignments, forecast_row = load_ai_outputs()

with st.container(border=True):
    col1, col2, col3, col4, col5 = st.columns(5)
    total = len(tasks)
    done = (tasks["status"] == "Done").sum()
    blocked = (tasks["status"] == "Blocked").sum()
    overdue = (pd.to_datetime(tasks["due_date"]).dt.date < date.today()).sum()
    days_to_deadline = (pd.to_datetime(project["deadline"]).date() - date.today()).days
    col1.metric("Total tasks", total)
    col2.metric("Done", f"{done}/{total}")
    col3.metric("Blocked", blocked)
    col4.metric("Overdue", overdue)
    col5.metric("Project deadline", project["deadline"], delta=f"{days_to_deadline} days left",
                delta_color="off")

if not forecast_row.empty:
    f = forecast_row.iloc[0]
    with st.container(border=True):
        if f["on_track"]:
            st.success(
                f"On track — predicted completion **{f['predicted_completion_date']}**, "
                f"{f['days_ahead_or_behind']} day(s) before the {f['project_deadline']} deadline."
            )
        else:
            st.error(
                f"At risk — predicted completion **{f['predicted_completion_date']}**, "
                f"{abs(f['days_ahead_or_behind'])} day(s) past the {f['project_deadline']} deadline."
            )

if st.button("🔄 Run AI analysis now"):
    with st.spinner("Scoring risk, checking workload, ranking assignments..."):
        ai_engine.main()
    st.success("AI analysis updated below.")
    st.rerun()

with st.container(border=True):
    st.subheader("Status breakdown")
    STATUS_COLORS = {
        "To Do": "#94a3b8", "In Progress": "#3b82f6", "In Review": "#f59e0b",
        "Blocked": "#ef4444", "Done": "#22c55e",
    }
    status_df = tasks["status"].value_counts().reset_index()
    status_df.columns = ["status", "count"]
    status_chart = (
        alt.Chart(status_df)
        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, size=40)
        .encode(
            x=alt.X("status:N", sort=None, title=None),
            y=alt.Y("count:Q", title=None),
            color=alt.Color("status:N",
                             scale=alt.Scale(domain=list(STATUS_COLORS.keys()),
                                              range=list(STATUS_COLORS.values())),
                             legend=None),
            tooltip=["status", "count"],
        )
        .configure_view(strokeWidth=0)
        .configure_axis(grid=False, labelColor=THEME["text"], domainColor=THEME["border"])
        .properties(height=260, background="transparent")
    )
    st.altair_chart(status_chart, use_container_width=True)

with st.container(border=True):
    st.subheader("Workload by team member")
    members["utilization_pct"] = (
        100 * members["current_allocated_hours"] / members["weekly_capacity_hours"]
    ).round(0)

    def workload_color(pct):
        if pct > 100:
            return "#ef4444"
        if pct > 80:
            return "#f59e0b"
        return "#22c55e"

    members["color"] = members["utilization_pct"].apply(workload_color)
    workload_chart = (
        alt.Chart(members)
        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, size=40)
        .encode(
            x=alt.X("name:N", sort=None, title=None),
            y=alt.Y("utilization_pct:Q", title="Utilization %"),
            color=alt.Color("color:N", scale=None, legend=None),
            tooltip=["name", "utilization_pct"],
        )
        .configure_view(strokeWidth=0)
        .configure_axis(grid=False, labelColor=THEME["text"], domainColor=THEME["border"],
                         titleColor=THEME["text"])
        .properties(height=260, background="transparent")
    )
    st.altair_chart(workload_chart, use_container_width=True)

    overloaded = members[members["utilization_pct"] > 90]
    for _, m in overloaded.iterrows():
        st.warning(f"{m['name']} is at {int(m['utilization_pct'])}% capacity — consider reassigning a task.")

    if not reallocations.empty:
        st.markdown("**Reallocation suggestions**")
        member_lookup = members.set_index("id")["name"].to_dict()
        task_lookup = tasks.set_index("id")["title"].to_dict()
        for _, r in reallocations.iterrows():
            task_title = task_lookup.get(r["task_id"], f"#{r['task_id']}")
            st.info(f"Move **{task_title}** — {r['reason']}")

with st.container(border=True):
    st.subheader("Tasks")

    def risk_band(score):
        if pd.isna(score):
            return ""
        if score >= 60:
            return "High"
        if score >= 30:
            return "Medium"
        return "Low"

    display = tasks.merge(risk_scores[["task_id", "score"]], left_on="id", right_on="task_id", how="left")
    display["risk"] = display["score"].apply(risk_band)

    capacity_lookup = members.set_index("id")["weekly_capacity_hours"].to_dict()

    def estimate_resolution(row):
        if row["status"] == "Done":
            return "Completed"
        if row["status"] == "Blocked":
            return "Unknown — blocked"
        remaining = max(row["estimated_hours"] - row["logged_hours"], 0)
        daily_capacity = capacity_lookup.get(row["assignee_id"], 0) / 5
        if daily_capacity <= 0 or remaining <= 0:
            return "Unknown"
        days_needed = math.ceil(remaining / daily_capacity)
        return str(date.today() + timedelta(days=days_needed))

    display["est_resolution"] = display.apply(estimate_resolution, axis=1)

    def highlight_row(row):
        if row["status"] == "Blocked":
            color = "background-color: #fee2e2"
        elif row["status"] == "Done":
            color = "background-color: #dcfce7"
        elif row["risk"] == "High":
            color = "background-color: #ffedd5"
        elif row["risk"] == "Medium":
            color = "background-color: #fef9c3"
        else:
            color = ""
        return [color] * len(row)

    member_lookup = members.set_index("id")["name"].to_dict()
    display["assignee"] = display["assignee_id"].map(member_lookup)
    display = display.rename(columns={"due_date": "deadline"})
    cols = ["id", "title", "assignee", "status", "risk", "deadline", "est_resolution",
            "estimated_hours", "logged_hours", "required_skills", "comment_text"]
    st.caption(
        "**deadline** = this task's own due date. **est_resolution** = projected finish date "
        "based on remaining hours and the assignee's daily capacity (not computable for Blocked "
        "tasks, since that depends on an external blocker, not more hours)."
    )
    st.dataframe(display[cols].style.apply(highlight_row, axis=1), use_container_width=True)

with st.container(border=True):
    st.subheader("Who can take this?")
    active_tasks = tasks[tasks["status"] != "Done"]
    if active_tasks.empty or assignments.empty:
        st.caption("No active tasks or no assignment suggestions yet — run ai_engine.py first.")
    else:
        chosen_task_id = st.selectbox(
            "Select a task to see ranked candidates",
            active_tasks["id"].tolist(),
            format_func=lambda i: f"#{i} {active_tasks.loc[active_tasks.id == i, 'title'].values[0]}",
        )
        member_lookup = members.set_index("id")["name"].to_dict()
        candidates = assignments[assignments["task_id"] == chosen_task_id].sort_values(
            "match_score", ascending=False
        )
        if candidates.empty:
            st.caption("No suggestions for this task yet — run ai_engine.py after adding it.")
        else:
            candidates_display = candidates.copy()
            candidates_display["candidate"] = candidates_display["candidate_member_id"].map(member_lookup)
            st.dataframe(
                candidates_display[["candidate", "match_score", "reason"]].reset_index(drop=True),
                use_container_width=True,
            )

# ---------- Add team member ----------
with st.container(border=True):
    st.subheader("Add team member")
    with st.form("member_form", clear_on_submit=True):
        member_name = st.text_input("Name", key="member_name")
        member_capacity = st.number_input("Weekly capacity hours", min_value=0.0, value=40.0, step=5.0)
        member_skills = st.multiselect("Skills", SKILLS_POOL, key="member_skills")

        member_submitted = st.form_submit_button("Add member")

        if member_submitted:
            if not member_name.strip():
                st.error("Name is required.")
            elif not member_skills:
                st.error("Select at least one skill.")
            else:
                conn = get_conn()
                cur = conn.cursor()
                new_member_id = int(members["id"].max()) + 1 if len(members) else 1
                cur.execute(
                    "INSERT INTO team_members (id, name, weekly_capacity_hours, current_allocated_hours, skills) "
                    "VALUES (?,?,?,?,?)",
                    (new_member_id, member_name.strip(), member_capacity, 0, ",".join(member_skills)),
                )
                conn.commit()
                conn.close()
                st.success(f"Added {member_name.strip()}. They'll appear in Workload and the Assignee dropdown below.")
                st.rerun()

# ---------- Create / update task (Jira-style manual entry) ----------
with st.container(border=True):
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
                cur.execute("""
                    UPDATE team_members
                    SET current_allocated_hours = (
                        SELECT COALESCE(SUM(estimated_hours), 0) FROM tasks
                        WHERE tasks.assignee_id = team_members.id AND tasks.status != 'Done'
                    )
                """)
                conn.commit()
                conn.close()
                st.success("Saved. Run ai_engine.py again to refresh risk/assignment suggestions for this change.")
                st.rerun()

if auto:
    time.sleep(15)
    st.rerun()