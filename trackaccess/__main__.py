"""CLI entrypoint.

  python -m trackaccess solve --data 01_data --scenario A --out out/A
  python -m trackaccess solveall --data 01_data --out out
  python -m trackaccess validate --data 01_data --sub out/A
"""
from __future__ import annotations

import argparse
import json
import os

from .loader import Instance
from .scenarios import SCENARIOS
from .solver import Solver
from .writer import write_all
from .validate import validate


def _solve_one(data_dir: str, scenario: str, out_dir: str) -> None:
    inst = Instance(data_dir)
    pol = SCENARIOS[scenario]
    solver = Solver(inst, pol)
    placements = solver.solve()
    write_all(out_dir, inst, placements, scenario)
    print(f"[{scenario}] wrote {len(placements)} access-nights -> {out_dir}")


def main() -> None:
    p = argparse.ArgumentParser(prog="trackaccess")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("solve")
    s.add_argument("--data", required=True)
    s.add_argument("--scenario", required=True, choices=["A", "B", "C"])
    s.add_argument("--out", required=True)

    sa = sub.add_parser("solveall")
    sa.add_argument("--data", required=True)
    sa.add_argument("--out", required=True)

    v = sub.add_parser("validate")
    v.add_argument("--data", required=True)
    v.add_argument("--sub", required=True)

    args = p.parse_args()
    if args.cmd == "solve":
        _solve_one(args.data, args.scenario, args.out)
    elif args.cmd == "solveall":
        for sc in ("A", "B", "C"):
            _solve_one(args.data, sc, os.path.join(args.out, sc))
    elif args.cmd == "validate":
        print(json.dumps(validate(args.data, args.sub), indent=2))


if __name__ == "__main__":
    main()
