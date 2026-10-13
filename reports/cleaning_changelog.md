# Cleaning changelog (Phase 3)

Raw extended dataset: **1025 rows x 41 columns**  
Cleaned dataset: **1025 rows x 46 columns**

## Transformations performed

1. **Base-form reconciliation** - every dex entry was rebuilt from the
   cached PokeAPI base form. The original file had mega/regional-form
   values merged into gen 1-7 base rows (e.g. Charizard `base_total`
   634 = Mega Charizard, Alolan typings on Rattata/Meowth/Vulpix).
   Why: one row per Pokédex entry with internally consistent
   stats/types/size is required before analysis and loading.
2. **Type consistency** - `type2` values identical to `type1` were
   dropped and all 18 `against_*` columns recomputed from the official
   type chart (dual types multiply). Why: the raw cells contradicted
   the declared typing for 16 Pokémon.
3. **Numeric standardisation** - `capture_rate` forced to an integer
   (Minior stored `30 (Meteorite)255 (Core)`), `percentage_male`
   converted to the game's real ratios (88.1 -> 87.5, 75.4 -> 75,
   24.6 -> 25, 11.2 -> 12.5).
4. **Text standardisation** - ability names taken from the official
   ability index (`Compoundeyes` -> `Compound Eyes`),
   `classfication` renamed to `classification`.
5. **Calculated columns** - `is_dual_type`, `type_pair`,
   `generation_name`, `main_offense` (physical/special/balanced),
   `size_class` (height buckets).
6. **Split into relational DataFrames** - dimension and fact tables
   written to `datasets/clean/` for the Phase 5/6 database load.

## Cells changed vs the raw dataset

| column | changed cells | % of rows | examples |
|---|---|---|---|
| `percentage_male` | 156 | 15.2% | Bulbasaur (88.1 -> 87.5); Ivysaur (88.1 -> 87.5); Venusaur (88.1 -> 87.5) |
| `abilities` | 66 | 6.4% | Butterfree (['Compoundeyes', 'Tinted Lens'] -> ['Compound Eyes', 'Tinted Lens']); Rattata (['Run Away', 'Guts', 'Hustle', 'Gluttony', 'Hustle', 'Thick Fat'] -> ['Run Away', 'Guts', 'Hustle']); Raticate (['Run Away', 'Guts', 'Hustle', 'Gluttony', 'Hustle', 'Thick Fat'] -> ['Run Away', 'Guts', 'Hustle']) |
| `attack` | 65 | 6.3% | Venusaur (100 -> 82); Charizard (104 -> 84); Blastoise (103 -> 83) |
| `sp_attack` | 65 | 6.3% | Venusaur (122 -> 100); Charizard (159 -> 109); Blastoise (135 -> 85) |
| `defense` | 62 | 6.0% | Venusaur (123 -> 83); Blastoise (120 -> 100); Pidgeot (80 -> 75) |
| `base_total` | 59 | 5.8% | Venusaur (625 -> 525); Charizard (634 -> 534); Blastoise (630 -> 530) |
| `sp_defense` | 57 | 5.6% | Venusaur (120 -> 100); Charizard (115 -> 85); Blastoise (115 -> 105) |
| `speed` | 56 | 5.5% | Beedrill (145 -> 75); Pidgeot (121 -> 101); Raticate (77 -> 97) |
| `japanese_name` | 23 | 2.2% | Nidoran♀ (Nidoran?ニドラン♀ -> Nidoran♀ニドラン♀); Nidoran♂ (Nidoran?ニドラン♂ -> Nidoran♂ニドラン♂); Umbreon (Blackyブラッキー -> Brackyブラッキー) |
| `weight_kg` | 23 | 2.2% | Rattata (NULL -> 3.5); Raticate (NULL -> 18.5); Raichu (NULL -> 30.0) |
| `height_m` | 22 | 2.1% | Rattata (NULL -> 0.3); Raticate (NULL -> 0.7); Raichu (NULL -> 0.8) |
| `type2` | 16 | 1.6% | Rattata (dark -> NULL); Raticate (dark -> NULL); Raichu (electric -> NULL) |
| `capture_rate` | 8 | 0.8% | Minior (30 (Meteorite)255 (Core) -> 30); Buzzwole (25 -> 45); Pheromosa (255 -> 45) |
| `hp` | 6 | 0.6% | Raticate (75 -> 55); Floette (74 -> 54); Pumpkaboo (59 -> 49) |
| `is_legendary` | 3 | 0.3% | Phione (0 -> 1); Type: Null (0 -> 1); Silvally (0 -> 1) |

## Split tables

| table | rows | columns |
|---|---|---|
| `generations` | 9 | 5 |
| `types` | 18 | 2 |
| `abilities` | 284 | 2 |
| `pokemon` | 1025 | 20 |
| `pokemon_stats` | 1025 | 8 |
| `pokemon_abilities` | 2411 | 4 |
| `type_matchups` | 324 | 3 |
| `pokemon_type_defense` | 18450 | 3 |

## Cleaning checks

- PASS - pokedex_number is unique and complete (1-1025) (1025 distinct ids, 1-1025)
- PASS - name is unique (1025 names)
- PASS - no duplicate type2 == type1 (0 rows)
- PASS - all against_* cells match the type chart (0 mismatching cells of 18450)
- PASS - base_total equals the sum of the six stats (0 rows differ)
- PASS - percentage_male uses standard game ratios (0 non-standard rows)
- PASS - capture_rate is a whole number everywhere (0 missing / non-integer values)
- PASS - no unexpected missing values (blank type2: 499, blank percentage_male: 155, other: none)

## Notes / retained decisions

* `type2` stays NULL for single-type Pokémon and `percentage_male`
  stays NULL for genderless Pokémon - these are structural, not defects.
* `is_legendary` keeps the original file's convention of flagging
  mythicals (Mew, Deoxys, ...) and the Ultra Beasts (Nihilego ...
  Guzzlord) together with legendaries - PokeAPI reports
  `is_legendary = false` for both groups, which is why they are
  listed explicitly in `scripts/build_dataset.py`.
* Outliers (Wailord's size, Blissey's HP, ...) were kept: they are
  true values, not errors.
