"""Fielding features: primary position, MiLB boxscore proxies, MLB Statcast defense."""

from __future__ import annotations

import polars as pl

from baseball_ratings.config import RatingsConfig
from baseball_ratings.features.common import add_level, col_or_zero, safe_div

OF = ["LF", "CF", "RF"]


def fielding_by_position(fielding: pl.DataFrame, cfg: RatingsConfig) -> pl.DataFrame:
    """Aggregate fielding rows to (player, level, position) and derive position-relative proxies."""
    if fielding.is_empty():
        return pl.DataFrame()
    df = add_level(fielding, cfg).filter(pl.col("level").is_not_null() & (pl.col("position") != "P"))

    def g(n: str) -> pl.Expr:
        return col_or_zero(df, n)

    agg = (
        df.with_columns(
            g("innings").alias("innings"),
            g("games").alias("def_games"),
            g("chances").alias("chances"),
            g("putOuts").alias("po"),
            g("assists").alias("a"),
            g("errors").alias("e"),
            g("stolenBases").alias("sb"),
            g("caughtStealing").alias("cs"),
        )
        .group_by("player_id", "level", "position")
        .agg(pl.col("innings", "def_games", "chances", "po", "a", "e", "sb", "cs").sum())
        .with_columns(
            safe_div((pl.col("po") + pl.col("a")) * 9, pl.col("innings")).alias("_rf9"),
            safe_div(pl.col("po") + pl.col("a"), pl.col("chances")).alias("_fpct"),
            pl.when(pl.col("position").is_in(OF))
            .then(safe_div(pl.col("a") * 9, pl.col("innings")))
            .when(pl.col("position") == "C")
            .then(safe_div(pl.col("cs"), pl.col("sb") + pl.col("cs")))
            .otherwise(None)
            .alias("_arm"),
            pl.when(pl.col("position") == "C")
            .then(pl.col("sb") + pl.col("cs"))
            .otherwise(pl.col("innings"))
            .alias("arm_opps"),
        )
    )
    # Express each proxy relative to the (level, position) average so positions are comparable.
    out = agg
    for raw, name, den in [("_rf9", "range_factor_rel", "innings"), ("_fpct", "fielding_pct_rel", "chances")]:
        means = (
            out.filter(pl.col(raw).is_not_null())
            .group_by("level", "position")
            .agg(((pl.col(raw) * pl.col(den)).sum() / pl.col(den).sum()).alias("_m"))
        )
        out = (
            out.join(means, on=["level", "position"], how="left")
            .with_columns((pl.col(raw) - pl.col("_m")).alias(name))
            .drop("_m")
        )
    means = (
        out.filter(pl.col("_arm").is_not_null())
        .group_by("level", "position")
        .agg(((pl.col("_arm") * pl.col("arm_opps")).sum() / pl.col("arm_opps").sum()).alias("_m"))
    )
    out = out.join(means, on=["level", "position"], how="left").with_columns(
        (pl.col("_arm") - pl.col("_m")).alias("arm_proxy")
    )
    return out.drop("_rf9", "_fpct", "_arm", "_m")


def primary_positions(by_pos: pl.DataFrame) -> pl.DataFrame:
    """Usage-based primary position per (player, level): most innings (DH if none)."""
    if by_pos.is_empty():
        return pl.DataFrame(schema={"player_id": pl.Int64, "level": pl.Utf8, "position": pl.Utf8})
    return (
        by_pos.filter(pl.col("position") != "DH")
        .sort("innings", descending=True)
        .group_by("player_id", "level")
        .first()
    )


def leaderboard_defense(
    oaa: pl.DataFrame,
    arm: pl.DataFrame,
    framing: pl.DataFrame,
    blocking: pl.DataFrame,
    throwing: pl.DataFrame,
    def_games: pl.DataFrame,
    cfg: RatingsConfig,
) -> pl.DataFrame:
    """MLB Statcast defense per player.

    ``def_games``: (player_id, position, def_games, total_def_games) at MLB. OAA covers every
    position a player fielded, so it is rated per *total* defensive games; catcher runs per
    games caught. Arm strength is shifted to an RF-equivalent with Tango's position offsets.
    """
    cols = ["player_id", "position", "def_games", "total_def_games"]
    out = def_games.select([c for c in cols if c in def_games.columns]) if not def_games.is_empty() else None
    if out is None:
        return pl.DataFrame()
    if not oaa.is_empty():
        o = oaa.select("player_id", pl.col("outs_above_average").cast(pl.Float64, strict=False).alias("_oaa"))
        out = (
            out.join(o, on="player_id", how="left")
            .with_columns(
                pl.when(pl.col("position") != "C")
                .then(safe_div(pl.col("_oaa") * 150, pl.col("total_def_games")))
                .otherwise(None)
                .alias("oaa_rate")
            )
            .drop("_oaa")
        )
    c_parts = []
    for df, col in [
        (framing, "rv_tot"),
        (blocking, "catcher_blocking_runs"),
        (throwing, "catcher_stealing_runs"),
    ]:
        if not df.is_empty() and col in df.columns:
            c_parts.append(
                df.select("player_id", pl.col(col).cast(pl.Float64, strict=False).alias(f"_c_{col}"))
            )
    for part in c_parts:
        out = out.join(part, on="player_id", how="left")
    if c_parts:
        runs = pl.sum_horizontal([pl.col(c).fill_null(0) for c in out.columns if c.startswith("_c_")])
        out = out.with_columns(
            pl.when(pl.col("position") == "C")
            .then(safe_div(runs * 120, pl.col("def_games")))
            .otherwise(None)
            .alias("catcher_def_rate")
        ).drop([c for c in out.columns if c.startswith("_c_")])
    if not arm.is_empty():
        a = arm.select(
            "player_id",
            pl.col("arm_overall").cast(pl.Float64, strict=False).alias("_arm"),
            pl.col("total_throws").cast(pl.Float64, strict=False).alias("throws"),
        )
        offsets = cfg.arm_position_offsets
        out = (
            out.join(a, on="player_id", how="left")
            .with_columns(
                (
                    pl.col("_arm")
                    + pl.col("position").replace_strict(offsets, default=0.0, return_dtype=pl.Float64)
                ).alias("arm_equiv")
            )
            .drop("_arm")
        )
    return out.drop("position", "def_games", strict=False).with_columns(pl.lit("MLB").alias("level"))
