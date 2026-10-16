-- ============================================================================
-- Pokemon analysis - Phase 5: relational schema (PostgreSQL)
--
-- Normalised design over the cleaned dataset (1025 Pokemon, generations I-IX).
-- Everything lives in a dedicated "pokemon" schema so it never clashes with
-- the default "public" objects.
--
-- Idempotent: drops and recreates the schema every time it is run.
--   psql -d pokemon_analysis -f sql/schema.sql
--
-- Tables : generations, types, abilities, pokemon, pokemon_stats,
--          pokemon_abilities, type_matchups
-- Views  : v_pokemon_profile, v_pokemon_type_defense
-- ============================================================================

DROP SCHEMA IF EXISTS pokemon CASCADE;
CREATE SCHEMA pokemon;
SET search_path TO pokemon;


-- ----------------------------------------------------------------- lookup ---
CREATE TABLE generations (
    generation_id  SMALLINT PRIMARY KEY,
    label          TEXT     NOT NULL UNIQUE,
    dex_start      SMALLINT NOT NULL,
    dex_end        SMALLINT NOT NULL,
    pokemon_count  SMALLINT NOT NULL,
    CONSTRAINT generations_id_ck    CHECK (generation_id BETWEEN 1 AND 9),
    CONSTRAINT generations_range_ck CHECK (dex_start <= dex_end)
);
COMMENT ON TABLE generations IS 'Pokedex generations I-IX and their dex ranges.';

CREATE TABLE types (
    type_id    SMALLINT PRIMARY KEY,
    type_name  TEXT     NOT NULL UNIQUE
);
COMMENT ON TABLE types IS 'The 18 elemental types.';

CREATE TABLE abilities (
    ability_id    SMALLINT PRIMARY KEY,
    ability_name  TEXT     NOT NULL UNIQUE
);
COMMENT ON TABLE abilities IS 'Distinct abilities referenced by any Pokemon.';


-- -------------------------------------------------------------- core entity --
CREATE TABLE pokemon (
    pokedex_number    SMALLINT     PRIMARY KEY,
    name              TEXT         NOT NULL UNIQUE,
    japanese_name     TEXT         NOT NULL,
    generation_id     SMALLINT     NOT NULL REFERENCES generations(generation_id),
    type1_id          SMALLINT     NOT NULL REFERENCES types(type_id),
    type2_id          SMALLINT              REFERENCES types(type_id),
    classification    TEXT         NOT NULL,
    height_m          NUMERIC(4,1) NOT NULL,
    weight_kg         NUMERIC(6,1) NOT NULL,
    percentage_male   NUMERIC(4,1),
    capture_rate      SMALLINT     NOT NULL,
    base_happiness    SMALLINT     NOT NULL,
    base_egg_steps    INTEGER      NOT NULL,
    experience_growth INTEGER      NOT NULL,
    is_legendary      BOOLEAN      NOT NULL,
    CONSTRAINT pokemon_dex_ck     CHECK (pokedex_number BETWEEN 1 AND 1025),
    CONSTRAINT pokemon_types_ck   CHECK (type2_id IS DISTINCT FROM type1_id),
    CONSTRAINT pokemon_height_ck  CHECK (height_m >= 0),
    CONSTRAINT pokemon_weight_ck  CHECK (weight_kg >= 0),
    CONSTRAINT pokemon_male_ck    CHECK (percentage_male BETWEEN 0 AND 100),
    CONSTRAINT pokemon_capture_ck CHECK (capture_rate >= 0)
);
COMMENT ON TABLE  pokemon IS 'One row per Pokedex entry (base form).';
COMMENT ON COLUMN pokemon.percentage_male IS 'NULL for genderless Pokemon.';
COMMENT ON COLUMN pokemon.type2_id IS 'NULL for single-type Pokemon.';
COMMENT ON COLUMN pokemon.is_legendary IS 'Includes mythicals and Ultra Beasts (dataset convention).';


-- ------------------------------------------------------------------ 1 : 1 ----
CREATE TABLE pokemon_stats (
    pokedex_number  SMALLINT PRIMARY KEY
                    REFERENCES pokemon(pokedex_number) ON DELETE CASCADE,
    hp              SMALLINT NOT NULL,
    attack          SMALLINT NOT NULL,
    defense         SMALLINT NOT NULL,
    sp_attack       SMALLINT NOT NULL,
    sp_defense      SMALLINT NOT NULL,
    speed           SMALLINT NOT NULL,
    base_total      SMALLINT NOT NULL,
    CONSTRAINT stats_range_ck CHECK (
        hp         BETWEEN 1 AND 255 AND
        attack     BETWEEN 1 AND 255 AND
        defense    BETWEEN 1 AND 255 AND
        sp_attack  BETWEEN 1 AND 255 AND
        sp_defense BETWEEN 1 AND 255 AND
        speed      BETWEEN 1 AND 255),
    CONSTRAINT stats_total_ck CHECK (
        base_total = hp + attack + defense + sp_attack + sp_defense + speed)
);
COMMENT ON TABLE pokemon_stats IS 'Base stats, split from pokemon (1:1).';


