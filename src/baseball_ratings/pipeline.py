"""Ingest + grade orchestration used by the CLI."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable

import polars as pl

from baseball_ratings.config import RatingsConfig
from baseball_ratings.env import park_factors
from baseball_ratings.grades.build import RawSeason, build_hitters, build_pitchers
from baseball_ratings.grades.engine import grade_side
from baseball_ratings.grades.overall import hitter_ofp, pitcher_ofp
from baseball_ratings.ingest.savant import LEADERBOARDS, Savant
from baseball_ratings.ingest.statsapi import StatsApi
from baseball_ratings.scale.scale import display_grade, grade_from_z
from baseball_ratings.store import Store
from baseball_ratings.version import METHODOLOGY_VERSION

Log = Callable[[str], None]

STAT_DATASETS = [
    ("hitting", "hitting", "season"),
    ("hitting_adv", "hitting", "seasonAdvanced"),
    ("pitching", "pitching", "season"),
    ("pitching_adv", "pitching", "seasonAdvanced"),
    ("fielding", "fielding", "season"),
]


def ingest_stats(
    api: StatsApi, store: Store, cfg: RatingsConfig, season: int, levels: Iterable[str], log: Log
) -> None:
    ids: set[int] = set()
    park_rows: list[pl.DataFrame] = []
    for level in levels:
        sport_id = cfg.levels[level].sport_id
        for dataset, group, stat_type in STAT_DATASETS:
            df = api.season_stats_by_league(group, sport_id, season, stat_type)
            log(f"  {level:>4} {dataset:<13} {df.height:>6} rows")
            store.write(df, dataset, season, level)
            if df.height and "player_id" in df.columns:
                ids.update(int(i) for i in df["player_id"].drop_nulls().to_list())
        for group in ("hitting", "pitching"):
            ha = api.team_home_away(group, sport_id, season)
            if ha.height:
                park_rows.append(ha)
    if park_rows:
        store.write(pl.concat(park_rows, how="diagonal_relaxed"), "team_home_away", season)
    if ids:
        people = api.people(ids)
        log(f"  people: {people.height}")
        store.write(people, "people", season)


def ingest_leaderboards(savant: Savant, store: Store, season: int, log: Log) -> None:
    for name in LEADERBOARDS:
        df = savant.leaderboard(name, season)
        log(f"  leaderboard {name:<17} {df.height:>5} rows")
        store.write(df, f"lb_{name}", season)


def season_dates(season: int, start: str | None, end: str | None, limit_days: int | None) -> list[str]:
    d0 = dt.date.fromisoformat(start or f"{season}-03-15")
    d1 = dt.date.fromisoformat(end or f"{season}-10-05")
    days = [(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
    return days[:limit_days] if limit_days else days


def ingest_pitches(
    savant: Savant, store: Store, cfg: RatingsConfig, levels: Iterable[str], dates: list[str], log: Log
) -> None:
    for level in levels:
        sc = cfg.statcast_levels.get(level)
        if sc is None:
            continue
        for date in dates:
            part = f"{level}_{date}"
            season = int(date[:4])
            if store.exists("pitches", season, part):
                continue
            df = savant.pitches_day(date, level, sc.path, sc.hf_level)
            store.write(df, "pitches", season, part)
            if df.height:
                tracked = df.select(pl.col("release_speed").is_not_null().mean()).item() or 0.0
                log(f"  pitches {level} {date}: {df.height} rows, tracked {tracked:.0%}")


def load_raw(store: Store, season: int, cfg: RatingsConfig) -> RawSeason:
    def r(name: str) -> pl.DataFrame:
        return store.read(name, season)

    home_away = r("team_home_away")
    park = park_factors(home_away, cfg) if not home_away.is_empty() else pl.DataFrame()
    return RawSeason(
        season=season,
        hitting=r("hitting"),
        hitting_adv=r("hitting_adv"),
        pitching=r("pitching"),
        pitching_adv=r("pitching_adv"),
        fielding=r("fielding"),
        people=r("people"),
        park=park,
        pitches=r("pitches"),
        leaderboards={name: r(f"lb_{name}") for name in LEADERBOARDS},
    )


def _stamp(df: pl.DataFrame, season: int, side: str) -> pl.DataFrame:
    return df.with_columns(
        pl.lit(side).alias("side"),
        pl.lit(METHODOLOGY_VERSION).alias("methodology_version"),
        pl.lit(dt.date.today().isoformat()).alias("graded_on"),
        pl.lit(season).alias("season"),
    )


def grade_season(raw: RawSeason, cfg: RatingsConfig) -> dict[str, pl.DataFrame]:
    out: dict[str, pl.DataFrame] = {}
    hitters = build_hitters(raw, cfg)
    if not hitters.is_empty():
        hitters = grade_side(hitters, "hitter", cfg, "pa")
        hitters = grade_side(hitters, "fielder", cfg, "pa")
        out["hitters"] = _stamp(hitter_ofp(hitters, cfg), raw.season, "hitter")
    pitchers, scored = build_pitchers(raw, cfg)
    if not pitchers.is_empty():
        pitchers = grade_side(pitchers, "pitcher", cfg, "bf")
        out["pitchers"] = _stamp(pitcher_ofp(pitchers, cfg), raw.season, "pitcher")
    if not scored.is_empty():
        raw_g = grade_from_z(pl.col("pitch_z"), cfg.scale)
        out["pitch_grades"] = _stamp(
            scored.with_columns(
                raw_g.alias("pitch_grade_raw"), display_grade(raw_g, cfg.scale).alias("pitch_grade")
            ),
            raw.season,
            "pitch",
        )
    return out


HITTER_COLUMNS = [
    "player_id",
    "player_name",
    "season",
    "level",
    "position",
    "age",
    "pa",
    "hit",
    "raw_power",
    "game_power",
    "discipline",
    "speed",
    "field",
    "arm",
    "ofp",
    "fv",
    "war_est",
    "hit_tier",
    "raw_power_tier",
    "speed_tier",
    "field_tier",
    "hit_conf",
    "game_power_conf",
]
PITCHER_COLUMNS = [
    "player_id",
    "player_name",
    "season",
    "level",
    "position",
    "age",
    "bf",
    "ip",
    "stuff",
    "control",
    "command",
    "ofp",
    "fv",
    "war_est",
    "stuff_tier",
    "stuff_conf",
    "control_conf",
]
