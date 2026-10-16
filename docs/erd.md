# Entity-Relationship Diagram (Phase 5)

Database: **PostgreSQL**, dedicated schema **`pokemon`**.

Seven base tables, two derived views:

* **`generations`, `types`, `abilities`** — lookup tables (natural surrogate keys).
* **`pokemon`** — one row per base-form Pokédex entry.
* **`pokemon_stats`** — base stats, split out as a **1:1** relation.
* **`pokemon_abilities`** — junction table for the **N:M** `pokemon ↔ abilities`.
* **`type_matchups`** — self-referencing **N:M** on `types` (the 18×18 chart).
* `v_pokemon_profile`, `v_pokemon_type_defense` — derived views.

```mermaid
erDiagram
    GENERATIONS ||--o{ POKEMON : "introduces"
    TYPES       ||--o{ POKEMON : "primary type"
    TYPES       ||--o{ POKEMON : "secondary type"
    POKEMON     ||--|| POKEMON_STATS : "has"
    POKEMON     ||--o{ POKEMON_ABILITIES : "can have"
    ABILITIES   ||--o{ POKEMON_ABILITIES : "granted via"
    TYPES       ||--o{ TYPE_MATCHUPS : "attacks"
    TYPES       ||--o{ TYPE_MATCHUPS : "defends"

    GENERATIONS {
        smallint generation_id PK
        text     label UK
        smallint dex_start
        smallint dex_end
        smallint pokemon_count
    }
    TYPES {
        smallint type_id PK
        text     type_name UK
    }
    ABILITIES {
        smallint ability_id PK
        text     ability_name UK
    }
    POKEMON {
        smallint     pokedex_number PK
        text         name UK
        text         japanese_name
        smallint     generation_id FK
        smallint     type1_id FK
        smallint     type2_id FK "nullable"
        text         classification
        numeric      height_m
        numeric      weight_kg
        numeric      percentage_male "nullable"
        smallint     capture_rate
        smallint     base_happiness
        integer      base_egg_steps
        integer      experience_growth
        boolean      is_legendary
    }
    POKEMON_STATS {
        smallint pokedex_number PK "FK -> pokemon"
        smallint hp
        smallint attack
        smallint defense
        smallint sp_attack
        smallint sp_defense
        smallint speed
        smallint base_total
    }
    POKEMON_ABILITIES {
        smallint pokedex_number PK "FK -> pokemon"
        smallint slot PK
        smallint ability_id FK
        boolean  is_hidden
    }
    TYPE_MATCHUPS {
        smallint attacking_type_id PK "FK -> types"
        smallint defending_type_id PK "FK -> types"
        numeric  multiplier
    }
```

## Cardinalities

| Relationship | Type | Notes |
|---|---|---|
| `generations` → `pokemon` | 1 : N | every Pokémon belongs to one generation |
| `types` → `pokemon` (`type1_id`) | 1 : N | mandatory primary type |
| `types` → `pokemon` (`type2_id`) | 1 : N | optional secondary type |
| `pokemon` → `pokemon_stats` | 1 : 1 | PK of the child is also the FK |
| `pokemon` ↔ `abilities` | N : M | through `pokemon_abilities` (`slot`, `is_hidden`) |
| `types` ↔ `types` | N : M | through `type_matchups` (self-referential) |

## Integrity rules
* `CHECK (type2_id IS DISTINCT FROM type1_id)` — a Pokémon cannot have two identical types.
* `CHECK (base_total = hp+attack+defense+sp_attack+sp_defense+speed)`.
* `CHECK (is_hidden = (slot = 3))` and `CHECK (slot BETWEEN 1 AND 3)`.
* `CHECK (multiplier IN (0, 0.5, 1, 2))` on the raw chart.
* `UNIQUE (pokedex_number, ability_id)` — a Pokémon cannot have the same ability twice.

The rendered diagram is in [`erd.png`](erd.png) (`python scripts/build_erd.py`).