-- ------------------------------------------------------------------ N : M ----
CREATE TABLE pokemon_abilities (
    pokedex_number  SMALLINT NOT NULL
                    REFERENCES pokemon(pokedex_number) ON DELETE CASCADE,
    ability_id      SMALLINT NOT NULL REFERENCES abilities(ability_id),
    slot            SMALLINT NOT NULL,
    is_hidden       BOOLEAN  NOT NULL,
    PRIMARY KEY (pokedex_number, slot),
    CONSTRAINT pokemon_abilities_unique   UNIQUE (pokedex_number, ability_id),
    CONSTRAINT pokemon_abilities_slot_ck  CHECK (slot BETWEEN 1 AND 3),
    CONSTRAINT pokemon_abilities_hidden_ck CHECK (is_hidden = (slot = 3))
);
COMMENT ON TABLE pokemon_abilities IS 'Junction: which abilities a Pokemon has, and in which slot.';

CREATE TABLE type_matchups (
    attacking_type_id  SMALLINT     NOT NULL REFERENCES types(type_id),
    defending_type_id  SMALLINT     NOT NULL REFERENCES types(type_id),
    multiplier         NUMERIC(3,2) NOT NULL,
    PRIMARY KEY (attacking_type_id, defending_type_id),
    CONSTRAINT matchups_multiplier_ck CHECK (multiplier IN (0, 0.5, 1, 2))
);
COMMENT ON TABLE type_matchups IS 'Self-referencing 18x18 damage chart for single types.';


-- ------------------------------------------------------------------- views ---
-- Per-Pokemon incoming damage (combines both types by multiplication).
CREATE VIEW v_pokemon_type_defense AS
SELECT p.pokedex_number,
       m1.attacking_type_id,
       (m1.multiplier * COALESCE(m2.multiplier, 1))::NUMERIC(3,2) AS multiplier
FROM pokemon p
JOIN type_matchups m1 ON m1.defending_type_id = p.type1_id
LEFT JOIN type_matchups m2
       ON m2.attacking_type_id = m1.attacking_type_id
      AND m2.defending_type_id = p.type2_id;
COMMENT ON VIEW v_pokemon_type_defense IS
    'Derived from pokemon.type1/type2 + type_matchups: 1025 x 18 incoming multipliers.';

-- Denormalised, analysis-ready view (re-adds the derived columns).
CREATE VIEW v_pokemon_profile AS
SELECT p.pokedex_number,
       p.name,
       p.japanese_name,
       p.generation_id,
       g.label AS generation_name,
       p.type1_id,
       t1.type_name AS type1,
       p.type2_id,
       t2.type_name AS type2,
       (p.type2_id IS NOT NULL) AS is_dual_type,
       CASE WHEN p.type2_id IS NULL THEN t1.type_name
            ELSE t1.type_name || ' / ' || t2.type_name END AS type_pair,
       p.classification,
       p.height_m,
       p.weight_kg,
       p.percentage_male,
       p.capture_rate,
       p.base_happiness,
       p.base_egg_steps,
       p.experience_growth,
       p.is_legendary,
       s.hp, s.attack, s.defense, s.sp_attack, s.sp_defense, s.speed, s.base_total,
       CASE WHEN s.attack > s.sp_attack THEN 'physical'
            WHEN s.sp_attack > s.attack THEN 'special'
            ELSE 'balanced' END AS main_offense,
       CASE WHEN p.height_m < 1 THEN 'small'
            WHEN p.height_m < 2 THEN 'medium'
            WHEN p.height_m < 4 THEN 'large'
            ELSE 'huge' END AS size_class
FROM pokemon p
JOIN generations   g  ON g.generation_id = p.generation_id
JOIN types         t1 ON t1.type_id      = p.type1_id
LEFT JOIN types    t2 ON t2.type_id      = p.type2_id
JOIN pokemon_stats s  ON s.pokedex_number = p.pokedex_number;
COMMENT ON VIEW v_pokemon_profile IS
    'Flat analysis view: base attributes + stats + derived labels.';


-- ----------------------------------------------------------------- indexes ---
CREATE INDEX pokemon_generation_idx ON pokemon (generation_id);
CREATE INDEX pokemon_type1_idx      ON pokemon (type1_id);
CREATE INDEX pokemon_type2_idx      ON pokemon (type2_id);
CREATE INDEX pokemon_abilities_ability_idx ON pokemon_abilities (ability_id);
CREATE INDEX type_matchups_defending_idx   ON type_matchups (defending_type_id);
CREATE INDEX pokemon_stats_total_idx       ON pokemon_stats (base_total DESC);


-- --------------------------------------------------------------- convenience --
-- Make the schema the default for new sessions on this database.
ALTER DATABASE pokemon_analysis SET search_path TO pokemon, public;
