import sqlite3
import time
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

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


title_col, toggle_col = st.columns([6, 1])
with title_col:
    st.title("📊 Project monitor")
with toggle_col:
    st.session_state.dark_mode = st.toggle("🌙 Dark", value=st.session_state.dark_mode)

inject_theme(st.session_state.dark_mode)
THEME = DARK if st.session_state.dark_mode else LIGHT

auto = st.checkbox("Auto-refresh every 15s")

tasks, members = load_tables()

with st.container(border=True):
    col1, col2, col3, col4 = st.columns(4)
    total = len(tasks)
    done = (tasks["status"] == "Done").sum()
    blocked = (tasks["status"] == "Blocked").sum()
    overdue = (pd.to_datetime(tasks["due_date"]).dt.date < date.today()).sum()
    col1.metric("Total tasks", total)
    col2.metric("Done", f"{done}/{total}")
    col3.metric("Blocked", blocked)
    col4.metric("Overdue", overdue)

forecast_row = pd.read_sql("SELECT * FROM project_forecast LIMIT 1", get_conn())
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

with st.container(border=True):
    st.subheader("Tasks")

    def highlight_status(row):
        color = ""
        if row["status"] == "Blocked":
            color = "background-color: #fee2e2"
        elif row["status"] == "Done":
            color = "background-color: #dcfce7"
        return [color] * len(row)

    member_lookup = members.set_index("id")["name"].to_dict()
    display = tasks.copy()
    display["assignee"] = display["assignee_id"].map(member_lookup)
    cols = ["id", "title", "assignee", "status", "due_date", "estimated_hours",
            "logged_hours", "required_skills", "comment_text"]
    st.dataframe(display[cols].style.apply(highlight_status, axis=1), use_container_width=True)

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
                st.success("Saved.")
                st.rerun()

if auto:
    time.sleep(15)
    st.rerun()