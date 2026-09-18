"""Load the 8 instance CSVs into typed model objects."""
from __future__ import annotations

import csv
import os
from datetime import date, datetime
from typing import Optional

from .models import (
    Activity,
    BufferRule,
    Contract,
    Location,
    Sector,
    Station,
)


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
        from datetime import timedelta
        return self.horizon_start + timedelta(days=(week - 1) * 7)
