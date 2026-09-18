"""Domain model dataclasses for the railway track-access problem."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


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
