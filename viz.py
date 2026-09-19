"""Visualisation & explainability helpers for the Track Access web app.

Pure functions that turn solver output (placements + instance + validator
report) into Plotly figures and summary tables. Kept separate from app.py so
they can be unit-tested without the Streamlit runtime.
"""
from __future__ import annotations

from collections import defaultdict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from trackaccess.loader import Instance
from trackaccess.network import parse_sector_location

LINE_NAME = {"ALP": "Line Alpha", "BET": "Line Beta"}
LINE_COLOR = {"ALP": "#0b6efd", "BET": "#e8590c"}
PRIORITY_BAND = {1: 100.0, 2: 10.0, 3: 1.0}


# ---------------------------------------------------------------------------
# 1. Gantt chart of possessions over weeks
# ---------------------------------------------------------------------------
def gantt_figure(inst: Instance, placements: list) -> go.Figure:
    """One bar per (activity, contiguous week-run), coloured by line, with
    co_share_group and sector in the hover so buffer non-overlap is visible."""
    rows = []
    # group placements by activity
    by_act = defaultdict(list)
    for p in placements:
        by_act[p.activity_id].append(p)

    for aid, ps in by_act.items():
        a = inst.activities[aid]
        c = inst.contracts[a.contract_number]
        ps_sorted = sorted(ps, key=lambda x: x.week)
        weeks = sorted({p.week for p in ps_sorted})
        # collapse consecutive weeks into contiguous runs for cleaner bars
        runs = []
        run_start = prev = weeks[0]
        for w in weeks[1:]:
            if w == prev + 1:
                prev = w
            else:
                runs.append((run_start, prev))
                run_start = prev = w
        runs.append((run_start, prev))

        ps0 = parse_sector_location(a.start_location_id)
        line = ps0[1] if ps0 else "ALP"
        bound = ps0[4] if ps0 else ""
        csg = ps_sorted[0].co_share_group
        for (w0, w1) in runs:
            rows.append(dict(
                Activity=aid,
                Contract=a.contract_number,
                Line=LINE_NAME.get(line, line),
                Start=inst.date_of_week(w0),
                Finish=inst.date_of_week(w1) + pd.Timedelta(days=6),
                Nature=c.nature_of_activity,
                Access=c.access_type,
                Bound=bound,
                CoShare=csg,
                Priority=f"P{c.contract_priority}",
                Weeks=f"wk{w0}-{w1}" if w1 > w0 else f"wk{w0}",
            ))
    df = pd.DataFrame(rows)
    if df.empty:
        return go.Figure()
    df = df.sort_values(["Line", "Contract", "Activity"])
    fig = px.timeline(
        df, x_start="Start", x_end="Finish", y="Activity", color="Line",
        color_discrete_map={LINE_NAME["ALP"]: LINE_COLOR["ALP"],
                            LINE_NAME["BET"]: LINE_COLOR["BET"]},
        hover_data=["Contract", "Priority", "Nature", "Access", "Bound",
                    "CoShare", "Weeks"],
    )
    fig.update_yaxes(autorange="reversed", title="")
    fig.update_layout(height=max(400, 18 * df["Activity"].nunique()),
                      legend_title="", margin=dict(l=0, r=0, t=10, b=0))
    return fig


# ---------------------------------------------------------------------------
# 2. Rail topology map
# ---------------------------------------------------------------------------
def topology_figure(inst: Instance, placements: list, week: int) -> go.Figure:
    """Schematic of both lines. Nodes = stations; interchange hubs highlighted.
    Sectors worked in the chosen week are drawn in the line colour (Live in red),
    idle sectors in grey."""
    # station x-positions by seq, y by line
    y_of = {"ALP": 1.0, "BET": 0.0}
    pos = {}
    for s in inst.stations:
        pos[(s.line_code, s.station_id)] = (s.seq, y_of[s.line_code])

    # which sectors are active this week + whether any Live closure hit them
    active = set()
    live_active = set()
    for p in placements:
        if p.week != week:
            continue
        a = inst.activities[p.activity_id]
        c = inst.contracts[a.contract_number]
        for loc in p.all_locations:
            ps = parse_sector_location(loc)
            if ps:
                active.add((ps[1], ps[2], ps[3]))  # line, from, to
        if c.nature_of_activity == "Live":
            for loc in p.closures:
                ps = parse_sector_location(loc)
                if ps:
                    live_active.add((ps[1], ps[2], ps[3]))

    fig = go.Figure()
    # draw sector edges
    for sec in inst.sectors:
        p1 = pos.get((sec.line_code, sec.from_station_id))
        p2 = pos.get((sec.line_code, sec.to_station_id))
        if not p1 or not p2:
            continue
        key = (sec.line_code, sec.from_station_id, sec.to_station_id)
        if key in live_active:
            color, width = "#d6336c", 6
        elif key in active:
            color, width = LINE_COLOR[sec.line_code], 5
        else:
            color, width = "#ced4da", 2
        fig.add_trace(go.Scatter(
            x=[p1[0], p2[0]], y=[p1[1], p2[1]], mode="lines",
            line=dict(color=color, width=width), hoverinfo="text",
            text=f"{sec.sector_id}", showlegend=False))

    # draw station nodes
    for s in inst.stations:
        x, y = pos[(s.line_code, s.station_id)]
        is_hub = s.is_interchange
        fig.add_trace(go.Scatter(
            x=[x], y=[y], mode="markers+text",
            marker=dict(size=22 if is_hub else 14,
                        color="#f59f00" if is_hub else LINE_COLOR[s.line_code],
                        symbol="diamond" if is_hub else "circle",
                        line=dict(width=1, color="white")),
            text=[s.station_id], textposition="top center",
            hovertext=f"{s.station_id} ({LINE_NAME[s.line_code]})",
            hoverinfo="text", showlegend=False))

    fig.update_layout(
        height=320, margin=dict(l=10, r=10, t=30, b=10),
        title=f"Network — week {week}  "
              f"(coloured = worked, red = Live closure)",
        xaxis=dict(visible=False), yaxis=dict(visible=False,
                                              range=[-0.6, 1.8]),
        plot_bgcolor="white")
    # line labels
    fig.add_annotation(x=0, y=1.0, text="ALP", showarrow=False,
                       xshift=-30, font=dict(color=LINE_COLOR["ALP"]))
    fig.add_annotation(x=0, y=0.0, text="BET", showarrow=False,
                       xshift=-30, font=dict(color=LINE_COLOR["BET"]))
    return fig


