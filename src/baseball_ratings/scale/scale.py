"""The 20-80 scale.

grade = 50 + 10 * z, clipped to [20, 80], where z is measured against a reference population
(MLB players in the season) using a *true-talent* standard deviation:

    var_true = var_obs / mean(1 + k/n)

because each observed rate carries sampling noise with variance ~ var_true * k / n when ``k`` is
the EB constant. Without this deflation the SD is inflated by noise and grades are compressed.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import polars as pl

from baseball_ratings.config import ScaleCfg


@dataclass(frozen=True)
class RefStats:
    mean: float
    sd: float
    n_players: int


def reference_stats(values: pl.Series, n: pl.Series, k: float, min_n: float = 0.0) -> RefStats | None:
    """Denominator-weighted mean and true-talent SD of raw ``values`` with sample sizes ``n``."""
    df = pl.DataFrame({"x": values, "n": n}).drop_nulls()
    df = df.filter((pl.col("n") >= max(min_n, 1e-9)) & pl.col("x").is_finite())
    if df.height < 3:
        return None
    w, x = pl.col("n").cast(pl.Float64), pl.col("x").cast(pl.Float64)
    wsum = float(df.select(w.sum()).item())
    mean = float(df.select((w * x).sum()).item()) / wsum
    var_obs = float(df.select((w * (x - mean) ** 2).sum()).item()) / wsum
    # sum(n * (1 + k/n)) / sum(n) = 1 + k * N / sum(n)
    inflation = 1.0 + k * df.height / wsum if k > 0 else 1.0
    var_true = var_obs / inflation
    if not math.isfinite(var_true) or var_true <= 0:
        return None
    return RefStats(mean=mean, sd=math.sqrt(var_true), n_players=df.height)


def plain_stats(values: pl.Series, weights: pl.Series | None = None) -> RefStats | None:
    """Weighted mean/SD with no noise deflation (for re-standardizing composites)."""
    w_s = weights if weights is not None else pl.Series([1.0] * len(values))
    df = pl.DataFrame({"x": values, "w": w_s}).drop_nulls().filter(pl.col("w") > 0)
    if df.height < 3:
        return None
    w, x = pl.col("w").cast(pl.Float64), pl.col("x").cast(pl.Float64)
    wsum = float(df.select(w.sum()).item())
    mean = float(df.select((w * x).sum()).item()) / wsum
    sd = math.sqrt(float(df.select((w * (x - mean) ** 2).sum()).item()) / wsum)
    if sd <= 0 or not math.isfinite(sd):
        return None
    return RefStats(mean=mean, sd=sd, n_players=df.height)


def z_expr(x: pl.Expr, ref: RefStats, higher_is_better: bool = True) -> pl.Expr:
    z = (x - ref.mean) / ref.sd
    return z if higher_is_better else -z


def grade_from_z(z: pl.Expr, cfg: ScaleCfg) -> pl.Expr:
    return (cfg.mean + cfg.points_per_sd * z).clip(cfg.clip_min, cfg.clip_max)


def display_grade(g: pl.Expr, cfg: ScaleCfg) -> pl.Expr:
    step = cfg.display_step
    return ((g / step).round(0) * step).clip(cfg.clip_min, cfg.clip_max).cast(pl.Int64)


def grade_value(z: float, cfg: ScaleCfg) -> float:
    """Scalar version of ``grade_from_z`` (used in tests and reports)."""
    return min(cfg.clip_max, max(cfg.clip_min, cfg.mean + cfg.points_per_sd * z))


def interpolate(x: float, table: list[tuple[float, float]]) -> float:
    """Piecewise-linear lookup with flat extrapolation."""
    pts = sorted(table)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in itertools.pairwise(pts):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]  # pragma: no cover
