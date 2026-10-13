# Analysis insights (Phase 4)

Derived from `datasets/pokemon_clean.csv` (1025 Pokémon, generations I–IX) using
`scripts/analysis.py`. Reproduced in `notebooks/03_analysis.ipynb`.

## Metrics

| Metric | Definition |
|---|---|
| offense | `attack + sp_attack` |
| bulk | `hp + defense + sp_defense` |
| power | `max(attack, sp_attack)` |
| defensive score | mean of the 18 incoming `against_*` multipliers (lower = better) |
| type offense / defense score | mean multiplier across the 18×18 chart |
| spread (min-maxing index) | `std(6 stats) / mean(6 stats)` — higher = more specialised |

## Question results

### A1 — Best type offensively / defensively
* Best offense: **Ground** (1.167), then Rock (1.139), Fire/Ice (1.111).
* Worst offense: **Normal** (0.889, strong against nothing) and Poison (0.944).
* Best defense: **Steel** (0.833 — 11 resistances + 1 immunity).
* Worst defense: **Ice** (1.194 — 4 weaknesses, 1 resistance) and Grass/Rock (1.167).

### A2 — Best / worst type combinations (≥5 members)
* Best: `steel` (0.833), `bug/steel` (0.875), `steel/psychic` (0.903).
* Worst: `bug/grass` (1.389), `rock/ground` (1.347), `grass/dragon` (1.292).
* Pattern: stacking Steel's resistances helps; overlapping weaknesses hurt.

### A3 — Is dual-typing a net win?
| typing | Pokémon | mean base_total | mean weaknesses | mean resistances | defensive score |
|---|---|---|---|---|---|
| dual | 526 | 451.03 | 3.89 | 5.62 | 1.07 |
| single | 499 | 403.08 | 2.59 | 3.38 | 1.04 |

Dual types gain **+48 base_total** but take **+1.3 weaknesses** and are slightly
*less* efficient defensively.

### B1 / B3 — Power creep
| generation | mean base_total (all) | mean base_total (non-legendary) |
|---|---|---|
| I | 407.6 | 400.9 |
| II | 407.2 | 393.8 |
| III | 403.7 | 386.7 |
| IV | 445.6 | 419.8 |
| V | 425.8 | 409.2 |
| VI | 429.3 | 411.4 |
| VII | 449.4 | 414.1 |
| VIII | 439.2 | 419.3 |
| IX | 457.4 | 444.5 |

+12% overall (408 → 457) and +11% excluding legendaries — creep is not just
legendaries.

### B2 — Stat budget allocation (% of base_total)

| generation | offense | bulk | speed |
|---|---|---|---|
| I | 34.1 | 48.7 | 17.2 |
| V | 35.0 | 49.3 | 15.6 |
| IX | 33.9 | 49.4 | 16.7 |

Essentially constant across all generations.

### BM — Min-maxing
* By generation: 0.287 (gen I) → 0.263 (gen IX), flat/slightly down.
* Legendary 0.225 vs non-legendary 0.278 → legendaries are **less** min-maxed.
* Most min-maxed types: Rock (0.449), Rock/Ground (0.402), Ghost (0.362).
* Most balanced: Fire/Flying (0.172), Poison (0.186).

### C1 — Speed vs power
`corr(speed, power) = +0.43`, `corr(speed, bulk) = +0.17`. No trade-off.
Extreme glass cannons: Deoxys, Pheromosa, Blacephalon. Extreme tanks: Shuckle,
Chansey, Blissey.

### D1 — Rarity / growth vs power
| metric | Pearson | Spearman |
|---|---|---|
| capture_rate (lower = rarer) | -0.730 | -0.726 |
| base_egg_steps | +0.499 | +0.456 |
| experience_growth (higher = slower) | +0.297 | +0.333 |

### D2 — Legendary gap per stat
| stat | non-legendary | legendary | delta | % |
|---|---|---|---|---|
| hp | 67.5 | 94.5 | +26.9 | +40% |
| attack | 74.6 | 103.9 | +29.3 | +39% |
| defense | 69.9 | 96.7 | +26.8 | +38% |
| sp_attack | 66.4 | 103.7 | +37.3 | **+56%** |
| sp_defense | 67.3 | 97.2 | +29.9 | +45% |
| speed | 64.2 | 94.5 | +30.3 | +47% |
| **base_total** | 409.9 | 590.4 | **+180.5** | **+44%** |

### D3 — Size vs power
`height` r = 0.51, `weight` r = 0.46 (Pearson) / **0.65 (Spearman)**,
`log10(weight)` r = 0.60. Size is a genuine, noisy power proxy.

### E2 — Most shared abilities
Swift Swim 44, Sturdy 42, Keen Eye 39, Chlorophyll 37, Inner Focus 35.
Levitate is never hidden (0/32); Sheer Force is hidden on 20/30. 856 of 2411
assignments are hidden across 284 distinct abilities.

## Consolidated insights

1. **Steel is the best defensive type, Ice the worst** — 0.833 vs 1.194
   defensive score.
2. **Best type combos stack Steel; worst share weaknesses** — `bug/steel` 0.875
   vs `bug/grass` 1.389.
3. **Dual typing trades ~+48 base_total for ~+1.3 weaknesses** (no free lunch).
4. **Power creep is real and not only legendaries** — mean base_total 408 → 457
   (all) and 401 → 445 (non-legendary).
5. **The stat-budget *allocation* is unchanged** across generations
   (~34% offense / ~50% bulk / ~16% speed).
6. **Legendaries are less min-maxed than average** (0.225 vs 0.278).
7. **There is no speed-vs-power trade-off** — faster Pokémon also hit harder
   (r = +0.43).
8. **Rarity predicts power** — capture_rate vs base_total r = -0.73.
9. **Legendaries are fast special attackers** — biggest gains in sp_attack
   (+56%) and speed (+47%).
10. **Size is a genuine power proxy** — weight vs base_total Spearman r = 0.65.
11. **Ability slots are heavily reused** — Swift Swim on 44 Pokémon; 856/2411
    assignments hidden.
