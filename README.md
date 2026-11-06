# baseball-ratings

Sabermetric **20-80 scouting grades** for MLB and MiLB players, built from public data
(MLB Stats API + Baseball Savant). Python engine + `br` CLI.

| Side | Tools |
|---|---|
| Hitters | Hit, Raw Power, Game Power, Discipline, Speed |
| Fielders | Field, Arm |
| Pitchers | Stuff (overall + per pitch), Control, Command |
| Overall | OFP (present value on the FV scale), FV (experimental) |

Every grade carries a raw float, a 5-step display grade, a **confidence** (EB reliability
`n/(n+k)`), and a **source tier** (`statcast` > `leaderboard` > `boxscore`) so you can tell a
Hawk-Eye-backed AAA grade from a boxscore-only Double-A one.

## Quick start

```bash
uv sync
uv run br ingest --season 2025 --levels MLB,AAA,AA,A+,A          # season stats + MLB leaderboards
uv run br ingest --season 2025 --levels MLB,AAA,A --no-stats --no-leaderboards --statcast  # pitch-level (slow)
uv run br grade --season 2025
uv run br show --season 2025 "Witt"
uv run br leaders --season 2025 --tool raw_power --level AAA --min-n 250
uv run br export --season 2025 --format csv --out grades/
```

Pitch-level Statcast is pulled one day per level per request (Savant silently truncates at
25,000 rows), so a full season is ~200 requests per level at 1 request/second; use
`--start/--end/--limit-days` for partial pulls. Everything is cached under
`~/.cache/baseball-ratings` (`BR_CACHE_DIR`, `BR_DATA_DIR` to override).

## How grades are computed (short version)

1. **Features** per player-level: boxscore rates at every level; Statcast (EV90, barrel%,
   chase%, zone-contact%, pitch shapes, edge/heart%) where Hawk-Eye exists (MLB; AAA 2023+,
   PCL 2022; Florida State League 2021+); MLB-only leaderboards (sprint speed, bat speed, OAA,
   arm strength, catcher framing/blocking/throwing).
2. **Outcome stats** are normalized to the level's run environment (PCL vs IL...), park
   adjusted, shrunk toward the level mean, then multiplied by a level factor to get an
   MLB-equivalent. **Physical stats** (EV, velo, sprint speed, arm) are compared raw.
3. **z-scores** vs the MLB population using a true-talent SD (observed variance deflated for
   sampling noise), blended into tools, re-standardized, and mapped `grade = 50 + 10z`,
   clipped to 20-80.
4. **OFP** = tool grades -> WAR (FG "20-80 in wins" weights + positional adjustment) -> FV bands.
   **FV** = OFP + age-vs-level adjustment (flagged experimental).

All constants live in [`config/ratings.yaml`](config/ratings.yaml) with source keys. Full
write-up: [`docs/methodology.md`](docs/methodology.md). Research behind the defaults:
[`docs/research/`](docs/research/).

## Coverage by level

| Level | Season stats | Pitch tracking (Stuff/Command/EV90) | Speed/Field/Arm |
|---|---|---|---|
| MLB | yes | yes | Statcast leaderboards |
| AAA | yes | 2023+ (PCL 2022+) | boxscore proxies (low confidence) |
| AA, High-A | yes | **none public** | boxscore proxies |
| Single-A | yes | FSL only, 2021+ (not Daytona) | boxscore proxies |
| Rookie | yes (sportId 16) | none | boxscore proxies |

MiLB support starts in 2021 (the reorganization changed sportId meanings).

## Roadmap

- **PR2** full-season Statcast features at scale; intent-based command (xCTRL-style).
- **PR3** trained per-pitch run-value Stuff model (leave-pitcher-out CV, held-out season).
- **PR4** empirical level/age calibration with selection-bias handling (regress-first,
  dropout-aware), multi-year park factors, wOBA weights per season.
- Later: variance-preserving shrinkage, changepoint-aware priors, FV as a calibrated outcome
  distribution, two-way player combination, API/UI.

## Development

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

Tests are offline (synthetic, schema-faithful data + `respx` HTTP mocks). The networked
`live-smoke` workflow is manual (`workflow_dispatch`).

## NOTICE: data terms

This project downloads data from MLB Advanced Media properties (statsapi.mlb.com,
baseballsavant.mlb.com). MLBAM's notice permits "individual, non-commercial, non-bulk use"
(http://gdx.mlb.com/components/copyright.txt), and the MLB.com terms of use restrict automated
collection. This repository is a **personal, non-commercial research project**: it ships no
MLBAM data, caches responses locally, and rate-limits requests. If you use it, you are
responsible for complying with those terms. Not affiliated with MLB, MLBAM, or any club.
