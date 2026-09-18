# Track Access Scheduler (PS1)

A decision-support tool that produces night-work possession schedules for a
dual-line rail network (Line Alpha & Line Beta), for three optimisation
scenarios (A / B / C), self-validates the result, and serves it through a live
web app a works controller can use.

## Live web app

Upload the 8 instance CSVs, pick a scenario, and the app runs the scheduler,
shows feasibility + score, visualises the schedule, and lets you download the
submission CSVs.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the URL Streamlit prints (default http://localhost:8501).

### Deploy free on Streamlit Community Cloud

1. Push this repo to GitHub/GitLab.
2. Go to https://share.streamlit.io → **New app**.
3. Pick this repo, branch `main`, main file `app.py`.
4. Click **Deploy**. You get a public URL like
   `https://<name>.streamlit.app` — that's the hosted-web-app deliverable.

## Command line

```bash
python run.py                                   # solve A/B/C -> ./out, then validate
# or the package form:
python -m trackaccess solveall --data 01_data --out out
python -m trackaccess validate --data 01_data --sub out/A
```

## Layout

- `app.py` — Streamlit web app (upload → run → visualise → download).
- `01_data/` — the 8 instance CSVs (network topology + demand).
- `trackaccess/` — solver package (models, loader, network engine, solver,
  scenarios, writer, local validator).
- `run.py` — single-file standalone version of the whole solver.
- `out/A|B|C/` — generated submission CSVs per scenario
  (`SCHEDULE_ACCESS.csv`, `SCHEDULE_OCCUPANCY.csv`, `RESULTS.csv`).
- `requirements.txt`, `.streamlit/config.toml` — app deps + config.

## The three scenarios

| Scenario | Policy | Optimises |
|----------|--------|-----------|
| **A** | Strict supply, flexible schedule. No capacity excess, no ECLO. | Priority-weighted overrun only. |
| **B** | Strict schedule, flexible supply. Zero overrun by construction. | `7 × excess access-nights + 5 × ECLO`. |
| **C** | Balanced / elastic. Up to +1 access-night per location-week. | Overrun + excess + ECLO together. |

## Results (local validator)

| Scenario | Feasible | Objective score |
|----------|----------|-----------------|
| A (strict supply)  | yes | 8.4 |
| B (strict dates)   | yes | 35  |
| C (elastic)        | yes | 35  |

All 54 activities are scheduled at 100% of their workload. The main contention
is the H01<->H02 hub tunnel (capacity 1), where Scenario B/C spend a +1
access-night on the busiest weeks and Scenario A absorbs a small Priority-3 slip.

> Note: `trackaccess/validate.py` is a **local re-implementation** of the rules
> for self-checking. Score against the official reference validator before final
> submission.

## How the solver works (brief)

Greedy, priority-ordered placement: activities are sorted by contract tier, then
activity priority, then earliest legal week. Each access-night is packed into the
earliest week/night that respects every hard rule — footprint capacity, co-share
legal mixes, weekly allocation, workfronts, buffers, `Live` opposite-bound
mirroring, and the `Live` hub cross-line coupling. The scenario policy decides
whether capacity overflow, ECLO, or date slip is the lever used under congestion.
