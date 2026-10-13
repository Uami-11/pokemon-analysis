"""Phase 4 - analysis questions and metrics.

Turns the cleaned dataset (``datasets/pokemon_clean.csv``) and the relational
tables in ``datasets/clean/`` into the tidy results behind each analysis
question. The notebook ``notebooks/03_analysis.ipynb`` imports these functions
and presents them; this module can also be run directly to print a digest.

Questions
    A1  best type offensively / defensively
    A2  best and worst type combinations defensively
    A3  is dual-typing a net win?
    B1  power creep across generations
    B2  stat budget allocation (offense / bulk / speed)
    BM  min-maxing (how concentrated the stat spread is)
    B3  power creep without legendary Pokemon
    C1  speed vs power trade-off (glass cannons and tanks)
    D1  do rarer / slower-growing Pokemon hit harder?
    D2  size of the legendary gap, per stat
    D3  does size predict power?
    E2  most shared abilities

Run:
    python scripts/analysis.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clean_dataset import AGAINST_COLUMNS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CLEAN_CSV = ROOT / "datasets" / "pokemon_clean.csv"
CLEAN_DIR = ROOT / "datasets" / "clean"

STATS = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]


# ------------------------------------------------------------------- loading
def load_clean() -> pd.DataFrame:
    return pd.read_csv(CLEAN_CSV)


def load_type_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(type_matchups, types) from the split tables."""
    return (pd.read_csv(CLEAN_DIR / "type_matchups.csv"),
            pd.read_csv(CLEAN_DIR / "types.csv"))


def load_ability_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    return (pd.read_csv(CLEAN_DIR / "pokemon_abilities.csv"),
            pd.read_csv(CLEAN_DIR / "abilities.csv"))


