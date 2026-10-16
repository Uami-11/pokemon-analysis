"""End-to-end pipeline runner for the Pokemon analysis project.

Runs every phase in order by invoking the phase scripts:

  1. scripts/fetch_pokeapi.py    (Phase 1 - cache the PokeAPI JSON)
  2. scripts/build_dataset.py    (Phase 1 - build datasets/pokemon_full.csv)
  3. scripts/clean_dataset.py    (Phase 3 - build datasets/pokemon_clean.csv + split tables)
  4. sql/schema.sql + scripts/load_database.py  (Phases 5-6 - schema + load)
  5. scripts/run_reports.py      (Phase 7 - write reports/sql_reports.md)
  6. scripts/build_erd.py        (Phase 5 - render docs/erd.png)

Examples:
    python scripts/run_pipeline.py                 # full run
    python scripts/run_pipeline.py --skip-fetch    # reuse cached JSON / existing CSVs
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

# (label, [script args], phase-group)
STEPS = [
    ("build dataset from cache", ["scripts/build_dataset.py"], "dataset"),
    ("clean dataset", ["scripts/clean_dataset.py"], "dataset"),
    ("render ERD", ["scripts/build_erd.py"], "database"),
    ("create schema + load database", ["scripts/load_database.py", "--recreate"], "database"),
    ("run SQL reports", ["scripts/run_reports.py"], "reports"),
]


def run_step(label: str, args: list[str]) -> None:
    print(f"\n{'=' * 70}\n>> {label}\n   $ {' '.join(args)}\n{'=' * 70}", flush=True)
    import subprocess

    t0 = time.time()
    proc = subprocess.run([PY, *args], cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit(f"step failed ({proc.returncode}): {label}")
    print(f"<< {label} done in {time.time() - t0:.1f}s", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-fetch", action="store_true",
                        help="do not re-download PokeAPI JSON")
    parser.add_argument("--skip-dataset", action="store_true",
                        help="do not rebuild pokemon_full.csv / clean tables")
    parser.add_argument("--skip-erd", action="store_true", help="do not re-render docs/erd.png")
    args = parser.parse_args()

    steps = list(STEPS)
    if args.skip_erd:
        steps = [s for s in steps if s[0] != "render ERD"]
    if args.skip_dataset:
        steps = [s for s in steps if s[2] != "dataset"]

    if not args.skip_fetch:
        run_step("cache PokeAPI JSON", ["scripts/fetch_pokeapi.py"])
    else:
        print("skipping PokeAPI fetch (--skip-fetch)")

    for label, argv, _group in steps:
        run_step(label, argv)

    print("\nPipeline complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
