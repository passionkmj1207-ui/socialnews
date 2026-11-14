from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Article:
    title: str
    link: str = ""
    source: str = ""
    published: Optional[datetime] = None  # timezone-aware(UTC) 권장


@dataclass
class Candidate:
    ticker: str
    name_en: str = ""
    name_kr: str = ""
    price_change_pct: float = 0.0
    volume_ratio: float = 1.0
    flags: set = field(default_factory=set)       # trending / gainer / loser / active / watch
    articles: list = field(default_factory=list)  # list[Article]
    filings: list = field(default_factory=list)   # list[dict(item, link, title)]
    reddit_mentions: int = 0
    trend_rise: float = 1.0
    yt_videos: int = 0
    yt_views: int = 0
    score: float = 0.0
    breakdown: dict = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return self.name_kr or self.name_en or self.ticker

    @property
    def outlets(self) -> set:
        return {a.source for a in self.articles if a.source}


@dataclass
class Idea:
    keyword: str
    alt_keywords: list
    ticker: str
    name: str
    event: str
    post_type: str
    topic: str
    score: float
    headlines: list            # list[dict(title, source, link)]
    related: list = field(default_factory=list)   # 네이버 자동완성 연관 키워드
    metrics: dict = field(default_factory=dict)
    kind: str = "us_stock"     # us_stock / macro


@dataclass
class Result:
    date: str
    demo: bool
    stock_ideas: list
    macro_ideas: list
    warnings: list = field(default_factory=list)
