#!/usr/bin/env python3
"""Track Access Optimisation solver (PS1) - single-file standalone version.

Usage:
    python run.py                         # solve all A/B/C -> ./out, then validate
    python run.py solveall --data 01_Data --out out
    python run.py solve --data 01_Data --scenario A --out out/A
    python run.py validate --data 01_Data --sub out/A
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional


# ===================== models.py =====================

# ---------------------------------------------------------------------------
# Network (supply side)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Station:
    station_id: str
    line_code: str
    seq: int
    is_interchange: bool


@dataclass(frozen=True)
class Sector:
    sector_id: str          # e.g. SEC:ALP:S01_S02
    line_code: str
    from_station_id: str
    to_station_id: str
    seq: int
    is_shared: bool


@dataclass(frozen=True)
class Location:
    """A bookable capacity unit: a tunnel sector or a platform, per bound."""
    location_id: str        # e.g. SEC:ALP:S01_S02:EB  or  PLAT:ALP:S03:EB
    kind: str               # 'tunnel sector' | 'platform sector'
    line_code: str
    bound: str              # 'EB' | 'WB'
    supply_capacity: int


# ---------------------------------------------------------------------------
# Demand side
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Contract:
    contract_number: str
    description: str
    award_date: Optional[date]
    activity_type: str            # Renewal | Construction
    nature_of_activity: str       # Live | Non-live (Consist) | Non-live (Others)
    contract_priority: int        # 1 (high) .. 3 (low)
    contract_completion_date: Optional[date]
    planned_completion_date: Optional[date]
    number_of_workfronts: int
    access_type: str              # PM | PC | C
    max_access_per_week: int      # 2 for Live, 3 otherwise


@dataclass
class Activity:
    activity_id: str
    contract_number: str
    activity_type: str
    start_location_id: str
    end_location_id: str
    total_accesses: float
    planned_start_date: Optional[date]
    predecessor_activity_id: Optional[str]
    activity_priority: int        # 1 (high) .. 3 (low)

    # Resolved at load time
    locations: list[str] = field(default_factory=list)   # expanded footprint


@dataclass
class BufferRule:
    nature_of_works: str
    up_to_buffer_sectors: int
    opposite_bound_required: bool

# ===================== loader.py =====================

def _parse_date(s: str) -> Optional[date]:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date: {s!r}")


def _find(data_dir: str, *needles: str) -> str:
    """Find a CSV file in data_dir whose name contains any needle (case-insensitive)."""
    for fn in sorted(os.listdir(data_dir)):
        low = fn.lower()
        if low.endswith(".csv") and any(n.lower() in low for n in needles):
            return os.path.join(data_dir, fn)
    raise FileNotFoundError(f"No CSV matching {needles} in {data_dir}")


def _rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


class Instance:
    """Fully-parsed problem instance."""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self._load()

    def _load(self) -> None:
        d = self.data_dir

        # --- parameters ---
        self.params: dict[str, str] = {}
        for r in _rows(_find(d, "PARAMETERS")):
            self.params[r["key"].strip()] = r["value"].strip()
        self.horizon_start: date = _parse_date(self.params["horizon_start"])
        self.horizon_weeks: int = int(self.params["horizon_weeks"])

        # --- lines ---
        self.lines = {r["line_code"]: r["line_name"] for r in _rows(_find(d, "LINES"))}

        # --- stations ---
        self.stations: list[Station] = [
            Station(
                station_id=r["station_id"].strip(),
                line_code=r["line_code"].strip(),
                seq=int(r["seq"]),
                is_interchange=str(r["is_interchange"]).strip() in ("1", "true", "True"),
            )
            for r in _rows(_find(d, "STATIONS"))
        ]

        # --- sectors ---
        self.sectors: list[Sector] = [
            Sector(
                sector_id=r["sector_id"].strip(),
                line_code=r["line_code"].strip(),
                from_station_id=r["from_station_id"].strip(),
                to_station_id=r["to_station_id"].strip(),
                seq=int(r["seq"]),
                is_shared=str(r["is_shared"]).strip() in ("1", "true", "True"),
            )
            for r in _rows(_find(d, "SECTORS"))
        ]

        # --- location supply ---
        self.locations: dict[str, Location] = {}
        for r in _rows(_find(d, "LOCATION_SUPPLY", "SUPPLY")):
            loc = Location(
                location_id=r["location_id"].strip(),
                kind=r["location_kind"].strip(),
                line_code=r["line_code"].strip(),
                bound=r["bound"].strip(),
                supply_capacity=int(r["supply_capacity"]),
            )
            self.locations[loc.location_id] = loc

        # --- buffer rules ---
        self.buffers: dict[str, BufferRule] = {}
        for r in _rows(_find(d, "BUFFER")):
            br = BufferRule(
                nature_of_works=r["nature_of_works"].strip(),
                up_to_buffer_sectors=int(r["up_to_buffer_sectors"]),
                opposite_bound_required=str(r["opposite_bound_required"]).strip() in ("1", "true", "True"),
            )
            self.buffers[br.nature_of_works] = br

        # --- contracts ---
        self.contracts: dict[str, Contract] = {}
        for r in _rows(_find(d, "PROJECT_DETAILS", "CONTRACT")):
            c = Contract(
                contract_number=r["contract_number"].strip(),
                description=r.get("contract_description", "").strip(),
                award_date=_parse_date(r.get("contract_award_date", "")),
                activity_type=r.get("activity_type", "").strip(),
                nature_of_activity=r["nature_of_activity"].strip(),
                contract_priority=int(r["contract_priority"]),
                contract_completion_date=_parse_date(r.get("contract_completion_date", "")),
                planned_completion_date=_parse_date(r.get("planned_completion_date", "")),
                number_of_workfronts=int(r["number_of_workfronts"]),
                access_type=r["access_type"].strip(),
                max_access_per_week=int(r["number_of_maximum_access_per_week"]),
            )
            self.contracts[c.contract_number] = c

        # --- activities ---
        self.activities: dict[str, Activity] = {}
        for r in _rows(_find(d, "ACTIVITY_DETAILS", "ACTIVITY")):
            pred = (r.get("predecessor_activity_id") or "").strip() or None
            a = Activity(
                activity_id=r["activity_id"].strip(),
                contract_number=r["contract_number"].strip(),
                activity_type=r.get("activity_type", "").strip(),
                start_location_id=r["start_location_id"].strip(),
                end_location_id=r["end_location_id"].strip(),
                total_accesses=float(r["total_accesses"]),
                planned_start_date=_parse_date(r.get("planned_start_date", "")),
                predecessor_activity_id=pred,
                activity_priority=int(r.get("activity_priority", "2") or "2"),
            )
            self.activities[a.activity_id] = a

    # --- date helpers -----------------------------------------------------
    def week_of(self, d: Optional[date]) -> int:
        """Return 1-based week index of a date within the horizon (clamped >=1)."""
        if d is None:
            return 1
        delta_days = (d - self.horizon_start).days
        wk = delta_days // 7 + 1
        return max(1, wk)

    def date_of_week(self, week: int) -> date:
        return self.horizon_start + timedelta(days=(week - 1) * 7)

# ===================== network.py =====================

def parse_sector_location(loc_id: str) -> Optional[tuple[str, str, str, str, str]]:
    """SEC:ALP:S01_S02:EB -> ('SEC','ALP','S01','S02','EB'). None if not a sector."""
    parts = loc_id.split(":")
    if len(parts) != 4 or parts[0] != "SEC":
        return None
    line = parts[1]
    a, b = parts[2].split("_")
    bound = parts[3]
    return ("SEC", line, a, b, bound)


OPPOSITE = {"EB": "WB", "WB": "EB"}


class Network:
    def __init__(self, inst: Instance):
        self.inst = inst
        # sectors keyed by (line, bound) in seq order for path building
        self._by_line: dict[str, list] = {}
        for s in sorted(inst.sectors, key=lambda x: x.seq):
            self._by_line.setdefault(s.line_code, []).append(s)
        # station seq lookup: (line, station) -> seq
        self._st_seq: dict[tuple[str, str], int] = {
            (s.line_code, s.station_id): s.seq for s in inst.stations
        }

    # ------------------------------------------------------------------
    def _sector_chain(self, line: str, a: str, b: str) -> list:
        """Ordered sectors between station a and station b on a line (inclusive path)."""
        seq_a = self._st_seq[(line, a)]
        seq_b = self._st_seq[(line, b)]
        lo, hi = min(seq_a, seq_b), max(seq_a, seq_b)
        chain = []
        for sec in self._by_line[line]:
            fa = self._st_seq[(line, sec.from_station_id)]
            fb = self._st_seq[(line, sec.to_station_id)]
            if lo <= min(fa, fb) and max(fa, fb) <= hi:
                chain.append(sec)
        return chain

    def _stations_between(self, line: str, a: str, b: str) -> list[str]:
        seq_a = self._st_seq[(line, a)]
        seq_b = self._st_seq[(line, b)]
        lo, hi = min(seq_a, seq_b), max(seq_a, seq_b)
        return [s.station_id for s in self.inst.stations
                if s.line_code == line and lo <= s.seq <= hi]

    # ------------------------------------------------------------------
    def footprint(self, start_loc: str, end_loc: str) -> list[str]:
        """Base occupied locations (tunnels + platforms) for a possession span."""
        ps, pe = parse_sector_location(start_loc), parse_sector_location(end_loc)
        if ps is None or pe is None:
            # Fall back: treat the two given ids as the footprint
            return sorted({start_loc, end_loc})
        _, line, a1, b1, bound = ps
        _, line2, a2, b2, bound2 = pe
        # Determine overall station span on the (shared) line/bound
        seqs = [self._st_seq[(line, a1)], self._st_seq[(line, b1)],
                self._st_seq[(line2, a2)], self._st_seq[(line2, b2)]]
        lo, hi = min(seqs), max(seqs)
        line_stations = {s.seq: s.station_id for s in self.inst.stations
                         if s.line_code == line}
        start_st = line_stations[lo]
        end_st = line_stations[hi]

        locs: set[str] = set()
        # tunnel sectors along the chain
        for sec in self._sector_chain(line, start_st, end_st):
            locs.add(f"{sec.sector_id}:{bound}")
        # platform sectors at every station passed through
        for st in self._stations_between(line, start_st, end_st):
            locs.add(f"PLAT:{line}:{st}:{bound}")
        return sorted(locs)

    # ------------------------------------------------------------------
    def _buffer_sectors(self, line: str, bound: str, footprint: list[str],
                        n: int) -> set[str]:
        """Extend n tunnel sectors of buffer on each side of the footprint span."""
        if n <= 0:
            return set()
        chain = self._by_line[line]
        # indices of footprint tunnel sectors within the line chain
        fp_ids = {loc.rsplit(":", 1)[0] for loc in footprint if loc.startswith("SEC:")}
        idxs = [i for i, sec in enumerate(chain) if sec.sector_id in fp_ids]
        if not idxs:
            return set()
        lo, hi = min(idxs), max(idxs)
        out: set[str] = set()
        for i in range(max(0, lo - n), lo):
            out.add(f"{chain[i].sector_id}:{bound}")
        for i in range(hi + 1, min(len(chain), hi + 1 + n)):
            out.add(f"{chain[i].sector_id}:{bound}")
        return out

    def closures(self, activity, contract) -> list[str]:
        """All locations closed by an activity's possession: footprint + buffer
        + Live opposite-bound mirror + Live hub cross-line coupling."""
        nature = contract.nature_of_activity
        br = self.inst.buffers.get(nature)
        base = self.footprint(activity.start_location_id, activity.end_location_id)
        closed: set[str] = set(base)

        # figure line/bound
        ps = parse_sector_location(activity.start_location_id)
        line = ps[1] if ps else None
        bound = ps[4] if ps else None

        buf = br.up_to_buffer_sectors if br else 0
        if buf and line and bound:
            closed |= self._buffer_sectors(line, bound, base, buf)

        # Live: mirror onto opposite bound
        if br and br.opposite_bound_required and line and bound:
            opp = OPPOSITE[bound]
            mirror = {self._swap_bound(l, opp) for l in list(closed)}
            closed |= mirror
            # Live at interchange: cross onto the OTHER line's H01_H02 tunnel + hub plats
            closed |= self._hub_cross_line(closed, line)

        # keep only real, known locations
        return sorted(l for l in closed if l in self.inst.locations)

    @staticmethod
    def _swap_bound(loc_id: str, new_bound: str) -> str:
        parts = loc_id.rsplit(":", 1)
        return f"{parts[0]}:{new_bound}" if len(parts) == 2 else loc_id

    def _hub_cross_line(self, closed: set[str], line: str) -> set[str]:
        """If a Live closure touches this line's H01_H02 tunnel or H01/H02 plats,
        cross the closure onto the other line's equivalent locations."""
        other = "BET" if line == "ALP" else "ALP"
        extra: set[str] = set()
        for loc in list(closed):
            if f"SEC:{line}:H01_H02:" in loc:
                extra.add(loc.replace(f":{line}:", f":{other}:"))
            if loc.startswith(f"PLAT:{line}:H01:") or loc.startswith(f"PLAT:{line}:H02:"):
                extra.add(loc.replace(f":{line}:", f":{other}:"))
        return extra