# ----------------------------------------------------- shared derived metrics
def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Offense / bulk / speed scores and the min-max spread index."""
    df = df.copy()
    df["offense"] = df["attack"] + df["sp_attack"]
    df["bulk"] = df["hp"] + df["defense"] + df["sp_defense"]
    df["defensive_score"] = df[AGAINST_COLUMNS].mean(axis=1)
    df["weaknesses"] = (df[AGAINST_COLUMNS] > 1).sum(axis=1)
    df["resistances"] = (df[AGAINST_COLUMNS] < 1).sum(axis=1)
    df["immunities"] = (df[AGAINST_COLUMNS] == 0).sum(axis=1)
    # min-maxing: how unevenly the six stats share the base_total budget
    df["spread"] = df[STATS].std(axis=1, ddof=0) / df[STATS].mean(axis=1)
    df["typing"] = np.where(df["is_dual_type"] == 1, "dual", "single")
    df["power"] = df[["attack", "sp_attack"]].max(axis=1)
    return df


# --------------------------------------------------------------------- A1
def type_scores(matchups: pd.DataFrame, types: pd.DataFrame) -> pd.DataFrame:
    """Offensive and defensive rating of each single type (from the chart)."""
    atk = types.rename(columns={"type_id": "attacking_type_id",
                                "type_name": "attacking"})
    dfn = types.rename(columns={"type_id": "defending_type_id",
                                "type_name": "defending"})
    m = matchups.merge(atk, on="attacking_type_id").merge(dfn, on="defending_type_id")
    offense = m.groupby("attacking")["multiplier"].agg(
        offense_score="mean",
        strong_against=lambda s: int((s > 1).sum()),
        weak_against=lambda s: int((s < 1).sum()),
        no_effect=lambda s: int((s == 0).sum()),
    )
    defense = m.groupby("defending")["multiplier"].agg(
        defense_score="mean",
        weaknesses=lambda s: int((s > 1).sum()),
        resistances=lambda s: int((s < 1).sum()),
        immunities=lambda s: int((s == 0).sum()),
    )
    out = offense.join(defense)
    out.index.name = "type"
    return out.reset_index().sort_values("offense_score", ascending=False)


# --------------------------------------------------------------------- A2 / A3
def combo_scores(df: pd.DataFrame, min_members: int = 5) -> pd.DataFrame:
    """Defensive profile of each type combination (needs enough members)."""
    g = (df.groupby("type_pair")
           .agg(members=("name", "count"),
                defensive_score=("defensive_score", "mean"),
                weaknesses=("weaknesses", "mean"),
                resistances=("resistances", "mean"),
                immunities=("immunities", "mean"))
           .reset_index())
    return g[g.members >= min_members].sort_values("defensive_score")


def dual_tradeoff(df: pd.DataFrame) -> pd.DataFrame:
    return (df.groupby("typing")
              .agg(pokemon=("name", "count"),
                   mean_base_total=("base_total", "mean"),
                   median_base_total=("base_total", "median"),
                   mean_weaknesses=("weaknesses", "mean"),
                   mean_resistances=("resistances", "mean"),
                   mean_immunities=("immunities", "mean"),
                   mean_defensive_score=("defensive_score", "mean"))
              .round(2))


# --------------------------------------------------------------------- B1 / B3
def generation_power(df: pd.DataFrame) -> pd.DataFrame:
    return (df.groupby("generation")
              .agg(pokemon=("name", "count"),
                   mean_base_total=("base_total", "mean"),
                   median_base_total=("base_total", "median"))
              .round(1))


# --------------------------------------------------------------------- B2
def budget_allocation(df: pd.DataFrame) -> pd.DataFrame:
    """Share (%) of the mean base_total going to offense / bulk / speed."""
    d = df.copy()
    d["offense_share"] = d["offense"] / d["base_total"] * 100
    d["bulk_share"] = d["bulk"] / d["base_total"] * 100
    d["speed_share"] = d["speed"] / d["base_total"] * 100
    return d.groupby("generation")[
        ["offense_share", "bulk_share", "speed_share"]].mean().round(1)


# --------------------------------------------------------------------- BM
def spread_by(df: pd.DataFrame, column: str) -> pd.DataFrame:
    return (df.groupby(column, as_index=False)
              .agg(pokemon=("name", "count"), mean_spread=("spread", "mean"))
              .round(3)
              .sort_values("mean_spread", ascending=False))


def spread_legendary(df: pd.DataFrame) -> pd.DataFrame:
    out = (df.groupby("is_legendary")
             .agg(pokemon=("name", "count"), mean_spread=("spread", "mean"),
                  mean_base_total=("base_total", "mean"))
             .round(3))
    out.index = ["non-legendary", "legendary"]
    return out


# --------------------------------------------------------------------- C1
def speed_power(df: pd.DataFrame) -> dict:
    return {
        "corr_speed_power": df["speed"].corr(df["power"]),
        "corr_speed_attack": df["speed"].corr(df["attack"]),
        "corr_speed_sp_attack": df["speed"].corr(df["sp_attack"]),
        "corr_speed_bulk": df["speed"].corr(df["bulk"]),
        "corr_speed_total": df["speed"].corr(df["base_total"]),
    }


def archetypes(df: pd.DataFrame, n: int = 6) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Extreme glass cannons (offense >> bulk) and tanks (bulk >> offense)."""
    d = df.copy()
    d["gap"] = d["offense"] - d["bulk"]
    cols = ["name", "type_pair", "hp", "attack", "sp_attack", "defense",
            "sp_defense", "speed", "offense", "bulk", "base_total", "gap"]
    cannons = (d[d.base_total >= d.base_total.median()]
               .nlargest(n, "gap")[cols].round(0))
    tanks = (d[d.base_total >= d.base_total.median()]
             .nsmallest(n, "gap")[cols].round(0))
    return cannons, tanks


# --------------------------------------------------------------------- D1
def spearman(a: pd.Series, b: pd.Series) -> float:
    """Spearman correlation as Pearson-on-ranks (avoids a scipy dependency)."""
    return a.rank().corr(b.rank())


def rarity_power(df: pd.DataFrame) -> pd.DataFrame:
    metrics = [("capture_rate", "capture_rate (lower = rarer)"),
               ("base_egg_steps", "base_egg_steps (higher = longer breeding)"),
               ("experience_growth", "experience_growth (higher = slower levelling)")]
    rows = [{"metric": label,
             "pearson": round(df[col].corr(df["base_total"]), 3),
             "spearman": round(spearman(df[col], df["base_total"]), 3)}
            for col, label in metrics]
    return pd.DataFrame(rows)


