# Baseball Savant: endpoints, coverage, gotchas

Research spike, 2026-11-06. [V] = probed live; [U] = from docs/page text or inference.

## Pitch-level CSV

```
MLB:  /statcast_search/csv?all=true&type=details&hfGT=R|&game_date_gt=D&game_date_lt=D
MiLB: /statcast-search-minors/csv?all=true&type=details&minors=true&hfLevel=AAA|&game_date_gt=D&game_date_lt=D
```

- Required: `all=true`, `type=details`, and `minors=true` on the minors path; missing ones
  return HTTP 200 with a header-only CSV [V]. Without `type=details` you get a 77-col
  per-player aggregate [V].
- `hfGT=R|` restricts to regular season (else spring `S` and postseason rows appear) [V].
- `hfLevel=AAA|`, `A|` filter minors levels; AA, A+, R return 0 rows [V].
- **Hard cap: 25,000 rows per request**, newest-first, oldest rows silently dropped (14-day MLB
  and 7-day AAA ranges both returned exactly 25,000) [V]. One day ≈ ≤4.8k MLB, ≤6.3k AAA+A rows.
- 119 columns, identical header (SHA-1) for MLB and minors; **no level/league column**; join
  `game_pk` = statsapi `gamePk` [V]. Bat-tracking columns empty in minors [V].
- `age_bat`/`age_pit` = age on 12/31; `*_legacy` = age on 6/30 [V].
- UTF-8 BOM; `cache-control: max-age=1200, s-maxage=3600` via Cloudflare [V].
- Minors aggregate mode (`group_by=name`, `player_type=batter`) returns per-player
  `launch_speed`, `barrels_per_bbe_percent`, `swing_miss_percent`, `xwoba`… cheaply [V].
- 2026: `plate_x/plate_z` now measured at middle of plate (front through 2025) and
  `sz_top/sz_bot` are the ABS zone (csv-docs) [U: effect on values not probed].

### MiLB tracking coverage (sampled one Saturday per season) [V]

| Season | AAA tracked | FSL (A) tracked |
|---|---|---|
| 2021 | none | 100% |
| 2022 | 34% (PCL only) | 100% |
| 2023 | 100% | 75% |
| 2024 | 100% | 99% |
| 2025 | 100% | 78% (Daytona untracked) |
| 2026 | 100% | 84% |

Savant page text: all AAA from 2023, PCL + Charlotte home games in 2022, FSL from 2021.

## Leaderboards (MLB only; append `&csv=true`) [V]

| Name | Path + params | ID column |
|---|---|---|
| sprint speed | `sprint_speed?min_season=Y&max_season=Y&position=&team=&min=0` | `player_id` |
| OAA | `outs_above_average?type=Fielder&startYear=Y&endYear=Y&split=no&range=year&min=0&pos=` | `player_id` |
| arm strength | `arm-strength?type=player&year=Y&minThrows=0` | `player_id` |
| pop time | `poptime?year=Y&min2b=5` | `entity_id` |
| framing | `catcher-framing?type=catcher&seasonStart=Y&seasonEnd=Y&gameType=Regular&minPitches=0` | `id` |
| blocking | `catcher-blocking?game_type=Regular&n=0&season_start=Y&season_end=Y&type=Cat&with_team_only=1` | `player_id` |
| throwing | `catcher-throwing?` (blocking params) | `player_id` |
| bat tracking | `bat-tracking?type=batter&seasonStart=Y&seasonEnd=Y&minSwings=0&gameType=Regular` | `id` |
| swing path | `bat-tracking/swing-path-attack-angle?` (same) | `id` |
| xStats | `expected_statistics?type=batter&year=Y&min=q` | `player_id` |
| EV/barrels | `statcast?type=batter&year=Y&min=q` | `player_id` |
| arsenal | `pitch-arsenal-stats?type=pitcher&year=Y&min=100` | `player_id` |
| movement | `pitch-movement?year=Y&min=q&pitch_type=FF` | `pitcher_id` |
| percentiles | `percentile-rankings?type=batter&year=Y` | `player_id` |

- No minors versions of any leaderboard (nav, JS bundles, 7 guessed params) [V].
- **Unknown params are silently ignored and the current season is returned** (e.g.
  `catcher-framing?year=2025` → 2026) [V]; season param names differ per endpoint (above).
- Bad params can return an HTML page with HTTP 200 [V]. `min=q` means different things per board.

## IDs and terms

- Savant ids = statsapi person ids (300/300 sampled incl. never-MLB players) [V].
- robots.txt allows all [V]; MLB.com Terms of Use prohibit "automated scripts to collect
  information" and allow personal, non-commercial use only [V].
