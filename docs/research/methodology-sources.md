# Methodology sources

Keys referenced from `config/ratings.yaml`. Numbers were transcribed from fetched pages;
re-verify before relying on them. (2nd) = secondary source.

## Scale

- **FG-Scale** — [Scouting Explained: the 20-80 scale](https://blogs.fangraphs.com/scouting-explained-the-20-80-scouting-scale): 50 avg, 10 pts = 1 SD, 20/80 = ±3 SD.
- **BA-Scale** — [Explaining the 20-80 scale (2026)](https://www.baseballamerica.com/stories/explaining-the-20-80-baseball-scouting-scale/): HR 80 = 40+, 50 = 19–22; SP FB 80 = 98+, 50 = 93; pop 80 ≤ 1.90 s.
- **BA-80s** — [All 13 players with 80 tools (2025 Handbook)](https://www.baseballamerica.com/stories/all-13-players-with-80-grade-tools-in-the-2025-prospect-handbook/).
- **FG-SABR / FG-SABR2** — [20-80 SABR style](https://blogs.fangraphs.com/the-20-80-scale-sabr-style/): 1 SD ≈ 23 pts AVG, 51 pts ISO, 2.0 pts SP BB%.
- **FG-Wins** — [20-80 translated to wins](https://blogs.fangraphs.com/the-20-80-scouting-scale-translated-to-wins): per 10 pts ≈ hit 1.0, power 0.5–0.9, run 0.3, field+arm 1.1 WAR.
- **Ringer** — [Reds scouting database](https://www.theringer.com/mlb/2019/3/4/18249155/cincinnati-reds-scouting-report-series-part-1-data-findings): real OFPs cluster 45–55.

## Shrinkage / stabilization

| Stat | k (Carleton N) | Notes |
|---|---|---|
| K% (H) | 60 PA | Tango x = 62, Rosenblum MiLB fit 65 |
| BB% (H) | 120 PA | Tango 96, Rosenblum 159 |
| HR | 170 PA | |
| ISO | 160 AB | |
| BABIP (H) | 820 BIP | |
| avg EV | ~18 BBE | derived from BP alpha table |
| EV90 / barrel% | 26 / 51 BBE | Rosenblum AAA forecast fit |
| K% / BB% (P) | 70 / 170 BF | |
| Stuff+ | reliable ~80 pitches | FG-Stuff; Location+ ~400 |

Sources: [FG library sample size](https://library.fangraphs.com/principles/sample-size), [Carleton BP](https://www.baseballprospectus.com/news/article/17659/), [Tango regression constants](https://www.tangotiger.net/archives/stud0274.shtml), [Rosenblum MiLB Statcast](https://fantasy.fangraphs.com/a-quick-look-into-minor-league-statcast-for-hitters/), [BP exit velocity](https://www.baseballprospectus.com/news/article/28956/).

## Translation

- **Cartwright** — [BP 2009 MLE factor selection](https://baseballprospectus.com/?p=8887): AAA→MLB all-chained K 1.20, BB .82, HR .78, non-HR hits .90; AA K 1.26, BB .73, HR .75; A+ K 1.33, BB .71, HR .73.
- **MGL-Tango** — [dual-level MLE study](https://tangotiger.net/archives/stud0262.shtml): selection correction moves HR .64→.74, K 1.28→1.20.
- **Davenport-2025** — [AAA↔MLB movers](https://claydavenport.com/archives/600): EqA gap ~−43 pts, "almost certainly an overstatement".
- **AllenTenenbaum** — [blueprint for MLEs](https://tht.fangraphs.com/a-theoretical-blueprint-for-improving-mles/): regress to level mean first.
- **Ringer-2025** — ~80% of AAA production survives to MLB; PCL vs IL differ.
- **BP-Age** — age at AAA is the single best predictor of reaching MLB.
- **Stoltz** — [age relative to level](https://www.excessiveprospectanalysis.com/post/quantifying-age-relative-to-level): ~22–25 wRC+ per year.

## Defense

- **Tango-Arm** — [arm strength offsets](https://tangotiger.com/index.php/site/comments/statcast-arm-strength-for-fielders): vs RF: CF/LF +1, SS/3B +4, 2B +7, 1B +10 mph.
- **FG-PosAdj** — positional adjustment runs/162: C +12.5, SS +7.5, 2B/3B/CF +2.5, LF/RF −7.5, 1B −12.5, DH −17.5.

## Pitching models

- **FG-Stuff** — [Stuff+/Location+/Pitching+ primer](https://library.fangraphs.com/pitching/stuff-location-and-pitching-primer): physical-only Stuff, 10 pts = 1 SD per pitch; grade within pitch type.
- **FG-PBot** — [PitchingBot](https://library.fangraphs.com/pitching/pitchingbot/): XGBoost sub-models → xRV, native 20-80.
- **PL-AAA** — [Stuff models on Triple-A](https://www.prospectslive.com/an-introduction-to-the-application-of-stuff-models-on-triple-a-data/).
- **Salorio** — [aStuff+ v2](https://adamsalorio.substack.com/p/introducing-astuff-v2): altitude adjustment, differentials mostly hurt.

## Value

- **FG-Primer2018** — FV ↔ WAR/yr bands (hitter FV 50 = 1.6–2.4).
- **FG-Val2026** — [updated prospect valuation](https://blogs.fangraphs.com/introducing-an-updated-method-for-prospect-valuation/): 50 FV hitter ≈ 7 WAR in team control, 13.5% star odds.

## Environment

- **BA-PF2022** — MiLB park factors; PCL 2022 R/9 5.92 vs IL 5.16.
- **BR-Register 2025** — league totals (AAA BB% 10.9% vs MLB 8.4%); mean ages MLB 27.9, AAA 26.5, AA 23.8, A+ 22.2, A 20.9.
- AAA uses the MLB ball since 2019; lower levels do not. ABS in AAA since 2023; MLB ABS challenge 2026.
