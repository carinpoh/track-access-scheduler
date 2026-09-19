"""Track Access Scheduler - Live Web App (deliverable #2).

A works-controller-facing UI: upload the 8 instance CSVs, run the scheduler for
Scenario A / B / C, see feasibility + score, browse the schedule, download the
submission CSVs, and read a plain-English explanation of the plan.

Run locally:   streamlit run app.py
Deploy:        Streamlit Community Cloud (see README).
"""
from __future__ import annotations

import io
import os
import tempfile
import zipfile
from collections import defaultdict

import pandas as pd
import streamlit as st

from trackaccess.loader import Instance
from trackaccess.scenarios import SCENARIOS
from trackaccess.solver import Solver
from trackaccess.writer import (
    write_schedule_access,
    write_schedule_occupancy,
    write_results,
)
from trackaccess.validate import validate

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Track Access Scheduler",
    page_icon="🚄",
    layout="wide",
)

# The 8 instance files the judges upload. Key = friendly name, value = filename
# fragment the loader matches on (case-insensitive).
REQUIRED_FILES = {
    "01_LINES": "LINES",
    "02_STATIONS": "STATIONS",
    "03_SECTORS": "SECTORS",
    "04_LOCATION_SUPPLY": "LOCATION_SUPPLY",
    "05_BUFFER_LOCATION": "BUFFER",
    "06_PARAMETERS": "PARAMETERS",
    "07_PROJECT_DETAILS": "PROJECT_DETAILS",
    "08_ACTIVITY_DETAILS": "ACTIVITY_DETAILS",
}

