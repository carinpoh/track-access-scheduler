"""Local re-implementation of the reference validator's checks.

Not the official judge, but mirrors the hard rules and soft-score formulae in
the README so we can self-verify feasibility and estimate scores before
submission.
"""
from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from datetime import date, timedelta

from .loader import Instance
from .network import Network
from .scenarios import SCENARIOS


def _read(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def validate(data_dir: str, sub_dir: str) -> dict:
    inst = Instance(data_dir)
    net = Network(inst)

    access = _read(os.path.join(sub_dir, "SCHEDULE_ACCESS.csv"))
    occ = _read(os.path.join(sub_dir, "SCHEDULE_OCCUPANCY.csv"))
    results = _read(os.path.join(sub_dir, "RESULTS.csv"))

    scenario = results[0]["scenario"].strip() if results else "A"
    pol = SCENARIOS[scenario]
    hard = []

    # index access rows
    acc_by_act = defaultdict(list)
    for r in access:
        acc_by_act[r["activity_id"]].append(r)

    # --- rule 1: workload conservation (100% scheduled) ---
    for aid, a in inst.activities.items():
        rows = acc_by_act.get(aid, [])
        yield_sum = sum(1.5 if int(r["eclo"]) else 1.0 for r in rows)
        if not rows:
            hard.append({"rule": "workload", "severity": "hard",
                         "detail": f"{aid}: not scheduled"})
        elif yield_sum + 1e-9 < a.total_accesses:
            hard.append({"rule": "workload", "severity": "hard",
                         "detail": f"{aid}: yield {yield_sum} < {a.total_accesses}"})

    # --- rule 2: planned start ---
    for r in access:
        a = inst.activities.get(r["activity_id"])
        if a is None:
            continue
        if int(r["week"]) < inst.week_of(a.planned_start_date):
            hard.append({"rule": "planned_start", "severity": "hard",
                         "detail": f"{r['activity_id']} wk{r['week']} before planned"})

    # --- rule: eclo forbidden in A ---
    if not pol.allow_eclo:
        for r in access:
            if int(r["eclo"]):
                hard.append({"rule": "eclo", "severity": "hard",
                             "detail": f"{r['activity_id']} uses eclo in {scenario}"})

    # --- capacity per location-week ---
    # count distinct co_share_group per (location, week)
    slots = defaultdict(set)
    for r in occ:
        slots[(r["location_id"], int(r["week"]))].add(r["co_share_group"])
    excess_total = 0
    for (loc, wk), groups in slots.items():
        cap = inst.locations[loc].supply_capacity if loc in inst.locations else 4
        used = len(groups)
        excess = max(0, used - cap)
        excess_total += excess
        if excess > 0 and not pol.capacity_unlimited:
            if excess > pol.capacity_slack:
                hard.append({"rule": "capacity", "severity": "hard",
                             "detail": f"{loc} wk{wk}: {used}/{cap} (+{excess})"})

    # --- rule 6/7: weekly access + workfront ---
    week_nights = defaultdict(set)          # (contract,atype,week)->access_nights
    wf = defaultdict(set)                    # (contract,atype,week,night)->activities
    for r in access:
        a = inst.activities.get(r["activity_id"])
        if not a:
            continue
        c = inst.contracts[a.contract_number]
        key = (a.contract_number, c.access_type, int(r["week"]))
        week_nights[key].add(int(r["access_night"]))
        wf[(a.contract_number, c.access_type, int(r["week"]), int(r["access_night"]))].add(r["activity_id"])
    for (cn, at, wk), nights in week_nights.items():
        c = inst.contracts[cn]
        if len(nights) > c.max_access_per_week:
            hard.append({"rule": "weekly_allocation", "severity": "hard",
                         "detail": f"{cn}/{at} wk{wk}: {len(nights)}>{c.max_access_per_week}"})
    for (cn, at, wk, night), acts in wf.items():
        c = inst.contracts[cn]
        if len(acts) > c.number_of_workfronts:
            hard.append({"rule": "workfront", "severity": "hard",
                         "detail": f"{cn}/{at} wk{wk} n{night}: {len(acts)}>{c.number_of_workfronts}"})

    # --- planned-date hard fail in B ---
    if pol.hard_planned_date:
        for r in results:
            if int(r["overrun_days"]) > 0:
                hard.append({"rule": "planned_date", "severity": "hard",
                             "detail": f"{r['contract_number']} overrun {r['overrun_days']}d"})

    # --- soft scores ---
    overrun_by_tier = defaultdict(int)
    weighted = 0.0
    overrun_total = 0
    contracts_over = 0
    for r in results:
        c = inst.contracts[r["contract_number"]]
        od = int(r["overrun_days"])
        overrun_total += od
        if od > 0:
            contracts_over += 1
        overrun_by_tier[c.contract_priority] += od
    # weighted needs per-activity priority; approximate at contract level using
    # each contract's activities' overrun share == contract overrun (activities
    # inherit contract completion). Use max activity nudge present.
    for r in results:
        c = inst.contracts[r["contract_number"]]
        od = int(r["overrun_days"])
        if od <= 0:
            continue
        band = pol.band[c.contract_priority]
        acts = [a for a in inst.activities.values() if a.contract_number == r["contract_number"]]
        nudge = max((pol.nudge[a.activity_priority] for a in acts), default=0.0)
        weighted += band * (1 + nudge) * od

    eclo_nights = sum(1 for r in access if int(r["eclo"]))
    nights_scheduled = len(access)

    soft = {
        "scenario": scenario,
        "overrun_days_total": overrun_total,
        "contracts_overrunning": contracts_over,
        "earliness_days_total": 0,
        "excess_access_nights_total": excess_total,
        "eclo_nights_total": eclo_nights,
        "priority_overrun": {str(k): overrun_by_tier.get(k, 0) for k in (1, 2, 3)},
        "priority_weighted_score": round(weighted, 2),
    }

    feasible = len(hard) == 0
    report = {
        "scenario": scenario,
        "feasible": feasible,
        "hard_violations": hard,
        "soft_scores": soft,
        "detail": {
            "capacity_hotspots": [],
            "nights_scheduled": nights_scheduled,
            "eclo_nights": eclo_nights,
        },
    }
    if feasible:
        if scenario == "A":
            report["objective_score"] = round(weighted, 2)
        elif scenario == "B":
            report["objective_score"] = round(7 * excess_total + 5 * eclo_nights, 2)
        else:
            report["objective_score"] = round(weighted + 7 * excess_total + 5 * eclo_nights, 2)
        report["formula_version"] = "ps1-local-1"
    return report


if __name__ == "__main__":
    import sys
    print(json.dumps(validate(sys.argv[1], sys.argv[2]), indent=2))