# ===================== scenarios.py =====================

@dataclass(frozen=True)
class ScenarioPolicy:
    name: str
    allow_eclo: bool            # may an access use eclo=1?
    capacity_slack: int         # extra access-nights tolerated per location-week
    capacity_unlimited: bool    # B: capacity never hard-fails
    hard_planned_date: bool     # B: overrun past planned_completion_date is a hard fail

    # objective weights (penalties)
    w_excess_night: float = 7.0
    w_eclo: float = 5.0
    # priority band weights per contract tier
    band = {1: 100.0, 2: 10.0, 3: 1.0}
    # activity_priority nudge within band
    nudge = {1: 0.3, 2: 0.2, 3: 0.0}


SCENARIOS = {
    "A": ScenarioPolicy(
        name="A", allow_eclo=False, capacity_slack=0,
        capacity_unlimited=False, hard_planned_date=False,
    ),
    "B": ScenarioPolicy(
        name="B", allow_eclo=True, capacity_slack=0,
        capacity_unlimited=True, hard_planned_date=True,
    ),
    "C": ScenarioPolicy(
        name="C", allow_eclo=True, capacity_slack=1,
        capacity_unlimited=False, hard_planned_date=False,
    ),
}

# ===================== solver.py =====================

@dataclass
class Placement:
    activity_id: str
    access_seq: int          # 1..n within the activity
    week: int
    eclo: int                # 0 or 1
    access_night: int        # 1..max_access_per_week (per contract+type+week)
    location_id: str         # primary location (start_location_id)
    co_share_group: str      # possession label per (location, week)
    all_locations: list[str] = field(default_factory=list)  # full footprint
    closures: list[str] = field(default_factory=list)       # footprint+buffer+mirror


