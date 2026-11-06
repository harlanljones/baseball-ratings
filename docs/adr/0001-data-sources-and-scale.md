# ADR 0001: Data sources and the 20-80 scale

- Status: accepted (PR1)
- Date: 2026-11-06

## Context

We want scouting-style 20-80 grades for MLB and every MiLB level from public data, for
personal/non-commercial research. Requirements: one consistent scale across levels, honest
uncertainty, and traceable constants.

## Decision

### Data sources

- **MLB Stats API** for season stats (hitting/pitching/fielding, `season` + `seasonAdvanced`)
  at MLB and all MiLB levels, people/bio, teams, schedules, team home/away splits. Pulled per
  `leagueId` to avoid cross-league collapsed rows. MiLB `sabermetrics`/`expectedStatistics` are
  absent/empty, so wOBA etc. are computed locally.
- **Baseball Savant** pitch-level CSV (MLB, AAA, A/FSL) one day per level, with a hard
  assertion on the 25,000-row cap, and MLB-only leaderboards (sprint speed, bat tracking, OAA,
  arm strength, catcher framing/blocking/throwing).
- **Not used:** FanGraphs/Baseball-Reference scraping (ToS/anti-bot), pybaseball (no PyPI
  release since 2023), OpenCommand (CC BY-NC-SA, MLB-only; benchmark only), licensed feeds.
  Hand-rolled thin httpx clients chosen over `MLB-StatsAPI`/`savant-extras` to control
  validation (silent 200 failures, season fallbacks).
- MLBAM ids are shared by both sources (verified 300/300), so no ID-mapping layer.
- Storage: polars + parquet partitions under the user cache dir; nothing committed.

### Scale

- grade = 50 + 10 z, clip [20, 80], display in steps of 5.
- z against the **MLB population in the graded season**, denominator-weighted, using a
  **true-talent SD** (`var_obs / (1 + k N / sum n)`), not "qualified" players (survivorship
  bias) and not the raw observed SD (noise inflates it).
- Empirical-Bayes shrinkage toward the **level** mean with stat-specific `k` (published
  stabilization points); MiLB level means exclude MLB-established players.
- Outcome stats: env-normalize per league-season -> park adjust -> shrink -> level factor.
  Physical stats: compared raw. Level factors are config priors; empirical estimation is a
  separate calibration step (paired-player deltas carry promotion selection bias).
- Tools are blends of component z-scores, re-standardized against MLB; each grade reports
  confidence and source tier.

## Consequences

- Grades from shrunk estimates are under-dispersed vs true talent at small samples (by
  design: conservative). Variance-preserving shrinkage is a follow-up.
- AA/High-A/Rookie have no public pitch tracking: those grades are boxscore tier.
- 2026 Savant zone coordinates changed (middle-of-plate, ABS zone); zone metrics use
  per-pitch `zone`/`sz_*` so they stay internally consistent within a season but are not
  directly comparable across the 2025/2026 boundary.
- Data terms limit redistribution: exports are for personal use.
