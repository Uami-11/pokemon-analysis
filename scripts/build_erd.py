"""Render docs/erd.png from the Phase 5 schema (matplotlib only - graphviz is
not installed). The Mermaid source of truth lives in docs/erd.md.

    python scripts/build_erd.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "erd.png"

ROW_H = 1.55          # vertical space per attribute line
HEADER_H = 3.6        # table-name band
PAD = 1.5

# name -> (x_left, y_top, width, rows, is_view)
ENTITIES = {
    "generations": (1.5, 97, 23, [
        "generation_id  PK", "label          UK", "dex_start",
        "dex_end", "pokemon_count"], False),
    "pokemon_stats": (1.5, 73, 26, [
        "pokedex_number PK,FK", "hp", "attack", "defense", "sp_attack",
        "sp_defense", "speed", "base_total"], False),
    "v_pokemon_profile": (1.5, 42, 26, [
        "pokedex_number", "type_pair", "is_dual_type", "generation_name",
        "main_offense", "size_class", "base_total"], True),
    "pokemon": (35, 97, 32, [
        "pokedex_number PK", "name           UK", "japanese_name",
        "generation_id  FK", "type1_id       FK", "type2_id       FK  null",
        "classification", "height_m", "weight_kg", "percentage_male null",
        "capture_rate", "base_happiness", "base_egg_steps",
        "experience_growth", "is_legendary"], False),
    "pokemon_abilities": (35, 55, 32, [
        "pokedex_number PK,FK", "slot           PK", "ability_id     FK",
        "is_hidden"], False),
    "types": (74, 97, 24, ["type_id   PK", "type_name UK"], False),
    "type_matchups": (74, 82, 24, [
        "attacking_type_id PK,FK", "defending_type_id PK,FK", "multiplier"], False),
    "v_pokemon_type_defense": (74, 67, 24, [
        "pokedex_number", "attacking_type_id", "multiplier"], True),
    "abilities": (74, 50, 24, ["ability_id   PK", "ability_name UK"], False),
}

# (from, side, frac, to, side, frac, label, dashed)
EDGES = [
    ("generations", "r", 0.5, "pokemon", "l", 0.88, "1 : N", False),
    ("types", "l", 0.62, "pokemon", "r", 0.92, "type1  1 : N", False),
    ("types", "l", 0.30, "pokemon", "r", 0.78, "type2  1 : N (null)", False),
    ("pokemon", "l", 0.55, "pokemon_stats", "r", 0.55, "1 : 1", False),
    ("pokemon", "b", 0.5, "pokemon_abilities", "t", 0.5, "1 : N", False),
    ("abilities", "l", 0.5, "pokemon_abilities", "r", 0.70, "1 : N", False),
    ("types", "b", 0.62, "type_matchups", "t", 0.5, "attacks 1 : N", False),
    ("types", "b", 0.38, "type_matchups", "t", 0.72, "defends 1 : N", False),
    ("type_matchups", "b", 0.5, "v_pokemon_type_defense", "t", 0.5, "derived", True),
    ("pokemon", "l", 0.30, "v_pokemon_profile", "r", 0.65, "derived view", True),
]

SIDE = {"l": "l", "r": "r", "t": "t", "b": "b"}


def geometry():
    geom = {}
    for name, (x, y_top, w, rows, is_view) in ENTITIES.items():
        h = HEADER_H + len(rows) * ROW_H + PAD
        geom[name] = {"x": x, "y": y_top - h, "w": w, "h": h, "top": y_top}
    return geom


def anchor(g, side, frac):
    x, y, w, h = g["x"], g["y"], g["w"], g["h"]
    if side == "r":
        return x + w, y + frac * h
    if side == "l":
        return x, y + frac * h
    if side == "t":
        return x + frac * w, y + h
    return x + frac * w, y


def draw_box(ax, name, spec):
    x, y_top, w, rows, is_view = spec
    h = HEADER_H + len(rows) * ROW_H + PAD
    y = y_top - h
    edge = "#555555" if is_view else "#111111"
    ls = (0, (5, 3)) if is_view else "solid"

    ax.add_patch(Rectangle((x, y), w, h, facecolor="white", edgecolor=edge,
                           linewidth=1.4, linestyle=ls, zorder=2))
    header = "#7a7a7a" if is_view else "#3d5a80"
    ax.add_patch(Rectangle((x, y + h - HEADER_H), w, HEADER_H, facecolor=header,
                           edgecolor=edge, linewidth=1.4, linestyle=ls, zorder=3))
    title = name + ("  «view»" if is_view else "")
    ax.text(x + w / 2, y + h - HEADER_H / 2, title, ha="center", va="center",
            color="white", fontsize=9.5, fontweight="bold", zorder=4)
    for i, row in enumerate(rows):
        yy = y + h - HEADER_H - PAD / 2 - (i + 0.5) * ROW_H
        ax.text(x + 1.2, yy, row, ha="left", va="center", fontsize=7.4,
                family="monospace", zorder=4)


def main():
    fig, ax = plt.subplots(figsize=(16, 11))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    geom = geometry()

    for name, (x, y_top, w, rows, is_view) in ENTITIES.items():
        draw_box(ax, name, (x, y_top, w, rows, is_view))

    for src, s_side, s_frac, dst, d_side, d_frac, label, dashed in EDGES:
        p1 = anchor(geom[src], s_side, s_frac)
        p2 = anchor(geom[dst], d_side, d_frac)
        style = (0, (4, 3)) if dashed else "solid"
        color = "#999999" if dashed else "#b03a2e"
        ax.annotate("", xy=p2, xytext=p1,
                    arrowprops=dict(arrowstyle="-|>", color=color, linewidth=1.5,
                                    linestyle=style, shrinkA=0, shrinkB=0,
                                    connectionstyle="arc3,rad=0.06"))
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        ax.text(mx, my + 1.1, label, ha="center", va="center", fontsize=7.5,
                color=color, zorder=5,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))

    ax.text(50, 98.6, "Pokemon analysis - ERD (schema: pokemon)",
            ha="center", va="top", fontsize=14, fontweight="bold")
    plt.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
