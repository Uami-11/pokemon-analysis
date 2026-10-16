"""Phase 6 - load the cleaned tables into PostgreSQL.

Reads the split CSVs produced by `scripts/clean_dataset.py` and loads them into
the `pokemon` schema created by `sql/schema.sql`. The load is idempotent: every
table is truncated first, then re-populated in foreign-key order.

    python scripts/load_database.py             # load into existing schema
    python scripts/load_database.py --recreate  # re-run schema.sql first

Connection string comes from $POKEMON_DB_URL, defaulting to the local socket:
    postgresql+psycopg2:///pokemon_analysis
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
CLEAN_DIR = ROOT / "datasets" / "clean"
SCHEMA_SQL = ROOT / "sql" / "schema.sql"

DEFAULT_URL = "postgresql+psycopg2:///pokemon_analysis"
SCHEMA = "pokemon"

# (csv_stem, table, columns, bool_cols, nullable_int_cols) in FK-safe load order.
TABLES = [
    ("generations", "generations",
     ["generation_id", "label", "dex_start", "dex_end", "pokemon_count"], (), ()),
    ("types", "types", ["type_id", "type_name"], (), ()),
    ("abilities", "abilities", ["ability_id", "ability_name"], (), ()),
    ("pokemon", "pokemon",
     ["pokedex_number", "name", "japanese_name", "generation_id", "type1_id",
      "type2_id", "classification", "height_m", "weight_kg", "percentage_male",
      "capture_rate", "base_happiness", "base_egg_steps", "experience_growth",
      "is_legendary"],
     ("is_legendary",), ("type2_id",)),
    ("pokemon_stats", "pokemon_stats",
     ["pokedex_number", "hp", "attack", "defense", "sp_attack", "sp_defense",
      "speed", "base_total"], (), ()),
    ("pokemon_abilities", "pokemon_abilities",
     ["pokedex_number", "ability_id", "slot", "is_hidden"], ("is_hidden",), ()),
    ("type_matchups", "type_matchups",
     ["attacking_type_id", "defending_type_id", "multiplier"], (), ()),
]


def read_table(stem: str, columns: list[str], bool_cols, nullable_int_cols) -> pd.DataFrame:
    path = CLEAN_DIR / f"{stem}.csv"
    df = pd.read_csv(path)[columns]
    for col in bool_cols:
        df[col] = df[col].astype(bool)
    for col in nullable_int_cols:
        df[col] = df[col].map(lambda v: None if pd.isna(v) else int(v))
    return df


def get_engine(url: str):
    return create_engine(url)


def recreate_schema(engine) -> None:
    dbname = engine.url.database
    print(f"recreating schema from {SCHEMA_SQL.relative_to(ROOT)} ...")
    subprocess.run(
        ["psql", "-d", dbname, "-v", "ON_ERROR_STOP=1", "-q", "-f", str(SCHEMA_SQL)],
        check=True,
    )


def truncate_all(engine) -> None:
    targets = ", ".join(f"{SCHEMA}.{t[1]}" for t in TABLES)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {targets} RESTART IDENTITY CASCADE"))


def load(engine) -> dict[str, int]:
    frames = {}
    for stem, table, cols, bools, nints in TABLES:
        frames[table] = read_table(stem, cols, bools, nints)

    loaded = {}
    with engine.begin() as conn:
        conn.execute(text(f"SET search_path TO {SCHEMA}, public"))
    for _, table, _, _, _ in TABLES:
        df = frames[table]
        df.to_sql(table, engine, schema=SCHEMA, if_exists="append",
                  index=False, method="multi", chunksize=500)
        loaded[table] = len(df)
        print(f"  loaded {table:18s} {len(df):>6d} rows")
    return loaded


def verify(engine) -> bool:
    checks = {
        "generations": 9, "types": 18, "abilities": 284, "pokemon": 1025,
        "pokemon_stats": 1025, "pokemon_abilities": 2411, "type_matchups": 324,
    }
    ok = True
    print("\nverification:")
    with engine.connect() as conn:
        for table, expected in checks.items():
            got = conn.execute(text(f"SELECT count(*) FROM {SCHEMA}.{table}")).scalar_one()
            flag = "ok " if got == expected else "BAD"
            ok &= got == expected
            print(f"  [{flag}] {table:18s} {got:>6d} (expected {expected})")

        # views
        prof = conn.execute(text(f"SELECT count(*) FROM {SCHEMA}.v_pokemon_profile")).scalar_one()
        defn = conn.execute(text(f"SELECT count(*) FROM {SCHEMA}.v_pokemon_type_defense")).scalar_one()
        print(f"  [{'ok ' if prof == 1025 else 'BAD'}] v_pokemon_profile  {prof:>6d} (expected 1025)")
        print(f"  [{'ok ' if defn == 18450 else 'BAD'}] v_pokemon_type_defense {defn:>6d} (expected 18450)")
        ok &= prof == 1025 and defn == 18450

        # spot checks against the flat analysis source
        clean = pd.read_csv(ROOT / "datasets" / "pokemon_clean.csv")
        row = conn.execute(text(
            f"SELECT name, base_total, type_pair, main_offense, size_class "
            f"FROM {SCHEMA}.v_pokemon_profile WHERE pokedex_number = 9")).one()
        print(f"  sample  v_pokemon_profile #9 = {tuple(row)}")
        tot = conn.execute(text(f"SELECT sum(base_total) FROM {SCHEMA}.pokemon_stats")).scalar_one()
        print(f"  [{'ok ' if tot == int(clean.base_total.sum()) else 'BAD'}] "
              f"sum(base_total) = {tot} (expected {int(clean.base_total.sum())})")
        ok &= tot == int(clean.base_total.sum())
        dual = conn.execute(text(
            f"SELECT count(*) FROM {SCHEMA}.v_pokemon_profile WHERE is_dual_type")).scalar_one()
        exp_dual = int(clean.is_dual_type.sum())
        print(f"  [{'ok ' if dual == exp_dual else 'BAD'}] dual types = {dual} (expected {exp_dual})")
        ok &= dual == exp_dual
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recreate", action="store_true",
                        help="re-run sql/schema.sql before loading")
    parser.add_argument("--url", default=os.environ.get("POKEMON_DB_URL", DEFAULT_URL))
    args = parser.parse_args()

    engine = get_engine(args.url)
    print(f"target: {engine.url.render_as_string(hide_password=False)}")

    if args.recreate:
        recreate_schema(engine)

    print("truncating tables ...")
    truncate_all(engine)

    print("loading:")
    load(engine)

    ok = verify(engine)
    print("\nLOAD OK" if ok else "\nLOAD COMPLETED WITH MISMATCHES")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
