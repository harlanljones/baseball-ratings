# MLB Stats API: MiLB data for 20-80 grades

Research spike, 2026-11-06. [V] = probed live; [U] = unverified. `BASE=https://statsapi.mlb.com/api/v1`.

## sportIds / leagues (2025) [V]

| Level | sportId | Leagues (id) |
|---|---|---|
| MLB | 1 | AL 103, NL 104 (spring: Cactus 114, Grapefruit 115 — also listed!) |
| AAA | 11 | IL 117, PCL 112 |
| AA | 12 | Eastern 113, Southern 111, Texas 109 |
| High-A | 13 | SAL 116, Midwest 118, Northwest 126 |
| Single-A | 14 | Carolina 122, **FSL 123**, California 110 |
| Rookie | 16 | ACL 121, FCL 124, DSL 130 |

**2021 reorg trap:** sportIds 13/14 swapped contents (2019: 13 = CAR/FSL/CAL). League ids are
stable; key on `leagueId` + season.

## Bulk season stats [V]

`BASE/stats?stats=season&group=hitting&season=2025&sportId=11&playerPool=ALL&limit=100000`

- Defaults: `limit` 50, `playerPool` QUALIFIED (132 of 920 AAA hitters). Use `ALL` + big limit.
- `stat.age` = age on June 30 (500/500). `position` is usage-based (≠ `primaryPosition` 243/500).
- Multi-team players collapse into one row labelled with the latest team, even across leagues
  → pull per `leagueId`.
- `totalSplits` is wrong with `sportIds=` (plural).
- `sabermetrics` MLB-only; MiLB `expectedStatistics` degenerate (xBA 0.0) → compute wOBA/FIP.
- `seasonAdvanced` (all levels): `totalSwings, swingAndMisses, ballsInPlay, iso,
  pitchesPerPlateAppearance`, batted-ball outcome counts; pitchers add `whiffPercentage`.
- Counting stats reconcile exactly with team totals (AAA 2025).
- Rates are strings (".349", ".---"); innings thirds notation ("152.2").

## People [V]

`/people?personIds=…` works to ~1,000 ids (2,000 → "URI Too Long"); use 500. Fields:
`birthDate, primaryPosition, batSide, pitchHand, draftYear, mlbDebutDate`. `hydrate=draft`
adds round/pick/bonus; no numeric scouting grades anywhere.

## Pitch tracking by level, 2025 (`/v1.1/game/{pk}/feed/live`) [V]

| Level | Tracked? |
|---|---|
| MLB | yes |
| AAA (IL, PCL) | yes, all 30 venues |
| AA, High-A, Carolina, California, Rookie | **no** |
| FSL | 9 of 10 venues (not Daytona) |

History: FSL 2021+, PCL 2022, all AAA 2023+. Tracked fields: `pitchData.startSpeed, extension,
breaks.spinRate, breakVerticalInduced…`, `hitData.launchSpeed/launchAngle`. Untracked games have
only stringer trajectory/hardness.

## Fielding [V]

Per (player, position): innings, games, chances, PO, A, E, DP, fielding %, range factors, and
catcher SB/CS/PB/WP. No MiLB OAA/framing/arm.

## Environment [V]

- Team totals: `teams/stats?stats=season&group=hitting&sportIds=11&gameType=R`.
- Park factors: `teams/stats?stats=statSplits&sitCodes=h,a&group=hitting|pitching…&limit=1000`.
- AAA 2025: IL 4.94 R/team-game, PCL 5.83; raw single-season run PF 0.73 (Toledo) – 1.30 (Las Vegas).

## Terms / limits [V]

Copyright notice: "Only individual, non-commercial, non-bulk use of the Materials is permitted."
No rate-limit headers, no 429s observed; Varnish CDN (`/stats` max-age 300 s). Send gzip.