# ---------------------------------------------------------------------------
# 3. Scenario comparison dashboard
# ---------------------------------------------------------------------------
def comparison_table(reports: dict) -> pd.DataFrame:
    """reports: {scenario: validator_report}. Returns a tidy comparison frame."""
    rows = []
    for sc in ("A", "B", "C"):
        r = reports.get(sc)
        if not r:
            continue
        s = r["soft_scores"]
        rows.append({
            "Scenario": sc,
            "Feasible": "Yes" if r["feasible"] else "No",
            "Objective score": r.get("objective_score", "—"),
            "Overrun days": s["overrun_days_total"],
            "P1 overrun": s["priority_overrun"]["1"],
            "P2 overrun": s["priority_overrun"]["2"],
            "P3 overrun": s["priority_overrun"]["3"],
            "Excess access-nights": s["excess_access_nights_total"],
            "ECLO nights": s["eclo_nights_total"],
            "Access-nights total": r["detail"]["nights_scheduled"],
        })
    return pd.DataFrame(rows)


def comparison_figure(reports: dict) -> go.Figure:
    """Grouped bars: the penalty components per scenario."""
    cats = ["Priority-weighted overrun", "Excess nights ×7", "ECLO ×5"]
    fig = go.Figure()
    for sc in ("A", "B", "C"):
        r = reports.get(sc)
        if not r:
            continue
        s = r["soft_scores"]
        vals = [s["priority_weighted_score"],
                7 * s["excess_access_nights_total"],
                5 * s["eclo_nights_total"]]
        fig.add_trace(go.Bar(name=f"Scenario {sc}", x=cats, y=vals,
                             text=[f"{v:g}" for v in vals], textposition="auto"))
    fig.update_layout(barmode="group", height=360,
                      yaxis_title="Penalty contribution (lower = better)",
                      margin=dict(l=0, r=0, t=10, b=0), legend_title="")
    return fig


# ---------------------------------------------------------------------------
# 4. Explainability & bottleneck insights
# ---------------------------------------------------------------------------
def hotspots_table(inst: Instance, occ_df: pd.DataFrame) -> pd.DataFrame:
    """Location-weeks at or over capacity, with utilisation %."""
    slots = (occ_df.groupby(["location_id", "week"])["co_share_group"]
             .nunique().reset_index(name="possessions"))
    slots["capacity"] = slots["location_id"].map(
        lambda l: inst.locations[l].supply_capacity if l in inst.locations else 4)
    slots["utilisation"] = (slots["possessions"] / slots["capacity"] * 100).round(0)
    slots["over_by"] = (slots["possessions"] - slots["capacity"]).clip(lower=0)
    return (slots.sort_values(["over_by", "utilisation"], ascending=False)
            .head(20).reset_index(drop=True))


def cosharing_efficiency(occ_df: pd.DataFrame) -> dict:
    """How much co-sharing packed multiple activities into one possession."""
    grp = occ_df.groupby(["location_id", "week", "co_share_group"])["activity_id"].nunique()
    shared = (grp > 1).sum()
    total = len(grp)
    activities_packed = grp[grp > 1].sum()
    return {
        "possessions_total": int(total),
        "possessions_shared": int(shared),
        "activities_in_shared": int(activities_packed),
        "share_rate_pct": round(100 * shared / total, 1) if total else 0.0,
    }


def priority_reasoning(inst: Instance, results_df: pd.DataFrame) -> list[str]:
    """Explain, in words, why delays landed where they did."""
    msgs = []
    overs = results_df[results_df["overrun_days"] > 0]
    if overs.empty:
        msgs.append("No contract overran its planned completion date — the "
                    "schedule absorbed all congestion without slipping any "
                    "deadline.")
        return msgs
    # group overruns by contract priority
    for _, row in overs.iterrows():
        c = inst.contracts[row["contract_number"]]
        band = PRIORITY_BAND[c.contract_priority]
        msgs.append(
            f"**{row['contract_number']}** (Priority {c.contract_priority}) "
            f"slipped **{int(row['overrun_days'])} day(s)**. At tier weight "
            f"×{band:g}, this was chosen for delay because lower-priority slip "
            f"costs far less than delaying a higher tier — the solver protects "
            f"Priority-1 work first.")
    return msgs
