"""League-season run environment and park factors.

Outcome stats are normalized to the *level* average before level translation, so a PCL hitter
(2025: 5.83 R/G) and an IL hitter (4.94 R/G) are compared on the same footing. Park factors use
team home/away run totals, regressed halfway to 1.0 because single seasons are noisy.
"""

from __future__ import annotations

import polars as pl

from baseball_ratings.config import RatingsConfig


def league_means(df: pl.DataFrame, value: str, denom: str, by: list[str]) -> pl.DataFrame:
    """Denominator-weighted mean of ``value`` within groups ``by``."""
    return (
        df.filter(pl.col(value).is_not_null() & (pl.col(denom) > 0))
        .group_by(by)
        .agg((pl.col(value) * pl.col(denom)).sum().alias("_num"), pl.col(denom).sum().alias("_den"))
        .with_columns((pl.col("_num") / pl.col("_den")).alias(f"{value}__mean"))
        .drop("_num", "_den")
    )


def park_factors(home_away: pl.DataFrame, cfg: RatingsConfig) -> pl.DataFrame:
    """Run park factor per team from hitting+pitching home/away splits.

    ``home_away`` rows: team_id, split_code (h/a), games, runs (scored or allowed; both groups
    concatenated). PF = (home runs per game) / (road runs per game), regressed toward 1.
    """
    if home_away.is_empty():
        return pl.DataFrame(schema={"team_id": pl.Int64, "park_factor": pl.Float64})
    agg = home_away.group_by("team_id", "split_code").agg(
        pl.col("runs").sum().alias("runs"), (pl.col("games").max()).alias("games")
    )
    wide = agg.pivot(on="split_code", index="team_id", values=["runs", "games"])
    needed = {"runs_h", "runs_a", "games_h", "games_a"}
    if not needed <= set(wide.columns):
        return pl.DataFrame(schema={"team_id": pl.Int64, "park_factor": pl.Float64})
    r = cfg.park.regress_to_one
    return wide.with_columns(
        (
            (1 - r) * ((pl.col("runs_h") / pl.col("games_h")) / (pl.col("runs_a") / pl.col("games_a"))) + r
        ).alias("park_factor")
    ).select("team_id", "park_factor")


def player_park_multiplier(pf: pl.Expr, cfg: RatingsConfig) -> pl.Expr:
    """Factor a player's line was inflated by: half his games at home, half spread elsewhere."""
    share = cfg.park.home_share
    return share * pf + (1 - share)
