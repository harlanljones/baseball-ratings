"""Empirical-Bayes shrinkage toward a group mean.

shrunk = (n*x + k*mu) / (n + k)

``k`` is in the metric's denominator units (PA, BBE, pitches...). Published "stabilization
points" (Carleton/Tango) behave like ``k`` (see docs/research/methodology-sources.md). The
player's weight ``n/(n+k)`` is reported as the grade's confidence.

Note: posterior means are under-dispersed relative to true talent (Jaffe, Ignatiadis & Sen 2025);
variance-preserving shrinkage is a planned follow-up.
"""

from __future__ import annotations

import polars as pl


def shrink(x: pl.Expr, n: pl.Expr, mu: pl.Expr, k: float) -> pl.Expr:
    n = n.fill_null(0).clip(lower_bound=0)
    return pl.when(x.is_null()).then(None).otherwise((n * x + k * mu) / (n + k))


def reliability(n: pl.Expr, k: float) -> pl.Expr:
    n = n.fill_null(0).clip(lower_bound=0)
    return n / (n + k) if k > 0 else pl.when(n > 0).then(1.0).otherwise(0.0)


def group_mean(
    df: pl.DataFrame, value: str, denom: str, by: list[str], mask: pl.Expr | None = None
) -> pl.DataFrame:
    """Denominator-weighted mean of ``value`` within ``by`` (rows passing ``mask``)."""
    cond = pl.col(value).is_not_null() & (pl.col(denom) > 0)
    if mask is not None:
        cond = cond & mask
    return (
        df.filter(cond)
        .group_by(by)
        .agg(((pl.col(value) * pl.col(denom)).sum() / pl.col(denom).sum()).alias(f"{value}__mu"))
    )
