# Product launches and analyst threads (mid-2025 → Nov 2026)

Research spike, 2026-11-06. X posts were read via mirrors; unread bodies marked UNVERIFIED.

## Launches / data changes

- **Savant 2026 zone change** ([csv-docs](https://baseballsavant.mlb.com/csv-docs),
  [changelog](https://baseballsavant.mlb.com/changelog/2026-02-19-new-strike-zone-images)):
  `plate_x/z` middle-of-plate, `sz_top/bot` ABS-defined. FG: effective zone ~2–5% smaller.
- **Savant 2025–26 additions** (MLB-only): swing path / attack angle (May 2025), swing timing &
  miss distance (Jun 2026), 1B receiving (Aug 2026), ABS value in catcher FRV (Oct 2026), ABS
  challenge leaderboards (Feb–Apr 2026).
- **MiLB data regulation** (BA Dec 2025): MLB centralizes MiLB tracking vendors from 2026;
  public coverage still AAA + FSL on Savant, though TJStats/BA publish A/A+/AA tracking-derived
  metrics → keep coverage configurable and measured per game.
- **Templates:** BA Hit+ (Oct 2026: contact%, zCon%, EV90, chase, barrel%, xwOBAcon); BA MiLB
  Stuff+ (per-pitch-type 100 scale, ≥800 pitches); FG OOPSY (EV90 as MiLB bat-speed proxy);
  THE BATcast (arm-angle-adjusted movement); FG prospect valuation (Jul 2026).
- **Libraries:** pybaseball (no PyPI release since 2023); baseballr 2.0.0 (R, minors Statcast);
  savant-extras 0.6.1 (warns Savant ignores unknown params → current season); MLB-StatsAPI 1.9.0.
- **Licensing:** MLBAM non-commercial/non-bulk; OpenCommand CC BY-NC-SA; Driveline
  OpenBiomechanics CC BY-NC-SA with pro-org exclusion.

## Threads

- Tangotiger: bat speed is largely timing; vertical swing tilt is the timing-proof metric
  ([1](https://x.com/tangotiger/status/2040460384532910475), [2](https://x.com/tangotiger/status/2071643369760030988));
  next-season data as an unbiased talent target for backtests ([3](https://x.com/tangotiger/status/2047695340522836183)).
- Eno Sarris: track ~75th-percentile bat speed ([post](https://x.com/enosarris/status/2039367116734996748));
  Location+ vs OpenCommand miss distance differ ([post](https://x.com/enosarris/status/2095971294093443563)).
- @PastTheEyeTest: temperature affects early-season bat speed ([post](https://x.com/PastTheEyeTest/status/2040479974738555138)).
- Jordan Rosenblum: EV90 into OOPSY as MiLB bat-speed proxy ([post](https://x.com/RosenJordanBlum/status/1945805397182357817)).
- TJStats: all spring-training parks now tracked ([post](https://x.com/TJStats/status/2021572472173187199)).
- Baseball America: 9 of 900 Handbook players have an 80 tool ([post](https://x.com/BaseballAmerica/status/2009325694170329438)).
- UNVERIFIED: Sutton-Brown on BP AAA StuffPro trained on MLB only (2024); Boddy on tools being
  thin Statcast wrappers (Mar 2026).

## Design implications taken into PR1

Season-aware zone handling; per-level coverage measured from data; EV90 as MiLB power signal;
per-pitch-type Stuff normalization; strong prior against 80s; non-commercial scope.
