"""Track Access Scheduler - Live Web App (deliverable #2).

A works-controller-facing UI: upload the 8 instance CSVs, run the scheduler for
Scenario A / B / C, compare their trade-offs, visualise possessions on a Gantt
chart and a rail topology map, read plain-English explanations of why work was
delayed, and download the submission CSVs.

Run locally:   streamlit run app.py
Deploy:        Streamlit Community Cloud (see README).
"""
from __future__ import annotations

import io
import os
import tempfile
import zipfile

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
import viz

st.set_page_config(page_title="Track Access Scheduler", page_icon="🚄",
                   layout="wide")

REQUIRED_FILES = {
    "01_LINES": "LINES", "02_STATIONS": "STATIONS", "03_SECTORS": "SECTORS",
    "04_LOCATION_SUPPLY": "LOCATION_SUPPLY", "05_BUFFER_LOCATION": "BUFFER",
    "06_PARAMETERS": "PARAMETERS", "07_PROJECT_DETAILS": "PROJECT_DETAILS",
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
def _save_uploads(uploaded, workdir: str) -> str:
    data_dir = os.path.join(workdir, "01_data")
    os.makedirs(data_dir, exist_ok=True)
    for f in uploaded:
        with open(os.path.join(data_dir, f.name), "wb") as out:
            out.write(f.getbuffer())
    return data_dir


def _solve_all(data_dir: str, out_root: str) -> dict:
    """Solve A/B/C once. Returns {scenario: {inst, placements, out_dir,
    report, acc, occ, results}}."""
    results = {}
    for sc in ("A", "B", "C"):
        inst = Instance(data_dir)
        placements = Solver(inst, SCENARIOS[sc]).solve()
        out_dir = os.path.join(out_root, sc)
        os.makedirs(out_dir, exist_ok=True)
        write_schedule_access(os.path.join(out_dir, "SCHEDULE_ACCESS.csv"), placements)
        write_schedule_occupancy(os.path.join(out_dir, "SCHEDULE_OCCUPANCY.csv"), placements)
        write_results(os.path.join(out_dir, "RESULTS.csv"), inst, placements, sc)
        report = validate(data_dir, out_dir)
        results[sc] = dict(
            inst=inst, placements=placements, out_dir=out_dir, report=report,
            acc=pd.read_csv(os.path.join(out_dir, "SCHEDULE_ACCESS.csv")),
            occ=pd.read_csv(os.path.join(out_dir, "SCHEDULE_OCCUPANCY.csv")),
            results=pd.read_csv(os.path.join(out_dir, "RESULTS.csv")),
        )
    return results


def _zip_dir(out_dir: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in ("SCHEDULE_ACCESS.csv", "SCHEDULE_OCCUPANCY.csv", "RESULTS.csv"):
            z.write(os.path.join(out_dir, fn), fn)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("🚄 Track Access Scheduler")
st.sidebar.caption("Decide who gets the track, on which nights — and prove it.")
st.sidebar.header("1. Upload instance files")
st.sidebar.write("Drop the **8 CSV** instance files.")
uploaded = st.sidebar.file_uploader("Instance CSVs", type=["csv"],
                                    accept_multiple_files=True,
                                    label_visibility="collapsed")
use_sample = st.sidebar.checkbox("Use bundled sample instance (01_data/)")
run = st.sidebar.button("▶ Run scheduler", type="primary",
                        use_container_width=True)

st.title("Railway Track Access Optimisation")
st.write("Upload an instance, run the scheduler, and get a feasible, explained "
         "possession schedule for **Line Alpha & Line Beta**.")

# ---------------------------------------------------------------------------
if run:
    workdir = tempfile.mkdtemp(prefix="ta_")
    if use_sample and os.path.isdir("01_data"):
        data_dir = "01_data"
    elif uploaded:
        data_dir = _save_uploads(uploaded, workdir)
    else:
        st.error("Upload the 8 instance CSVs, or tick 'Use bundled sample'.")
        st.stop()

    present = [f.lower() for f in os.listdir(data_dir)]
    missing = [n for n, frag in REQUIRED_FILES.items()
               if not any(frag.lower() in p for p in present)]
    if missing:
        st.warning("Possibly missing files: " + ", ".join(missing))

    try:
        with st.spinner("Solving Scenarios A, B and C…"):
            R = _solve_all(data_dir, os.path.join(workdir, "out"))
    except Exception as e:  # noqa: BLE001
        st.exception(e)
        st.stop()
    st.session_state["R"] = R

R = st.session_state.get("R")
if not R:
    with st.expander("What do the three scenarios mean?", expanded=True):
        for code in ("A", "B", "C"):
            st.markdown(f"**Scenario {code}** — {SCENARIO_BLURB[code]}")
    st.info("👈 Upload the 8 instance CSVs (or use the bundled sample), then "
            "click **Run scheduler**.")
    st.stop()

# ---------------------------------------------------------------------------
# Results UI
# ---------------------------------------------------------------------------
reports = {sc: R[sc]["report"] for sc in R}
tab_cmp, tab_a, tab_b, tab_c = st.tabs(
    ["📊 Compare A/B/C", "Scenario A", "Scenario B", "Scenario C"])

# ---- Comparison dashboard ----
with tab_cmp:
    st.subheader("Scenario comparison — penalty trade-offs (lower = better)")
    cols = st.columns(3)
    for col, sc in zip(cols, ("A", "B", "C")):
        rep = reports[sc]
        s = rep["soft_scores"]
        with col:
            st.markdown(f"### Scenario {sc}")
            st.metric("Objective score", rep.get("objective_score", "—"))
            st.caption(f"{'✅ feasible' if rep['feasible'] else '❌ infeasible'}"
                       f" · {len(rep['hard_violations'])} hard violations")
            st.write(f"- Overrun days: **{s['overrun_days_total']}**")
            st.write(f"- Excess access-nights: **{s['excess_access_nights_total']}**")
            st.write(f"- ECLO nights: **{s['eclo_nights_total']}**")
    st.plotly_chart(viz.comparison_figure(reports), use_container_width=True)
    st.dataframe(viz.comparison_table(reports), use_container_width=True,
                 hide_index=True)
    st.caption("Scenario A pays only in delay; B pays only in extra "
               "nights/ECLO; C balances both. Pick the policy that matches "
               "your operational constraints.")

# ---- Per-scenario tabs ----
for tab, sc in zip((tab_a, tab_b, tab_c), ("A", "B", "C")):
    with tab:
        d = R[sc]
        rep = d["report"]
        inst = d["inst"]
        st.markdown(f"#### Scenario {sc} — {SCENARIO_BLURB[sc]}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Feasible", "✅ Yes" if rep["feasible"] else "❌ No")
        c2.metric("Hard violations", len(rep["hard_violations"]))
        c3.metric("Objective score", rep.get("objective_score", "—"))

        if rep["hard_violations"]:
            st.error("Hard violations")
            st.dataframe(pd.DataFrame(rep["hard_violations"]),
                         use_container_width=True, hide_index=True,
                         key=f"viol_{sc}")

        # --- Gantt ---
        st.markdown("##### 🗓️ Possession Gantt (grouped by line)")
        st.caption("Each bar is an activity's possession run. Hover for "
                   "contract, nature, bound, and co-share group.")
        st.plotly_chart(viz.gantt_figure(inst, d["placements"]),
                        use_container_width=True, key=f"gantt_{sc}")

        # --- Topology map ---
        st.markdown("##### 🗺️ Rail topology map")
        weeks = sorted(d["acc"]["week"].unique())
        wk = st.select_slider("Week to view", options=weeks,
                              value=weeks[0], key=f"wk_{sc}")
        st.plotly_chart(viz.topology_figure(inst, d["placements"], wk),
                        use_container_width=True, key=f"topo_{sc}")

        # --- Explainability ---
        st.markdown("##### 🔍 Explainability & bottlenecks")
        eff = viz.cosharing_efficiency(d["occ"])
        e1, e2, e3 = st.columns(3)
        e1.metric("Possessions", eff["possessions_total"])
        e2.metric("Co-shared", eff["possessions_shared"])
        e3.metric("Co-share rate", f"{eff['share_rate_pct']}%")
        st.write("**Why work was delayed (or not):**")
        for msg in viz.priority_reasoning(inst, d["results"]):
            st.markdown(f"- {msg}")
        st.write("**Capacity hotspots** (busiest location-weeks):")
        st.dataframe(viz.hotspots_table(inst, d["occ"]),
                     use_container_width=True, hide_index=True,
                     key=f"hot_{sc}")

        # --- Downloads ---
        st.markdown("##### ⬇️ Download submission files")
        g1, g2, g3, g4 = st.columns(4)
        g1.download_button("SCHEDULE_ACCESS.csv", d["acc"].to_csv(index=False),
                           "SCHEDULE_ACCESS.csv", "text/csv",
                           use_container_width=True, key=f"dl_a_{sc}")
        g2.download_button("SCHEDULE_OCCUPANCY.csv", d["occ"].to_csv(index=False),
                           "SCHEDULE_OCCUPANCY.csv", "text/csv",
                           use_container_width=True, key=f"dl_o_{sc}")
        g3.download_button("RESULTS.csv", d["results"].to_csv(index=False),
                           "RESULTS.csv", "text/csv",
                           use_container_width=True, key=f"dl_r_{sc}")
        g4.download_button("⬇ All 3 (zip)", _zip_dir(d["out_dir"]),
                           f"submission_{sc}.zip", "application/zip",
                           use_container_width=True, key=f"dl_z_{sc}")