# --------------------------------------------------------------------- D2
def legendary_gap(df: pd.DataFrame) -> pd.DataFrame:
    cols = STATS + ["base_total"]
    out = df.groupby("is_legendary")[cols].mean().T
    out.columns = ["non_legendary", "legendary"]
    out["delta"] = out["legendary"] - out["non_legendary"]
    out["pct"] = (out["delta"] / out["non_legendary"] * 100).round(1)
    return out.round(1)


# --------------------------------------------------------------------- D3
def size_power(df: pd.DataFrame) -> pd.Series:
    log_weight = np.log10(df["weight_kg"].replace(0, np.nan))
    return pd.Series({
        "height_m vs base_total": round(df["height_m"].corr(df["base_total"]), 3),
        "weight_kg vs base_total": round(df["weight_kg"].corr(df["base_total"]), 3),
        "log10(weight) vs base_total": round(log_weight.corr(df["base_total"]), 3),
        "spearman(weight)": round(spearman(df["weight_kg"], df["base_total"]), 3),
    })


# --------------------------------------------------------------------- E2
def ability_frequency(pokemon_abilities: pd.DataFrame,
                      abilities: pd.DataFrame) -> pd.DataFrame:
    m = pokemon_abilities.merge(abilities, on="ability_id")
    return (m.groupby("ability_name")
             .agg(pokemon=("pokedex_number", "nunique"),
                  as_hidden=("is_hidden", "sum"))
             .reset_index()
             .sort_values("pokemon", ascending=False)
             .reset_index(drop=True))


# --------------------------------------------------------------------- digest
def main() -> None:
    df = add_derived(load_clean())
    matchups, types = load_type_data()
    pa, ab = load_ability_data()

    print("=" * 78)
    print("A1  type ratings (offense_score high = good, defense_score low = good)")
    print(type_scores(matchups, types).to_string(index=False))

    print("\nA2  best / worst type combinations defensively (>=5 members)")
    combos = combo_scores(df)
    print("\nbest:\n", combos.head(6).round(3).to_string(index=False))
    print("\nworst:\n", combos.tail(6).round(3).to_string(index=False))

    print("\nA3  dual vs single")
    print(dual_tradeoff(df))

    print("\nB1  power by generation")
    print(generation_power(df))
    print("\nB3  power by generation (non-legendary only)")
    print(generation_power(df[df.is_legendary == 0]))

    print("\nB2  stat budget allocation (% of base_total)")
    print(budget_allocation(df))

    print("\nBM  min-maxing spread index by generation")
    print(spread_by(df, "generation").sort_values("generation").to_string(index=False))
    print("\nBM  spread: legendary vs not")
    print(spread_legendary(df))
    print("\nBM  spread by type (top/bottom 5)")
    st = spread_by(df, "type_pair")
    print(st[st.pokemon >= 5].head(5).to_string(index=False))
    print(st[st.pokemon >= 5].tail(5).to_string(index=False))

    print("\nC1  speed vs power correlations")
    for k, v in speed_power(df).items():
        print(f"   {k:22s} {v:+.3f}")
    cannons, tanks = archetypes(df)
    print("\n   glass cannons:\n", cannons.to_string(index=False))
    print("\n   tanks:\n", tanks.to_string(index=False))

    print("\nD1  rarity / growth vs base_total")
    print(rarity_power(df).to_string(index=False))

    print("\nD2  legendary gap per stat")
    print(legendary_gap(df))

    print("\nD3  size vs power")
    print(size_power(df).to_string())

    print("\nE2  most shared abilities")
    print(ability_frequency(pa, ab).head(15).to_string(index=False))
    print(f"\n   distinct abilities  : {ab.ability_name.nunique()}")
    print(f"   pokemon-ability rows: {len(pa)}")


if __name__ == "__main__":
    main()
