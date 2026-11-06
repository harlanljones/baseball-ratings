"""OFP (present overall value) and FV (EXPERIMENTAL future value).

OFP converts tool grades to an estimated WAR per season (FG "20-80 translated to wins" weights
plus positional adjustment), then maps WAR onto the FV scale with FanGraphs' FV->WAR bands, so
"OFP 50" means an average regular. FV adds an age-vs-level adjustment for players who are young
(or old) for their level. FV is a rule of thumb, not a calibrated projection (see roadmap).
"""

from __future__ import annotations

import polars as pl

from baseball_ratings.config import RatingsConfig
from baseball_ratings.scale.levels import fv_age_adjustment
from baseball_ratings.scale.scale import display_grade, interpolate


def _delta(tool: str) -> pl.Expr:
    return ((pl.col(f"{tool}_raw") - 50) / 10).fill_null(0.0)


def _war_to_grade(war: pl.Expr, table: list[tuple[float, float]]) -> pl.Expr:
    return war.map_elements(lambda w: interpolate(float(w), table), return_dtype=pl.Float64)


def hitter_ofp(df: pl.DataFrame, cfg: RatingsConfig) -> pl.DataFrame:
    h = cfg.ofp.hitter
    war = pl.lit(h.base_war)
    for tool, w in h.war_per_10.items():
        if f"{tool}_raw" in df.columns:
            war = war + w * _delta(tool)
    pos = pl.col("position").replace_strict(h.positional_adj_runs, default=0.0, return_dtype=pl.Float64)
    war = war + pos / h.runs_per_win
    return _finish(df.with_columns(war.alias("war_est")), cfg, "hitter")


def pitcher_ofp(df: pl.DataFrame, cfg: RatingsConfig) -> pl.DataFrame:
    p = cfg.ofp.pitcher
    sp = pl.lit(p.base_war_sp)
    rp = pl.lit(p.base_war_rp)
    for tool, w in p.war_per_10_sp.items():
        if f"{tool}_raw" in df.columns:
            sp = sp + w * _delta(tool)
    for tool, w in p.war_per_10_rp.items():
        if f"{tool}_raw" in df.columns:
            rp = rp + w * _delta(tool)
    war = pl.when(pl.col("position") == "SP").then(sp).otherwise(rp)
    return _finish(df.with_columns(war.alias("war_est")), cfg, "pitcher")


def _finish(df: pl.DataFrame, cfg: RatingsConfig, side: str) -> pl.DataFrame:
    table = [(float(a), float(b)) for a, b in cfg.ofp.war_to_grade[side]]
    s = cfg.scale
    df = df.with_columns(_war_to_grade(pl.col("war_est"), table).alias("ofp_raw"))
    fv = (pl.col("ofp_raw") + fv_age_adjustment(cfg, side)).clip(s.clip_min, s.clip_max)
    return df.with_columns(
        pl.col("war_est").round(2),
        display_grade(pl.col("ofp_raw"), s).alias("ofp"),
        fv.alias("fv_raw"),
        display_grade(fv, s).alias("fv"),
        pl.lit(True).alias("fv_experimental"),
    )
