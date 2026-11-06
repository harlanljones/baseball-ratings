"""Synthetic, schema-faithful data for offline tests (no MLBAM data is committed to the repo)."""

from __future__ import annotations

import random
from dataclasses import dataclass

import polars as pl

from baseball_ratings.grades.build import RawSeason

LEVEL_SPORT = {"MLB": 1, "AAA": 11, "AA": 12}
LEVEL_LEAGUES = {"MLB": [103, 104], "AAA": [112, 117], "AA": [109, 113]}
POSITIONS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]
PITCH_TYPES = [("FF", 0.55), ("SL", 0.25), ("CH", 0.20)]


@dataclass
class Hitter:
    pid: int
    level: str
    league: int
    talent: float  # standard-normal overall bat talent
    power: float  # EV-ish physical power talent
    pa: int
    age: float
    position: str


def _hitters(rng: random.Random, n_per_level: int) -> list[Hitter]:
    out = []
    pid = 100_000
    for level in LEVEL_SPORT:
        for i in range(n_per_level):
            pid += 1
            pa = rng.choice([40, 120, 300, 500, 650]) if level == "MLB" else rng.choice([80, 250, 450])
            out.append(
                Hitter(
                    pid=pid,
                    level=level,
                    league=LEVEL_LEAGUES[level][i % 2],
                    talent=rng.gauss(0, 1),
                    power=rng.gauss(0, 1),
                    pa=pa,
                    age={"MLB": 28.0, "AAA": 26.0, "AA": 23.5}[level] + rng.uniform(-3, 3),
                    position=POSITIONS[i % len(POSITIONS)],
                )
            )
    return out


def _binom(rng: random.Random, n: int, p: float) -> int:
    p = min(max(p, 0.001), 0.999)
    return sum(1 for _ in range(n) if rng.random() < p)


