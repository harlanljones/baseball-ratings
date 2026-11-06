"""Golden-file regression test: display grades on fixed synthetic data must not drift silently.

If a methodology change is intentional, bump METHODOLOGY_VERSION and regenerate with
``BR_UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py``.
"""

import os
from pathlib import Path

import polars as pl
from polars.testing import assert_frame_equal

from baseball_ratings.config import default_config
from baseball_ratings.pipeline import grade_season
from tests.synthetic import make_raw

GOLDEN = Path(__file__).parent / "golden"
COLS = {
    "hitters": [
        "player_id",
        "level",
        "hit",
        "raw_power",
        "game_power",
        "discipline",
        "speed",
        "field",
        "arm",
        "ofp",
        "fv",
    ],
    "pitchers": ["player_id", "level", "stuff", "control", "command", "ofp", "fv"],
}


def test_golden_grades() -> None:
    tables = grade_season(make_raw(), default_config())
    for name, cols in COLS.items():
        got = tables[name].select(cols).sort("player_id", "level")
        path = GOLDEN / f"{name}.csv"
        if os.environ.get("BR_UPDATE_GOLDEN"):
            got.write_csv(path)
        want = pl.read_csv(path, schema=got.schema)
        assert_frame_equal(got, want)
