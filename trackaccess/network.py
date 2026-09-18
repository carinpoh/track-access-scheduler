"""Network engine: footprint expansion, Live mirroring, hub coupling, buffers.

Given an activity's start_location_id -> end_location_id (both are tunnel
sectors of the form SEC:<LINE>:<A_B>:<BOUND>), compute the full set of
bookable locations (tunnel sectors + platform sectors) the possession occupies,
plus any buffer / mirror / cross-line closures its nature_of_works implies.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .loader import Instance


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
