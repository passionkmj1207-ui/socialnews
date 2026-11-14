"""핫함 점수 계산. 후보들 사이의 상대 순위(백분위)로 정규화해서 합산합니다."""
from __future__ import annotations

import math

from .config import KR_FAVORITES, Config
from .models import Candidate

PRE_KEYS = ("news", "outlets", "move", "volume", "trending", "reddit", "filing", "kr")
DEEP_KEYS = PRE_KEYS + ("trends", "youtube")


def _norm(values: list[float]) -> list[float]:
    """0~1 백분위. 모두 같은 값이면 전부 0 (신호 없음)."""
    n = len(values)
    if n < 2 or max(values) == min(values):
        return [0.0] * n
    out = []
    for v in values:
        less = sum(1 for x in values if x < v)
        equal = sum(1 for x in values if x == v)
        out.append((less + 0.5 * (equal - 1)) / (n - 1))
    return out


def _raw_features(c: Candidate) -> dict[str, float]:
    return {
        "news": float(len(c.articles)),
        "outlets": float(len(c.outlets)),
        "move": abs(c.price_change_pct),
        "volume": max(c.volume_ratio, 0.0),
        "trending": 1.0 if "trending" in c.flags else 0.0,
        "reddit": float(c.reddit_mentions),
        "filing": float(len(c.filings)),
        "kr": 1.0 if c.ticker in KR_FAVORITES else 0.0,
        "trends": min(max(c.trend_rise, 0.5), 3.0),
        "youtube": math.log1p(c.yt_videos) + 0.3 * math.log1p(c.yt_views / 1000),
    }


def score_candidates(cands: list[Candidate], cfg: Config, deep: bool) -> None:
    """cands의 score/breakdown을 갱신. deep=False면 Trends·YouTube를 제외한 1차 점수."""
    if not cands:
        return
    keys = DEEP_KEYS if deep else PRE_KEYS
    raws = [_raw_features(c) for c in cands]
    normed = {k: _norm([r[k] for r in raws]) for k in keys}
    wsum = sum(cfg.weights[k] for k in keys)
    for i, c in enumerate(cands):
        parts = {k: normed[k][i] * cfg.weights[k] / wsum * 100 for k in keys}
        c.breakdown = {k: round(v, 1) for k, v in parts.items()}
        c.score = round(sum(parts.values()), 1)
