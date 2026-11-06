"""Per-pitch Stuff.

PR1 ships a transparent heuristic: within each pitch type, z-score the physical traits that
public Stuff+ models lean on (velocity, IVB, arm-side run, extension, spin, total movement,
velocity/drop gap off the primary fastball) plus shrunk whiffs-per-swing, all against the MLB
population for that pitch type. A trained run-value model (leave-pitcher-out CV, held-out
season) replaces ``HeuristicStuff`` in PR3 behind the same ``StuffModel`` interface.
"""

from __future__ import annotations

from typing import Protocol

import polars as pl

from baseball_ratings.config import RatingsConfig
from baseball_ratings.scale.scale import RefStats, plain_stats


class StuffModel(Protocol):
    def score_pitches(self, shapes: pl.DataFrame) -> pl.DataFrame:
        """Return shapes + ``pitch_z`` (per-pitch Stuff z vs MLB pitch type)."""
        ...

    def pitcher_stuff(self, scored: pl.DataFrame) -> pl.DataFrame:
        """Return (player_id, level, p_stuff_raw, pitches)."""
        ...


class HeuristicStuff:
    def __init__(self, cfg: RatingsConfig) -> None:
        self.cfg = cfg
        self.h = cfg.stuff_heuristic
        self.class_of = {pt: cls for cls, pts in self.h.pitch_classes.items() for pt in pts}

    def _ref(self, mlb: pl.DataFrame, pitch_type: str, col: str) -> RefStats | None:
        sub = mlb.filter((pl.col("pitch_type") == pitch_type) & (pl.col("n") >= self.h.min_pitches_per_type))
        if col not in sub.columns or sub.height < 3:
            return None
        return plain_stats(sub[col], sub["n"].cast(pl.Float64))

    def score_pitches(self, shapes: pl.DataFrame) -> pl.DataFrame:
        if shapes.is_empty():
            return shapes
        k = self.h.whiff_k_swings
        df = shapes.with_columns(
            pl.col("pitch_type")
            .replace_strict(self.class_of, default=None, return_dtype=pl.Utf8)
            .alias("pclass")
        ).filter(pl.col("pclass").is_not_null())
        # Shrink whiff rate toward the MLB pitch-type mean.
        mlb = df.filter(pl.col("level") == "MLB")
        wmu = mlb.group_by("pitch_type").agg((pl.col("whiffs").sum() / pl.col("swings").sum()).alias("_wmu"))
        df = df.join(wmu, on="pitch_type", how="left").with_columns(
            ((pl.col("whiffs") + k * pl.col("_wmu").fill_null(0.25)) / (pl.col("swings") + k)).alias("whiff")
        )
        mlb = df.filter(pl.col("level") == "MLB")
        parts: list[pl.DataFrame] = []
        for pt in df["pitch_type"].unique().to_list():
            sub = df.filter(pl.col("pitch_type") == pt)
            weights = self.h.weights[self.class_of[pt]]
            num = pl.lit(0.0)
            den = pl.lit(0.0)
            for feat, w in weights.items():
                ref = self._ref(mlb, pt, feat)
                if ref is None or feat not in sub.columns:
                    continue
                z = (pl.col(feat) - ref.mean) / ref.sd
                num = num + pl.when(z.is_not_null()).then(z * w).otherwise(0.0)
                den = den + pl.when(z.is_not_null()).then(w).otherwise(0.0)
            sub = sub.with_columns(pl.when(den > 0).then(num / den).otherwise(None).alias("_score"))
            ref = self._ref(sub.filter(pl.col("level") == "MLB"), pt, "_score")
            if ref is None:
                ref = plain_stats(sub["_score"]) or RefStats(0.0, 1.0, 0)
            parts.append(sub.with_columns(((pl.col("_score") - ref.mean) / ref.sd).alias("pitch_z")))
        out = pl.concat(parts, how="diagonal_relaxed") if parts else df
        return out.drop("_wmu", "_score", strict=False)

    def pitcher_stuff(self, scored: pl.DataFrame) -> pl.DataFrame:
        if scored.is_empty():
            return pl.DataFrame()
        return (
            scored.filter(pl.col("pitch_z").is_not_null())
            .group_by("player_id", "level")
            .agg(
                ((pl.col("pitch_z") * pl.col("n")).sum() / pl.col("n").sum()).alias("p_stuff_raw"),
                pl.col("n").sum().alias("sc_shape_pitches"),
            )
        )
