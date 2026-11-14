"""티커 → 한국 투자자가 검색하는 이름. 없는 종목은 영문명으로 대체됩니다(필요하면 계속 추가)."""

KR_NAMES = {
    "AAPL": "애플", "MSFT": "마이크로소프트", "NVDA": "엔비디아", "TSLA": "테슬라",
    "AMZN": "아마존", "GOOGL": "구글", "GOOG": "구글", "META": "메타",
    "AVGO": "브로드컴", "AMD": "AMD", "INTC": "인텔", "MU": "마이크론",
    "TSM": "TSMC", "NFLX": "넷플릭스", "PLTR": "팔란티어", "COIN": "코인베이스",
    "MSTR": "마이크로스트래티지", "SMCI": "슈퍼마이크로컴퓨터", "ARM": "ARM",
    "QCOM": "퀄컴", "ORCL": "오라클", "CRM": "세일즈포스", "ADBE": "어도비",
    "UBER": "우버", "DIS": "디즈니", "NKE": "나이키", "SBUX": "스타벅스",
    "KO": "코카콜라", "PEP": "펩시코", "MCD": "맥도날드", "WMT": "월마트",
    "COST": "코스트코", "JPM": "JP모건", "BAC": "뱅크오브아메리카",
    "GS": "골드만삭스", "V": "비자", "MA": "마스터카드", "BRK-B": "버크셔해서웨이",
    "XOM": "엑슨모빌", "CVX": "셰브론", "LLY": "일라이릴리", "NVO": "노보노디스크",
    "PFE": "화이자", "JNJ": "존슨앤드존슨", "BA": "보잉", "LMT": "록히드마틴",
    "F": "포드", "GM": "GM", "RIVN": "리비안", "LCID": "루시드", "SOFI": "소파이",
    "HOOD": "로빈후드", "RDDT": "레딧", "SNOW": "스노우플레이크", "SHOP": "쇼피파이",
    "PYPL": "페이팔", "TQQQ": "TQQQ", "SOXL": "SOXL", "INTU": "인튜이트",
    "NOW": "서비스나우", "PANW": "팔로알토네트웍스", "CRWD": "크라우드스트라이크",
    "DELL": "델", "HPQ": "HP", "IBM": "IBM", "CSCO": "시스코", "T": "AT&T",
}

_SUFFIXES = (
    ", Inc.", " Inc.", " Inc", ", Inc", " Corporation", " Corp.", " Corp",
    " Holdings", " Holding", " Co.", " Company", " Ltd.", " Ltd", " plc", " PLC",
    " Class A", " Class B", " Class C", " Common Stock",
)


def kr_name(ticker: str) -> str:
    return KR_NAMES.get(ticker.upper(), "")


def short_name(name: str) -> str:
    """'NVIDIA Corporation' → 'NVIDIA'"""
    out = name or ""
    changed = True
    while changed:
        changed = False
        for s in _SUFFIXES:
            if out.endswith(s):
                out = out[: -len(s)]
                changed = True
    return out.strip(" ,.")
