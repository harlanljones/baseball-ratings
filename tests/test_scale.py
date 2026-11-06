import itertools
import math
import random

import polars as pl
import pytest
from hypothesis import given
from hypothesis import strategies as st

from baseball_ratings.config import ScaleCfg
from baseball_ratings.scale.regression import reliability, shrink
from baseball_ratings.scale.scale import (
    display_grade,
    grade_from_z,
    grade_value,
    interpolate,
    plain_stats,
    reference_stats,
)

CFG = ScaleCfg()


def test_grade_mapping_anchors() -> None:
    assert grade_value(0, CFG) == 50
    assert grade_value(1, CFG) == 60
    assert grade_value(-2, CFG) == 30
    assert grade_value(4, CFG) == 80  # clipped
    assert grade_value(-9, CFG) == 20


def test_display_rounds_to_five() -> None:
    df = pl.DataFrame({"g": [52.4, 52.6, 77.6, 19.0, 81.0]})
    out = df.select(display_grade(pl.col("g"), CFG)).to_series().to_list()
    assert out == [50, 55, 80, 20, 80]


@given(st.lists(st.floats(-6, 6), min_size=2, max_size=50))
def test_grade_is_monotone_and_bounded(zs: list[float]) -> None:
    zs = sorted(zs)
    grades = pl.DataFrame({"z": zs}).select(grade_from_z(pl.col("z"), CFG)).to_series().to_list()
    assert all(20 <= g <= 80 for g in grades)
    assert all(a <= b for a, b in itertools.pairwise(grades))


def test_reference_sd_is_deflated_to_true_talent() -> None:
    """Simulate binomial rates: the deflated SD should recover the true-talent SD."""
    rng = random.Random(1)
    p_mean, sd_true = 0.22, 0.04
    k = p_mean * (1 - p_mean) / sd_true**2  # noise/true variance ratio in PA units
    xs, ns = [], []
    for _ in range(3000):
        p = min(max(rng.gauss(p_mean, sd_true), 0.01), 0.99)
        n = rng.choice([100, 200, 400, 600])
        xs.append(sum(rng.random() < p for _ in range(n)) / n)
        ns.append(float(n))
    ref = reference_stats(pl.Series(xs), pl.Series(ns), k)
    assert ref is not None
    assert ref.mean == pytest.approx(p_mean, abs=0.003)
    assert ref.sd == pytest.approx(sd_true, rel=0.08)
    naive = plain_stats(pl.Series(xs), pl.Series(ns))
    assert naive is not None and naive.sd > ref.sd


def test_reference_stats_needs_three_players() -> None:
    assert reference_stats(pl.Series([0.1, 0.2]), pl.Series([100.0, 100.0]), 50) is None


def test_shrink_limits() -> None:
    df = pl.DataFrame({"x": [0.40, 0.40, 0.40, None], "n": [0.0, 60.0, 1e9, 100.0], "mu": [0.2] * 4})
    out = df.select(shrink(pl.col("x"), pl.col("n"), pl.col("mu"), 60)).to_series().to_list()
    assert out[0] == pytest.approx(0.2)
    assert out[1] == pytest.approx(0.3)  # n == k -> halfway
    assert out[2] == pytest.approx(0.4, abs=1e-6)
    assert out[3] is None
    rel = df.select(reliability(pl.col("n"), 60)).to_series().to_list()
    assert rel[0] == 0 and rel[1] == pytest.approx(0.5)


def test_interpolate() -> None:
    table = [(0.0, 40.0), (2.0, 50.0), (4.0, 60.0)]
    assert interpolate(1.0, table) == 45
    assert interpolate(-5, table) == 40
    assert interpolate(9, table) == 60
    assert math.isclose(interpolate(3.0, table), 55)
