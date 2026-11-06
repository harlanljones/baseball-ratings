# Methodology (v2026.11-pr1)

All constants referenced here live in `config/ratings.yaml`; sources are keyed to
`docs/research/methodology-sources.md`.

## 1. The scale

`grade = 50 + 10·z`, clipped to [20, 80]; raw float kept as `<tool>_raw`, display grade rounded
to 5. 50 = MLB average, 10 points = 1 SD (FG-Scale, BA-Scale). Real scouting distributions are
thinner in the tails than a normal (BA's 2025 Handbook: 13 players of ~900 with any 80 tool),
so 75+ should be rare; shrinkage keeps small samples near 50.

**Reference population.** MLB players in the graded season, weighted by the metric's
denominator, restricted to `reference_min_n` (e.g. 300 PA). The SD is a true-talent SD:

    var_true = var_obs / (1 + k·N / Σn)

which removes the sampling-noise share of observed variance (each player's noise variance is
≈ var_true·k/n when `k` is the EB constant).

## 2. Per-metric pipeline

For metric `x` with denominator `n` and constant `k`:

1. **Environment** (boxscore outcome stats, per league row): `x · level_mean / league_mean`,
   then park: `x / (0.5·PF + 0.5)` with run park factors from team home/away splits regressed
   50% to 1.0. Rows are then collapsed to (player, level) by denominator-weighted means.
2. **Shrink** toward the level mean: `(n·x + k·μ_level)/(n + k)`. MiLB level means exclude
   players who debuted in MLB before the season (rehabs, optioned veterans).
3. **Translate** (outcome stats only): multiply by `level_factors[side][level][metric]`
   (hitters: Cartwright all-chained factors; pitchers: reciprocals as priors).
4. **z** vs the reference population (or vs the same level for MiLB-only proxies such as
   range factor; catchers vs catchers for arm strength). Sign flipped when lower is better.

Confidence = `n/(n+k)`, blended across the tool's components with the tool weights.

## 3. Tools

Weights renormalize over available components; if no primary component exists the fallback
set is used. Each blend is re-standardized against MLB (PA/BF-weighted).

| Tool | Primary components | Fallback |
|---|---|---|
| Hit | contact% (.30), K% (.35, −), zone-contact% (.20), BABIP (.15) | — |
| Raw Power | EV90 (.70), bat speed (.30) | ISO, HR/PA |
| Game Power | ISO (.45), HR/PA (.35), barrel% (.20) | — |
| Discipline | BB% (.45), chase% (.45, −), pitches/PA (.10) | — |
| Speed | sprint speed | SB attempt rate (.6), triple share (.4) |
| Field | OAA per 150 games (non-C); framing+blocking+throwing runs per 120 G (C) | range factor, fielding % vs level-position mean |
| Arm | arm strength + Tango position offset (C separate) | OF assists/9, C CS% vs level-position mean |
| Stuff | heuristic per-pitch Stuff, usage-weighted | SwStr%, K% |
| Control | BB% (−) | — |
| Command | edge% (.5), heart% (.3, −), zone% (.2) | — |

xBA is deliberately excluded from Hit (it double counts power). Bat speed is MLB-only (no
public MiLB bat tracking); EV90 is the MiLB power signal.

### Stuff (heuristic, PR1)

Within each pitch type, z-scores vs MLB for class-specific features — fastballs: velo, IVB,
extension; sinkers: velo, arm-side run; cutters: velo, glove-side break, IVB; breaking balls:
spin, movement, velo; offspeed: velo gap and drop vs the primary fastball — plus whiffs per
swing shrunk toward the MLB pitch-type mean (k = 40 swings). The blend is re-standardized per
pitch type (`pitch_grade`), and the pitcher's Stuff is the usage-weighted mean, then shrunk
(k = 80 pitches, FG-Stuff reliability) and standardized vs MLB pitchers.

### Command (PR1)

Location-only: edge% (within ±2 in of the zone border), heart% (inner 67% of the zone), and
zone%, on tracked pitches. Uses per-pitch `sz_top/sz_bot`, so 2026's ABS-defined zones stay
internally consistent within a season.

## 4. OFP and FV

**Hitters:** `WAR = 2.0 + Σ w_t·(grade_t − 50)/10 + positional_runs/10` with
`w = {hit 1.0, game_power 0.9, discipline 0.6, speed 0.3, field 0.8, arm 0.3}` (FG-Wins) and
FG positional adjustments (C +12.5 … DH −17.5 runs/162). **Pitchers:** separate SP and RP
bases (2.15 / 0.45 WAR) and weights. WAR maps to the FV scale through FanGraphs' band
midpoints (hitter FV 50 ≈ 2.0 WAR/yr).

**FV (experimental):** `OFP + age adjustment`, where years young for level (level mean age on
June 30 minus player age) earn +2.5/yr (cap +10; +5 for big leaguers), old-for-level costs
−3/yr (cap −10), and MLB players 26+ get none. This is a rule of thumb; calibrating FV to
outcome distributions (FG 2025/2026 valuation tables) is on the roadmap.

## 5. Known limitations

- Shrunk estimates are under-dispersed (Jaffe et al. 2025); grades for small samples are
  conservative.
- Level factors are literature priors; A/ROK and all pitcher factors are extrapolations.
- Park factors are single-season run factors applied to power stats too.
- 2026 MiLB home-run surge (BA, Sept 2026) is not modeled; HR-based power at MiLB is noisy, so
  Raw Power leans on EV90 where tracked.
- Two-way players are graded separately as hitter and pitcher.
- Pitch-level Statcast must be ingested for the full season for Statcast-tier grades to be
  meaningful; partial pulls just mean heavier shrinkage.