SCENARIO_BLURB = {
    "A": "**Strict supply, flexible schedule.** Never exceed track capacity, "
         "no ECLO, no extra nights — the only lever is letting dates slip. "
         "Minimises priority-weighted overrun.",
    "B": "**Strict schedule, flexible supply.** Hit every planned date exactly "
         "(zero overrun). Pays with extra access-nights and ECLO. Minimises "
         "`7 × excess nights + 5 × ECLO`.",
    "C": "**Balanced / elastic.** Neither side is absolute — trades a little "
         "capacity strain against a little delay. Allows up to +1 access-night "
         "per location-week. Minimises overrun + excess + ECLO together.",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _save_uploads(uploaded, workdir: str) -> None:
    data_dir = os.path.join(workdir, "01_data")
    os.makedirs(data_dir, exist_ok=True)
    for f in uploaded:
        with open(os.path.join(data_dir, f.name), "wb") as out:
            out.write(f.getbuffer())


def _run_scenario(data_dir: str, scenario: str, out_root: str) -> dict:
    inst = Instance(data_dir)
    pol = SCENARIOS[scenario]
    solver = Solver(inst, pol)
    placements = solver.solve()
    out_dir = os.path.join(out_root, scenario)
    os.makedirs(out_dir, exist_ok=True)
    write_schedule_access(os.path.join(out_dir, "SCHEDULE_ACCESS.csv"), placements)
    write_schedule_occupancy(os.path.join(out_dir, "SCHEDULE_OCCUPANCY.csv"), placements)
    write_results(os.path.join(out_dir, "RESULTS.csv"), inst, placements, scenario)
    report = validate(data_dir, out_dir)
    return {"inst": inst, "placements": placements, "out_dir": out_dir,
            "report": report}


def _zip_dir(out_dir: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in ("SCHEDULE_ACCESS.csv", "SCHEDULE_OCCUPANCY.csv", "RESULTS.csv"):
            z.write(os.path.join(out_dir, fn), fn)
    buf.seek(0)
    return buf.read()


def _score_badge(report: dict) -> None:
    c1, c2, c3 = st.columns(3)
    feasible = report["feasible"]
    c1.metric("Feasible", "✅ Yes" if feasible else "❌ No")
    c2.metric("Hard violations", len(report["hard_violations"]))
    c3.metric("Objective score", report.get("objective_score", "—"))


def _explain(report: dict, inst: Instance) -> str:
    s = report["soft_scores"]
    lines = []
    sc = report["scenario"]
    if report["feasible"]:
        lines.append(f"Scenario **{sc}** is **feasible** — every one of "
                     f"{len(inst.activities)} activities is fully scheduled with "
                     f"no hard-rule breaches.")
    else:
        lines.append(f"Scenario **{sc}** is **NOT feasible** — "
                     f"{len(report['hard_violations'])} hard violation(s) to fix.")
    lines.append(f"- Total access-nights placed: **{s['nights_scheduled'] if 'nights_scheduled' in s else report['detail']['nights_scheduled']}**")
    lines.append(f"- Overrun days (all contracts): **{s['overrun_days_total']}** "
                 f"across **{s['contracts_overrunning']}** contract(s)")
    lines.append(f"- Extra access-nights above supply: **{s['excess_access_nights_total']}**")
    lines.append(f"- ECLO nights used: **{s['eclo_nights_total']}**")
    po = s["priority_overrun"]
    lines.append(f"- Overrun by contract priority — P1: {po['1']}d, "
                 f"P2: {po['2']}d, P3: {po['3']}d "
                 f"(delays are pushed onto the lowest priority first).")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sidebar — upload
# ---------------------------------------------------------------------------
st.sidebar.title("🚄 Track Access Scheduler")
st.sidebar.caption("Decide who gets the track, on which nights — and prove it.")

st.sidebar.header("1. Upload instance files")
st.sidebar.write("Drop the **8 CSV** instance files (the demand book for a "
                 "planning horizon).")
uploaded = st.sidebar.file_uploader(
    "Instance CSVs", type=["csv"], accept_multiple_files=True,
    label_visibility="collapsed",
)

use_sample = st.sidebar.checkbox("Use bundled sample instance (01_data/)",
                                 value=False)

st.sidebar.header("2. Choose scenario(s)")
scenarios = st.sidebar.multiselect(
    "Scenarios to solve", ["A", "B", "C"], default=["A", "B", "C"],
)

run = st.sidebar.button("▶ Run scheduler", type="primary", use_container_width=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
st.title("Railway Track Access Optimisation")
st.write("Upload an instance, run the scheduler, and get a feasible possession "
         "schedule for **Line Alpha & Line Beta** — validated and explained.")

for code in ("A", "B", "C"):
    with st.expander(f"What is Scenario {code}?"):
        st.markdown(SCENARIO_BLURB[code])

if run:
    workdir = tempfile.mkdtemp(prefix="ta_")
    if use_sample and os.path.isdir("01_data"):
        data_dir = "01_data"
    else:
        if not uploaded:
            st.error("Please upload the 8 instance CSVs, or tick "
                     "'Use bundled sample instance'.")
            st.stop()
        _save_uploads(uploaded, workdir)
        data_dir = os.path.join(workdir, "01_data")

    # basic completeness check
    try:
        present = [f.lower() for f in os.listdir(data_dir)]
    except FileNotFoundError:
        st.error("No data found.")
        st.stop()
    missing = [name for name, frag in REQUIRED_FILES.items()
               if not any(frag.lower() in p for p in present)]
    if missing:
        st.warning("Some expected files may be missing (matched by name): "
                   + ", ".join(missing))

    out_root = os.path.join(workdir, "out")
    tabs = st.tabs([f"Scenario {s}" for s in scenarios] or ["Result"])
    for tab, sc in zip(tabs, scenarios):
        with tab:
            with st.spinner(f"Solving Scenario {sc}…"):
                try:
                    res = _run_scenario(data_dir, sc, out_root)
                except Exception as e:  # noqa: BLE001
                    st.exception(e)
                    continue
            report = res["report"]
            _score_badge(report)

            st.markdown("#### What this plan means")
            st.markdown(_explain(report, res["inst"]))

            if report["hard_violations"]:
                st.error("Hard violations:")
                st.dataframe(pd.DataFrame(report["hard_violations"]),
                             use_container_width=True, hide_index=True,
                             key=f"viol_{sc}")

            # --- schedule tables ---
            acc = pd.read_csv(os.path.join(res["out_dir"], "SCHEDULE_ACCESS.csv"))
            occ = pd.read_csv(os.path.join(res["out_dir"], "SCHEDULE_OCCUPANCY.csv"))
            results = pd.read_csv(os.path.join(res["out_dir"], "RESULTS.csv"))

            st.markdown("#### Contract completion")
            st.dataframe(results, use_container_width=True, hide_index=True,
                         key=f"results_{sc}")

            # --- simple timeline: activity x week heat of access-nights ---
            st.markdown("#### Access timeline (activities × weeks)")
            pivot = (acc.groupby(["activity_id", "week"]).size()
                     .reset_index(name="nights"))
            grid = pivot.pivot(index="activity_id", columns="week",
                               values="nights").fillna(0).astype(int)
            st.dataframe(grid, use_container_width=True, key=f"grid_{sc}")

            # --- capacity hotspots ---
            st.markdown("#### Busiest locations (by distinct possessions)")
            hot = (occ.groupby(["location_id", "week"])["co_share_group"]
                   .nunique().reset_index(name="possessions")
                   .sort_values("possessions", ascending=False).head(15))
            st.dataframe(hot, use_container_width=True, hide_index=True,
                         key=f"hot_{sc}")

            # --- downloads ---
            st.markdown("#### Download submission files")
            d1, d2, d3, d4 = st.columns(4)
            d1.download_button("SCHEDULE_ACCESS.csv",
                               acc.to_csv(index=False), "SCHEDULE_ACCESS.csv",
                               "text/csv", use_container_width=True,
                               key=f"dl_access_{sc}")
            d2.download_button("SCHEDULE_OCCUPANCY.csv",
                               occ.to_csv(index=False), "SCHEDULE_OCCUPANCY.csv",
                               "text/csv", use_container_width=True,
                               key=f"dl_occ_{sc}")
            d3.download_button("RESULTS.csv",
                               results.to_csv(index=False), "RESULTS.csv",
                               "text/csv", use_container_width=True,
                               key=f"dl_results_{sc}")
            d4.download_button("⬇ All 3 (zip)", _zip_dir(res["out_dir"]),
                               f"submission_{sc}.zip", "application/zip",
                               use_container_width=True,
                               key=f"dl_zip_{sc}")
else:
    st.info("👈 Upload the 8 instance CSVs (or use the bundled sample), pick "
            "scenario(s), and click **Run scheduler**.")
