import sqlite3
import pandas as pd

DB_PATH = "project_monitor.db"
EXCEL_PATH = "project_monitor.xlsx"


def export():
    conn = sqlite3.connect(DB_PATH)

    tables = {
        "Projects": "SELECT * FROM projects",
        "Team Members": "SELECT * FROM team_members",
        "Tasks": "SELECT * FROM tasks",
        "Risk Scores": "SELECT * FROM risk_scores",
        "Reallocation Suggestions": "SELECT * FROM reallocation_suggestions",
        "Assignment Suggestions": "SELECT * FROM assignment_suggestions",
    }

    with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
        for sheet_name, query in tables.items():
            df = pd.read_sql(query, conn)
            df.to_excel(writer, sheet_name=sheet_name, index=False)

            # Auto-fit column widths so it's readable without manual resizing
            worksheet = writer.sheets[sheet_name]
            for i, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max() if len(df) else 0, len(col)) + 2
                worksheet.column_dimensions[chr(65 + i)].width = min(max_len, 40)

    conn.close()
    print(f"Exported to {EXCEL_PATH}")


if __name__ == "__main__":
    export()