@dataclass
class WeekLoc:
    """Per (location_id, week) occupancy tracker for capacity + co-sharing."""
    # group label -> set of (contract, access_type) sharing that possession
    groups: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)

    def used_slots(self) -> int:
        return len(self.groups)


class Solver:
    def __init__(self, inst: Instance, policy: ScenarioPolicy):
        self.inst = inst
        self.net = Network(inst)
        self.policy = policy

        # occupancy state
        self.occ: dict[tuple[str, int], WeekLoc] = {}
        # closures per (location, week, access_night) -> list of activity ids
        self.closed: dict[tuple[str, int, int], list[str]] = defaultdict(list)
        # weekly access-night usage: (contract, atype, week) -> set(access_night)
        self.week_nights: dict[tuple[str, str, int], set[int]] = defaultdict(set)
        # workfront: (contract, atype, week, access_night) -> set(activity_id)
        self.wf: dict[tuple[str, str, int, int], set[str]] = defaultdict(set)
        # buffer occupancy per (location, week, access_night)
        self.buffer_at: dict[tuple[str, int, int], list[str]] = defaultdict(list)

        self.placements: list[Placement] = []
        self.finish_week: dict[str, int] = {}

    # ------------------------------------------------------------------
    def _order(self) -> list:
        acts = list(self.inst.activities.values())

        def key(a):
            c = self.inst.contracts[a.contract_number]
            return (c.contract_priority, a.activity_priority,
                    self.inst.week_of(a.planned_start_date), a.activity_id)

        return sorted(acts, key=key)

    def _earliest_week(self, a) -> int:
        w = self.inst.week_of(a.planned_start_date)
        if a.predecessor_activity_id:
            pf = self.finish_week.get(a.predecessor_activity_id)
            if pf is not None:
                w = max(w, pf + 1)
        return max(1, w)

    # ------------------------------------------------------------------
    def _capacity_ok(self, loc: str, week: int, adding_new_slot: bool) -> bool:
        cap = self.inst.locations[loc].supply_capacity
        wl = self.occ.get((loc, week))
        used = wl.used_slots() if wl else 0
        if not adding_new_slot:
            return True
        if self.policy.capacity_unlimited:
            return True
        return used + 1 <= cap + self.policy.capacity_slack

    def _excess_for(self, loc: str, week: int) -> int:
        cap = self.inst.locations[loc].supply_capacity
        wl = self.occ.get((loc, week))
        used = wl.used_slots() if wl else 0
        return max(0, used - cap)

    def _cosharable(self, wl: WeekLoc, contract, atype: str) -> Optional[str]:
        """Find an existing possession group this activity may join (co-share).
        PC + C, or C + C. PM never shares. Returns group label or None."""
        if atype == "PM":
            return None
        for label, members in wl.groups.items():
            types = {m[2] for m in members}
            if "PM" in types:
                continue
            n_pc = sum(1 for t in types if t == "PC")
            n_c = sum(1 for t in types if t == "C")
            # legal mix: 1 PC + <=3 C, or <=4 C
            if atype == "PC" and n_pc >= 1:
                continue
            if atype == "PC" and n_c > 3:
                continue
            if atype == "C" and (n_c + (0 if atype == "PC" else 1)) > 3 and n_pc >= 1:
                continue
            if atype == "C" and n_pc == 0 and n_c >= 4:
                continue
            return label
        return None

    # ------------------------------------------------------------------
    def _closure_conflict(self, closures: list[str], week: int, night: int,
                          group_locs_shared: set[str]) -> bool:
        """True if placing on this night collides with an existing closure/buffer
        that isn't the same co-share possession."""
        for loc in closures:
            for a_prev in self.closed.get((loc, week, night), []):
                # allowed only if same co-share possession (handled by caller)
                if loc not in group_locs_shared:
                    return True
        return False

    def _place_one_night(self, a, contract, access_seq: int, eclo: int) -> bool:
        """Attempt to place a single access night for activity a. Returns success."""
        atype = contract.access_type
        primary = a.start_location_id
        foot = self.net.footprint(a.start_location_id, a.end_location_id)
        closures = self.net.closures(a, contract)
        max_nights = contract.max_access_per_week

        # scan weeks from earliest legal week forward
        start_w = self._earliest_week(a)
        # allow overrun beyond horizon in flexible-date scenarios
        max_w = self.inst.horizon_weeks + 260
        for week in range(start_w, max_w + 1):
            used_nights = self.week_nights[(a.contract_number, atype, week)]
            # candidate access_night indices (reuse existing for co-share, else new)
            night_options = sorted(used_nights) + [
                n for n in range(1, max_nights + 1) if n not in used_nights
            ]
            for night in night_options:
                is_new_night = night not in used_nights
                # weekly cap
                if is_new_night and len(used_nights) >= max_nights:
                    continue
                # workfront cap
                wf_set = self.wf[(a.contract_number, atype, week, night)]
                if a.activity_id not in wf_set and len(wf_set) >= contract.number_of_workfronts:
                    continue

                # try to co-share on the primary location this week
                wl = self.occ.setdefault((primary, week), WeekLoc())
                share_label = self._cosharable(wl, contract, atype)

                # locations that would be shared (same possession) -> exempt from closure
                shared_locs: set[str] = set()
                if share_label is not None:
                    shared_locs = set(foot)

                # closure conflict check across full closure set
                if self._closure_conflict(closures, week, night, shared_locs):
                    continue

                # capacity check on every footprint location
                adding_slot = share_label is None
                cap_ok = all(self._capacity_ok(loc, week, adding_slot)
                             for loc in foot if loc in self.inst.locations)
                if not cap_ok:
                    continue

                # ---- commit ----
                if share_label is None:
                    share_label = f"g{len(wl.groups)+1}_{primary[-6:]}"
                for loc in foot:
                    w = self.occ.setdefault((loc, week), WeekLoc())
                    w.groups.setdefault(share_label, [])
                    if (a.activity_id, a.contract_number, atype) not in w.groups[share_label]:
                        w.groups[share_label].append((a.activity_id, a.contract_number, atype))
                for loc in closures:
                    self.closed[(loc, week, night)].append(a.activity_id)
                used_nights.add(night)
                self.wf[(a.contract_number, atype, week, night)].add(a.activity_id)

                self.placements.append(Placement(
                    activity_id=a.activity_id, access_seq=access_seq, week=week,
                    eclo=eclo, access_night=night, location_id=primary,
                    co_share_group=share_label, all_locations=foot, closures=closures,
                ))
                self.finish_week[a.activity_id] = max(
                    self.finish_week.get(a.activity_id, 0), week)
                return True
        return False

    # ------------------------------------------------------------------
    def solve(self) -> list[Placement]:
        for a in self._order():
            contract = self.inst.contracts[a.contract_number]
            remaining = a.total_accesses
            seq = 1
            guard = 0
            while remaining > 1e-9:
                guard += 1
                if guard > 10000:
                    raise RuntimeError(f"Could not place {a.activity_id}")
                # Decide eclo: use it only when policy allows and it helps finish
                eclo = 0
                yield_unit = 1.0
                if self.policy.allow_eclo and remaining < 1.0 + 1e-9 and remaining > 0:
                    # a fractional tail: a standard night already covers it; no eclo needed
                    eclo = 0
                ok = self._place_one_night(a, contract, seq, eclo)
                if not ok:
                    # As last resort in flexible scenarios, force overrun handled by
                    # widening week range already; if still failing, raise.
                    raise RuntimeError(
                        f"No feasible night for {a.activity_id} "
                        f"(contract {a.contract_number})")
                remaining -= yield_unit * (1.5 if eclo else 1.0)
                seq += 1
        return self.placements

