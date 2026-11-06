"""MLB Stats API (statsapi.mlb.com) client for MLB + MiLB season data.

Gotchas encoded here (all verified, see docs/research/statsapi.md):
- ``limit`` defaults to 50 and ``playerPool`` to QUALIFIED; we always send ``ALL`` + a big limit.
- A player traded across leagues gets one collapsed row labelled with his latest team, so season
  stats are pulled per ``leagueId`` to keep each row inside one run environment.
- ``sabermetrics`` (wOBA/FIP) is MLB-only; MiLB ``expectedStatistics`` is empty. We compute those.
- sportId 13/14 changed meaning in the 2021 reorganization; only 2021+ is supported for MiLB.
- Rate fields arrive as strings (".349", ".---"); innings as thirds notation ("152.2").
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

import polars as pl

from baseball_ratings.ingest.http import DataSourceError, HttpClient

BASE = "https://statsapi.mlb.com/api/v1"
MIN_MILB_SEASON = 2021
PEOPLE_BATCH = 500

_STRING_KEEP = {"position", "player_name", "team_name", "league_name", "split_code", "birth_date"}


def parse_number(value: Any) -> float | None:
    """Convert statsapi values ("1.000", ".---", 12, "-.--") to float/None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    s = str(value).strip()
    if not s or set(s) <= set("-.*"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_innings(value: Any) -> float | None:
    """'152.2' (thirds notation) -> 152.667."""
    if value is None:
        return None
    s = str(value)
    if "." in s:
        whole, frac = s.split(".", 1)
        try:
            return int(whole) + int(frac or 0) / 3.0
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _flatten_split(split: dict[str, Any]) -> dict[str, Any]:
    stat = split.get("stat", {})
    player = split.get("player", {})
    team = split.get("team", {})
    league = split.get("league", {})
    sport = split.get("sport", {})
    position = split.get("position", {})
    row: dict[str, Any] = {
        "player_id": player.get("id"),
        "player_name": player.get("fullName"),
        "team_id": team.get("id"),
        "team_name": team.get("name"),
        "league_id": league.get("id"),
        "sport_id": sport.get("id"),
        "position": position.get("abbreviation"),
        "num_teams": split.get("numTeams"),
    }
    for key, value in stat.items():
        if key == "innings" or key == "inningsPitched":
            row[key] = parse_innings(value)
        elif isinstance(value, dict):
            continue
        else:
            row[key] = parse_number(value)
    return row


def splits_to_frame(splits: Iterable[dict[str, Any]]) -> pl.DataFrame:
    rows = [_flatten_split(s) for s in splits]
    if not rows:
        return pl.DataFrame()
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    data = {k: [r.get(k) for r in rows] for k in keys}
    schema = {
        k: (
            pl.Utf8
            if k in _STRING_KEEP
            else pl.Int64
            if k.endswith("_id") or k == "num_teams"
            else pl.Float64
        )
        for k in keys
    }
    return pl.DataFrame(data, schema=schema, strict=False)


class StatsApi:
    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def _get(self, path: str, **params: Any) -> Any:
        return self.http.get_json(f"{BASE}/{path}", {k: v for k, v in params.items() if v is not None})

    # -- reference data --------------------------------------------------------------------
    def leagues(self, sport_id: int, season: int) -> list[dict[str, Any]]:
        """Regular-season leagues: those that have teams this season (drops spring/winter leagues
        such as Cactus 114 / Grapefruit 115 that /leagues also lists under sportId=1)."""
        teams = self.teams(sport_id, season)
        league_ids = set(teams["league_id"].drop_nulls().to_list()) if teams.height else set()
        data = self._get("leagues", sportId=sport_id, season=season)
        return [
            lg
            for lg in data.get("leagues", [])
            if lg.get("sport", {}).get("id") == sport_id and lg.get("id") in league_ids
        ]

    def teams(self, sport_id: int, season: int) -> pl.DataFrame:
        data = self._get("teams", sportId=sport_id, season=season)
        rows = [
            {
                "team_id": t["id"],
                "team_name": t.get("name"),
                "abbreviation": t.get("abbreviation"),
                "league_id": t.get("league", {}).get("id"),
                "venue_id": t.get("venue", {}).get("id"),
                "parent_org_id": t.get("parentOrgId"),
                "sport_id": sport_id,
            }
            for t in data.get("teams", [])
        ]
        return pl.DataFrame(rows, strict=False) if rows else pl.DataFrame()

    # -- season stats ----------------------------------------------------------------------
    def season_stats(
        self,
        group: str,
        sport_id: int,
        season: int,
        stat_type: str = "season",
        league_id: int | None = None,
    ) -> pl.DataFrame:
        if sport_id != 1 and season < MIN_MILB_SEASON:
            raise ValueError(f"MiLB seasons before {MIN_MILB_SEASON} use a different sportId map")
        data = self._get(
            "stats",
            stats=stat_type,
            group=group,
            season=season,
            sportId=sport_id,
            leagueId=league_id,
            playerPool="ALL",
            gameType="R",
            limit=100000,
        )
        stats = data.get("stats", [])
        splits = stats[0].get("splits", []) if stats else []
        df = splits_to_frame(splits)
        if df.height:
            df = df.with_columns(pl.lit(season).alias("season"))
        return df

    def season_stats_by_league(
        self, group: str, sport_id: int, season: int, stat_type: str = "season"
    ) -> pl.DataFrame:
        frames = []
        for lg in self.leagues(sport_id, season):
            df = self.season_stats(group, sport_id, season, stat_type, league_id=lg["id"])
            if df.height:
                frames.append(df.with_columns(pl.lit(lg["id"], dtype=pl.Int64).alias("league_id")))
        return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()

    def team_home_away(self, group: str, sport_id: int, season: int) -> pl.DataFrame:
        data = self._get(
            "teams/stats",
            stats="statSplits",
            sitCodes="h,a",
            group=group,
            season=season,
            sportIds=sport_id,
            gameType="R",
            limit=1000,
        )
        rows = []
        for block in data.get("stats", []):
            for s in block.get("splits", []):
                stat = s.get("stat", {})
                rows.append(
                    {
                        "team_id": s.get("team", {}).get("id"),
                        "split_code": s.get("split", {}).get("code"),
                        "games": parse_number(stat.get("gamesPlayed")),
                        "runs": parse_number(stat.get("runs")),
                        "home_runs": parse_number(stat.get("homeRuns")),
                        "pa": parse_number(stat.get("plateAppearances") or stat.get("battersFaced")),
                    }
                )
        return pl.DataFrame(rows, strict=False) if rows else pl.DataFrame()

    # -- people ----------------------------------------------------------------------------
    def people(self, ids: Iterable[int]) -> pl.DataFrame:
        id_list = sorted({int(i) for i in ids})
        rows: list[dict[str, Any]] = []
        for chunk in _chunks(id_list, PEOPLE_BATCH):
            data = self._get("people", personIds=",".join(map(str, chunk)))
            for p in data.get("people", []):
                rows.append(
                    {
                        "player_id": p["id"],
                        "player_name": p.get("fullName"),
                        "birth_date": p.get("birthDate"),
                        "primary_position": p.get("primaryPosition", {}).get("abbreviation"),
                        "bats": p.get("batSide", {}).get("code"),
                        "throws": p.get("pitchHand", {}).get("code"),
                        "mlb_debut_date": p.get("mlbDebutDate"),
                        "draft_year": p.get("draftYear"),
                    }
                )
        return pl.DataFrame(rows, strict=False) if rows else pl.DataFrame()

    def search_people(self, name: str) -> list[dict[str, Any]]:
        data = self._get("people/search", names=name)
        return list(data.get("people", []))

    # -- schedule (game_pk -> level/league/venue for Savant joins) --------------------------
    def schedule(self, sport_id: int, date: str) -> pl.DataFrame:
        data = self._get("schedule", sportId=sport_id, date=date, gameType="R")
        rows = []
        for d in data.get("dates", []):
            for g in d.get("games", []):
                rows.append(
                    {
                        "game_pk": g["gamePk"],
                        "game_date": d.get("date"),
                        "sport_id": sport_id,
                        "venue_id": g.get("venue", {}).get("id"),
                        "home_team_id": g.get("teams", {}).get("home", {}).get("team", {}).get("id"),
                        "away_team_id": g.get("teams", {}).get("away", {}).get("team", {}).get("id"),
                    }
                )
        return pl.DataFrame(rows, strict=False) if rows else pl.DataFrame()


def _chunks(items: list[int], size: int) -> Iterator[list[int]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


__all__ = ["DataSourceError", "StatsApi", "parse_innings", "parse_number", "splits_to_frame"]
