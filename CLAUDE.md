# CLAUDE.md

Python 3.12+, uv, src layout (`src/baseball_ratings`). CLI entry point `br` (`cli.py`).

## Commands

- Check everything: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
- Regenerate golden grades after an intentional methodology change (also bump
  `METHODOLOGY_VERSION` in `version.py`): `BR_UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py`
- Live smoke (network): `uv run br ingest --season 2025 --levels MLB,AAA --statcast --start 2025-07-12 --limit-days 2 && uv run br grade --season 2025`

## Layout

- `ingest/` HTTP clients. `http.py` caches + rate-limits + validates (both MLB endpoints return
  HTTP 200 for errors). `statsapi.py`, `savant.py` encode the endpoint gotchas in docstrings.
- `features/` raw -> per (player, level/league) metrics. `grades/build.py` assembles tables.
- `scale/` the math: `scale.py` (z, true-talent SD, 20-80), `regression.py` (EB shrink),
  `levels.py` (env normalization, level factors, age-vs-level).
- `grades/engine.py` is generic and config-driven: add a metric in `config/ratings.yaml`
  (`metrics:`) and reference it from a tool (`tools:`); no code change needed if the feature
  column exists.
- `models/stuff.py` Stuff behind a `StuffModel` protocol (heuristic now, trained model later).

## Rules

- Every constant goes in `config/ratings.yaml` with a source key or `UNSOURCED`.
- Outcome stats get env-normalized + level-translated; physical stats never do.
- Never commit raw MLBAM/Savant data (terms). Tests use `tests/synthetic.py`.
- Savant pitch pulls: one day per level; keep the 25k-row cap assertion.
- `docs/research/` holds the sourced research behind defaults; cite it when changing constants.