# ===================== writer.py =====================

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

# ===================== validate.py =====================

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

# ===================== CLI =====================
def _solve_one(data_dir, scenario, out_dir):
    inst = Instance(data_dir)
    pol = SCENARIOS[scenario]
    solver = Solver(inst, pol)
    placements = solver.solve()
    write_all(out_dir, inst, placements, scenario)
    print(f"[{scenario}] wrote {len(placements)} access-nights -> {out_dir}")


def main():
    p = argparse.ArgumentParser(prog="trackaccess")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("solve")
    s.add_argument("--data", required=True); s.add_argument("--scenario", required=True, choices=["A","B","C"]); s.add_argument("--out", required=True)
    sa = sub.add_parser("solveall")
    sa.add_argument("--data", default="01_Data"); sa.add_argument("--out", default="out")
    v = sub.add_parser("validate")
    v.add_argument("--data", required=True); v.add_argument("--sub", required=True)
    args = p.parse_args()
    if args.cmd == "solve":
        _solve_one(args.data, args.scenario, args.out)
    elif args.cmd == "validate":
        print(json.dumps(validate(args.data, args.sub), indent=2))
    else:
        data = getattr(args, "data", None) or "01_Data"
        out = getattr(args, "out", None) or "out"
        for sc in ("A","B","C"):
            _solve_one(data, sc, os.path.join(out, sc))
        print()
        for sc in ("A","B","C"):
            rep = validate(data, os.path.join(out, sc))
            print(f"Scenario {sc}: feasible={rep['feasible']}  "
                  f"objective_score={rep.get('objective_score','-')}  "
                  f"hard_violations={len(rep['hard_violations'])}")


if __name__ == "__main__":
    main()
