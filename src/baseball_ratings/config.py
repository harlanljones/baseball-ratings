"""Typed access to ``config/ratings.yaml``."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "ratings.yaml"


class ScaleCfg(BaseModel):
    mean: float = 50
    points_per_sd: float = 10
    clip_min: float = 20
    clip_max: float = 80
    display_step: float = 5
    reference_min_n: dict[str, float] = Field(default_factory=dict)


class LevelCfg(BaseModel):
    sport_id: int
    rank: int
    mean_age_hitter: float
    mean_age_pitcher: float


class StatcastLevelCfg(BaseModel):
    path: str
    hf_level: str | None = None


class ParkCfg(BaseModel):
    regress_to_one: float = 0.5
    home_share: float = 0.5


class MetricCfg(BaseModel):
    side: Literal["hitter", "pitcher", "fielder"]
    denom: str
    k: float
    kind: Literal["outcome", "physical"]
    higher_is_better: bool = True
    tier: Literal["statcast", "boxscore", "leaderboard"]
    reference: Literal["mlb", "level"] = "mlb"
    park: bool = False
    factor: str | None = None  # level-factor key; defaults to the metric name
    catcher_group: bool = False  # standardize catchers against catchers only


class ToolCfg(BaseModel):
    weights: dict[str, float]
    fallback: dict[str, float] = Field(default_factory=dict)


class StuffHeuristicCfg(BaseModel):
    pitch_classes: dict[str, list[str]]
    weights: dict[str, dict[str, float]]
    whiff_k_swings: float = 40
    min_pitches_per_type: int = 25


class OfpHitterCfg(BaseModel):
    base_war: float
    war_per_10: dict[str, float]
    positional_adj_runs: dict[str, float]
    runs_per_win: float = 10


class OfpPitcherCfg(BaseModel):
    base_war_sp: float
    base_war_rp: float
    war_per_10_sp: dict[str, float]
    war_per_10_rp: dict[str, float]
    starter_gs_share: float = 0.5


class OfpCfg(BaseModel):
    hitter: OfpHitterCfg
    pitcher: OfpPitcherCfg
    war_to_grade: dict[str, list[tuple[float, float]]]


class FvCfg(BaseModel):
    points_per_year_young: float
    points_per_year_old: float
    cap_up: float
    cap_down: float
    mlb_age_floor: float
    mlb_cap_up: float = 5.0


class RatingsConfig(BaseModel):
    scale: ScaleCfg
    levels: dict[str, LevelCfg]
    statcast_levels: dict[str, StatcastLevelCfg]
    woba_weights: dict[str, float]
    park: ParkCfg
    level_factors: dict[str, dict[str, dict[str, float]]]
    metrics: dict[str, MetricCfg]
    tools: dict[str, dict[str, ToolCfg]]
    arm_position_offsets: dict[str, float]
    stuff_heuristic: StuffHeuristicCfg
    ofp: OfpCfg
    fv: FvCfg

    def level_by_sport(self, sport_id: int) -> str:
        for name, lvl in self.levels.items():
            if lvl.sport_id == sport_id:
                return name
        raise KeyError(f"no configured level for sportId={sport_id}")

    def level_factor(self, side: str, level: str, key: str) -> float:
        return self.level_factors.get(side, {}).get(level, {}).get(key, 1.0)


def _parse_tools(raw: dict[str, Any]) -> dict[str, dict[str, ToolCfg]]:
    out: dict[str, dict[str, ToolCfg]] = {}
    for side, tools in raw.items():
        out[side] = {}
        for tool, spec in tools.items():
            spec = dict(spec)
            fallback = spec.pop("fallback", {}) or {}
            out[side][tool] = ToolCfg(weights=spec, fallback=fallback)
    return out


def load_config(path: str | Path | None = None) -> RatingsConfig:
    """Load ratings config from ``path``, ``$BR_CONFIG``, or the repo default."""
    p = Path(path or os.environ.get("BR_CONFIG") or DEFAULT_CONFIG)
    raw = yaml.safe_load(p.read_text())
    raw["tools"] = _parse_tools(raw["tools"])
    return RatingsConfig.model_validate(raw)


@lru_cache(maxsize=1)
def default_config() -> RatingsConfig:
    return load_config()
