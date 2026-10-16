# Pokémon Data Analysis — Project Report

**Domain:** Data engineering / analytics on the National Pokédex (generations I–IX)
**Stack:** Python (pandas, SQLAlchemy), PostgreSQL 18, SQL, Jupyter
**Scope:** 1,025 Pokémon, 18 types, 284 abilities

---

## Abstract

This project builds an end-to-end ETL and analysis pipeline over a Pokémon
dataset. Starting from a 801-row generation I–VII CSV, it augments the data with
generations VIII–IX from [PokéAPI](https://pokeapi.co), cleans and validates it,
performs exploratory analysis, models it as a normalised PostgreSQL database,
and answers a set of analytical and reporting questions in SQL and pandas.

Headline findings: **Steel** is the strongest defensive type and **Ice** the
weakest; **dual typing** buys ~48 base-stat points at the cost of ~1.3 extra
weaknesses; **power creep is real** (mean base total 408 → 457 from Gen I to IX)
but the *allocation* of stats is stable; and **legendaries are less min-maxed
than the average Pokémon**, winning mostly on speed and special attack.

---

## 1. Objectives

1. Extract a raw dataset and extend it to the full 1,025-entry Pokédex (gens I–IX).
2. Explore the data and document quality issues (EDA).
3. Clean and transform it, keeping a full audit trail.
4. Answer ≥5 analytical questions and produce ≥5 data-driven insights.
5. Design a relational database with primary/foreign keys, constraints and an ERD.
6. Load the cleaned data into PostgreSQL.
7. Deliver ≥8 SQL reports and a reproducible pipeline.

---

## 2. Dataset

| Item | Detail |
|---|---|
| Source (base) | `datasets/pokemon.csv` — 801 rows, generations I–VII |
| Source (extension) | PokéAPI `pokemon` + `pokemon-species` + `type` + `growth-rate` endpoints |
| Raw cache | `datasets/raw/*.json` (2,075 files, gitignored) |
| Extended raw | `datasets/pokemon_full.csv` — 1,025 × 41 |
| Cleaned | `datasets/pokemon_clean.csv` — 1,025 × 46 |
| Split tables | `datasets/clean/*.csv` — 7 files (one per database table) |

Generation VIII–IX rows were fetched from PokéAPI and all 1,025 entries were
rebuilt from base forms so the schema is consistent (no Mega/Alolan variants).
`is_legendary` follows the dataset convention: `species.is_legendary OR
is_mythical OR` one of the seven Ultra Beasts — **101 legendary rows**.

---

## 3. Methodology

The work follows seven phases; every phase has a script and most have a notebook.

| Phase | Task | Artefact |
|---|---|---|
| 1 | Extract / extend dataset | `scripts/fetch_pokeapi.py`, `scripts/build_dataset.py` |
| 2 | Exploratory data analysis | `notebooks/01_eda.ipynb` |
| 3 | Clean & transform | `scripts/clean_dataset.py`, `notebooks/02_cleaning.ipynb`, `reports/cleaning_changelog.md` |
| 4 | Analysis | `scripts/analysis.py`, `notebooks/03_analysis.ipynb`, `reports/insights.md` |
| 5 | Schema + ERD | `sql/schema.sql`, `docs/erd.md`, `docs/erd.png` |
| 6 | Load | `scripts/load_database.py`, `notebooks/04_load_and_reports.ipynb` |
| 7 | SQL reports + report | `sql/reports.sql`, `scripts/run_reports.py`, `reports/sql_reports.md`, this document |

The whole pipeline is reproducible with a single command:

```bash
python scripts/run_pipeline.py            # fetch → build → clean → load → reports
python scripts/run_pipeline.py --skip-fetch   # reuse cached JSON
```

### Cleaning (Phase 3)

`scripts/clean_dataset.py` applied 687 corrections and passed 8 automated
checks. Notable fixes: renamed the typo column `classfication` →
`classification`, filled missing `height_m`/`weight_kg` from the API, normalised
type names, and derived the split tables. Two columns are legitimately missing
and preserved as `NULL`: `type2` (499 single-type Pokémon) and `percentage_male`
(155 genderless Pokémon).

---

## 4. Database design (Phase 5)

Schema **`pokemon`** in database `pokemon_analysis` — 7 tables + 2 views.

```
generations ──1:N──▶ pokemon ◀──N:1── types   (type1 / type2)
                       │  ▲
              1:1      │  │ N:M
                       ▼  │
              pokemon_stats  pokemon_abilities ──N:1── abilities
                       types ◀──N:M──▶ types   (type_matchups, self-referencing)
```

* **`generations`, `types`, `abilities`** — lookup tables.
* **`pokemon`** — one row per Pokédex entry (15 base attributes).
* **`pokemon_stats`** — base stats as a **1:1** child (shared primary key).
* **`pokemon_abilities`** — **N:M** junction (`slot`, `is_hidden`).
* **`type_matchups`** — self-referencing **N:M** on `types` (18×18 chart).
* Views **`v_pokemon_profile`** (flat, analysis-ready) and
  **`v_pokemon_type_defense`** (1,025 × 18 incoming multipliers computed from
  both types).

Full diagram: [`docs/erd.md`](erd.md) (Mermaid) and [`docs/erd.png`](erd.png).

**Integrity rules enforced in the DDL** (all verified with failing test inserts):
`type2_id IS DISTINCT FROM type1_id`; `base_total = sum(stats)`;
`is_hidden = (slot = 3)`; `multiplier IN (0,0.5,1,2)`; `UNIQUE (pokedex_number,
ability_id)`; plus PK/FK/NOT NULL on every table.

### Phase 6 load verification

| table | rows |
|---|---|
| generations | 9 |
| types | 18 |
| abilities | 284 |
| pokemon / pokemon_stats | 1,025 / 1,025 |
| pokemon_abilities | 2,411 |
| type_matchups | 324 |
| v_pokemon_profile | 1,025 |
| v_pokemon_type_defense | 18,450 |

The loader is idempotent (truncate + reload) and cross-checks `sum(base_total)`
and the dual-type count against the source CSV.

---

## 5. SQL reports (Phase 7)

Twelve reports in `sql/reports.sql`, generated into
[`reports/sql_reports.md`](../reports/sql_reports.md) by `scripts/run_reports.py`.

| # | Report | Headline result |
|---|---|---|
| R1 | Roster & legendary share per generation | 9 generations, 151 → 120 species; Gen VII has the most legendaries (23) |
| R2 | Top 10 by base stat total | Arceus 720; then Eternatus 690, Mewtwo/Lugia/… 680 |
| R3 | Power creep per generation (CTE + windows) | Gen I 407.6 → Gen IX 457.4 (**+49.8**) |
| R4 | Legendary vs regular profile | legendary **590.4** vs regular **409.9** avg base total |
| R5 | Offensive type power (view + FILTER) | Rock 1.231 and Ice 1.204 are the best attacking types |
| R6 | Type combos with most weaknesses | `normal / flying` (many), `bug / flying`; Steel-stacking resists best |
| R7 | Most common abilities (N:M + rank) | **Swift Swim** (44), Sturdy (42), Keen Eye (39) |
| R8 | "Glass cannons" (offense − bulk) | Deoxys, Pheromosa, Blacephalon |
| R9 | Hardest-to-catch strong Pokémon | capture_rate 3: Arceus, Dialga, Giratina, … |
| R10 | Primary type distribution | **water 13.1%**, normal 11.5%, grass 10.0% |
| R11 | Most common type combos | `normal`, `water`, `grass` (single types) lead |
| R12 | Dual vs single average profile | dual **451** vs single **403** base total |

The queries exercise joins, `GROUP BY`, aggregates with `FILTER`, CTEs, window
functions (`rank`, `first_value`, `sum OVER`) and both reporting views.

---

## 6. Analysis insights (Phase 4)

Full write-up in [`reports/insights.md`](../reports/insights.md); 13 questions
were answered. The eleven consolidated insights:

1. **Steel is the best defensive type, Ice the worst** — defensive score 0.833 vs 1.194.
2. **Best type combos stack Steel** (`bug/steel` 0.875); worst share weaknesses (`bug/grass` 1.389).
3. **Dual typing trades ~+48 base total for ~+1.3 extra weaknesses** (no free lunch).
4. **Power creep is real and not only legendaries** — 408 → 457 overall, 401 → 445 excluding legendaries.
5. **Stat-budget allocation is unchanged** across generations (~34% offense / ~50% bulk / ~16% speed).
6. **Legendaries are less min-maxed than average** (spread 0.225 vs 0.278).
7. **There is no speed-vs-power trade-off** — `corr(speed, power) = +0.43`.
8. **Rarity predicts power** — `capture_rate` vs `base_total` `r = −0.73`.
9. **Legendaries are fast special attackers** — biggest deltas in sp. attack (+56%) and speed (+47%).
10. **Size is a genuine power proxy** — weight vs base total Spearman `r = 0.65`.
11. **Ability slots are heavily reused** — Swift Swim on 44 Pokémon; 856 of 2,411 assignments are hidden.

---

## 7. Limitations

* The extension relies on PokéAPI's current values; historical/base-form stats
  are used, so battle-mechanic minutiae (Mega forms, in-battle transformations)
  are out of scope.
* `is_legendary` mixes legendaries, mythicals and Ultra Beasts by design.
* Type-effectiveness uses the modern (Gen VI+) chart; pre-Gen VI differences
  (e.g. Steel/Ghost resistances) are ignored.
* Correlations are descriptive, not causal.

---

## 8. Reproducing the project

```bash
# prerequisites: Python venv with pandas, sqlalchemy, psycopg2-binary, matplotlib, jupyter
createdb pokemon_analysis                     # role must have CREATEDB

python scripts/run_pipeline.py --skip-fetch   # build → clean → schema+load → reports
# or run phases individually
python scripts/build_dataset.py
python scripts/clean_dataset.py
psql -d pokemon_analysis -f sql/schema.sql
python scripts/load_database.py
python scripts/run_reports.py
python scripts/build_erd.py
```

Notebooks are executed with `jupyter` (or `nbclient`); each is self-contained
and reads/writes the artefacts listed in §3.

---

## 9. Repository layout

```
pokemon-analysis/
├── datasets/
│   ├── pokemon.csv              # original raw source (never modified)
│   ├── pokemon_full.csv         # extended raw (1025 × 41)
│   ├── pokemon_clean.csv        # cleaned master (1025 × 46)
│   ├── clean/                   # 7 split tables for the database
│   └── raw/                     # cached PokeAPI JSON (gitignored)
├── scripts/
│   ├── fetch_pokeapi.py         # Phase 1 extract
│   ├── build_dataset.py         # Phase 1 build
│   ├── clean_dataset.py         # Phase 3 clean/transform
│   ├── analysis.py              # Phase 4 metrics
│   ├── build_erd.py             # Phase 5 ERD render
│   ├── load_database.py         # Phase 6 load
│   ├── run_reports.py           # Phase 7 SQL reports
│   └── run_pipeline.py          # end-to-end orchestration
├── notebooks/
│   ├── 01_eda.ipynb             # Phase 2
│   ├── 02_cleaning.ipynb        # Phase 3
│   ├── 03_analysis.ipynb        # Phase 4
│   └── 04_load_and_reports.ipynb# Phases 6–7
├── sql/
│   ├── schema.sql               # DDL (tables, views, constraints)
│   └── reports.sql              # 12 reports
├── docs/
│   ├── erd.md                   # Mermaid ERD
│   ├── erd.png                  # rendered ERD
│   └── report.md                # this report
└── reports/
    ├── cleaning_changelog.md    # Phase 3 audit trail
    ├── insights.md              # Phase 4 insights
    └── sql_reports.md           # Phase 7 output
```
