# AI-Powered Project Monitoring Tool

A lean project monitoring web app combining a live tracking dashboard with two AI layers:
task-risk prediction and workload/skill-based assignment recommendations. Built as a
compressed 2-day sprint.

## Why this exists

Most project management tools (Jira, Asana, Wrike) either:
- Only track status manually, with no predictive insight, or
- Gate predictive AI features and workload balancing behind expensive enterprise tiers

This tool ships real-time dashboards, predictive risk scoring, and skill-based task
assignment by default, aimed at small teams and students who can't justify enterprise
PPM pricing.

## Features

- **Real-time dashboard** — status breakdown, workload utilization, and a color-coded task table
- **Jira-style manual entry form** — create or update tasks live and watch the dashboard react
- **AI-driven task analytics** *(in progress)* — a risk score per task predicting likelihood of delay
- **AI-driven workload management** *(in progress)* — utilization tracking with reallocation suggestions
- **Skill-based task assignment** *(in progress)* — ranks team members by skill fit and current load

## Tech stack

- Python
- SQLite (single source of truth, no separate API layer)
- Streamlit (dashboard + manual entry UI)
- pandas
- scikit-learn (risk-prediction model)

## Project structure

```
.
├── generate_data.py     # Creates the schema and seeds a synthetic demo dataset
├── dashboard.py          # Streamlit dashboard + manual entry form
├── ai_engine.py           # Risk scoring, workload/reallocation, skill-matching (WIP)
├── requirements.txt
├── report/
│   └── document.tex       # LaTeX presentation (Beamer)
└── README.md
```

## Getting started

```bash
pip install -r requirements.txt
python generate_data.py     # creates project_monitor.db with demo data
streamlit run dashboard.py  # launches the dashboard at http://localhost:8501
```

## Current status

- [x] Database schema and synthetic dataset (with team skills and task requirements)
- [x] Live dashboard: status breakdown, workload chart, task table
- [x] Manual entry form (create/update tasks in real time)
- [ ] Risk-scoring model
- [ ] Workload reallocation engine
- [ ] Skill-based assignment ranking

## Future scope

- Integrate with real Jira/Asana/GitHub data instead of synthetic input
- Add explainability to the risk score
- Richer resourcing: skill taxonomies, leave calendars, multi-project contention
- A conversational layer on top ("what's blocking Project X?")

## Author

Rushikesh
