"""Extract raw JSON data from PokeAPI and cache it on disk.

This is the *extract* stage of the ETL pipeline. Every HTTP response is
stored under ``datasets/raw/`` so that:

  * the original sources are preserved (raw CSV + raw API JSON),
  * the pipeline stays reproducible (a second run reads the cache and
    does not hit the API again).

Usage:
    python scripts/fetch_pokeapi.py                 # fetch anything missing
    python scripts/fetch_pokeapi.py --refresh        # re-download everything
    python scripts/fetch_pokeapi.py --only types     # only the static endpoints
    python scripts/fetch_pokeapi.py --only new       # only dex 802-1025
    python scripts/fetch_pokeapi.py --only sample    # only the validation sample
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://pokeapi.co/api/v2"
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "datasets" / "raw"

# The original CSV stops at dex 801 (Magearna). Everything from here to the
# end of the national pokedex has to be extracted from the API.
NEW_DEX_RANGE = range(802, 1026)

# A deterministic sample of dex entries already present in the CSV. It is
# re-extracted so the field mapping can be validated against the raw data
# before it is trusted for the new rows.
VALIDATION_DEX = sorted(
    set(range(1, 802, 17))
    | {1, 4, 6, 12, 26, 50, 51, 88, 89, 122, 129, 132, 151, 152, 241,
       292, 386, 492, 493, 554, 649, 700, 721, 722, 774, 801}
)

REQUEST_PAUSE = 0.05  # seconds between requests - be polite to the API


def _session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=4, backoff_factor=0.5,
                  status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "pokemon-analysis-etl/1.0"
    return session


def get_json(url: str, cache_name: str, refresh: bool = False,
             session: requests.Session | None = None) -> dict:
    """Return the JSON for *url*, reading from / writing to the raw cache."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = RAW_DIR / cache_name
    if cache_path.exists() and not refresh:
        with open(cache_path, encoding="utf-8") as fh:
            return json.load(fh)

    session = session or _session()
    response = session.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    time.sleep(REQUEST_PAUSE)
    return data


# ---------------------------------------------------------------- static data
def fetch_static(refresh: bool = False) -> tuple[dict, dict]:
    """Type damage relations (18) and growth rates (6).

    The type relations are what the ``against_*`` columns are built from;
    the growth rates provide ``experience_growth`` (experience needed to
    reach level 100).
    """
    session = _session()
    types: dict[str, dict] = {}
    for name in ["bug", "dark", "dragon", "electric", "fairy", "fighting",
                 "fire", "flying", "ghost", "grass", "ground", "ice",
                 "normal", "poison", "psychic", "rock", "steel", "water"]:
        types[name] = get_json(f"{BASE_URL}/type/{name}",
                               f"type_{name}.json", refresh, session)
        print(f"  type/{name}")

    growth: dict[str, dict] = {}
    for idx in range(1, 7):
        growth[str(idx)] = get_json(f"{BASE_URL}/growth-rate/{idx}",
                                    f"growth_rate_{idx}.json", refresh, session)
        print(f"  growth-rate/{idx}")
    return types, growth


# --------------------------------------------------------------- species/pkmn
def fetch_pokemon_ids(ids: range | list[int], refresh: bool = False) -> tuple[dict, dict]:
    """Species + pokemon payloads for the given national dex ids."""
    session = _session()
    species: dict[str, dict] = {}
    pokemon: dict[str, dict] = {}
    for dex_id in ids:
        try:
            species[str(dex_id)] = get_json(
                f"{BASE_URL}/pokemon-species/{dex_id}",
                f"species_{dex_id:04d}.json", refresh, session)
            pokemon[str(dex_id)] = get_json(
                f"{BASE_URL}/pokemon/{dex_id}",
                f"pokemon_{dex_id:04d}.json", refresh, session)
        except requests.HTTPError as exc:
            print(f"  !! dex {dex_id}: {exc}", file=sys.stderr)
        if dex_id % 50 == 0:
            print(f"  dex {dex_id}...")
    return species, pokemon


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true",
                        help="re-download even if a cached copy exists")
    parser.add_argument("--only", choices=["types", "new", "sample"],
                        help="fetch a single group of endpoints")
    args = parser.parse_args()

    print("RAW_DIR:", RAW_DIR)
    if args.only in (None, "types"):
        print("Static endpoints (types, growth rates):")
        fetch_static(args.refresh)
    if args.only in (None, "new"):
        print(f"New national dex entries ({NEW_DEX_RANGE.start}-"
              f"{NEW_DEX_RANGE.stop - 1}):")
        fetch_pokemon_ids(NEW_DEX_RANGE, args.refresh)
    if args.only in (None, "sample"):
        print(f"Validation sample ({len(VALIDATION_DEX)} entries):")
        fetch_pokemon_ids(VALIDATION_DEX, args.refresh)
    print("done")


if __name__ == "__main__":
    main()
