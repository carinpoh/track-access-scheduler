"""Emit the three submission CSVs for a scenario from solver placements."""
from __future__ import annotations

import csv
import os
from datetime import timedelta

from .loader import Instance
from .solver import Placement


def write_schedule_access(path: str, placements: list[Placement]) -> None:
    rows = sorted(placements, key=lambda p: (p.activity_id, p.access_seq))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["activity_id", "access_seq", "week", "eclo", "access_night"])
        for p in rows:
            w.writerow([p.activity_id, p.access_seq, p.week, p.eclo, p.access_night])


def write_schedule_occupancy(path: str, placements: list[Placement]) -> None:
    """One row per (activity, week, location) with its co_share_group label."""
    seen = set()
    rows = []
    for p in placements:
        for loc in p.all_locations:
            key = (p.activity_id, p.week, loc)
            if key in seen:
                continue
            seen.add(key)
            rows.append((p.activity_id, p.week, loc, p.co_share_group))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["activity_id", "week", "location_id", "co_share_group"])
        for r in rows:
            w.writerow(r)


def write_results(path: str, inst: Instance, placements: list[Placement],
                  scenario: str) -> None:
    """Contract completion summary. simulated_completion_date = last access week's
    date; overrun_days vs planned_completion_date (>=0)."""
    # last week per contract
    last_week: dict[str, int] = {}
    for p in placements:
        c = inst.activities[p.activity_id].contract_number
        last_week[c] = max(last_week.get(c, 0), p.week)

    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "contract_number",
                    "simulated_completion_date", "overrun_days"])
        for cnum, contract in inst.contracts.items():
            wk = last_week.get(cnum, 1)
            # completion date = end (Sunday) of the last access week
            sim_date = inst.date_of_week(wk) + timedelta(days=6)
            planned = contract.planned_completion_date
            overrun = max(0, (sim_date - planned).days) if planned else 0
            w.writerow([scenario, cnum, sim_date.isoformat(), overrun])


def write_all(out_dir: str, inst: Instance, placements: list[Placement],
              scenario: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    write_schedule_access(os.path.join(out_dir, "SCHEDULE_ACCESS.csv"), placements)
    write_schedule_occupancy(os.path.join(out_dir, "SCHEDULE_OCCUPANCY.csv"), placements)
    write_results(os.path.join(out_dir, "RESULTS.csv"), inst, placements, scenario)
