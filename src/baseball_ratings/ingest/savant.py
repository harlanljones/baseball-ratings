"""Baseball Savant client: MLB leaderboards + pitch-level Statcast (MLB, AAA, FSL).

Gotchas encoded here (verified, see docs/research/savant.md):
- Pitch-level CSV requests are capped at 25,000 rows and silently drop the *oldest* rows, so we
  pull one day per level and raise if a response hits the cap.
- Missing required params return HTTP 200 with a header-only CSV; bad leaderboard params can
  return an HTML page; unknown params silently fall back to the *current* season. Season params
  are named differently per leaderboard, so each endpoint declares its own.
- CSVs start with a UTF-8 BOM. The minors CSV has the MLB schema but no level column, so rows are
  tagged with the level we requested and joined to statsapi by ``game_pk`` downstream.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from baseball_ratings.ingest.http import DataSourceError, HttpClient

BASE = "https://baseballsavant.mlb.com"
ROW_CAP = 25_000

PITCH_COLUMNS: dict[str, pl.DataType] = {
    "game_pk": pl.Int64(),
    "game_date": pl.Utf8(),
    "game_year": pl.Int64(),
    "game_type": pl.Utf8(),
    "home_team": pl.Utf8(),
    "batter": pl.Int64(),
    "pitcher": pl.Int64(),
    "stand": pl.Utf8(),
    "p_throws": pl.Utf8(),
    "at_bat_number": pl.Int64(),
    "pitch_number": pl.Int64(),
    "balls": pl.Int64(),
    "strikes": pl.Int64(),
    "pitch_type": pl.Utf8(),
    "release_speed": pl.Float64(),
    "release_spin_rate": pl.Float64(),
    "release_extension": pl.Float64(),
    "release_pos_x": pl.Float64(),
    "release_pos_z": pl.Float64(),
    "arm_angle": pl.Float64(),
    "pfx_x": pl.Float64(),
    "pfx_z": pl.Float64(),
    "plate_x": pl.Float64(),
    "plate_z": pl.Float64(),
    "sz_top": pl.Float64(),
    "sz_bot": pl.Float64(),
    "zone": pl.Int64(),
    "type": pl.Utf8(),
    "description": pl.Utf8(),
    "events": pl.Utf8(),
    "bb_type": pl.Utf8(),
    "launch_speed": pl.Float64(),
    "launch_angle": pl.Float64(),
    "launch_speed_angle": pl.Int64(),
    "estimated_woba_using_speedangle": pl.Float64(),
    "delta_run_exp": pl.Float64(),
    "bat_speed": pl.Float64(),
    "swing_length": pl.Float64(),
}


@dataclass(frozen=True)
class Leaderboard:
    path: str
    season_params: tuple[str, ...]  # params that must carry the season
    params: dict[str, Any] = field(default_factory=dict)
    id_column: str = "player_id"
    season_column: str | None = None  # column to assert against the requested season


LEADERBOARDS: dict[str, Leaderboard] = {
    "sprint_speed": Leaderboard(
        "sprint_speed", ("min_season", "max_season"), {"position": "", "team": "", "min": 0}
    ),
    "oaa": Leaderboard(
        "outs_above_average",
        ("startYear", "endYear"),
        {
            "type": "Fielder",
            "split": "no",
            "team": "",
            "range": "year",
            "min": 0,
            "pos": "",
            "roles": "",
            "viz": "hide",
        },
    ),
    "arm_strength": Leaderboard(
        "arm-strength",
        ("year",),
        {"type": "player", "minThrows": 0, "pos": "", "team": ""},
        season_column="year",
    ),
    "catcher_framing": Leaderboard(
        "catcher-framing",
        ("seasonStart", "seasonEnd"),
        {"type": "catcher", "gameType": "Regular", "minPitches": 0},
        id_column="id",
    ),
    "catcher_blocking": Leaderboard(
        "catcher-blocking",
        ("season_start", "season_end"),
        {"game_type": "Regular", "n": 0, "split": "", "team": "", "type": "Cat", "with_team_only": 1},
    ),
    "catcher_throwing": Leaderboard(
        "catcher-throwing",
        ("season_start", "season_end"),
        {"game_type": "Regular", "n": 0, "split": "", "team": "", "type": "Cat", "with_team_only": 1},
    ),
    "bat_tracking": Leaderboard(
        "bat-tracking",
        ("seasonStart", "seasonEnd"),
        {"type": "batter", "minSwings": 0, "gameType": "Regular"},
        id_column="id",
    ),
}


def read_csv_text(text: str, all_strings: bool = False) -> pl.DataFrame:
    return pl.read_csv(
        io.StringIO(text),
        infer_schema_length=0 if all_strings else None,
        null_values=["", "null", "NA"],
    )


def leaderboard_url(name: str, season: int) -> tuple[str, dict[str, Any]]:
    lb = LEADERBOARDS[name]
    params = dict(lb.params)
    for p in lb.season_params:
        params[p] = season
    params["csv"] = "true"
    return f"{BASE}/leaderboard/{lb.path}", params


def normalize_leaderboard(name: str, df: pl.DataFrame, season: int) -> pl.DataFrame:
    lb = LEADERBOARDS[name]
    if lb.id_column not in df.columns:
        raise DataSourceError(f"{name}: id column {lb.id_column!r} missing; got {df.columns[:8]}")
    if lb.season_column and lb.season_column in df.columns:
        seasons = set(df[lb.season_column].drop_nulls().cast(pl.Int64).unique().to_list())
        if seasons and seasons != {season}:
            raise DataSourceError(f"{name}: asked for {season}, got seasons {sorted(seasons)}")
    if lb.id_column != "player_id":
        df = df.drop("player_id", strict=False).rename({lb.id_column: "player_id"})
    return df.with_columns(pl.col("player_id").cast(pl.Int64), pl.lit(season).alias("season"))


def normalize_pitches(df: pl.DataFrame, level: str, date: str) -> pl.DataFrame:
    if df.height >= ROW_CAP:
        raise DataSourceError(
            f"Savant returned {df.height} rows for {level} {date}: hit the {ROW_CAP}-row cap, data truncated"
        )
    if df.height == 0:
        return pl.DataFrame(schema={**PITCH_COLUMNS, "level": pl.Utf8()})
    cols = []
    for name, dtype in PITCH_COLUMNS.items():
        if name in df.columns:
            cols.append(pl.col(name).cast(dtype, strict=False))
        else:
            cols.append(pl.lit(None, dtype=dtype).alias(name))
    out = df.select(cols).with_columns(pl.lit(level).alias("level"))
    bad = out.filter(pl.col("game_date") != date)
    if bad.height:
        raise DataSourceError(
            f"Savant returned rows outside {date} for {level}: {bad['game_date'].unique().to_list()}"
        )
    return out


class Savant:
    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def leaderboard(self, name: str, season: int) -> pl.DataFrame:
        url, params = leaderboard_url(name, season)
        df = read_csv_text(self.http.get_csv_text(url, params))
        return normalize_leaderboard(name, df, season)

    def pitches_day(self, date: str, level: str, path: str, hf_level: str | None) -> pl.DataFrame:
        params: dict[str, Any] = {
            "all": "true",
            "type": "details",
            "hfGT": "R|",
            "game_date_gt": date,
            "game_date_lt": date,
        }
        if hf_level:
            params["minors"] = "true"
            params["hfLevel"] = f"{hf_level}|"
        text = self.http.get_csv_text(f"{BASE}/{path}/csv", params)
        df = read_csv_text(text, all_strings=True) if text.count("\n") > 1 else pl.DataFrame()
        return normalize_pitches(df, level, date)
