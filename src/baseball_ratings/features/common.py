"""Shared feature helpers."""

from __future__ import annotations

import polars as pl

from baseball_ratings.config import RatingsConfig

SWING_DESCRIPTIONS = [
    "swinging_strike",
    "swinging_strike_blocked",
    "foul",
    "foul_tip",
    "hit_into_play",
    "foul_bunt",
    "missed_bunt",
    "bunt_foul_tip",
]
WHIFF_DESCRIPTIONS = ["swinging_strike", "swinging_strike_blocked", "missed_bunt"]

PLATE_HALF_WIDTH_FT = 17 / 24  # 8.5 in
EDGE_BAND_FT = 2 / 12  # +/- 2 in around the zone border counts as "edge"
HEART_SHRINK = 0.67  # inner 67% of the zone ~ Savant's "heart" attack region


def add_level(df: pl.DataFrame, cfg: RatingsConfig, sport_col: str = "sport_id") -> pl.DataFrame:
    mapping = {lvl.sport_id: name for name, lvl in cfg.levels.items()}
    return df.with_columns(
        pl.col(sport_col).replace_strict(mapping, default=None, return_dtype=pl.Utf8).alias("level")
    )


def safe_div(num: pl.Expr, den: pl.Expr) -> pl.Expr:
    return pl.when(den > 0).then(num / den).otherwise(None)


def col_or_zero(df: pl.DataFrame, name: str) -> pl.Expr:
    return pl.col(name).fill_null(0) if name in df.columns else pl.lit(0.0)


def pitch_flags() -> list[pl.Expr]:
    """Per-pitch boolean flags used by hitter and pitcher features."""
    in_zone = pl.col("zone").is_between(1, 9)
    swing = pl.col("description").is_in(SWING_DESCRIPTIONS)
    whiff = pl.col("description").is_in(WHIFF_DESCRIPTIONS)
    bbe = (pl.col("type") == "X") & pl.col("launch_speed").is_not_null()
    mid_z = (pl.col("sz_top") + pl.col("sz_bot")) / 2
    half_h = (pl.col("sz_top") - pl.col("sz_bot")) / 2
    dx = pl.col("plate_x").abs() - PLATE_HALF_WIDTH_FT
    dz = (pl.col("plate_z") - mid_z).abs() - half_h
    # distance outside (+) / inside (-) the nearest zone border, Chebyshev-style
    border = pl.max_horizontal(dx, dz)
    located = (
        pl.col("plate_x").is_not_null() & pl.col("plate_z").is_not_null() & pl.col("sz_top").is_not_null()
    )
    edge = located & (border.abs() <= EDGE_BAND_FT)
    heart = (
        located
        & (pl.col("plate_x").abs() <= PLATE_HALF_WIDTH_FT * HEART_SHRINK)
        & ((pl.col("plate_z") - mid_z).abs() <= half_h * HEART_SHRINK)
    )
    return [
        in_zone.alias("in_zone"),
        (pl.col("zone") > 9).alias("out_zone"),
        swing.alias("swing"),
        whiff.alias("whiff"),
        bbe.alias("bbe"),
        located.alias("located"),
        edge.alias("edge"),
        heart.alias("heart"),
        pl.col("release_speed").is_not_null().alias("tracked"),
    ]
