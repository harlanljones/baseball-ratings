import httpx
import polars as pl
import pytest
import respx

from baseball_ratings.ingest.http import DataSourceError, HttpClient, check_csv_text, strip_bom
from baseball_ratings.ingest.savant import (
    ROW_CAP,
    Savant,
    leaderboard_url,
    normalize_leaderboard,
    normalize_pitches,
)
from baseball_ratings.ingest.statsapi import StatsApi, parse_innings, parse_number


@pytest.fixture
def http(tmp_path):  # type: ignore[no-untyped-def]
    return HttpClient(cache_dir=tmp_path, min_interval_s=0.0, max_retries=0)


def test_parse_number_and_innings() -> None:
    assert parse_number(".349") == pytest.approx(0.349)
    assert parse_number(".---") is None
    assert parse_number("-.--") is None
    assert parse_number("-1.5") == -1.5
    assert parse_number(12) == 12.0
    assert parse_innings("152.2") == pytest.approx(152 + 2 / 3)
    assert parse_innings("10.0") == 10.0


def test_bom_and_html_detection() -> None:
    assert strip_bom("﻿a,b") == "a,b"
    with pytest.raises(DataSourceError):
        check_csv_text("<!DOCTYPE html><html>", "u")
    with pytest.raises(DataSourceError):
        check_csv_text("   ", "u")


@respx.mock
def test_season_stats_flatten_and_cache(http: HttpClient) -> None:
    payload = {
        "stats": [
            {
                "splits": [
                    {
                        "player": {"id": 1, "fullName": "A B"},
                        "team": {"id": 10, "name": "T"},
                        "league": {"id": 112},
                        "sport": {"id": 11},
                        "position": {"abbreviation": "SS"},
                        "numTeams": 1,
                        "stat": {"age": 22, "plateAppearances": 400, "avg": ".301", "babip": ".---"},
                    }
                ]
            }
        ]
    }
    route = respx.get("https://statsapi.mlb.com/api/v1/stats").mock(
        return_value=httpx.Response(200, json=payload)
    )
    api = StatsApi(http)
    df = api.season_stats("hitting", 11, 2025, league_id=112)
    assert df.height == 1
    row = df.row(0, named=True)
    assert row["player_id"] == 1 and row["position"] == "SS" and row["avg"] == pytest.approx(0.301)
    assert row["babip"] is None and row["season"] == 2025
    sent = route.calls[0].request.url.params
    assert sent["playerPool"] == "ALL" and int(sent["limit"]) >= 100000 and sent["leagueId"] == "112"
    api.season_stats("hitting", 11, 2025, league_id=112)
    assert route.call_count == 1  # served from cache


@respx.mock
def test_api_error_body_raises(http: HttpClient) -> None:
    respx.get("https://statsapi.mlb.com/api/v1/stats").mock(
        return_value=httpx.Response(200, json={"message": "Internal error occurred"})
    )
    with pytest.raises(DataSourceError):
        StatsApi(http).season_stats("hitting", 1, 2025)


def test_milb_pre_2021_rejected(http: HttpClient) -> None:
    with pytest.raises(ValueError):
        StatsApi(http).season_stats("hitting", 13, 2019)


@respx.mock
def test_people_batches_of_500(http: HttpClient) -> None:
    route = respx.get("https://statsapi.mlb.com/api/v1/people").mock(
        return_value=httpx.Response(200, json={"people": [{"id": 1, "fullName": "X"}]})
    )
    StatsApi(http).people(range(1, 1002))
    assert route.call_count == 3


def _pitch_frame(n: int, date: str = "2025-07-12") -> pl.DataFrame:
    return pl.DataFrame({"game_pk": ["1"] * n, "game_date": [date] * n, "release_speed": ["95.1"] * n})


def test_row_cap_raises() -> None:
    with pytest.raises(DataSourceError, match="cap"):
        normalize_pitches(_pitch_frame(ROW_CAP), "MLB", "2025-07-12")


def test_pitch_normalize_casts_and_tags() -> None:
    out = normalize_pitches(_pitch_frame(3), "AAA", "2025-07-12")
    assert out["level"].to_list() == ["AAA"] * 3
    assert out["release_speed"].dtype == pl.Float64 and out["game_pk"].dtype == pl.Int64
    assert "launch_speed" in out.columns  # missing columns filled with nulls


def test_pitch_rows_outside_date_raise() -> None:
    with pytest.raises(DataSourceError, match="outside"):
        normalize_pitches(_pitch_frame(3, "2025-07-11"), "MLB", "2025-07-12")


def test_leaderboard_params_carry_season_everywhere() -> None:
    for name in ("sprint_speed", "oaa", "catcher_framing", "catcher_blocking", "bat_tracking"):
        _, params = leaderboard_url(name, 2024)
        season_values = [v for k, v in params.items() if "year" in k.lower() or "season" in k.lower()]
        assert season_values and all(v == 2024 for v in season_values), name
        assert params["csv"] == "true"


def test_leaderboard_season_mismatch_and_id_rename() -> None:
    df = pl.DataFrame({"player_id": [1, 2], "year": [2026, 2026], "arm_overall": [90.0, 85.0]})
    with pytest.raises(DataSourceError, match="asked for 2025"):
        normalize_leaderboard("arm_strength", df, 2025)
    framing = pl.DataFrame({"id": [7], "rv_tot": [3.2]})
    out = normalize_leaderboard("catcher_framing", framing, 2025)
    assert out["player_id"].to_list() == [7]


@respx.mock
def test_savant_day_pull_params(http: HttpClient) -> None:
    csv = "﻿game_pk,game_date,release_speed\n1,2025-07-12,95.0\n"
    route = respx.get("https://baseballsavant.mlb.com/statcast-search-minors/csv").mock(
        return_value=httpx.Response(200, text=csv)
    )
    df = Savant(http).pitches_day("2025-07-12", "AAA", "statcast-search-minors", "AAA")
    assert df.height == 1
    params = route.calls[0].request.url.params
    assert params["minors"] == "true" and params["hfLevel"] == "AAA|" and params["all"] == "true"
    assert params["game_date_gt"] == params["game_date_lt"] == "2025-07-12"


@respx.mock
def test_savant_html_response_raises(http: HttpClient) -> None:
    respx.get(url__startswith="https://baseballsavant.mlb.com/leaderboard/").mock(
        return_value=httpx.Response(200, text="<html><body>oops</body></html>")
    )
    with pytest.raises(DataSourceError, match="HTML"):
        Savant(http).leaderboard("sprint_speed", 2025)
