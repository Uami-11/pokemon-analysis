-- ============================================================================
-- Pokemon analysis - Phase 7: reporting queries
--
-- Each report starts with a marker line:  -- @report: <id>. <title>
-- Run them all with:  python scripts/run_reports.py
-- or interactively:   psql -d pokemon_analysis -f sql/reports.sql
--
-- All objects are schema-qualified (pokemon.) so the search_path does not
-- matter. Reports demonstrate joins, GROUP BY/HAVING, aggregates with FILTER,
-- CTEs, window functions and the two reporting views.
-- ============================================================================


-- @report: R1. Pokedex roster and legendary share per generation
-- Uses: INNER/LEFT joins, aggregates, FILTER
SELECT g.generation_id,
       g.label                       AS generation,
       g.dex_start,
       g.dex_end,
       count(p.pokedex_number)       AS pokemon,
       count(*) FILTER (WHERE p.is_legendary) AS legendary,
       round(avg(s.base_total), 1)   AS avg_base_total
FROM pokemon.generations g
LEFT JOIN pokemon.pokemon       p ON p.generation_id = g.generation_id
LEFT JOIN pokemon.pokemon_stats s ON s.pokedex_number = p.pokedex_number
GROUP BY g.generation_id, g.label, g.dex_start, g.dex_end
ORDER BY g.generation_id;


-- @report: R2. Top 10 Pokemon by base stat total
-- Uses: view, ORDER BY + LIMIT
SELECT pokedex_number, name, generation_name, type_pair,
       hp, attack, defense, sp_attack, sp_defense, speed, base_total
FROM pokemon.v_pokemon_profile
ORDER BY base_total DESC, speed DESC, name
LIMIT 10;


-- @report: R3. Average base stat total per generation (power creep)
-- Uses: CTE + window functions (first_value, rank)
WITH gen AS (
    SELECT generation_id,
           generation_name,
           count(*)                    AS pokemon,
           round(avg(base_total), 1)   AS avg_base_total
    FROM pokemon.v_pokemon_profile
    GROUP BY generation_id, generation_name
)
SELECT generation_id,
       generation_name,
       pokemon,
       avg_base_total,
       round(avg_base_total - first_value(avg_base_total) OVER (ORDER BY generation_id), 1)
                        AS delta_vs_gen1,
       rank() OVER (ORDER BY avg_base_total DESC) AS total_rank
FROM gen
ORDER BY generation_id;


-- @report: R4. Legendary vs regular stat profile
-- Uses: CASE, aggregates with FILTER
SELECT CASE WHEN is_legendary THEN 'legendary' ELSE 'regular' END AS tier,
       count(*)                       AS pokemon,
       round(avg(hp), 1)              AS hp,
       round(avg(attack), 1)          AS attack,
       round(avg(defense), 1)         AS defense,
       round(avg(sp_attack), 1)       AS sp_attack,
       round(avg(sp_defense), 1)      AS sp_defense,
       round(avg(speed), 1)           AS speed,
       round(avg(base_total), 1)      AS base_total,
       max(base_total)                AS best_base_total
FROM pokemon.v_pokemon_profile
GROUP BY is_legendary
ORDER BY is_legendary DESC;


-- @report: R5. Offensive type power: incoming effectiveness by attacking type
-- Uses: view + join + aggregates with FILTER
SELECT t.type_name                                          AS attacking_type,
       round(avg(d.multiplier), 3)                          AS avg_multiplier,
       count(*) FILTER (WHERE d.multiplier > 1)             AS super_effective,
       count(*) FILTER (WHERE d.multiplier = 1)             AS neutral,
       count(*) FILTER (WHERE d.multiplier < 1 AND d.multiplier > 0) AS resisted,
       count(*) FILTER (WHERE d.multiplier = 0)             AS immune
FROM pokemon.v_pokemon_type_defense d
JOIN pokemon.types t ON t.type_id = d.attacking_type_id
GROUP BY t.type_name
ORDER BY avg_multiplier DESC;


-- @report: R6. Type combinations with the most weaknesses (dual types)
-- Uses: view + join + GROUP BY/HAVING-style filters, top N
SELECT p.type_pair,
       count(*) FILTER (WHERE d.multiplier > 1)             AS weaknesses,
       count(*) FILTER (WHERE d.multiplier < 1 AND d.multiplier > 0) AS resistances,
       count(*) FILTER (WHERE d.multiplier = 0)             AS immunities,
       round(avg(p.base_total), 1)                          AS avg_base_total
FROM pokemon.v_pokemon_type_defense d
JOIN pokemon.v_pokemon_profile p USING (pokedex_number)
WHERE p.is_dual_type
GROUP BY p.type_pair
ORDER BY weaknesses DESC, resistances DESC
LIMIT 10;


-- @report: R7. Most common abilities
-- Uses: N:M junction join + window rank + FILTER
SELECT rank() OVER (ORDER BY count(*) DESC) AS rnk,
       a.ability_name,
       count(*)                             AS pokemon_count,
       count(*) FILTER (WHERE pa.is_hidden) AS hidden_count
FROM pokemon.pokemon_abilities pa
JOIN pokemon.abilities a USING (ability_id)
GROUP BY a.ability_name
ORDER BY pokemon_count DESC, a.ability_name
LIMIT 15;


-- @report: R8. Top 10 "glass cannons" (offense minus bulk, speed as tiebreak)
-- Uses: computed columns, arithmetic on aggregates/attributes
SELECT name, generation_name, type_pair,
       (attack + sp_attack)                                   AS offense,
       (hp + defense + sp_defense)                            AS bulk,
       (attack + sp_attack) - (hp + defense + sp_defense)     AS offense_minus_bulk,
       speed
FROM pokemon.v_pokemon_profile
ORDER BY offense_minus_bulk DESC, speed DESC, name
LIMIT 10;


-- @report: R9. Hardest-to-catch strong Pokemon (base_total >= 500)
-- Uses: WHERE filter + multi-key ORDER BY
SELECT name, generation_name, type_pair, capture_rate, base_total, is_legendary
FROM pokemon.v_pokemon_profile
WHERE base_total >= 500
ORDER BY capture_rate ASC, base_total DESC, name
LIMIT 10;


-- @report: R10. Primary type distribution (share of the dex)
-- Uses: window SUM for percentage + FILTER
SELECT type1 AS primary_type,
       count(*)                                          AS pokemon,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct_of_dex,
       count(*) FILTER (WHERE is_legendary)              AS legendary,
       round(avg(base_total), 1)                         AS avg_base_total
FROM pokemon.v_pokemon_profile
GROUP BY type1
ORDER BY pokemon DESC, primary_type;


-- @report: R11. Most common type combinations
-- Uses: GROUP BY on a derived label
SELECT type_pair,
       is_dual_type,
       count(*)                  AS pokemon,
       round(avg(base_total), 1) AS avg_base_total
FROM pokemon.v_pokemon_profile
GROUP BY type_pair, is_dual_type
ORDER BY pokemon DESC, type_pair
LIMIT 10;


-- @report: R12. Dual vs single type: average stat profile
-- Uses: CASE + aggregates
SELECT CASE WHEN is_dual_type THEN 'dual' ELSE 'single' END AS typing,
       count(*)                       AS pokemon,
       round(avg(base_total), 1)      AS avg_base_total,
       round(avg(attack + sp_attack), 1)              AS avg_offense,
       round(avg(hp + defense + sp_defense), 1)       AS avg_bulk,
       round(avg(speed), 1)           AS avg_speed
FROM pokemon.v_pokemon_profile
GROUP BY is_dual_type
ORDER BY is_dual_type DESC;
