"""
AI engine for the project monitoring tool.

Computes from the current state of project_monitor.db and writes results back
into the derived tables the schema has ready for them:

1. Risk scores per task          -> risk_scores
2. Reallocation suggestions      -> reallocation_suggestions
3. Skill-based assignment ranks  -> assignment_suggestions
4. Schedule forecast (on track / at risk vs. the project deadline) -> project_forecast

Run this any time after editing tasks in the dashboard to refresh the AI
outputs, then re-open the dashboard or re-run export_to_excel.py to see them.
"""

import math
import sqlite3
from datetime import date, datetime, timedelta

import pandas as pd

DB_PATH = "project_monitor.db"

RISK_KEYWORDS = ["blocked", "waiting", "delay", "slip", "stuck"]


def load_data(conn):
    tasks = pd.read_sql("SELECT * FROM tasks", conn)
    members = pd.read_sql("SELECT * FROM team_members", conn)
    return tasks, members


def load_project(conn):
    return pd.read_sql("SELECT * FROM projects", conn).iloc[0]


def create_forecast_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_forecast (
            project_id INTEGER PRIMARY KEY,
            remaining_hours REAL,
            predicted_completion_date TEXT,
            project_deadline TEXT,
            days_ahead_or_behind INTEGER,
            on_track INTEGER,
            computed_at TEXT
        )
    """)
    conn.commit()


def compute_risk_scores(tasks: pd.DataFrame, today: date):
    tasks_by_id = tasks.set_index("id").to_dict("index")
    rows = []

    for _, task in tasks.iterrows():
        if task["status"] == "Done":
            continue

        score = 0
        factors = []

        if task["status"] == "Blocked":
            score += 40
            factors.append("blocked_status")

        due = datetime.strptime(task["due_date"], "%Y-%m-%d").date()
        if due < today:
            score += 25
            factors.append("overdue")

        if task["estimated_hours"] > 0 and task["logged_hours"] > task["estimated_hours"]:
            score += 20
            factors.append("over_estimate")

        dep_ids = [int(x) for x in str(task["dependency_ids"]).split(",") if x.strip()]
        if any(tasks_by_id.get(d, {}).get("status") not in ("Done", None) for d in dep_ids):
            score += 15
            factors.append("unresolved_dependency")

        comment = str(task["comment_text"] or "").lower()
        if any(word in comment for word in RISK_KEYWORDS):
            score += 10
            factors.append("risk_language_in_comment")

        score = min(score, 100)
        rows.append({
            "task_id": int(task["id"]),
            "score": score,
            "factors": ",".join(factors) if factors else "none",
            "computed_at": datetime.now().isoformat(timespec="seconds"),
        })

    return pd.DataFrame(rows)


def predict_completion(tasks: pd.DataFrame, members: pd.DataFrame, today: date):
    remaining = (tasks.loc[tasks["status"] != "Done", "estimated_hours"]
                 - tasks.loc[tasks["status"] != "Done", "logged_hours"]).clip(lower=0).sum()
    daily_capacity = (members["weekly_capacity_hours"] / 5).sum()
    if daily_capacity <= 0:
        return remaining, None
    days_needed = math.ceil(remaining / daily_capacity)
    return remaining, today + timedelta(days=days_needed)


def compute_forecast_row(project, remaining_hours, completion_date):
    deadline = datetime.strptime(project["deadline"], "%Y-%m-%d").date()
    days_diff = (deadline - completion_date).days
    return {
        "project_id": int(project["id"]),
        "remaining_hours": round(remaining_hours, 1),
        "predicted_completion_date": str(completion_date),
        "project_deadline": str(deadline),
        "days_ahead_or_behind": days_diff,
        "on_track": int(completion_date <= deadline),
        "computed_at": datetime.now().isoformat(timespec="seconds"),
    }


def compute_reallocations(tasks: pd.DataFrame, members: pd.DataFrame):
    members = members.copy()
    members["utilization_pct"] = 100 * members["current_allocated_hours"] / members["weekly_capacity_hours"]
    running_allocated = dict(zip(members["id"], members["current_allocated_hours"]))

    overloaded = members[members["utilization_pct"] > 100].sort_values("utilization_pct", ascending=False)
    underloaded = members[members["utilization_pct"] < 70].sort_values("utilization_pct")

    suggestions = []
    not_done = tasks[tasks["status"] != "Done"]

    for _, over in overloaded.iterrows():
        movable = not_done[
            (not_done["assignee_id"] == over["id"]) & (not_done["status"] != "Blocked")
        ].sort_values("estimated_hours")

        moved = 0
        for _, task in movable.iterrows():
            if moved >= 2:
                break
            req_skills = set(str(task["required_skills"]).split(","))

            best_candidate = None
            best_overlap = -1
            for _, under in underloaded.iterrows():
                if under["id"] == over["id"]:
                    continue
                member_skills = set(str(under["skills"]).split(","))
                overlap = len(req_skills & member_skills)
                projected = running_allocated[under["id"]] + task["estimated_hours"]
                if projected <= under["weekly_capacity_hours"] * 0.9 and overlap > best_overlap:
                    best_overlap = overlap
                    best_candidate = under

            if best_candidate is not None:
                reason = (f"{over['name']} is over capacity; {best_candidate['name']} has room "
                          f"and matches {best_overlap}/{len(req_skills)} required skills")
                suggestions.append({
                    "from_member_id": int(over["id"]),
                    "to_member_id": int(best_candidate["id"]),
                    "task_id": int(task["id"]),
                    "reason": reason,
                })
                running_allocated[best_candidate["id"]] += task["estimated_hours"]
                running_allocated[over["id"]] -= task["estimated_hours"]
                moved += 1

    return pd.DataFrame(suggestions), members


def compute_assignment_suggestions(tasks: pd.DataFrame, members: pd.DataFrame):
    members = members.copy()
    members["utilization_pct"] = 100 * members["current_allocated_hours"] / members["weekly_capacity_hours"]

    rows = []
    not_done = tasks[tasks["status"] != "Done"]

    for _, task in not_done.iterrows():
        req_skills = set(s for s in str(task["required_skills"]).split(",") if s)
        candidates = []
        for _, member in members.iterrows():
            member_skills = set(s for s in str(member["skills"]).split(",") if s)
            overlap = len(req_skills & member_skills)
            skill_score = (overlap / len(req_skills) * 70) if req_skills else 35
            capacity_score = max(0, 100 - member["utilization_pct"]) / 100 * 30
            match_score = round(skill_score + capacity_score, 1)
            reason = (f"Matches {overlap}/{len(req_skills)} required skills; "
                      f"{max(0, 100 - member['utilization_pct']):.0f}% capacity free")
            candidates.append({
                "task_id": int(task["id"]),
                "candidate_member_id": int(member["id"]),
                "match_score": match_score,
                "reason": reason,
            })
        top3 = sorted(candidates, key=lambda c: c["match_score"], reverse=True)[:3]
        rows.extend(top3)

    return pd.DataFrame(rows)


def write_results(conn, risk_df, realloc_df, assign_df, forecast_row):
    cur = conn.cursor()
    cur.execute("DELETE FROM risk_scores")
    cur.execute("DELETE FROM reallocation_suggestions")
    cur.execute("DELETE FROM assignment_suggestions")
    cur.execute("DELETE FROM project_forecast WHERE project_id = ?", (forecast_row["project_id"],))
    conn.commit()

    if not risk_df.empty:
        risk_df.to_sql("risk_scores", conn, if_exists="append", index=False)
    if not realloc_df.empty:
        realloc_df.to_sql("reallocation_suggestions", conn, if_exists="append", index=False)
    if not assign_df.empty:
        assign_df.to_sql("assignment_suggestions", conn, if_exists="append", index=False)

    conn.execute(
        "INSERT INTO project_forecast VALUES (:project_id, :remaining_hours, :predicted_completion_date, "
        ":project_deadline, :days_ahead_or_behind, :on_track, :computed_at)",
        forecast_row,
    )
    conn.commit()


def main():
    conn = sqlite3.connect(DB_PATH)
    tasks, members = load_data(conn)
    project = load_project(conn)
    create_forecast_table(conn)
    today = date.today()

    risk_df = compute_risk_scores(tasks, today)
    remaining_hours, completion_date = predict_completion(tasks, members, today)
    forecast_row = compute_forecast_row(project, remaining_hours, completion_date)
    realloc_df, members_with_util = compute_reallocations(tasks, members)
    assign_df = compute_assignment_suggestions(tasks, members)

    write_results(conn, risk_df, realloc_df, assign_df, forecast_row)
    conn.close()

    print("=" * 60)
    print("RISK SCORES (highest first)")
    print("=" * 60)
    if not risk_df.empty:
        merged = risk_df.merge(tasks[["id", "title"]], left_on="task_id", right_on="id")
        for _, r in merged.sort_values("score", ascending=False).head(5).iterrows():
            print(f"  [{r['score']:>3}] #{r['task_id']:<3} {r['title']:<32} ({r['factors']})")
    else:
        print("  No active tasks to score.")

    print()
    print("=" * 60)
    print("SCHEDULE FORECAST")
    print("=" * 60)
    status_word = "ON TRACK" if forecast_row["on_track"] else "AT RISK OF SLIPPING"
    print(f"  Remaining work: {forecast_row['remaining_hours']} hours")
    print(f"  Predicted completion: {forecast_row['predicted_completion_date']}")
    print(f"  Project deadline:     {forecast_row['project_deadline']}")
    print(f"  Status: {status_word} ({forecast_row['days_ahead_or_behind']:+d} days vs. deadline)")

    print()
    print("=" * 60)
    print("WORKLOAD")
    print("=" * 60)
    for _, m in members_with_util.iterrows():
        flag = "  <-- overloaded" if m["utilization_pct"] > 100 else ""
        print(f"  {m['name']:<15} {m['utilization_pct']:>5.0f}%{flag}")

    print()
    print("=" * 60)
    print("REALLOCATION SUGGESTIONS")
    print("=" * 60)
    if not realloc_df.empty:
        for _, r in realloc_df.iterrows():
            print(f"  Task #{r['task_id']}: {r['reason']}")
    else:
        print("  None needed right now.")

    print()
    print("=" * 60)
    print("SAMPLE ASSIGNMENT SUGGESTIONS (first task)")
    print("=" * 60)
    if not assign_df.empty:
        first_task_id = assign_df["task_id"].iloc[0]
        sample = assign_df[assign_df["task_id"] == first_task_id]
        member_lookup = members.set_index("id")["name"].to_dict()
        title = tasks.loc[tasks["id"] == first_task_id, "title"].values[0]
        print(f"  Task #{first_task_id} ({title}):")
        for _, s in sample.iterrows():
            print(f"    {member_lookup[s['candidate_member_id']]:<15} score={s['match_score']:<5} {s['reason']}")

    print()
    print("Done. risk_scores, reallocation_suggestions, assignment_suggestions, and project_forecast updated.")


if __name__ == "__main__":
    main()