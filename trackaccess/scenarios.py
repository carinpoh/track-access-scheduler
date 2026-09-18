"""Scenario A / B / C policy configuration.

Each scenario is the same solver with a different policy on the three levers:
capacity overflow, ECLO, and overrun past planned dates.
"""
from __future__ import annotations

from dataclasses import dataclass


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
