"""Hitter features: boxscore rates (every level), Statcast batted-ball/plate-discipline
(MLB, AAA, FSL), and MLB-only leaderboard metrics."""

from __future__ import annotations

import polars as pl

from baseball_ratings.config import RatingsConfig
from baseball_ratings.features.common import add_level, col_or_zero, pitch_flags, safe_div

_ADV_KEEP = ["totalSwings", "swingAndMisses", "ballsInPlay"]


def boxscore_hitting(season: pl.DataFrame, advanced: pl.DataFrame, cfg: RatingsConfig) -> pl.DataFrame:
    """One row per (player, league) with rate metrics and their denominators."""
    if season.is_empty():
        return pl.DataFrame()
    df = season
    if not advanced.is_empty():
        adv = advanced.select("player_id", "league_id", *[c for c in _ADV_KEEP if c in advanced.columns])
        df = df.join(adv, on=["player_id", "league_id"], how="left")
    df = add_level(df, cfg)

    def g(n: str) -> pl.Expr:
        return col_or_zero(df, n)

    w = cfg.woba_weights
    singles = g("hits") - g("doubles") - g("triples") - g("homeRuns")
    ubb = g("baseOnBalls") - g("intentionalWalks")
    woba_den = g("atBats") + ubb + g("sacFlies") + g("hitByPitch")
    woba_num = (
        w["ubb"] * ubb
        + w["hbp"] * g("hitByPitch")
        + w["single"] * singles
        + w["double"] * g("doubles")
        + w["triple"] * g("triples")
        + w["hr"] * g("homeRuns")
    )
    times_on_first = singles + g("baseOnBalls") + g("hitByPitch")
    bip = g("atBats") - g("strikeOuts") - g("homeRuns") + g("sacFlies")
    return df.select(
        "player_id",
        "player_name",
        "season",
        "level",
        "league_id",
        "team_id",
        pl.col("age"),
        g("plateAppearances").alias("pa"),
        g("atBats").alias("ab"),
        g("totalSwings").alias("swings"),
        times_on_first.alias("times_on_first"),
        (g("doubles") + g("triples")).alias("xbh_23"),
        bip.alias("bip"),
        safe_div(g("strikeOuts"), g("plateAppearances")).alias("k_pct"),
        safe_div(g("baseOnBalls"), g("plateAppearances")).alias("bb_pct"),
        safe_div(g("totalBases") - g("hits"), g("atBats")).alias("iso"),
        safe_div(g("hits") - g("homeRuns"), bip).alias("babip"),
        safe_div(g("homeRuns"), g("plateAppearances")).alias("hr_pa"),
        safe_div(g("totalSwings") - g("swingAndMisses"), g("totalSwings")).alias("contact_pct"),
        safe_div(g("numberOfPitches"), g("plateAppearances")).alias("pitches_per_pa"),
        safe_div(g("stolenBases") + g("caughtStealing"), times_on_first).alias("sb_att_rate"),
        safe_div(g("triples"), g("doubles") + g("triples")).alias("triple_share"),
        safe_div(woba_num, woba_den).alias("woba"),
    ).filter(pl.col("level").is_not_null() & (pl.col("pa") > 0))


def statcast_hitting(pitches: pl.DataFrame) -> pl.DataFrame:
    """Per (batter, level): EV90, barrel%, chase%, zone-contact%, from tracked pitches."""
    if pitches.is_empty():
        return pl.DataFrame()
    df = pitches.filter(pl.col("release_speed").is_not_null()).with_columns(pitch_flags())
    return (
        df.group_by(pl.col("batter").alias("player_id"), "level")
        .agg(
            pl.col("bbe").sum().alias("bbe"),
            pl.col("launch_speed").filter(pl.col("bbe")).quantile(0.9).alias("ev90"),
            (pl.col("launch_speed_angle") == 6).filter(pl.col("bbe")).mean().alias("barrel_pct"),
            pl.col("out_zone").sum().alias("o_pitches"),
            (pl.col("swing") & pl.col("out_zone")).sum().alias("_o_swings"),
            (pl.col("swing") & pl.col("in_zone")).sum().alias("z_swings"),
            (pl.col("whiff") & pl.col("in_zone")).sum().alias("_z_whiffs"),
        )
        .with_columns(
            safe_div(pl.col("_o_swings"), pl.col("o_pitches")).alias("chase_pct"),
            safe_div(pl.col("z_swings") - pl.col("_z_whiffs"), pl.col("z_swings")).alias("zone_contact_pct"),
        )
        .drop("_o_swings", "_z_whiffs")
        .with_columns(pl.col("player_id").cast(pl.Int64))
    )


def leaderboard_hitting(sprint: pl.DataFrame, bat: pl.DataFrame) -> pl.DataFrame:
    """MLB-only: sprint speed and bat speed."""
    frames = []
    if not sprint.is_empty():
        frames.append(
            sprint.select(
                "player_id",
                pl.col("sprint_speed").cast(pl.Float64, strict=False),
                pl.col("competitive_runs").cast(pl.Float64, strict=False).alias("sprints"),
            )
        )
    if not bat.is_empty():
        frames.append(
            bat.select(
                "player_id",
                pl.col("avg_bat_speed").cast(pl.Float64, strict=False).alias("bat_speed"),
                pl.col("swings_competitive").cast(pl.Float64, strict=False).alias("swings_tracked"),
            )
        )
    if not frames:
        return pl.DataFrame()
    out = frames[0]
    for f in frames[1:]:
        out = out.join(f, on="player_id", how="full", coalesce=True)
    return out.with_columns(pl.lit("MLB").alias("level"))
