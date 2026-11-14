"""실제 무료 소스에서 수집하는 구현. 각 호출은 실패해도 빈 값으로 대체해 전체가 멈추지 않습니다.

사용 소스(전부 API 키 불필요):
  Yahoo Finance(yfinance·트렌딩 JSON) · Google News RSS · SEC EDGAR 8-K 피드 ·
  Reddit 공개 RSS · Google Trends(pytrends) · YouTube(yt-dlp 검색) · 네이버 자동완성
"""
from __future__ import annotations

import functools
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

import requests

from ..config import Config
from ..models import Article

log = logging.getLogger("kw")


def safe(default):
    """예외를 잡아 경고로 기록하고 default를 반환."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(self, *a, **kw):
            try:
                return fn(self, *a, **kw)
            except Exception as e:  # noqa: BLE001 - 수집 실패는 전부 흡수
                msg = f"{fn.__name__} 실패: {type(e).__name__}: {str(e)[:100]}"
                first = fn.__name__ not in {w.split(" ")[0] for w in self.warnings}
                if first:                      # 소스별 첫 실패만 경고로 남기고, 이후는 조용히 처리
                    log.warning(msg)
                    self.warnings.append(msg)
                else:
                    log.debug(msg)
                return default() if callable(default) else default
        return wrapper
    return deco


def _dt(struct) -> datetime | None:
    if not struct:
        return None
    return datetime(*struct[:6], tzinfo=timezone.utc)


class LiveSources:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.warnings: list[str] = []
        self.http = requests.Session()
        self.http.headers["User-Agent"] = cfg.user_agent

    # ---------- 공통 ----------
    def _get(self, url: str, headers: dict | None = None, **kw) -> requests.Response:
        r = self.http.get(url, timeout=self.cfg.timeout, headers=headers, **kw)
        r.raise_for_status()
        time.sleep(self.cfg.sleep)
        return r

    def _rss(self, url: str, headers: dict | None = None):
        import feedparser
        return feedparser.parse(self._get(url, headers=headers).content)

    # ---------- Yahoo Finance ----------
    @safe(list)
    def trending_tickers(self) -> list[str]:
        data = self._get("https://query1.finance.yahoo.com/v1/finance/trending/US?count=25").json()
        quotes = data["finance"]["result"][0]["quotes"]
        return [q["symbol"] for q in quotes]

    @safe(list)
    def screener(self, kind: str) -> list[dict]:
        import yfinance as yf
        res = yf.screen(kind, count=25)
        out = []
        for q in res.get("quotes", []):
            out.append({
                "symbol": q.get("symbol"),
                "name": q.get("longName") or q.get("shortName") or "",
                "change_pct": q.get("regularMarketChangePercent"),
                "volume": q.get("regularMarketVolume") or 0,
                "avg_volume": q.get("averageDailyVolume3Month") or 0,
            })
        time.sleep(self.cfg.sleep)
        return out

    @safe(dict)
    def quote_info(self, ticker: str) -> dict:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        fi = tk.fast_info
        last, prev = fi["last_price"], fi["previous_close"]
        vol, avg = fi["last_volume"], fi["three_month_average_volume"]
        name = ""
        try:
            info = tk.info
            name = info.get("longName") or info.get("shortName") or ""
        except Exception:  # noqa: BLE001
            pass
        time.sleep(self.cfg.sleep)
        return {
            "name": name,
            "change_pct": (last / prev - 1) * 100 if prev else 0.0,
            "volume_ratio": (vol / avg) if avg else 1.0,
        }

    @safe(list)
    def _yahoo_news(self, ticker: str) -> list[Article]:
        import yfinance as yf
        out = []
        for n in yf.Ticker(ticker).news or []:
            c = n.get("content") or n          # 신/구 응답 형식 모두 처리
            title = c.get("title") or ""
            link = ((c.get("canonicalUrl") or {}).get("url")) or c.get("link") or ""
            src = ((c.get("provider") or {}).get("displayName")) or c.get("publisher") or ""
            pub = None
            if c.get("pubDate"):
                pub = datetime.fromisoformat(c["pubDate"].replace("Z", "+00:00"))
            elif c.get("providerPublishTime"):
                pub = datetime.fromtimestamp(c["providerPublishTime"], tz=timezone.utc)
            if title:
                out.append(Article(title=title, link=link, source=src, published=pub))
        time.sleep(self.cfg.sleep)
        return out

    # ---------- Google News RSS ----------
    @safe(list)
    def _gnews(self, query: str, kr: bool = False) -> list[Article]:
        loc = "hl=ko&gl=KR&ceid=KR:ko" if kr else "hl=en-US&gl=US&ceid=US:en"
        feed = self._rss(f"https://news.google.com/rss/search?q={quote_plus(query)}&{loc}")
        out = []
        for e in feed.entries:
            title = e.get("title", "")
            source = (e.get("source") or {}).get("title", "")
            if source and title.endswith(f" - {source}"):
                title = title[: -len(source) - 3]
            out.append(Article(title=title, link=e.get("link", ""), source=source,
                               published=_dt(e.get("published_parsed"))))
        return out

    def news(self, ticker: str, name: str) -> list[Article]:
        arts = self._yahoo_news(ticker)
        arts += self._gnews(f"{name} stock when:2d")
        return arts

    @safe((0, 0, list))
    def gnews_kr(self, seed: str):
        arts = self._gnews(f"{seed} when:2d", kr=True)
        heads = [{"title": a.title, "source": a.source, "link": a.link} for a in arts[:5]]
        return len(arts), len({a.source for a in arts if a.source}), heads

    # ---------- SEC EDGAR ----------
    @safe(list)
    def edgar_8k(self) -> list[dict]:
        url = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K"
               "&company=&dateb=&owner=include&count=100&output=atom")
        feed = self._rss(url, headers={"User-Agent": self.cfg.edgar_user_agent})
        out = []
        for e in feed.entries:
            m = re.match(r"8-K\S*\s*-\s*(.+?)\s*\(\d+\)", e.get("title", ""))
            if not m:
                continue
            summary = re.sub(r"<[^>]+>", " ", e.get("summary", ""))
            item = "2.02" if re.search(r"item\s*2\.02", summary, re.I) else ""
            out.append({"company": m.group(1), "item": item, "link": e.get("link", ""), "title": e.get("title", "")})
        return out

    # ---------- Reddit ----------
    @safe(dict)
    def reddit_mentions(self, tickers: list[str]) -> dict[str, int]:
        tset = set(tickers)
        counts: dict[str, int] = {t: 0 for t in tickers}
        for sub in ("wallstreetbets", "stocks", "investing"):
            try:
                feed = self._rss(f"https://www.reddit.com/r/{sub}/hot.rss?limit=50")
            except Exception as e:  # noqa: BLE001
                log.warning("reddit %s 실패: %s", sub, e)
                continue
            for e in feed.entries:
                text = e.get("title", "") + " " + re.sub(r"<[^>]+>", " ", e.get("summary", ""))
                for tok in set(re.findall(r"\$?\b[A-Z]{1,5}\b", text)):
                    t = tok.lstrip("$")
                    if t in tset and (tok.startswith("$") or len(t) >= 3):
                        counts[t] += 1
        return counts

    # ---------- Google Trends ----------
    @safe(dict)
    def trends_rise(self, terms: list[str], geo: str = "") -> dict[str, float]:
        """최근 48시간 평균 ÷ 그 이전 5일 평균. 1보다 크면 관심 상승."""
        from pytrends.request import TrendReq
        py = TrendReq(hl="ko-KR", tz=540, timeout=(10, 25))
        out: dict[str, float] = {}
        for i in range(0, len(terms), 5):
            chunk = terms[i:i + 5]
            for attempt in (1, 2):
                try:
                    py.build_payload(chunk, timeframe="now 7-d", geo=geo)
                    df = py.interest_over_time()
                    break
                except Exception as e:  # noqa: BLE001 - 429 등은 한 번 쉬고 재시도
                    if attempt == 2:
                        raise
                    log.info("Trends 재시도 (%s)", e)
                    time.sleep(10)
            for t in chunk:
                if t in df and len(df) > 60:
                    recent, prev = df[t].tail(48).mean(), df[t].iloc[:-48].mean()
                    out[t] = float((recent + 1) / (prev + 1))
            time.sleep(self.cfg.sleep * 2)
        return out

    # ---------- YouTube ----------
    @safe((0, 0))
    def youtube_signal(self, query: str) -> tuple[int, int]:
        import yt_dlp
        opts = {"quiet": True, "extract_flat": True, "skip_download": True, "no_warnings": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearchdate10:{query}", download=False)
        entries = [e for e in (info or {}).get("entries", []) if e]
        views = sum(int(e.get("view_count") or 0) for e in entries)
        time.sleep(self.cfg.sleep)
        return len(entries), views

    # ---------- 네이버 자동완성 ----------
    @safe(list)
    def naver_suggest(self, q: str) -> list[str]:
        url = ("https://ac.search.naver.com/nx/ac?con=1&frm=nx&ans=2&r_format=json&r_enc=UTF-8"
               "&r_unicode=0&t_koreng=1&run=2&rev=4&q_enc=UTF-8&st=100&q=" + quote_plus(q))
        data = self._get(url).json()
        out = []
        for group in data.get("items", []):
            for it in group:
                if it and isinstance(it[0], str):
                    out.append(it[0])
        return out
