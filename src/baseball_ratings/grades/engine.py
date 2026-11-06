"""Generic metric -> tool-grade engine driven by ``config/ratings.yaml``.

For each metric:
  shrink toward the level mean (MiLB means exclude MLB-established players)
  -> translate outcome stats with the level factor
  -> z vs the reference population (MLB, or same level for MiLB-only proxies), true-talent SD
For each tool:
  weighted blend of available component z-scores (primary set, else fallback set)
  -> re-standardize the blend against the MLB reference cohort
  -> grade = clip(50 + 10 z), display rounded to 5, plus confidence and source tier.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from baseball_ratings.config import MetricCfg, RatingsConfig, ToolCfg
from baseball_ratings.scale.levels import level_factor_expr
from baseball_ratings.scale.regression import group_mean, reliability, shrink
from baseball_ratings.scale.scale import (
    RefStats,
    display_grade,
    grade_from_z,
    plain_stats,
    reference_stats,
)

TIER_RANK = {"statcast": 3, "leaderboard": 2, "boxscore": 1}


@dataclass
class MetricResult:
    z_col: str
    rel_col: str


def _target_mask() -> pl.Expr:
    """Rows that define level means: everyone at MLB; at MiLB, exclude established big leaguers
    (rehab assignments, optioned veterans) so they don't distort prospect baselines."""
    return (pl.col("level") == "MLB") | ~pl.col("mlb_established").fill_null(False)


def metric_z(df: pl.DataFrame, name: str, m: MetricCfg, side: str, cfg: RatingsConfig) -> pl.DataFrame:
    """Add ``{name}__z`` and ``{name}__rel`` columns."""
    if name not in df.columns or m.denom not in df.columns:
        return df.with_columns(
            pl.lit(None, dtype=pl.Float64).alias(f"{name}__z"),
            pl.lit(None, dtype=pl.Float64).alias(f"{name}__rel"),
        )
    group = ["level"]
    pos_group = None
    if m.catcher_group and "position" in df.columns:
        pos_group = pl.when(pl.col("position") == "C").then(pl.lit("C")).otherwise(pl.lit("F")).alias("_pg")
        df = df.with_columns(pos_group)
        group = ["level", "_pg"]
    elif m.reference == "level" and "position" in df.columns and m.side == "fielder":
        df = df.with_columns(pl.col("position").fill_null("DH").alias("_pg"))
        group = ["level", "_pg"]

    has_mask = "mlb_established" in df.columns
    mu = group_mean(df, name, m.denom, group, _target_mask() if has_mask else None)
    df = df.join(mu, on=group, how="left")
    shrunk = shrink(pl.col(name), pl.col(m.denom), pl.col(f"{name}__mu"), m.k)
    if m.kind == "outcome" and m.reference == "mlb":
        shrunk = shrunk * level_factor_expr(cfg, side if side != "fielder" else "hitter", m.factor or name)
    df = df.with_columns(shrunk.alias(f"{name}__s"), reliability(pl.col(m.denom), m.k).alias(f"{name}__rel"))

    min_n = cfg.scale.reference_min_n.get(m.denom, 0.0)
    pg_vals: list[object] = df["_pg"].unique().to_list() if "_pg" in df.columns else [None]
    z_parts: list[pl.Expr] = []
    for pg in pg_vals:
        pg_sel = pl.col("_pg") == pg if pg is not None else pl.lit(True)
        if m.reference == "mlb":
            scopes: list[tuple[pl.Expr, pl.Expr]] = [((pl.col("level") == "MLB") & pg_sel, pg_sel)]
        else:
            scopes = [
                ((pl.col("level") == lvl) & pg_sel, (pl.col("level") == lvl) & pg_sel)
                for lvl in df["level"].unique().to_list()
            ]
        for ref_cond, apply_cond in scopes:
            ref_df = df.filter(ref_cond)
            ref = reference_stats(ref_df[name], ref_df[m.denom], m.k, min_n) or reference_stats(
                ref_df[name], ref_df[m.denom], m.k, 0.0
            )
            if ref is None:
                continue
            z = (pl.col(f"{name}__s") - ref.mean) / ref.sd
            z_parts.append(pl.when(apply_cond).then(z if m.higher_is_better else -z))
    if z_parts:
        z_all = pl.coalesce(z_parts) if len(z_parts) > 1 else z_parts[0]
        df = df.with_columns(z_all.alias(f"{name}__z"))
    else:
        df = df.with_columns(pl.lit(None, dtype=pl.Float64).alias(f"{name}__z"))
    return df.drop([c for c in (f"{name}__mu", f"{name}__s", "_pg") if c in df.columns])