def make_raw(seed: int = 7, n_per_level: int = 80, with_pitches: bool = True) -> RawSeason:
    rng = random.Random(seed)
    hitters = _hitters(rng, n_per_level)
    # Lower levels: easier competition -> fewer K, more walks/power (the level effect).
    lvl_shift = {"MLB": 0.0, "AAA": 0.25, "AA": 0.45}
    # PCL (112) is a hitter-friendly league: inflate its outcomes.
    league_boost = {112: 0.3}
    hit_rows, adv_rows, fld_rows, ppl = [], [], [], []
    for h in hitters:
        b = h.talent + lvl_shift[h.level] + league_boost.get(h.league, 0.0)
        k = _binom(rng, h.pa, 0.22 - 0.035 * b)
        bb = _binom(rng, h.pa, 0.085 + 0.02 * b)
        hr = _binom(rng, h.pa, 0.03 + 0.008 * (b + h.power))
        ab = h.pa - bb
        bip = max(ab - k - hr, 1)
        hits_bip = _binom(rng, bip, 0.29 + 0.01 * b)
        doubles = _binom(rng, hits_bip, 0.2)
        triples = _binom(rng, hits_bip, 0.02)
        hits = hits_bip + hr
        swings = int(h.pa * 2.0)
        whiffs = _binom(rng, swings, 0.25 - 0.03 * b)
        team = h.league * 10 + (h.pid % 3)
        hit_rows.append(
            {
                "player_id": h.pid,
                "player_name": f"Hitter {h.pid}",
                "team_id": team,
                "team_name": f"Team {team}",
                "league_id": h.league,
                "sport_id": LEVEL_SPORT[h.level],
                "position": h.position,
                "age": float(round(h.age)),
                "plateAppearances": float(h.pa),
                "atBats": float(ab),
                "hits": float(hits),
                "doubles": float(doubles),
                "triples": float(triples),
                "homeRuns": float(hr),
                "baseOnBalls": float(bb),
                "intentionalWalks": 0.0,
                "hitByPitch": 0.0,
                "strikeOuts": float(k),
                "stolenBases": float(_binom(rng, 10, 0.5)),
                "caughtStealing": float(_binom(rng, 4, 0.3)),
                "numberOfPitches": float(h.pa * 4),
                "sacFlies": 0.0,
                "totalBases": float(hits + doubles + 2 * triples + 3 * hr),
                "season": 2025,
            }
        )
        adv_rows.append(
            {
                "player_id": h.pid,
                "league_id": h.league,
                "totalSwings": float(swings),
                "swingAndMisses": float(whiffs),
            }
        )
        games = h.pa / 4.2
        fld_rows.append(
            {
                "player_id": h.pid,
                "sport_id": LEVEL_SPORT[h.level],
                "league_id": h.league,
                "position": h.position,
                "innings": games * 8.5,
                "games": games,
                "chances": games * 3,
                "putOuts": games * 2.2,
                "assists": games * 0.7 + rng.gauss(0, 1),
                "errors": games * 0.05,
                "stolenBases": games * 0.5 if h.position == "C" else 0.0,
                "caughtStealing": games * 0.15 if h.position == "C" else 0.0,
            }
        )
        ppl.append({"player_id": h.pid, "mlb_debut_date": "2019-04-01" if h.level == "MLB" else None})

    pit_rows, padv_rows, pitchers = [], [], []
    pid = 500_000
    for level in LEVEL_SPORT:
        for i in range(n_per_level):
            pid += 1
            stuff = rng.gauss(0, 1)
            control = rng.gauss(0, 1)
            bf = rng.choice([60, 200, 450, 700])
            starter = bf >= 450
            k = _binom(rng, bf, 0.22 + 0.04 * stuff + 0.03 * lvl_shift[level])
            bb = _binom(rng, bf, 0.085 - 0.015 * control)
            pitches = bf * 4
            league = LEVEL_LEAGUES[level][i % 2]
            pit_rows.append(
                {
                    "player_id": pid,
                    "player_name": f"Pitcher {pid}",
                    "team_id": league * 10 + (pid % 3),
                    "league_id": league,
                    "sport_id": LEVEL_SPORT[level],
                    "position": "P",
                    "age": float(rng.randint(21, 33)),
                    "battersFaced": float(bf),
                    "strikeOuts": float(k),
                    "baseOnBalls": float(bb),
                    "numberOfPitches": float(pitches),
                    "gamesPlayed": 30.0 if starter else 50.0,
                    "gamesStarted": 30.0 if starter else 0.0,
                    "inningsPitched": bf / 4.2,
                    "season": 2025,
                }
            )
            padv_rows.append(
                {
                    "player_id": pid,
                    "league_id": league,
                    "swingAndMisses": float(_binom(rng, pitches, 0.11 + 0.02 * stuff)),
                }
            )
            pitchers.append((pid, level, stuff, control, pitches))
            ppl.append({"player_id": pid, "mlb_debut_date": None})

    pitches_df = _pitches(rng, hitters, pitchers) if with_pitches else pl.DataFrame()
    teams = sorted({r["team_id"] for r in hit_rows + pit_rows})
    ha = pl.DataFrame(
        [
            {
                "team_id": t,
                "split_code": code,
                "games": 70.0,
                "runs": 330.0 * (1.15 if (t // 10) == 112 and code == "h" else 1.0),
            }
            for t in teams
            for code in ("h", "a")
        ]
    )
    from baseball_ratings.config import default_config
    from baseball_ratings.env import park_factors

    return RawSeason(
        season=2025,
        hitting=pl.DataFrame(hit_rows),
        hitting_adv=pl.DataFrame(adv_rows),
        pitching=pl.DataFrame(pit_rows),
        pitching_adv=pl.DataFrame(padv_rows),
        fielding=pl.DataFrame(fld_rows),
        people=pl.DataFrame(ppl, schema={"player_id": pl.Int64, "mlb_debut_date": pl.Utf8}),
        park=park_factors(ha, default_config()),
        pitches=pitches_df,
        leaderboards={},
    )


def _pitches(
    rng: random.Random, hitters: list[Hitter], pitchers: list[tuple[int, str, float, float, int]]
) -> pl.DataFrame:
    rows = []
    tracked_levels = {"MLB", "AAA"}
    by_level: dict[str, list[Hitter]] = {}
    for h in hitters:
        by_level.setdefault(h.level, []).append(h)
    game_pk = 1
    for pid, level, stuff, control, n in pitchers:
        if level not in tracked_levels:
            continue
        pool = by_level[level]
        for j in range(min(n, 400)):
            h = pool[j % len(pool)]
            pt = rng.choices([p for p, _ in PITCH_TYPES], weights=[w for _, w in PITCH_TYPES])[0]
            velo = {"FF": 94, "SL": 85, "CH": 86}[pt] + 1.5 * stuff + rng.gauss(0, 0.8)
            ivb = {"FF": 15, "SL": 1, "CH": 6}[pt] + (1.5 * stuff if pt == "FF" else 0) + rng.gauss(0, 1)
            in_zone = rng.random() < 0.48 + 0.04 * control
            px = rng.uniform(-0.6, 0.6) if in_zone else rng.choice([-1, 1]) * rng.uniform(0.8, 1.6)
            pz = (
                rng.uniform(1.7, 3.3)
                if in_zone
                else rng.choice([rng.uniform(0.5, 1.4), rng.uniform(3.6, 4.4)])
            )
            swing = rng.random() < (0.65 if in_zone else 0.30 - 0.05 * h.talent)
            whiff = swing and rng.random() < 0.22 + 0.05 * stuff - 0.04 * h.talent
            in_play = swing and not whiff and rng.random() < 0.45
            ev = 89 + 3.0 * h.power + rng.gauss(0, 7) if in_play else None
            desc = (
                "swinging_strike"
                if whiff
                else "hit_into_play"
                if in_play
                else "foul"
                if swing
                else ("called_strike" if in_zone else "ball")
            )
            rows.append(
                {
                    "game_pk": game_pk + j // 90,
                    "game_date": "2025-07-12",
                    "game_year": 2025,
                    "game_type": "R",
                    "home_team": "AAA",
                    "batter": h.pid,
                    "pitcher": pid,
                    "stand": "R",
                    "p_throws": "R",
                    "at_bat_number": j // 4,
                    "pitch_number": j % 4 + 1,
                    "balls": 0,
                    "strikes": 0,
                    "pitch_type": pt,
                    "release_speed": velo,
                    "release_spin_rate": 2300 + 100 * stuff + rng.gauss(0, 50),
                    "release_extension": 6.3 + 0.2 * stuff,
                    "release_pos_x": -2.0,
                    "release_pos_z": 5.8,
                    "arm_angle": 40.0,
                    "pfx_x": (-0.6 if pt == "FF" else 0.4) + rng.gauss(0, 0.1),
                    "pfx_z": ivb / 12,
                    "plate_x": px,
                    "plate_z": pz,
                    "sz_top": 3.4,
                    "sz_bot": 1.6,
                    "zone": 5 if in_zone else 13,
                    "type": "X" if in_play else "S" if (swing or in_zone) else "B",
                    "description": desc,
                    "events": None,
                    "bb_type": None,
                    "launch_speed": ev,
                    "launch_angle": 15.0 if in_play else None,
                    "launch_speed_angle": (6 if ev and ev > 98 else 3) if in_play else None,
                    "estimated_woba_using_speedangle": None,
                    "delta_run_exp": None,
                    "bat_speed": None,
                    "swing_length": None,
                    "level": level,
                }
            )
        game_pk += 10
    return pl.DataFrame(rows, infer_schema_length=None)
