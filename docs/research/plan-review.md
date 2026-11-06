# Independent plan review (pre-implementation)

Summary of the critical review of the initial plan and how PR1 responded.

| Recommendation | PR1 response |
|---|---|
| Split into ~4 PRs (foundation, Statcast at scale, trained Stuff, empirical calibration) | Done; roadmap in README |
| Stuff heuristic only in PR1, no ML deps | `models/stuff.py` heuristic behind `StuffModel` protocol |
| Savant: 1-day chunks + truncation assertion | `normalize_pitches` raises at 25,000 rows |
| Join `game_pk` → statsapi for level/league | Rows tagged with requested level; schedule join available in `StatsApi.schedule` |
| Translate outcome stats only; physical stats raw | `kind: outcome|physical` in config |
| Config-default level factors; empirical estimation separate | Factors in config; estimation deferred to PR4 |
| Reference pop = all MLB weighted, true-talent SD | `reference_stats` deflation |
| League/park environment adjustment | `apply_env_normalization` + run park factors |
| Exclude MLB-established players from MiLB baselines | `mlb_established` mask on level means |
| Shrink to level mean, stat-specific k | `regression.shrink` with per-metric k |
| No xBA in Hit; bat speed into Raw Power | Done |
| Catcher defense: framing + blocking + throwing; arm within position group | Done (catchers standardized separately) |
| FV flagged experimental with explicit age rule | `fv_experimental` column; rule in config |
| One store (parquet) | polars + parquet |
| Offline CI, respx, golden tests, manual live smoke | Done |
| Data NOTICE, ≤1 rps, gzip | README NOTICE; `HttpClient` |
| Stamp methodology version + date | `methodology_version`, `graded_on` columns |
