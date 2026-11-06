# Recent papers (2024–2026) relevant to the design

Research spike, 2026-11-06. 2026 arXiv items are unreviewed preprints; numbers were extracted
through a summarizing fetch and should be re-verified.

## Most actionable

1. **Shrink without squashing; reset at changepoints.** Jaffe, Ignatiadis & Sen,
   [Constrained Denoising, Empirical Bayes, and Optimal Transport](https://arxiv.org/abs/2506.09986)
   (2025–26): plain EB posterior means under-disperse; constrain to match the latent
   distribution (incl. a joint MiLB→MLB rookie example). Glazer,
   [Changepoint detection in player metrics](https://arxiv.org/abs/2510.25961) (2025): flag
   velo/role/approach changes and widen priors. → follow-up for `scale/regression.py`.
2. **Bat speed: reliable but modest signal.** Powers & Yurko,
   [Swinging, Fast and Slow](https://arxiv.org/abs/2507.01238) (2025): measured bat speed is
   confounded by count/timing; model "intended" speed. Rosenblum (FG 2024): bat speed
   stabilizes in ~3 swings but y1 bat speed → y2 wOBA r ≈ .22 vs xwOBA .45. → bat speed is a
   30% Raw Power component, never alone.
3. **Command from locations alone.** Ludwig, Brill & Wyner,
   [Separating Intent from Execution (xCTRL)](https://arxiv.org/abs/2508.19184) (2025): Gaussian
   mixture of targets per pitcher/pitch type; FB year-to-year r ≈ .65; ≥250 pitches per bin;
   works on AAA/FSL data. OpenCommand (BP, Sept 2026) is the MLB-only video benchmark. → PR2.
4. **Normalize MiLB for ball, park, level, age.** BA (Sept 2026): MiLB HR/G +38% in 2026, ~60%
   unexplained by EV/LA (ball suspected) → don't grade MiLB power from HR rates. Ringer/Szymborski
   (2025): ~80% AAA→MLB survival, IL vs PCL factors. Stoltz (2022): ~22–25 wRC+/yr of age.
5. **FV as a calibrated outcome distribution.** Clemens (FG 2025, 2026): FV → washout/star odds;
   keep never-reached players as zero-WAR rows. Nguyen & Matthews,
   [multiple imputation aging curves](https://arxiv.org/abs/2210.02383) (JSA 2024): dropout bias.

## By topic

- **Stuff / pitch value:** FG Stuff+ primer (reliable ~80 pitches; RP→SP −5.5 pts); Judge (BP
  2023) Stuff+ y/y .74 but weak for team-switchers; DiGiovanni & Kurland,
  [tunneling](https://arxiv.org/abs/2610.35714) (2026) — sequencing as optional modifier.
- **Plate discipline:** Yee & Deshpande, [BART swing decisions](https://arxiv.org/abs/2305.05752) (JQAS).
- **Hierarchical forecasting:** Gerber & Craig, mixed-effects multinomial PA model (JQAS 2021);
  Jensen, McShane & Wyner (2009); Brown (2008).
- **Aging/envelope:** Lee, [performance envelope](https://arxiv.org/abs/2608.06635) (2026).
- **Defense:** Cerenzio, route efficiency by level (SABR 2025); Tango arm-strength definition.
- **Draft:** Kilanowski, Cape Cod League + TrackMan (SABR 2026); BA top-100 hit rates.

## Gaps found

No peer-reviewed Stuff+ paper; no validation of MiLB tracking metrics vs later MLB results; no
public AA/High-A tracking; no public MiLB OAA/catch-probability.