def _blend(weights: dict[str, float]) -> tuple[pl.Expr, pl.Expr, pl.Expr]:
    """Weighted mean of available z's, weighted reliability, and count of components present."""
    num = pl.lit(0.0)
    den = pl.lit(0.0)
    rel = pl.lit(0.0)
    for name, w in weights.items():
        z = pl.col(f"{name}__z")
        present = z.is_not_null()
        num = num + pl.when(present).then(z * w).otherwise(0.0)
        den = den + pl.when(present).then(w).otherwise(0.0)
        rel = rel + pl.when(present).then(pl.col(f"{name}__rel") * w).otherwise(0.0)
    blend = pl.when(den > 0).then(num / den).otherwise(None)
    return blend, pl.when(den > 0).then(rel / den).otherwise(None), den


def _tier(weights: dict[str, float], metrics: dict[str, MetricCfg]) -> pl.Expr:
    ranks = [
        pl.when(pl.col(f"{n}__z").is_not_null()).then(TIER_RANK[metrics[n].tier]).otherwise(0)
        for n in weights
        if n in metrics
    ]
    best = pl.max_horizontal(ranks) if ranks else pl.lit(0)
    inv = {v: k for k, v in TIER_RANK.items()}
    return best.replace_strict(inv, default=None, return_dtype=pl.Utf8)


def _restandardize(df: pl.DataFrame, col: str, weight_col: str | None) -> RefStats | None:
    ref = df.filter((pl.col("level") == "MLB") & pl.col(col).is_not_null())
    if weight_col and weight_col in ref.columns:
        # Weight the cohort by sample size so noisy cups of coffee don't set the spread.
        return plain_stats(ref[col], ref[weight_col].cast(pl.Float64))
    return plain_stats(ref[col])


def tool_grade(
    df: pl.DataFrame,
    tool: str,
    tcfg: ToolCfg,
    metrics: dict[str, MetricCfg],
    cfg: RatingsConfig,
    weight_col: str,
) -> pl.DataFrame:
    paths = [("p", tcfg.weights)] + ([("f", tcfg.fallback)] if tcfg.fallback else [])
    chosen_z: list[pl.Expr] = []
    for tag, weights in paths:
        blend, rel, _ = _blend(weights)
        df = df.with_columns(
            blend.alias(f"_{tool}_{tag}"),
            rel.alias(f"_{tool}_{tag}_rel"),
            _tier(weights, metrics).alias(f"_{tool}_{tag}_tier"),
        )
        ref = _restandardize(df, f"_{tool}_{tag}", weight_col)
        if ref is None:
            # Not enough MLB rows (e.g. a MiLB-only run): fall back to the cohort being graded.
            vals = df[f"_{tool}_{tag}"]
            ref = plain_stats(vals) or RefStats(0.0, 1.0, 0)
        df = df.with_columns(((pl.col(f"_{tool}_{tag}") - ref.mean) / ref.sd).alias(f"_{tool}_{tag}_z"))
        chosen_z.append(pl.col(f"_{tool}_{tag}_z"))
    p_ok = pl.col(f"_{tool}_p").is_not_null()
    if len(paths) == 2:
        z = pl.when(p_ok).then(pl.col(f"_{tool}_p_z")).otherwise(pl.col(f"_{tool}_f_z"))
        rel = pl.when(p_ok).then(pl.col(f"_{tool}_p_rel")).otherwise(pl.col(f"_{tool}_f_rel"))
        tier = pl.when(p_ok).then(pl.col(f"_{tool}_p_tier")).otherwise(pl.col(f"_{tool}_f_tier"))
    else:
        z, rel, tier = pl.col(f"_{tool}_p_z"), pl.col(f"_{tool}_p_rel"), pl.col(f"_{tool}_p_tier")
    raw = grade_from_z(z, cfg.scale)
    df = df.with_columns(
        raw.alias(f"{tool}_raw"),
        display_grade(raw, cfg.scale).alias(tool),
        rel.round(3).alias(f"{tool}_conf"),
        tier.alias(f"{tool}_tier"),
    )
    return df.drop([c for c in df.columns if c.startswith(f"_{tool}_")])


def grade_side(df: pl.DataFrame, side: str, cfg: RatingsConfig, weight_col: str) -> pl.DataFrame:
    """Grade every tool configured for ``side`` (hitter | pitcher | fielder)."""
    tools = cfg.tools.get(side, {})
    needed = {n for t in tools.values() for n in (*t.weights, *t.fallback)}
    metrics = {n: cfg.metrics[n] for n in needed if n in cfg.metrics}
    for name, m in metrics.items():
        df = metric_z(df, name, m, side, cfg)
    for tool, tcfg in tools.items():
        df = tool_grade(df, tool, tcfg, metrics, cfg, weight_col)
    return df.drop([c for c in df.columns if c.endswith("__z") or c.endswith("__rel")])
