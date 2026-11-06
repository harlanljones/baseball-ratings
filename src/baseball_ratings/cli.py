"""``br`` command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import polars as pl
import typer

from baseball_ratings import pipeline
from baseball_ratings.config import load_config
from baseball_ratings.export import export_tables
from baseball_ratings.ingest.http import HttpClient
from baseball_ratings.ingest.savant import Savant
from baseball_ratings.ingest.statsapi import StatsApi
from baseball_ratings.store import Store

app = typer.Typer(help="Sabermetric 20-80 grades for MLB and MiLB.", no_args_is_help=True)

ConfigOpt = Annotated[Path | None, typer.Option("--config", help="ratings.yaml path")]
DataOpt = Annotated[Path | None, typer.Option("--data-dir", help="parquet store root")]


def _levels(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@app.command()
def ingest(
    season: Annotated[int, typer.Option(help="Season to pull")],
    levels: Annotated[str, typer.Option(help="Comma list: MLB,AAA,AA,A+,A,ROK")] = "MLB,AAA,AA,A+,A",
    stats: Annotated[bool, typer.Option(help="MLB Stats API season stats")] = True,
    leaderboards: Annotated[bool, typer.Option(help="Savant MLB leaderboards")] = True,
    statcast: Annotated[
        bool, typer.Option(help="Savant pitch-level data (slow: 1 request/day/level)")
    ] = False,
    start: Annotated[str | None, typer.Option(help="Statcast start date YYYY-MM-DD")] = None,
    end: Annotated[str | None, typer.Option(help="Statcast end date YYYY-MM-DD")] = None,
    limit_days: Annotated[int | None, typer.Option(help="Only pull the first N days (smoke tests)")] = None,
    config: ConfigOpt = None,
    data_dir: DataOpt = None,
) -> None:
    """Download and cache raw data for a season."""
    cfg = load_config(config)
    lv = _levels(levels)
    unknown = [x for x in lv if x not in cfg.levels]
    if unknown:
        raise typer.BadParameter(f"unknown levels {unknown}; choose from {list(cfg.levels)}")
    http = HttpClient()
    store = Store(data_dir)
    if stats:
        typer.echo(f"MLB Stats API {season}: {lv}")
        pipeline.ingest_stats(StatsApi(http), store, cfg, season, lv, typer.echo)
    savant = Savant(http)
    if leaderboards and "MLB" in lv:
        typer.echo("Savant leaderboards")
        pipeline.ingest_leaderboards(savant, store, season, typer.echo)
    if statcast:
        dates = pipeline.season_dates(season, start, end, limit_days)
        typer.echo(f"Savant pitch-level: {len(dates)} days x {[x for x in lv if x in cfg.statcast_levels]}")
        pipeline.ingest_pitches(savant, store, cfg, lv, dates, typer.echo)


@app.command()
def grade(
    season: Annotated[int, typer.Option(help="Season to grade")],
    config: ConfigOpt = None,
    data_dir: DataOpt = None,
) -> None:
    """Compute grades from stored data and save them to the store."""
    cfg = load_config(config)
    store = Store(data_dir)
    tables = pipeline.grade_season(pipeline.load_raw(store, season, cfg), cfg)
    if not tables:
        typer.echo("no stored data for that season; run `br ingest` first", err=True)
        raise typer.Exit(1)
    for name, df in tables.items():
        store.write(df, f"grades_{name}", season)
        typer.echo(f"{name}: {df.height} rows")


@app.command()
def show(
    season: Annotated[int, typer.Option(help="Season")],
    name: Annotated[str | None, typer.Argument(help="Player name (substring match)")] = None,
    player_id: Annotated[int | None, typer.Option("--id", help="MLBAM player id")] = None,
    data_dir: DataOpt = None,
) -> None:
    """Print a player's grades."""
    if name is None and player_id is None:
        raise typer.BadParameter("give a name or --id")
    store = Store(data_dir)
    pl.Config.set_tbl_cols(-1)
    pl.Config.set_tbl_width_chars(200)
    found = False
    for table, cols in (("hitters", pipeline.HITTER_COLUMNS), ("pitchers", pipeline.PITCHER_COLUMNS)):
        df = store.read(f"grades_{table}", season)
        if df.is_empty():
            continue
        if player_id is not None:
            df = df.filter(pl.col("player_id") == player_id)
        else:
            needle = (name or "").lower()
            df = df.filter(pl.col("player_name").str.to_lowercase().str.contains(needle, literal=True))
        if df.height:
            found = True
            typer.echo(f"\n{table}")
            typer.echo(df.select([c for c in cols if c in df.columns]).sort("level"))
    if not found:
        typer.echo("no matching player (run `br grade` first?)")


@app.command()
def leaders(
    season: Annotated[int, typer.Option(help="Season")],
    tool: Annotated[str, typer.Option(help="Tool column, e.g. raw_power, stuff, ofp")] = "ofp",
    level: Annotated[str, typer.Option(help="Level")] = "MLB",
    side: Annotated[str, typer.Option(help="hitters | pitchers")] = "hitters",
    top: Annotated[int, typer.Option(help="Rows")] = 20,
    min_n: Annotated[int, typer.Option(help="Minimum PA (hitters) / BF (pitchers)")] = 200,
    data_dir: DataOpt = None,
) -> None:
    """Top players at a level by a tool grade."""
    df = Store(data_dir).read(f"grades_{side}", season)
    if df.is_empty() or (f"{tool}_raw" not in df.columns and tool not in df.columns):
        typer.echo(f"no {tool} grades for {side} {season}", err=True)
        raise typer.Exit(1)
    n_col = "pa" if side == "hitters" else "bf"
    sort_col = f"{tool}_raw" if f"{tool}_raw" in df.columns else tool
    cols = pipeline.HITTER_COLUMNS if side == "hitters" else pipeline.PITCHER_COLUMNS
    pl.Config.set_tbl_cols(-1)
    pl.Config.set_tbl_width_chars(200)
    res = (
        df.filter((pl.col("level") == level) & (pl.col(n_col) >= min_n))
        .sort(sort_col, descending=True, nulls_last=True)
        .head(top)
    )
    typer.echo(res.select([c for c in cols if c in res.columns]))


@app.command()
def export(
    season: Annotated[int, typer.Option(help="Season")],
    fmt: Annotated[str, typer.Option("--format", help="csv | parquet")] = "csv",
    out: Annotated[Path, typer.Option(help="Output directory")] = Path("grades"),
    data_dir: DataOpt = None,
) -> None:
    """Export stored grades."""
    store = Store(data_dir)
    tables = {name: store.read(f"grades_{name}", season) for name in ("hitters", "pitchers", "pitch_grades")}
    tables = {k: v for k, v in tables.items() if not v.is_empty()}
    if not tables:
        typer.echo("no grades stored; run `br grade` first", err=True)
        raise typer.Exit(1)
    for p in export_tables(tables, out, fmt):
        typer.echo(str(p))


if __name__ == "__main__":  # pragma: no cover
    app()
