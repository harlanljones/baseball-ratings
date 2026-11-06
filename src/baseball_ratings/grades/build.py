"""Assemble per-(player, level) feature tables from stored raw data.

Boxscore rows arrive per (player, league); outcome metrics are environment-normalized and
park-adjusted at that grain, then collapsed to (player, level) by denominator-weighted means.
Statcast and leaderboard metrics are already per (player, level).
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from baseball_ratings.config import RatingsConfig
from baseball_ratings.scale.levels import apply_env_normalization


@dataclass
class RawSeason:
    """Everything ingest stores for one season (empty frames when a source wasn't pulled)."""

    season: int
    hitting: pl.DataFrame
    hitting_adv: pl.DataFrame
    pitching: pl.DataFrame
    pitching_adv: pl.DataFrame
    fielding: pl.DataFrame
    people: pl.DataFrame
    park: pl.DataFrame
    pitches: pl.DataFrame
    leaderboards: dict[str, pl.DataFrame]

    def lb(self, name: str) -> pl.DataFrame:
        return self.leaderboards.get(name, pl.DataFrame())


def collapse_levels(
    df: pl.DataFrame, rate_cols: dict[str, str], count_cols: list[str], weight_col: str
) -> pl.DataFrame:
    """(player, league) rows -> (player, level). ``rate_cols`` maps rate -> its denominator."""
    aggs: list[pl.Expr] = [pl.col(c).sum() for c in count_cols if c in df.columns]
    for rate, den in rate_cols.items():
        if rate not in df.columns:
            continue
        ok = pl.col(rate).is_not_null() & (pl.col(den) > 0)
        aggs.append(
            pl.when(pl.col(den).filter(ok).sum() > 0)
            .then((pl.col(rate) * pl.col(den)).filter(ok).sum() / pl.col(den).filter(ok).sum())
            .otherwise(None)
            .alias(rate)
        )
    ordered = df.sort(weight_col, descending=True)
    firsts = [
        pl.col(c).first() for c in ("player_name", "season", "team_id", "league_id", "age") if c in df.columns
    ]
    return ordered.group_by("player_id", "level").agg(*firsts, *aggs)


def _metric_names(cfg: RatingsConfig, side: str, tier: str | None = None) -> list[str]:
    return [n for n, m in cfg.metrics.items() if m.side == side and (tier is None or m.tier == tier)]


def _env_metrics(cfg: RatingsConfig, side: str) -> list[tuple[str, str, bool]]:
    return [
        (n, m.denom, m.park)
        for n, m in cfg.metrics.items()
        if m.side == side and m.tier == "boxscore" and m.kind == "outcome"
    ]


def _established(people: pl.DataFrame, season: int) -> pl.DataFrame:
    if people.is_empty() or "mlb_debut_date" not in people.columns:
        return pl.DataFrame(schema={"player_id": pl.Int64, "mlb_established": pl.Boolean})
    return people.select(
        pl.col("player_id").cast(pl.Int64),
        (pl.col("mlb_debut_date").str.slice(0, 4).cast(pl.Int64, strict=False) < season)
        .fill_null(False)
        .alias("mlb_established"),
    )


def build_hitters(raw: RawSeason, cfg: RatingsConfig) -> pl.DataFrame:
    from baseball_ratings.features.fielding import (
        fielding_by_position,
        leaderboard_defense,
        primary_positions,
    )
    from baseball_ratings.features.hitting import boxscore_hitting, leaderboard_hitting, statcast_hitting

    box = boxscore_hitting(raw.hitting, raw.hitting_adv, cfg)
    if box.is_empty():
        return pl.DataFrame()
    box = apply_env_normalization(box, _env_metrics(cfg, "hitter"), cfg, raw.park)
    rates = {n: cfg.metrics[n].denom for n in _metric_names(cfg, "hitter", "boxscore")}
    rates["woba"] = "pa"
    counts = ["pa", "ab", "swings", "times_on_first", "xbh_23", "bip"]
    df = collapse_levels(box, rates, counts, "pa")

    sc = statcast_hitting(raw.pitches)
    if not sc.is_empty():
        df = df.join(sc, on=["player_id", "level"], how="left")
    lb = leaderboard_hitting(raw.lb("sprint_speed"), raw.lb("bat_tracking"))
    if not lb.is_empty():
        df = df.join(lb, on=["player_id", "level"], how="left")

    by_pos = fielding_by_position(raw.fielding, cfg)
    prim = primary_positions(by_pos)
    if not prim.is_empty():
        keep = [
            "player_id",
            "level",
            "position",
            "innings",
            "def_games",
            "chances",
            "arm_opps",
            "range_factor_rel",
            "fielding_pct_rel",
            "arm_proxy",
        ]
        df = df.join(
            prim.select([c for c in keep if c in prim.columns]), on=["player_id", "level"], how="left"
        )
        totals = (
            by_pos.filter((pl.col("level") == "MLB") & (pl.col("position") != "DH"))
            .group_by("player_id")
            .agg(pl.col("def_games").sum().alias("total_def_games"))
        )
        mlb_pos = (
            prim.filter(pl.col("level") == "MLB")
            .select("player_id", "position", "def_games")
            .join(totals, on="player_id", how="left")
        )
        dfn = leaderboard_defense(
            raw.lb("oaa"),
            raw.lb("arm_strength"),
            raw.lb("catcher_framing"),
            raw.lb("catcher_blocking"),
            raw.lb("catcher_throwing"),
            mlb_pos,
            cfg,
        )
        if not dfn.is_empty():
            df = df.join(dfn, on=["player_id", "level"], how="left")
    if "position" not in df.columns:
        df = df.with_columns(pl.lit(None, dtype=pl.Utf8).alias("position"))
    df = df.with_columns(pl.col("position").fill_null("DH"))
    df = df.join(_established(raw.people, raw.season), on="player_id", how="left")

    # Drop pitchers who merely batted (more BF than PA at the level), keep two-way players.
    if not raw.pitching.is_empty():
        from baseball_ratings.features.common import add_level

        bf = (
            add_level(raw.pitching, cfg)
            .group_by("player_id", "level")
            .agg(pl.col("battersFaced").sum().alias("_bf"))
        )
        df = (
            df.join(bf, on=["player_id", "level"], how="left")
            .filter(pl.col("_bf").is_null() | (pl.col("pa") >= pl.col("_bf")))
            .drop("_bf")
        )
    return df


def build_pitchers(raw: RawSeason, cfg: RatingsConfig) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Returns (pitchers, per-pitch scored shapes)."""
    from baseball_ratings.features.pitching import (
        boxscore_pitching,
        pitcher_role,
        statcast_pitch_shapes,
        statcast_pitching,
    )
    from baseball_ratings.models.stuff import HeuristicStuff

    box = boxscore_pitching(raw.pitching, raw.pitching_adv, cfg)
    if box.is_empty():
        return pl.DataFrame(), pl.DataFrame()
    box = apply_env_normalization(box, _env_metrics(cfg, "pitcher"), cfg, raw.park)
    rates = {n: cfg.metrics[n].denom for n in _metric_names(cfg, "pitcher", "boxscore")}
    counts = ["bf", "pitches", "games", "games_started", "ip"]
    df = collapse_levels(box, rates, counts, "bf")
    df = df.with_columns(pitcher_role(df, cfg).alias("position"))

    scored = pl.DataFrame()
    if not raw.pitches.is_empty():
        loc = statcast_pitching(raw.pitches)
        if not loc.is_empty():
            df = df.join(loc, on=["player_id", "level"], how="left")
        model = HeuristicStuff(cfg)
        scored = model.score_pitches(statcast_pitch_shapes(raw.pitches))
        stuff = model.pitcher_stuff(scored)
        if not stuff.is_empty():
            df = df.join(stuff, on=["player_id", "level"], how="left")
    df = df.join(_established(raw.people, raw.season), on="player_id", how="left")
    return df, scored
