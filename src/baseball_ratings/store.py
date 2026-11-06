"""Local parquet store: ``<root>/<dataset>/season=<yyyy>/<part>.parquet``.

Raw MLBAM/Savant data is never committed to the repo (data terms); the default root lives under
the user cache directory.
"""

from __future__ import annotations

import os
from pathlib import Path

import polars as pl

DEFAULT_ROOT = Path(os.environ.get("BR_DATA_DIR", Path.home() / ".cache" / "baseball-ratings" / "data"))


class Store:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or DEFAULT_ROOT)

    def path(self, dataset: str, season: int, part: str = "all") -> Path:
        safe = part.replace("/", "_").replace("+", "plus")
        return self.root / dataset / f"season={season}" / f"{safe}.parquet"

    def write(self, df: pl.DataFrame, dataset: str, season: int, part: str = "all") -> Path:
        p = self.path(dataset, season, part)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        df.write_parquet(tmp)
        tmp.replace(p)
        return p

    def exists(self, dataset: str, season: int, part: str = "all") -> bool:
        return self.path(dataset, season, part).exists()

    def read(self, dataset: str, season: int, part: str | None = None) -> pl.DataFrame:
        """Read one part, or all parts of a dataset-season concatenated (empty frame if none)."""
        if part is not None:
            p = self.path(dataset, season, part)
            return pl.read_parquet(p) if p.exists() else pl.DataFrame()
        d = self.root / dataset / f"season={season}"
        files = sorted(d.glob("*.parquet")) if d.exists() else []
        if not files:
            return pl.DataFrame()
        return pl.concat([pl.read_parquet(f) for f in files], how="diagonal_relaxed")
