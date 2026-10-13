"""Phase 3 - clean and transform the dataset.

Starts from the raw extended dataset (``datasets/pokemon_full.csv``) and
produces a consistent, analysis-ready dataset:

* **base-form reconciliation** - the original CSV mixed mega/regional-form
  stats and types into gen 1-7 base rows (found during EDA). Every row is
  rebuilt from the cached PokeAPI base form of the same dex number.
* **type fixes** - ``type2 == type1`` duplicates removed, all 18 ``against_*``
  columns recomputed from the official type chart.
* **standardisation** - ``percentage_male`` uses the real in-game ratios,
  ``capture_rate`` is numeric (Minior's combined value collapsed), ability
  spellings come from the official index, ``classfication`` renamed.
* **calculated columns** and **splitting into relational DataFrames**.

Outputs
    datasets/pokemon_clean.csv      flat, cleaned dataset (1025 rows)
    datasets/clean/*.csv            dimension/fact tables for the database
    reports/cleaning_changelog.md   what changed and why

Usage:
    python scripts/clean_dataset.py
    python scripts/clean_dataset.py --skip-fetch
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_dataset import (load_cached, load_cached_growth,  # noqa: E402
                           load_cached_types, build_row, build_type_chart)
from fetch_pokeapi import BASE_DEX_RANGE, RAW_DIR, ROOT, fetch_pokemon_ids  # noqa: E402

RAW_CSV = ROOT / "datasets" / "pokemon.csv"
FULL_CSV = ROOT / "datasets" / "pokemon_full.csv"
CLEAN_CSV = ROOT / "datasets" / "pokemon_clean.csv"
CLEAN_DIR = ROOT / "datasets" / "clean"
CHANGELOG = ROOT / "reports" / "cleaning_changelog.md"

DEX_RANGE = range(1, 1026)
STANDARD_RATIOS = {0.0, 12.5, 25.0, 37.5, 50.0, 62.5, 75.0, 87.5, 100.0}
GENERATION_LABELS = {1: "Generation I", 2: "Generation II", 3: "Generation III",
                     4: "Generation IV", 5: "Generation V", 6: "Generation VI",
                     7: "Generation VII", 8: "Generation VIII", 9: "Generation IX"}

INT_COLUMNS = ["pokedex_number", "hp", "attack", "defense", "sp_attack",
               "sp_defense", "speed", "base_total", "base_egg_steps",
               "base_happiness", "capture_rate", "experience_growth",
               "generation", "is_legendary"]
FLOAT_COLUMNS = ["height_m", "weight_kg", "percentage_male"]
AGAINST_COLUMNS = [c for c in
                   ["against_bug", "against_dark", "against_dragon",
                    "against_electric", "against_fairy", "against_fight",
                    "against_fire", "against_flying", "against_ghost",
                    "against_grass", "against_ground", "against_ice",
                    "against_normal", "against_poison", "against_psychic",
                    "against_rock", "against_steel", "against_water"]]
TYPE_TO_COLUMN = {t: ("against_fight" if t == "fighting" else f"against_{t}")
                  for t in ["bug", "dark", "dragon", "electric", "fairy",
                            "fighting", "fire", "flying", "ghost", "grass",
                            "ground", "ice", "normal", "poison", "psychic",
                            "rock", "steel", "water"]}


# --------------------------------------------------------------- build + clean
def build_api_rows() -> pd.DataFrame:
    """Rebuild every dex entry from the cached PokeAPI base forms."""
    growth = load_cached_growth()
    chart = build_type_chart(load_cached_types())
    species = load_cached("species", DEX_RANGE)
    pokemon = load_cached("pokemon", DEX_RANGE)
    missing = [d for d in DEX_RANGE if str(d) not in species or str(d) not in pokemon]
    if missing:
        raise SystemExit(f"missing cached API data for dex {missing[:5]} ... "
                         f"run: python scripts/fetch_pokeapi.py --only base")

    rows = [build_row(species[str(d)], pokemon[str(d)], growth, chart)
            for d in DEX_RANGE]
    df = pd.DataFrame(rows)
    df = df.rename(columns={"classfication": "classification"})
    return df


def coerce_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.replace("", np.nan)
    for col in INT_COLUMNS:
        df[col] = pd.to_numeric(df[col]).astype("Int64")
    for col in FLOAT_COLUMNS + AGAINST_COLUMNS:
        df[col] = pd.to_numeric(df[col]).astype(float)
    # keep the ability list in the same stringified form as the raw file
    df["abilities"] = df["abilities"].astype(str)
    return df


def add_calculated_columns(df: pd.DataFrame) -> pd.DataFrame:
    df["is_dual_type"] = df["type2"].notna().astype("Int64")
    df["type_pair"] = np.where(df["type2"].notna(),
                               df["type1"] + " / " + df["type2"].astype(str),
                               df["type1"])
    df["generation_name"] = df["generation"].map(GENERATION_LABELS)
    df["main_offense"] = np.select(
        [df["attack"] > df["sp_attack"], df["sp_attack"] > df["attack"]],
        ["physical", "special"], default="balanced")
    df["size_class"] = pd.cut(df["height_m"], bins=[0, 1, 2, 4, np.inf],
                              labels=["small", "medium", "large", "huge"],
                              right=False).astype(str)
    return df


# ------------------------------------------------------------------- changelog
def compare_frames(raw: pd.DataFrame, clean: pd.DataFrame) -> pd.DataFrame:
    """Cells that differ between the raw and the cleaned dataset."""
    raw = raw.set_index("pokedex_number")
    clean = clean.set_index("pokedex_number")
    raw.index = raw.index.astype(int)
    clean.index = clean.index.astype(int)
    shared = [c for c in raw.columns if c in clean.columns
              and c not in ("pokedex_number", "name")]
    records = []
    for col in shared:
        changed, examples = 0, []
        for dex in clean.index:
            old = raw.at[dex, col]
            new = clean.at[dex, col]
            old_empty = pd.isna(old) or old == ""
            new_empty = pd.isna(new) or new == ""
            if old_empty and new_empty:
                same = True
            elif old_empty or new_empty:
                same = False
            elif col in INT_COLUMNS + FLOAT_COLUMNS + AGAINST_COLUMNS:
                try:
                    same = abs(float(old) - float(new)) < 1e-9
                except (TypeError, ValueError):
                    same = str(old) == str(new)
            else:
                same = str(old) == str(new)
            if not same:
                changed += 1
                if len(examples) < 3:
                    old_show = "NULL" if old_empty else old
                    new_show = "NULL" if new_empty else new
                    examples.append(f"{clean.at[dex, 'name']} ({old_show} -> {new_show})")
        if changed:
            records.append({"column": col, "changed_cells": changed,
                            "of_total_pct": round(changed / len(clean) * 100, 1),
                            "examples": "; ".join(examples)})
    return pd.DataFrame(records).sort_values("changed_cells", ascending=False)


# ------------------------------------------------------------------ split tables
def split_tables(df: pd.DataFrame, chart: dict) -> dict[str, pd.DataFrame]:
    type_names = sorted(set(df["type1"]) | set(df["type2"].dropna()))
    type_id = {name: i + 1 for i, name in enumerate(type_names)}
    types = pd.DataFrame({"type_id": list(type_id.values()),
                          "type_name": list(type_id.keys())})

    generations = (df.groupby("generation")
                     .agg(dex_start=("pokedex_number", "min"),
                          dex_end=("pokedex_number", "max"),
                          pokemon_count=("pokedex_number", "count"))
                     .reset_index()
                     .rename(columns={"generation": "generation_id"}))
    generations["label"] = generations["generation_id"].map(GENERATION_LABELS)

    # abilities: names, slots and hidden flag come from the cached pokemon data
    pokemon_json = load_cached("pokemon", DEX_RANGE)
    ability_rows = []
    for dex in df["pokedex_number"]:
        for entry in sorted(pokemon_json[str(dex)]["abilities"],
                            key=lambda a: a["slot"]):
            ability_rows.append({"pokedex_number": int(dex),
                                 "ability_name": entry["ability"]["name"].replace("-", " ").title(),
                                 "slot": entry["slot"],
                                 "is_hidden": int(entry["is_hidden"])})
    ability_long = pd.DataFrame(ability_rows)
    abilities = (pd.DataFrame({"ability_name": sorted(ability_long.ability_name.unique())})
                 .reset_index(names="ability_id"))
    abilities["ability_id"] = abilities["ability_id"] + 1
    pokemon_abilities = (ability_long
                         .merge(abilities, on="ability_name")
                         [["pokedex_number", "ability_id", "slot", "is_hidden"]])

    pokemon = df[["pokedex_number", "name", "japanese_name",
                  "generation", "type1", "type2", "classification",
                  "height_m", "weight_kg", "percentage_male", "capture_rate",
                  "base_happiness", "base_egg_steps", "experience_growth",
                  "is_legendary", "is_dual_type", "type_pair",
                  "generation_name", "main_offense", "size_class"]].copy()
    pokemon = pokemon.rename(columns={"generation": "generation_id",
                                      "type1": "type1_id", "type2": "type2_id"})
    pokemon["type1_id"] = pokemon["type1_id"].map(type_id).astype("Int64")
    pokemon["type2_id"] = pokemon["type2_id"].map(type_id)
    pokemon = pokemon[["pokedex_number", "name", "japanese_name",
                       "generation_id", "type1_id", "type2_id",
                       "classification", "height_m", "weight_kg",
                       "percentage_male", "capture_rate", "base_happiness",
                       "base_egg_steps", "experience_growth", "is_legendary",
                       "is_dual_type", "type_pair", "generation_name",
                       "main_offense", "size_class"]]

    pokemon_stats = df[["pokedex_number", "hp", "attack", "defense",
                        "sp_attack", "sp_defense", "speed", "base_total"]].copy()

    matchups = pd.DataFrame(
        [{"attacking_type_id": type_id[a], "defending_type_id": type_id[d],
          "multiplier": chart[a].get(d, 1.0)}
         for a in type_names for d in type_names])

    defence = df.melt(id_vars="pokedex_number", value_vars=AGAINST_COLUMNS,
                      var_name="column", value_name="multiplier")
    column_to_type = {v: k for k, v in TYPE_TO_COLUMN.items()}
    defence["attacking_type_id"] = defence["column"].map(column_to_type).map(type_id)
    defence = defence[["pokedex_number", "attacking_type_id", "multiplier"]]

    return {"generations": generations, "types": types, "abilities": abilities,
            "pokemon": pokemon, "pokemon_stats": pokemon_stats,
            "pokemon_abilities": pokemon_abilities,
            "type_matchups": matchups, "pokemon_type_defense": defence}


# ----------------------------------------------------------------------- checks
def run_checks(df: pd.DataFrame, chart: dict) -> list[tuple[str, bool, str]]:
    checks = []

    def add(name, condition, detail):
        checks.append((name, bool(condition), detail))

    add("pokedex_number is unique and complete (1-1025)",
        sorted(df.pokedex_number) == list(DEX_RANGE),
        f"{df.pokedex_number.nunique()} distinct ids, {df.pokedex_number.min()}-{df.pokedex_number.max()}")
    add("name is unique", df.name.is_unique, f"{df.name.nunique()} names")
    add("no duplicate type2 == type1",
        not (df.type2.notna() & (df.type1 == df.type2)).any(),
        f"{(df.type2.notna() & (df.type1 == df.type2)).sum()} rows")

    mism = 0
    for row in df.itertuples():
        types = [row.type1] + ([row.type2] if isinstance(row.type2, str) else [])
        for atk, col in TYPE_TO_COLUMN.items():
            expected = 1.0
            for d in types:
                expected *= chart[atk].get(d, 1.0)
            if abs(float(getattr(row, col)) - expected) > 1e-9:
                mism += 1
    add("all against_* cells match the type chart", mism == 0,
        f"{mism} mismatching cells of {len(df) * 18}")

    stats_sum = df[["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]].sum(axis=1)
    add("base_total equals the sum of the six stats",
        bool((stats_sum == df.base_total).all()), f"{int((stats_sum != df.base_total).sum())} rows differ")

    bad_ratio = df[df.percentage_male.notna() & ~df.percentage_male.isin(STANDARD_RATIOS)]
    add("percentage_male uses standard game ratios", bad_ratio.empty,
        f"{len(bad_ratio)} non-standard rows")

    add("capture_rate is a whole number everywhere",
        bool(df.capture_rate.notna().all() and (df.capture_rate % 1 == 0).all()),
        f"{int(df.capture_rate.isna().sum())} missing / non-integer values")

    nulls = df.isna().sum()
    unexpected = {c: int(n) for c, n in nulls.items()
                  if n and c not in ("type2", "percentage_male")}
    add("no unexpected missing values", not unexpected,
        f"blank type2: {int(nulls.type2)}, blank percentage_male: {int(nulls.percentage_male)}, "
        f"other: {unexpected or 'none'}")
    return checks


# ------------------------------------------------------------------------- main
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-fetch", action="store_true",
                        help="do not fetch missing base-form data from the API")
    args = parser.parse_args()

    if not args.skip_fetch:
        missing = [d for d in BASE_DEX_RANGE
                   if not (RAW_DIR / f"pokemon_{d:04d}.json").exists()]
        if missing:
            print(f"fetching {len(missing)} base forms from PokeAPI...")
            fetch_pokemon_ids(BASE_DEX_RANGE)

    raw = pd.read_csv(FULL_CSV, dtype=str, keep_default_na=False)
    print(f"raw extended dataset : {raw.shape[0]} rows x {raw.shape[1]} columns")

    clean = add_calculated_columns(coerce_dtypes(build_api_rows()))
    chart = build_type_chart(load_cached_types())
    print(f"cleaned dataset      : {clean.shape[0]} rows x {clean.shape[1]} columns")

    # --- flat output ----------------------------------------------------------
    CLEAN_CSV.parent.mkdir(parents=True, exist_ok=True)
    clean.to_csv(CLEAN_CSV, index=False)
    print(f"wrote {CLEAN_CSV.relative_to(ROOT)}")

    # --- split outputs --------------------------------------------------------
    tables = split_tables(clean, chart)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    print("split tables:")
    for name, frame in tables.items():
        frame.to_csv(CLEAN_DIR / f"{name}.csv", index=False)
        print(f"  datasets/clean/{name}.csv: {frame.shape[0]} rows x {frame.shape[1]} columns")

    # --- checks ---------------------------------------------------------------
    checks = run_checks(clean, chart)
    print("\ncleaning checks:")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} ({detail})")

    # --- changelog ------------------------------------------------------------
    diff = compare_frames(raw, clean)
    CHANGELOG.parent.mkdir(parents=True, exist_ok=True)
    write_changelog(diff, checks, tables, raw, clean)
    print(f"\nwrote {CHANGELOG.relative_to(ROOT)} ({diff.changed_cells.sum()} changed cells)")


def write_changelog(diff, checks, tables, raw, clean) -> None:
    lines = [
        "# Cleaning changelog (Phase 3)",
        "",
        f"Raw extended dataset: **{raw.shape[0]} rows x {raw.shape[1]} columns**  ",
        f"Cleaned dataset: **{clean.shape[0]} rows x {clean.shape[1]} columns**",
        "",
        "## Transformations performed",
        "",
        "1. **Base-form reconciliation** - every dex entry was rebuilt from the",
        "   cached PokeAPI base form. The original file had mega/regional-form",
        "   values merged into gen 1-7 base rows (e.g. Charizard `base_total`",
        "   634 = Mega Charizard, Alolan typings on Rattata/Meowth/Vulpix).",
        "   Why: one row per Pokédex entry with internally consistent",
        "   stats/types/size is required before analysis and loading.",
        "2. **Type consistency** - `type2` values identical to `type1` were",
        "   dropped and all 18 `against_*` columns recomputed from the official",
        "   type chart (dual types multiply). Why: the raw cells contradicted",
        "   the declared typing for 16 Pokémon.",
        "3. **Numeric standardisation** - `capture_rate` forced to an integer",
        "   (Minior stored `30 (Meteorite)255 (Core)`), `percentage_male`",
        "   converted to the game's real ratios (88.1 -> 87.5, 75.4 -> 75,",
        "   24.6 -> 25, 11.2 -> 12.5).",
        "4. **Text standardisation** - ability names taken from the official",
        "   ability index (`Compoundeyes` -> `Compound Eyes`),",
        "   `classfication` renamed to `classification`.",
        "5. **Calculated columns** - `is_dual_type`, `type_pair`,",
        "   `generation_name`, `main_offense` (physical/special/balanced),",
        "   `size_class` (height buckets).",
        "6. **Split into relational DataFrames** - dimension and fact tables",
        "   written to `datasets/clean/` for the Phase 5/6 database load.",
        "",
        "## Cells changed vs the raw dataset",
        "",
        "| column | changed cells | % of rows | examples |",
        "|---|---|---|---|",
    ]
    for row in diff.itertuples():
        lines.append(f"| `{row.column}` | {row.changed_cells} | {row.of_total_pct}% | {row.examples} |")
    lines += ["", "## Split tables", "",
              "| table | rows | columns |", "|---|---|---|"]
    for name, frame in tables.items():
        lines.append(f"| `{name}` | {frame.shape[0]} | {frame.shape[1]} |")
    lines += ["", "## Cleaning checks", ""]
    for name, ok, detail in checks:
        lines.append(f"- {'PASS' if ok else 'FAIL'} - {name} ({detail})")
    lines += ["",
              "## Notes / retained decisions",
              "",
              "* `type2` stays NULL for single-type Pokémon and `percentage_male`",
              "  stays NULL for genderless Pokémon - these are structural, not defects.",
              "* `is_legendary` keeps the original file's convention of flagging",
              "  mythicals (Mew, Deoxys, ...) and the Ultra Beasts (Nihilego ...",
              "  Guzzlord) together with legendaries - PokeAPI reports",
              "  `is_legendary = false` for both groups, which is why they are",
              "  listed explicitly in `scripts/build_dataset.py`.",
              "* Outliers (Wailord's size, Blissey's HP, ...) were kept: they are",
              "  true values, not errors.",
              ""]
    CHANGELOG.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
