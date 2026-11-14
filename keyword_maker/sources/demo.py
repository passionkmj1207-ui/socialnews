"""오프라인 검증용 모의 데이터. 실제 시장 데이터가 아니며, 출력물에 DEMO 표시가 붙습니다."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import Article

_NOW = datetime.now(timezone.utc)


def _a(title, source, hours_ago=3):
    return Article(title=title, link=f"https://example.com/demo/{abs(hash(title)) % 10**6}",
                   source=source, published=_NOW - timedelta(hours=hours_ago))


# ticker: (회사명, 등락률, 거래량 배율, 헤드라인들)
_DATA = {
    "NVDA": ("NVIDIA Corporation", 4.1, 1.8, [("Nvidia posts record quarterly revenue, raises guidance", "Demo Wire"),
                                              ("Nvidia earnings beat estimates on data center demand", "Demo Journal"),
                                              ("Nvidia results lift AI chip stocks", "Demo Daily")]),
    "TSLA": ("Tesla, Inc.", -6.3, 2.2, [("Tesla shares plunge after delivery miss", "Demo Wire"),
                                         ("Tesla stock tumbles as sales slump in Europe", "Demo Journal"),
                                         ("Tesla falls on weak outlook", "Demo Daily"),
                                         ("Why Tesla stock is sinking today", "Demo Finance")]),
    "PLTR": ("Palantir Technologies Inc.", 8.7, 2.9, [("Palantir stock soars on new Pentagon contract", "Demo Wire"),
                                                      ("Palantir wins government contract worth billions", "Demo Journal")]),
    "AAPL": ("Apple Inc.", 0.8, 1.0, [("Apple unveils new iPhone with AI features", "Demo Wire"),
                                       ("Apple launches new chip for Macs", "Demo Daily")]),
    "META": ("Meta Platforms, Inc.", -1.2, 1.3, [("Meta faces FTC antitrust probe over acquisitions", "Demo Wire"),
                                                  ("EU opens investigation into Meta ads model", "Demo Journal"),
                                                  ("Meta lawsuit could reshape ad business", "Demo Daily")]),
    "COIN": ("Coinbase Global, Inc.", 5.5, 1.9, [("Coinbase jumps as bitcoin rallies", "Demo Wire"),
                                                  ("Coinbase shares climb on trading volume surge", "Demo Daily")]),
    "AMD": ("Advanced Micro Devices, Inc.", 1.9, 1.1, [("AMD announces new AI GPU lineup", "Demo Journal")]),
    "MSFT": ("Microsoft Corporation", 0.3, 0.9, [("Microsoft partnership expands cloud AI deal", "Demo Wire")]),
    "INTC": ("Intel Corporation", -2.4, 1.4, [("Intel announces layoffs as restructuring deepens", "Demo Wire"),
                                              ("Intel job cuts to hit manufacturing unit", "Demo Daily")]),
    "NFLX": ("Netflix, Inc.", 0.2, 0.8, []),
    "AMZN": ("Amazon.com, Inc.", 1.1, 1.0, [("Amazon announces dividend plan", "Demo Journal")]),
    "SMCI": ("Super Micro Computer, Inc.", 12.4, 3.5, [("Super Micro stock surges after earnings guidance", "Demo Wire"),
                                                       ("Super Micro results top estimates", "Demo Journal"),
                                                       ("Super Micro rally continues on AI server demand", "Demo Daily")]),
}

_MACRO = {
    "기준금리": (14, 6, 1.9), "환율 전망": (11, 5, 1.6), "연말정산": (18, 8, 2.4),
    "청약": (6, 3, 1.1), "퇴직연금": (5, 3, 1.3), "ETF 투자": (7, 4, 1.0),
    "배당주": (4, 2, 0.9), "국민연금": (9, 5, 1.5), "대출 규제": (8, 4, 1.4),
    "물가 상승": (10, 5, 1.2), "해외주식 양도세": (6, 3, 1.8), "금투세": (3, 2, 0.8),
    "IRP": (5, 3, 1.7), "ISA 계좌": (4, 2, 1.4), "달러 투자": (3, 2, 1.1),
}


class DemoSources:
    def __init__(self):
        self.warnings: list[str] = []

    def trending_tickers(self):
        return ["NVDA", "TSLA", "PLTR", "SMCI"]

    def screener(self, kind):
        pick = {"day_gainers": ["SMCI", "PLTR", "COIN"], "day_losers": ["TSLA", "INTC"],
                "most_actives": ["NVDA", "TSLA", "AMD"]}[kind]
        return [{"symbol": s, "name": _DATA[s][0], "change_pct": _DATA[s][1],
                 "volume": int(_DATA[s][2] * 1e6), "avg_volume": int(1e6)} for s in pick]

    def quote_info(self, ticker):
        d = _DATA.get(ticker)
        return {"name": d[0], "change_pct": d[1], "volume_ratio": d[2]} if d else {}

    def news(self, ticker, name):
        d = _DATA.get(ticker)
        return [_a(t, s, hours_ago=2 + i) for i, (t, s) in enumerate(d[3])] if d else []

    def edgar_8k(self):
        return [{"company": "NVIDIA CORP", "item": "2.02", "link": "https://example.com/8k/nvda", "title": "8-K - NVIDIA CORP"},
                {"company": "SUPER MICRO COMPUTER, INC.", "item": "2.02", "link": "https://example.com/8k/smci", "title": "8-K"}]

    def reddit_mentions(self, tickers):
        base = {"NVDA": 9, "TSLA": 12, "PLTR": 7, "SMCI": 4, "COIN": 3}
        return {t: base.get(t, 0) for t in tickers}

    def trends_rise(self, terms, geo=""):
        if geo == "KR":
            return {t: _MACRO[t][2] for t in terms if t in _MACRO}
        rises = {"NVIDIA stock": 1.7, "Tesla stock": 2.1, "Palantir Technologies stock": 2.4,
                 "Super Micro Computer stock": 2.8, "Coinbase Global stock": 1.4}
        return {t: rises.get(t, 1.0) for t in terms}

    def youtube_signal(self, query):
        return {"엔비디아 주가": (9, 820_000), "테슬라 주가": (10, 1_400_000), "팔란티어 주가": (8, 400_000),
                "슈퍼마이크로컴퓨터 주가": (6, 150_000)}.get(query, (2, 5_000))

    def naver_suggest(self, q):
        return [f"{q} 전망", f"{q} 뉴스", f"{q} 목표주가", f"{q} 배당"]

    def gnews_kr(self, seed):
        n, o, _ = _MACRO.get(seed, (1, 1, 1.0))
        heads = [{"title": f"[데모] {seed} 관련 기사 {i + 1}", "source": "데모일보", "link": "https://example.com/demo"} for i in range(min(n, 3))]
        return n, o, heads
