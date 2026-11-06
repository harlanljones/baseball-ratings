"""Write graded tables to CSV/parquet."""

from __future__ import annotations

from pathlib import Path

import polars as pl


def export_tables(tables: dict[str, pl.DataFrame], out_dir: Path, fmt: str = "csv") -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, df in tables.items():
        season = df["season"][0] if "season" in df.columns and df.height else "na"
        path = out_dir / f"{name}_{season}.{fmt}"
        if fmt == "csv":
            df.write_csv(path)
        elif fmt == "parquet":
            df.write_parquet(path)
        else:
            raise ValueError(f"unknown format {fmt!r}")
        paths.append(path)
    return paths
