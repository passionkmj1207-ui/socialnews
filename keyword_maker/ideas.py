"""헤드라인·가격 변동으로 이벤트를 판별하고, 한국어 키워드·글 유형·주제를 만듭니다."""
from __future__ import annotations

import re

from .models import Candidate, Idea

# (이벤트, 판별 정규식, 글 유형, 키워드 템플릿들, 주제 템플릿)  — 위에서부터 우선순위
EVENTS = [
    ("earnings", r"\b(earnings|eps|revenue|quarterly|guidance|results|q[1-4]|(beats?|miss(es)?) (estimates|expectations|forecasts))\b",
     "기업실적 분석형",
     ["{n} 실적 발표", "{n} 실적 분석", "{n} 어닝 서프라이즈"],
     "{n} 실적 발표 핵심 정리: 매출·이익·가이던스와 주가 반응"),
    ("regulation", r"\b(sec|ftc|doj|antitrust|tariffs?|ban|lawsuit|probe|investigation|fda|approval|sanctions?|export (curbs?|controls?))\b",
     "정책·규제 변경형",
     ["{n} 규제 영향", "{n} 소송 쟁점", "{n} 관세 영향"],
     "{n}에 닥친 규제·정책 이슈, 사업과 주가에 미치는 영향"),
    ("deal", r"\b(acquir\w*|acquisition|merger|buyout|takeover)\b",
     "이슈 해설형",
     ["{n} 인수합병", "{n} 인수 발표"],
     "{n}의 인수합병 소식, 왜 중요한가"),
    ("contract", r"\b(contracts?|partnership|stake|invests?|investment|awarded|wins?)\b",
     "이슈 해설형",
     ["{n} 계약 체결", "{n} 투자 발표", "{n} 수주"],
     "{n}의 계약·투자 발표, 사업에 미칠 영향"),
    ("layoff", r"\b(layoffs?|job cuts?|restructuring|cuts? jobs)\b",
     "이슈 해설형",
     ["{n} 구조조정", "{n} 감원"],
     "{n} 구조조정·감원 소식과 시장 해석"),
    ("capital", r"\b(dividends?|buybacks?|repurchase|stock split|split)\b",
     "기업실적 분석형",
     ["{n} 배당", "{n} 자사주 매입", "{n} 주식분할"],
     "{n}의 배당·자사주·분할 발표가 주주에게 의미하는 것"),
    ("product", r"\b(launch\w*|unveil\w*|releases?|announces?|new (model|chip|product)|ai|gpu|chips?)\b",
     "이슈 해설형",
     ["{n} 신제품", "{n} AI 전략", "{n} 신제품 발표 주가"],
     "{n} 신제품·신기술 발표, 사업에 미칠 영향"),
]

SURGE_RE = re.compile(r"\b(soars?|surges?|jumps?|rall(y|ies)|spikes?|climbs?|pops?|skyrockets?)\b", re.I)
PLUNGE_RE = re.compile(r"\b(plunges?|tumbles?|sinks?|slumps?|falls?|drops?|crash\w*|sell-?off)\b", re.I)


def detect_event(c: Candidate) -> str:
    text = " ".join(a.title for a in c.articles) + " " + " ".join(f.get("item", "") for f in c.filings)
    # 8-K Item 2.02 = 실적 발표
    if any("2.02" in f.get("item", "") for f in c.filings):
        return "earnings"
    for name, pattern, *_ in EVENTS:
        if re.search(pattern, text, re.I):
            return name
    if c.price_change_pct >= 5 or SURGE_RE.search(text):
        return "surge"
    if c.price_change_pct <= -5 or PLUNGE_RE.search(text):
        return "plunge"
    return "general"


def _move_event(c: Candidate, event: str) -> str:
    """실적·규제 등 이벤트 위에 큰 주가 변동이 있으면 변동 키워드를 보조로 붙이기 위한 판별."""
    if c.price_change_pct >= 5:
        return "surge"
    if c.price_change_pct <= -5:
        return "plunge"
    return ""


def build_idea(c: Candidate) -> Idea:
    n = c.display_name
    event = detect_event(c)
    alts: list[str] = []

    if event in ("surge", "plunge"):
        up = event == "surge"
        post_type = "이슈 해설형"
        primary = f"{n} 주가 {'급등 이유' if up else '하락 이유'}"
        alts += [f"{n} {'주가 급등' if up else '주가 폭락 원인'}", f"{n} 주가 전망"]
        topic = f"{n} 주가가 {'급등' if up else '급락'}한 배경과 앞으로의 변수"
    elif event == "general":
        post_type = "이슈 해설형"
        primary = f"{n} 주가 전망"
        alts += [f"{n} 주식 뉴스", f"{n} 최근 이슈"]
        topic = f"{n} 최근 이슈 점검과 주가 전망"
    else:
        _, _, post_type, kws, topic_t = next(e for e in EVENTS if e[0] == event)
        primary = kws[0].format(n=n)
        alts += [k.format(n=n) for k in kws[1:]]
        topic = topic_t.format(n=n)
        mv = _move_event(c, event)
        if mv:
            move_kw = f"{n} 주가 {'급등 이유' if mv == 'surge' else '하락 이유'}"
            if event == "earnings":
                alts.append(move_kw)            # 실적 발표가 주제면 실적을 대표로 유지
            else:                               # 그 밖의 이벤트는 큰 주가 변동을 대표로 올림
                alts.insert(0, primary)
                primary = move_kw
                topic = f"{n} 주가가 {'급등' if mv == 'surge' else '급락'}한 배경: {topic}"
        alts.append(f"{n} 주가 전망")

    headlines = [
        {"title": a.title, "source": a.source, "link": a.link}
        for a in sorted(c.articles, key=lambda a: (a.published is None, -(a.published.timestamp() if a.published else 0)))[:5]
    ]
    return Idea(
        keyword=primary,
        alt_keywords=list(dict.fromkeys(alts)),
        ticker=c.ticker,
        name=n,
        event=event,
        post_type=post_type,
        topic=topic,
        score=c.score,
        headlines=headlines,
        metrics={
            "등락률(%)": round(c.price_change_pct, 2),
            "거래량 배율": round(c.volume_ratio, 2),
            "기사 수": len(c.articles),
            "매체 수": len(c.outlets),
            "Trends 상승세": round(c.trend_rise, 2),
            "YouTube 영상 수": c.yt_videos,
            "Reddit 언급": c.reddit_mentions,
            "8-K 공시": len(c.filings),
        },
    )
