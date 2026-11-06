"""End-to-end grading on synthetic data."""

import polars as pl
import pytest

from baseball_ratings.config import default_config
from baseball_ratings.pipeline import grade_season
from baseball_ratings.scale.levels import apply_env_normalization, fv_age_adjustment
from baseball_ratings.version import METHODOLOGY_VERSION
from tests.synthetic import make_raw


@pytest.fixture(scope="module")
def tables() -> dict[str, pl.DataFrame]:
    return grade_season(make_raw(), default_config())


def test_tables_and_stamps(tables: dict[str, pl.DataFrame]) -> None:
    assert {"hitters", "pitchers", "pitch_grades"} <= set(tables)
    for df in tables.values():
        assert df["methodology_version"].unique().to_list() == [METHODOLOGY_VERSION]
    h = tables["hitters"]
    for tool in ("hit", "raw_power", "game_power", "discipline", "speed", "field", "arm", "ofp", "fv"):
        assert tool in h.columns
        vals = h[tool].drop_nulls()
        assert vals.min() >= 20 and vals.max() <= 80
        assert all(v % 5 == 0 for v in vals.to_list())


def test_mlb_regulars_center_on_50(tables: dict[str, pl.DataFrame]) -> None:
    h = tables["hitters"].filter((pl.col("level") == "MLB") & (pl.col("pa") >= 300))
    for tool in ("hit", "game_power", "discipline"):
        assert h[f"{tool}_raw"].mean() == pytest.approx(50, abs=4)
        assert 5 < h[f"{tool}_raw"].std() < 13


def test_minor_leaguers_grade_below_mlb(tables: dict[str, pl.DataFrame]) -> None:
    """Synthetic MiLB players have the same talent distribution but face easier competition:
    level translation must pull their outcome grades below MLB, and lower levels further."""
    h = tables["hitters"]
    means = {lvl: h.filter(pl.col("level") == lvl)["hit_raw"].mean() for lvl in ("MLB", "AAA", "AA")}
    assert means["MLB"] > means["AAA"] > means["AA"]


def test_tiers_follow_data_availability(tables: dict[str, pl.DataFrame]) -> None:
    h = tables["hitters"]
    aa = h.filter(pl.col("level") == "AA")
    assert set(aa["raw_power_tier"].drop_nulls().unique().to_list()) == {"boxscore"}
    mlb = h.filter((pl.col("level") == "MLB") & (pl.col("pa") >= 300))
    assert "statcast" in mlb["raw_power_tier"].to_list()
    p = tables["pitchers"]
    assert set(p.filter(pl.col("level") == "AA")["stuff_tier"].drop_nulls().to_list()) == {"boxscore"}


def test_confidence_grows_with_sample(tables: dict[str, pl.DataFrame]) -> None:
    h = tables["hitters"].filter(pl.col("level") == "MLB")
    small = h.filter(pl.col("pa") < 100)["hit_conf"].mean()
    big = h.filter(pl.col("pa") > 500)["hit_conf"].mean()
    assert big > small


def test_pitch_grades_per_type(tables: dict[str, pl.DataFrame]) -> None:
    pg = tables["pitch_grades"]
    assert set(pg["pitch_type"].unique().to_list()) <= {"FF", "SL", "CH"}
    mlb_ff = pg.filter((pl.col("level") == "MLB") & (pl.col("pitch_type") == "FF") & (pl.col("n") >= 25))
    assert mlb_ff["pitch_z"].mean() == pytest.approx(0, abs=0.35)


def test_env_normalization_equalizes_leagues() -> None:
    cfg = default_config()
    df = pl.DataFrame(
        {
            "level": ["AAA"] * 4,
            "league_id": [112, 112, 117, 117],
            "team_id": [1, 2, 3, 4],
            "iso": [0.20, 0.22, 0.15, 0.17],
            "ab": [400.0] * 4,
        }
    )
    out = apply_env_normalization(df, [("iso", "ab", False)], cfg, None)
    by = out.group_by("league_id").agg(pl.col("iso").mean()).sort("league_id")["iso"].to_list()
    assert by[0] == pytest.approx(by[1])


def test_fv_age_adjustment_caps() -> None:
    cfg = default_config()
    df = pl.DataFrame({"level": ["AA", "AA", "MLB", "MLB"], "age": [17.0, 31.0, 22.0, 30.0]})
    adj = df.select(fv_age_adjustment(cfg, "hitter")).to_series().to_list()
    assert adj[0] == cfg.fv.cap_up
    assert adj[1] == -cfg.fv.cap_down
    assert 0 < adj[2] <= cfg.fv.mlb_cap_up
    assert adj[3] == 0


def test_physical_metrics_are_not_level_translated() -> None:
    cfg = default_config()
    for name, m in cfg.metrics.items():
        if m.kind == "physical":
            assert all(name not in f for f in cfg.level_factors["hitter"].values())
