# Track Access Scheduler (PS1)

A decision-support tool that produces night-work possession schedules for a
dual-line rail network (Line Alpha & Line Beta), for three optimisation
scenarios (A / B / C), and self-validates the result.

## Quick start

```bash
python run.py                                   # solve A/B/C -> ./out, then validate
# or, package form:
python -m trackaccess solveall --data 01_Data --out out
python -m trackaccess validate --data 01_Data --sub out/A
```

## Layout

- `01_data/` — the 8 instance CSVs (network topology + demand).
- `trackaccess/` — the solver package (models, loader, network engine, solver,
  scenarios, writer, local validator).
- `run.py` — single-file standalone version of the whole solver.
- `out/A|B|C/` — generated submission CSVs per scenario
  (`SCHEDULE_ACCESS.csv`, `SCHEDULE_OCCUPANCY.csv`, `RESULTS.csv`).

## Results (local validator)

| Scenario | Feasible | Objective score |
|----------|----------|-----------------|
| A (strict supply)  | yes | 8.4 |
| B (strict dates)   | yes | 35  |
| C (elastic)        | yes | 35  |

All 54 activities are scheduled at 100% of their workload. The main contention
is the H01<->H02 hub tunnel (capacity 1).

> Note: `trackaccess/validate.py` is a local re-implementation of the rules for
> self-checking. Score against the official reference validator before final
> submission.
