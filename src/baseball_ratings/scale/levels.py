"""MiLB -> MLB translation and age-vs-level.

Order of operations for an *outcome* stat (K%, BB%, ISO...):
  1. normalize each league row to its level's average run environment (PCL vs IL etc.),
  2. park-adjust (power/run stats only),
  3. EB-shrink toward the level mean,
  4. multiply by the level factor (config ``level_factors``) to get an MLB-equivalent rate.
*Physical* stats (EV90, velo, sprint speed, arm) skip 1, 2 and 4: they are compared raw.

Factors are config defaults (literature priors). Estimating them from paired players is a
separate calibration step (PR4) because promotion selection biases naive paired deltas.
"""

from __future__ import annotations

import polars as pl

from baseball_ratings.config import RatingsConfig
from baseball_ratings.env import player_park_multiplier
from baseball_ratings.scale.regression import group_mean


def apply_env_normalization(
    df: pl.DataFrame, metrics: list[tuple[str, str, bool]], cfg: RatingsConfig, park: pl.DataFrame | None
) -> pl.DataFrame:
    """Normalize per-league rows of outcome metrics.

    ``metrics``: (metric, denom, park_adjust). Rows must carry level, league_id, team_id.
    """
    out = df
    if park is not None and not park.is_empty():
        out = out.join(park, on="team_id", how="left")
    else:
        out = out.with_columns(pl.lit(None, dtype=pl.Float64).alias("park_factor"))
    for metric, denom, park_adj in metrics:
        if metric not in out.columns:
            continue
        lvl = group_mean(out, metric, denom, ["level"]).rename({f"{metric}__mu": "_lvl"})
        lg = group_mean(out, metric, denom, ["level", "league_id"]).rename({f"{metric}__mu": "_lg"})
        out = out.join(lvl, on="level", how="left").join(lg, on=["level", "league_id"], how="left")
        factor = pl.when(pl.col("_lg") > 0).then(pl.col("_lvl") / pl.col("_lg")).otherwise(1.0)
        expr = pl.col(metric) * factor
        if park_adj:
            mult = player_park_multiplier(pl.col("park_factor").fill_null(1.0), cfg)
            expr = expr / mult
        out = out.with_columns(expr.alias(metric)).drop("_lvl", "_lg")
    return out.drop("park_factor")


def level_factor_expr(cfg: RatingsConfig, side: str, key: str) -> pl.Expr:
    mapping = {lvl: f.get(key, 1.0) for lvl, f in cfg.level_factors.get(side, {}).items()}
    return pl.col("level").replace_strict(mapping, default=1.0, return_dtype=pl.Float64)


def years_young_for_level(cfg: RatingsConfig, side: str) -> pl.Expr:
    """Level mean age minus player age (positive = young for level)."""
    attr = "mean_age_pitcher" if side == "pitcher" else "mean_age_hitter"
    mapping = {name: getattr(lvl, attr) for name, lvl in cfg.levels.items()}
    return pl.col("level").replace_strict(mapping, default=None, return_dtype=pl.Float64) - pl.col("age")


def fv_age_adjustment(cfg: RatingsConfig, side: str) -> pl.Expr:
    f = cfg.fv
    yrs = years_young_for_level(cfg, side)
    adj = (
        pl.when(yrs >= 0)
        .then((yrs * f.points_per_year_young).clip(upper_bound=f.cap_up))
        .otherwise((yrs * f.points_per_year_old).clip(lower_bound=-f.cap_down))
    )
    is_mlb = pl.col("level") == "MLB"
    mlb_vet = is_mlb & (pl.col("age") >= f.mlb_age_floor)
    adj = pl.when(is_mlb).then(adj.clip(upper_bound=f.mlb_cap_up)).otherwise(adj)
    return pl.when(mlb_vet | yrs.is_null()).then(0.0).otherwise(adj)
