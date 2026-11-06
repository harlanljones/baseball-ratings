"""Pitcher features: boxscore rates (every level) and Statcast pitch shapes/locations."""

from __future__ import annotations

import polars as pl

from baseball_ratings.config import RatingsConfig
from baseball_ratings.features.common import add_level, col_or_zero, pitch_flags, safe_div


def boxscore_pitching(season: pl.DataFrame, advanced: pl.DataFrame, cfg: RatingsConfig) -> pl.DataFrame:
    if season.is_empty():
        return pl.DataFrame()
    df = season
    if not advanced.is_empty() and "swingAndMisses" in advanced.columns:
        df = df.join(
            advanced.select("player_id", "league_id", "swingAndMisses"),
            on=["player_id", "league_id"],
            how="left",
        )
    df = add_level(df, cfg)

    def g(n: str) -> pl.Expr:
        return col_or_zero(df, n)

    return df.select(
        "player_id",
        "player_name",
        "season",
        "level",
        "league_id",
        "team_id",
        pl.col("age"),
        g("battersFaced").alias("bf"),
        g("numberOfPitches").alias("pitches"),
        g("gamesPlayed").alias("games"),
        g("gamesStarted").alias("games_started"),
        g("inningsPitched").alias("ip"),
        safe_div(g("strikeOuts"), g("battersFaced")).alias("p_k_pct"),
        safe_div(g("baseOnBalls"), g("battersFaced")).alias("p_bb_pct"),
        safe_div(g("swingAndMisses"), g("numberOfPitches")).alias("p_swstr_pct"),
    ).filter(pl.col("level").is_not_null() & (pl.col("bf") > 0))


def _shape_columns() -> list[pl.Expr]:
    # Savant pfx_x is catcher's-view feet; flip for LHP so positive = arm side.
    arm_sign = pl.when(pl.col("p_throws") == "L").then(1.0).otherwise(-1.0)
    return [
        (pl.col("pfx_z") * 12).alias("ivb"),
        (pl.col("pfx_x") * 12 * arm_sign).alias("arm_hb"),
        ((pl.col("pfx_x") * 12).pow(2) + (pl.col("pfx_z") * 12).pow(2)).sqrt().alias("mov"),
    ]


def statcast_pitch_shapes(pitches: pl.DataFrame) -> pl.DataFrame:
    """Per (pitcher, level, pitch_type): usage, average shape, whiffs/swings."""
    if pitches.is_empty():
        return pl.DataFrame()
    df = (
        pitches.filter(pl.col("release_speed").is_not_null() & pl.col("pitch_type").is_not_null())
        .with_columns(pitch_flags())
        .with_columns(_shape_columns())
    )
    shapes = df.group_by(pl.col("pitcher").alias("player_id"), "level", "pitch_type").agg(
        pl.len().alias("n"),
        pl.col("release_speed").mean().alias("velo"),
        pl.col("ivb").mean(),
        pl.col("arm_hb").mean(),
        pl.col("mov").mean(),
        pl.col("release_extension").mean().alias("ext"),
        pl.col("release_spin_rate").mean().alias("spin"),
        pl.col("swing").sum().alias("swings"),
        pl.col("whiff").sum().alias("whiffs"),
    )
    totals = shapes.group_by("player_id", "level").agg(pl.col("n").sum().alias("_total"))
    shapes = shapes.join(totals, on=["player_id", "level"]).with_columns(
        (pl.col("n") / pl.col("_total")).alias("usage"), (-pl.col("arm_hb")).alias("glove_hb")
    )
    # Primary fastball (most-used of FF/SI) per pitcher-level for offspeed differentials.
    fb = (
        shapes.filter(pl.col("pitch_type").is_in(["FF", "SI"]))
        .sort("n", descending=True)
        .group_by("player_id", "level")
        .first()
        .select("player_id", "level", pl.col("velo").alias("_fb_velo"), pl.col("ivb").alias("_fb_ivb"))
    )
    return (
        shapes.join(fb, on=["player_id", "level"], how="left")
        .with_columns(
            (pl.col("_fb_velo") - pl.col("velo")).alias("velo_gap"),
            (pl.col("_fb_ivb") - pl.col("ivb")).alias("drop"),
        )
        .drop("_total", "_fb_velo", "_fb_ivb")
        .with_columns(pl.col("player_id").cast(pl.Int64))
    )


def statcast_pitching(pitches: pl.DataFrame) -> pl.DataFrame:
    """Per (pitcher, level): location/command rates on tracked pitches."""
    if pitches.is_empty():
        return pl.DataFrame()
    df = pitches.filter(pl.col("release_speed").is_not_null()).with_columns(pitch_flags())
    return (
        df.group_by(pl.col("pitcher").alias("player_id"), "level")
        .agg(
            pl.len().alias("sc_pitches"),
            pl.col("located").sum().alias("_located"),
            pl.col("edge").sum().alias("_edge"),
            pl.col("heart").sum().alias("_heart"),
            pl.col("in_zone").sum().alias("_zone"),
        )
        .with_columns(
            safe_div(pl.col("_edge"), pl.col("_located")).alias("p_edge_pct"),
            safe_div(pl.col("_heart"), pl.col("_located")).alias("p_heart_pct"),
            safe_div(pl.col("_zone"), pl.col("_located")).alias("p_zone_pct"),
        )
        .drop("_located", "_edge", "_heart", "_zone")
        .with_columns(pl.col("player_id").cast(pl.Int64))
    )


def pitcher_role(df: pl.DataFrame, cfg: RatingsConfig) -> pl.Expr:
    share = safe_div(pl.col("games_started"), pl.col("games"))
    return pl.when(share >= cfg.ofp.pitcher.starter_gs_share).then(pl.lit("SP")).otherwise(pl.lit("RP"))
