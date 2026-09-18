"""Greedy, scenario-aware track-access scheduler.

Strategy
--------
Process activities in a priority order (contract tier, then activity priority,
then earliest planned start). For each activity, place its required access
nights week by week starting at its earliest legal week (max of planned-start
week and predecessor-finish week), packing into co-share groups where legal and
respecting every hard rule the local validator checks.

The result is a list of "placements", one per access-night, from which the two
schedule CSVs are written.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .loader import Instance
from .network import Network, parse_sector_location
from .scenarios import ScenarioPolicy


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
