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

inject_th