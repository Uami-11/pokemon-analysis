"""Build the extended raw dataset (original 801 rows + dex 802-1025).

What this script does:

1. Reads ``datasets/pokemon.csv`` (never modified - it stays the raw source).
2. Maps the cached PokeAPI JSON onto the exact 41 columns of the CSV.
3. *Validates* that mapping first: it rebuilds a sample of dex entries that
   are already in the CSV and reports every disagreement instead of
   silently overwriting anything.
4. Appends the new rows (dex 802-1025) and writes ``datasets/pokemon_full.csv``
   with ``pokedex_number`` and ``name`` moved to the front.

Run ``python scripts/fetch_pokeapi.py`` first (or let this script call it
for whatever is missing from the cache).

Usage:
    python scripts/build_dataset.py
    python scripts/build_dataset.py --skip-validation
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_pokeapi import RAW_DIR, ROOT, VALIDATION_DEX, fetch_pokemon_ids, fetch_static  # noqa: E402

RAW_CSV = ROOT / "datasets" / "pokemon.csv"
OUT_CSV = ROOT / "datasets" / "pokemon_full.csv"

ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5,
         "vi": 6, "vii": 7, "viii": 8, "ix": 9}

# stat name in the API -> column name in the CSV
STAT_COLUMNS = {
    "hp": "hp",
    "attack": "attack",
    "defense": "defense",
    "special-attack": "sp_attack",
    "special-defense": "sp_defense",
    "speed": "speed",
}

NUMERIC_COLUMNS = [
    "against_bug", "against_dark", "against_dragon", "against_electric",
    "against_fairy", "against_fight", "against_fire", "against_flying",
    "against_ghost", "against_grass", "against_ground", "against_ice",
    "against_normal", "against_poison", "against_psychic", "against_rock",
    "against_steel", "against_water", "attack", "base_egg_steps",
    "base_happiness", "base_total", "capture_rate", "defense",
    "experience_growth", "height_m", "hp", "percentage_male",
    "pokedex_number", "sp_attack", "sp_defense", "speed", "weight_kg",
    "generation", "is_legendary",
]


# --------------------------------------------------------------------- helpers
def fmt_mult(value: float) -> str:
    """against_* cells: 1 -> '1', 0.5 -> '0.5', 4 -> '4'."""
    return str(int(value)) if float(value).is_integer() else str(value)


def fmt_float(value) -> str:
    """'0.7', '2.0' ... exactly how the raw CSV writes heights/weights."""
    if value is None:
        return ""
    return str(float(value))


def fmt_pct_male(gender_rate: int) -> str:
    """PokeAPI gender_rate: -1 genderless, 0 all male, 8 all female."""
    if gender_rate is None or gender_rate < 0:
        return ""
    value = (8 - gender_rate) * 100 / 8
    return str(int(value)) if float(value).is_integer() else str(value)


def title_ability(slug: str) -> str:
    return slug.replace("-", " ").title()


def display_name(raw: str) -> str:
    """The API writes Sirfetch'd with a curly apostrophe, the CSV with '."""
    return raw.replace("\u2019", "'")


# ------------------------------------------------------------------ type chart
def build_type_chart(types: dict) -> dict[str, dict[str, float]]:
    """attacking type -> {defending type: multiplier}, from the raw API data."""
    chart: dict[str, dict[str, float]] = {}
    for name, payload in types.items():
        rel = payload["damage_relations"]
        multipliers = {d["name"]: 1.0 for d in rel["double_damage_to"]}
        multipliers.update({d["name"]: 0.5 for d in rel["half_damage_to"]})
        multipliers.update({d["name"]: 0.0 for d in rel["no_damage_to"]})
        chart[name] = multipliers
    return chart


def effectiveness(chart: dict, attacking: str, defending: list[str]) -> float:
    """Dual types multiply, so the chart is applied per defending type."""
    value = 1.0
    for dtype in defending:
        value *= chart[attacking].get(dtype, 1.0)
    return value


def against_columns(chart: dict, defending: list[str]) -> dict[str, str]:
    cells = {}
    for attacking in chart:
        column = "against_fight" if attacking == "fighting" else f"against_{attacking}"
        cells[column] = fmt_mult(effectiveness(chart, attacking, defending))
    return cells


# ------------------------------------------------------------------ field map
def build_row(species: dict, pokemon: dict, growth: dict, chart: dict) -> dict:
    """Translate one species + one pokemon payload into a raw-CSV row."""
    names = {n["language"]["name"]: n["name"] for n in species["names"]}
    genera = {g["language"]["name"]: g["genus"] for g in species["genera"]}
    growth_id = species["growth_rate"]["url"].rstrip("/").split("/")[-1]

    types = sorted(pokemon["types"], key=lambda t: t["slot"])
    defending = [t["type"]["name"] for t in types]

    stats = {s["stat"]["name"]: s["base_stat"] for s in pokemon["stats"]}
    abilities = sorted(pokemon["abilities"], key=lambda a: a["slot"])

    hatch_counter = species.get("hatch_counter")
    height, weight = pokemon.get("height", 0), pokemon.get("weight", 0)

    row = {
        "abilities": str([title_ability(a["ability"]["name"]) for a in abilities]),
        **against_columns(chart, defending),
        "attack": str(stats["attack"]),
        "base_egg_steps": str(hatch_counter * 256) if hatch_counter is not None else "",
        "base_happiness": str(species["base_happiness"]) if species.get("base_happiness") is not None else "",
        "base_total": str(sum(stats.values())),
        "capture_rate": str(species["capture_rate"]),
        "classfication": genera.get("en", ""),
        "defense": str(stats["defense"]),
        "experience_growth": str(growth[str(growth_id)]["levels"][99]["experience"]),
        "height_m": fmt_float(height / 10) if height else "",
        "hp": str(stats["hp"]),
        "japanese_name": names.get("ja-roma", "") + names.get("ja-hrkt", ""),
        "name": display_name(names.get("en", pokemon["name"])),
        "percentage_male": fmt_pct_male(species["gender_rate"]),
        "pokedex_number": str(species["id"]),
        "sp_attack": str(stats["special-attack"]),
        "sp_defense": str(stats["special-defense"]),
        "speed": str(stats["speed"]),
        "type1": defending[0],
        "type2": defending[1] if len(defending) > 1 else "",
        "weight_kg": fmt_float(weight / 10) if weight else "",
        "generation": str(ROMAN[species["generation"]["name"].split("-")[1]]),
        "is_legendary": "1" if species["is_legendary"] else "0",
    }
    return row


# ------------------------------------------------------------------ validation
def validate(sample_dex: list[int], df: pd.DataFrame, growth: dict,
             chart: dict, sample_species: dict, sample_pokemon: dict) -> None:
    """Rebuild rows that already exist in the CSV and report disagreements."""
    existing = df.copy()
    existing.index = existing["pokedex_number"].astype(int)
    mismatches: dict[str, list[str]] = {}
    checked = 0

    for dex_id in sample_dex:
        if str(dex_id) not in sample_species:
            continue
        if dex_id not in existing.index:
            continue
        checked += 1
        rebuilt = build_row(sample_species[str(dex_id)], sample_pokemon[str(dex_id)],
                            growth, chart)
        original = existing.loc[dex_id]
        for column, new_value in rebuilt.items():
            old_value = original[column]
            if column in NUMERIC_COLUMNS:
                try:
                    equal = abs(float(new_value) - float(old_value)) < 1e-9
                except (TypeError, ValueError):
                    equal = str(new_value) == str(old_value)
            else:
                equal = str(new_value) == str(old_value)
            if not equal:
                mismatches.setdefault(column, []).append(
                    f"dex {dex_id} {original['name']}: csv={old_value!r} api={new_value!r}")

    print("=" * 70)
    print(f"VALIDATION: rebuilt {checked} existing entries, "
          f"{len(mismatches)} columns disagree")
    print("=" * 70)
    for column in sorted(mismatches, key=lambda c: -len(mismatches[c])):
        examples = mismatches[column]
        print(f"  {column:18s} {len(examples):4d} mismatches  e.g. "
              f"{examples[0]}" + (f" | {examples[1]}" if len(examples) > 1 else ""))
    if not mismatches:
        print("  perfect match - the mapping can be trusted")
    print()


# ------------------------------------------------------------------------ main
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-validation", action="store_true",
                        help="do not rebuild the existing sample rows")
    args = parser.parse_args()

    # --- raw source, untouched ------------------------------------------------
    df_raw = pd.read_csv(RAW_CSV, dtype=str, keep_default_na=False)
    print(f"raw dataset: {df_raw.shape[0]} rows x {df_raw.shape[1]} columns")

    # --- extract (cached) -----------------------------------------------------
    if not (RAW_DIR / "type_fire.json").exists():
        print("type/growth cache missing - fetching static endpoints...")
        fetch_static()
    if not (RAW_DIR / "species_0810.json").exists():
        print("species cache missing - fetching dex 802-1025...")
        fetch_pokemon_ids(range(802, 1026))
    if not (RAW_DIR / "species_0001.json").exists():
        print("validation cache missing - fetching sample...")
        fetch_pokemon_ids(VALIDATION_DEX)

    def load(prefix: str, ids) -> dict:
        out = {}
        for dex_id in ids:
            path = RAW_DIR / f"{prefix}_{int(dex_id):04d}.json"
            if path.exists():
                out[str(int(dex_id))] = json.loads(path.read_text(encoding="utf-8"))
        return out

    types = {p.stem.split("_", 1)[1]: json.loads(p.read_text(encoding="utf-8"))
             for p in sorted(RAW_DIR.glob("type_*.json"))}
    growth = {p.stem.split("_")[-1]: json.loads(p.read_text(encoding="utf-8"))
              for p in sorted(RAW_DIR.glob("growth_rate_*.json"))}
    print(f"cached: {len(types)} types, {len(growth)} growth rates")

    chart = build_type_chart(types)

    # --- validation against the raw CSV --------------------------------------
    if not args.skip_validation:
        sample_species = load("species", VALIDATION_DEX)
        sample_pokemon = load("pokemon", VALIDATION_DEX)
        validate(VALIDATION_DEX, df_raw, growth, chart,
                 sample_species, sample_pokemon)

    # --- new rows -------------------------------------------------------------
    new_species = load("species", range(802, 1026))
    new_pokemon = load("pokemon", range(802, 1026))
    missing = [d for d in range(802, 1026) if str(d) not in new_species]
    if missing:
        print("!! missing from the API cache:", missing, file=sys.stderr)

    new_rows = []
    for dex_id in range(802, 1026):
        if str(dex_id) not in new_species:
            continue
        new_rows.append(build_row(new_species[str(dex_id)],
                                  new_pokemon[str(dex_id)], growth, chart))
    df_new = pd.DataFrame(new_rows, columns=df_raw.columns)

    # --- assemble the extended raw dataset -----------------------------------
    extended = pd.concat([df_raw, df_new], ignore_index=True)
    extended["__dex"] = extended["pokedex_number"].astype(int)
    extended = extended.sort_values("__dex").drop(columns="__dex")

    front = ["pokedex_number", "name"]
    ordered = front + [c for c in df_raw.columns if c not in front]
    extended = extended[ordered]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    extended.to_csv(OUT_CSV, index=False)

    added = pd.DataFrame(new_rows)
    print("=" * 70)
    print(f"wrote {OUT_CSV.relative_to(ROOT)}: {extended.shape[0]} rows x "
          f"{extended.shape[1]} columns ({len(new_rows)} new)")
    if not added.empty:
        counts = added["generation"].astype(int).value_counts().sort_index()
        print("new rows per generation:", dict(counts))
    print("column order:", ", ".join(ordered[:6]), ", ...')


if __name__ == "__main__":
    main()
