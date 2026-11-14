"""전체 흐름: 수집 → 정제 → 1차 점수 → 상위 종목 심층 조회 → 최종 점수 → 키워드 제안."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from .config import Config
from .ideas import build_idea
from .kr_names import kr_name, short_name
from .models import Candidate, Idea, Result
from .scoring import _norm, score_candidates

log = logging.getLogger("kw")

_TICKER_OK = re.compile(r"^[A-Z]{1,5}([.-][A-Z])?$")
_NORM_TITLE = re.compile(r"[^a-z0-9가-힣]+")


def _valid_ticker(t: str) -> bool:
    return bool(_TICKER_OK.match(t))


def collect_candidates(src, cfg: Config) -> list[Candidate]:
    """트렌딩·급등·급락·거래량 상위·관심종목에서 후보 모으기 (우선순위 순)."""
    order: dict[str, Candidate] = {}
    names: dict[str, str] = {}
    pre: dict[str, dict] = {}

    def add(sym: str, flag: str):
        sym = (sym or "").upper()
        if not _valid_ticker(sym):
            return
        c = order.setdefault(sym, Candidate(ticker=sym))
        c.flags.add(flag)

    for sym in src.trending_tickers():
        add(sym, "trending")
    for kind, flag in (("day_gainers", "gainer"), ("day_losers", "loser"), ("most_actives", "active")):
        for q in src.screener(kind):
            sym = (q.get("symbol") or "").upper()
            add(sym, flag)
            if sym in order:
                pre[sym] = q
                if q.get("name"):
                    names[sym] = q["name"]
    for sym in cfg.watchlist:
        add(sym, "watch")

    cands = list(order.values())

    def priority(c: Candidate):
        return (0 if "trending" in c.flags else 1, -len(c.flags))

    cands.sort(key=priority)
    cands = cands[: cfg.max_candidates]

    for c in cands:
        q = pre.get(c.ticker)
        info = {}
        if q and q.get("change_pct") is not None:
            avg = q.get("avg_volume") or 0
            info = {
                "name": q.get("name", ""),
                "change_pct": q["change_pct"],
                "volume_ratio": (q.get("volume", 0) / avg) if avg else 1.0,
            }
        else:
            info = src.quote_info(c.ticker) or {}
        c.name_en = short_name(info.get("name") or names.get(c.ticker, ""))
        c.price_change_pct = float(info.get("change_pct", 0.0) or 0.0)
        c.volume_ratio = float(info.get("volume_ratio", 1.0) or 1.0)
        c.name_kr = kr_name(c.ticker)
    return cands


def _clean_articles(arts, hours: int):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    seen, out = set(), []
    for a in arts:
        key = _NORM_TITLE.sub("", a.title.lower())[:80]
        if not key or key in seen:
            continue
        if a.published and a.published < cutoff:
            continue
        seen.add(key)
        out.append(a)
    return out


def _match_filings(cands: list[Candidate], filings: list[dict]) -> None:
    for c in cands:
        token = (c.name_en or "").lower().split(" ")[0] if c.name_en else ""
        if len(token) < 3:
            continue
        pat = re.compile(r"\b" + re.escape(token) + r"\b")
        for f in filings:
            if pat.search(f.get("company", "").lower()):
                c.filings.append(f)


def run(src, cfg: Config, demo: bool = False, today: str | None = None) -> Result:
    today = today or datetime.now().strftime("%Y-%m-%d")

    # 1) 후보 수집 + 뉴스
    cands = collect_candidates(src, cfg)
    log.info("후보 종목 %d개", len(cands))
    for c in cands:
        c.articles = _clean_articles(src.news(c.ticker, c.name_en or c.ticker), cfg.news_hours)

    # 2) 공시·Reddit
    _match_filings(cands, src.edgar_8k())
    mentions = src.reddit_mentions([c.ticker for c in cands])
    for c in cands:
        c.reddit_mentions = mentions.get(c.ticker, 0)

    # 3) 1차 점수 → 상위 deep_k 선별
    score_candidates(cands, cfg, deep=False)
    cands.sort(key=lambda c: c.score, reverse=True)
    top = cands[: cfg.deep_k]

    # 4) 심층 조회: Google Trends · YouTube
    if cfg.use_trends:
        terms = {c.ticker: f"{c.name_en or c.ticker} stock" for c in top}
        rises = src.trends_rise(list(terms.values()), geo="")
        for c in top:
            c.trend_rise = rises.get(terms[c.ticker], 1.0)
    if cfg.use_youtube:
        for c in top:
            c.yt_videos, c.yt_views = src.youtube_signal(f"{c.name_kr or c.name_en or c.ticker} 주가")
    score_candidates(top, cfg, deep=True)
    top.sort(key=lambda c: c.score, reverse=True)
    top = top[: cfg.top_n]

    # 5) 키워드·주제 제안 + 네이버 자동완성 확장
    stock_ideas = []
    for c in top:
        idea = build_idea(c)
        base = c.name_kr or c.name_en
        idea.related = _related(src, base)
        stock_ideas.append(idea)

    macro_ideas = macro_keywords(src, cfg)
    return Result(date=today, demo=demo, stock_ideas=stock_ideas, macro_ideas=macro_ideas,
                  warnings=list(getattr(src, "warnings", [])))


def _related(src, base: str, limit: int = 8) -> list[str]:
    if not base:
        return []
    out: list[str] = []
    for q in (f"{base} 주가", base):
        for s in src.naver_suggest(q):
            if s not in out and s != q:
                out.append(s)
    return out[:limit]


def macro_keywords(src, cfg: Config) -> list[Idea]:
    """한국 독자용 거시·상시 키워드: 뉴스량 + Google Trends(KR) 상승세 + 자동완성 풍부도."""
    seeds = list(cfg.macro_seeds)
    rises = src.trends_rise(seeds, geo="KR") if cfg.use_trends else {}
    rows = []
    for s in seeds:
        count, outlets, heads = src.gnews_kr(s)
        sugg = src.naver_suggest(s)
        rows.append({"seed": s, "news": count, "outlets": outlets, "heads": heads,
                     "rise": rises.get(s, 1.0), "sugg": sugg})
    n_news = _norm([float(r["news"]) for r in rows])
    n_out = _norm([float(r["outlets"]) for r in rows])
    n_rise = _norm([min(max(r["rise"], 0.5), 3.0) for r in rows])
    n_sugg = _norm([float(len(r["sugg"])) for r in rows])
    ideas = []
    for i, r in enumerate(rows):
        score = round((0.35 * n_news[i] + 0.15 * n_out[i] + 0.35 * n_rise[i] + 0.15 * n_sugg[i]) * 100, 1)
        s = r["seed"]
        ideas.append(Idea(
            keyword=s,
            alt_keywords=[x for x in r["sugg"][:4] if x != s],
            ticker="", name=s, event="macro",
            post_type="정책·규제 변경형" if any(k in s for k in ("세", "규제", "금투", "연말정산", "연금", "IRP", "ISA", "청약")) else "이슈 해설형",
            topic=f"'{s}' 최근 변화와 독자가 챙길 점",
            score=score, headlines=r["heads"][:5], related=r["sugg"][:8],
            metrics={"기사 수": r["news"], "매체 수": r["outlets"], "Trends 상승세": round(r["rise"], 2)},
            kind="macro",
        ))
    ideas.sort(key=lambda x: x.score, reverse=True)
    return ideas[: cfg.macro_top_n]
