"""설정값 모음. 가중치·후보 수·시드 키워드는 여기서만 고치면 됩니다."""
from dataclasses import dataclass, field


@dataclass
class Config:
    user_agent: str = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
    # SEC EDGAR는 연락처가 들어간 User-Agent를 요구합니다. 본인 이메일로 바꿔 주세요.
    edgar_user_agent: str = "KeywordMaker your-email@example.com"
    timeout: int = 15
    sleep: float = 1.0            # 요청 사이 대기(초). 차단 방지용
    max_candidates: int = 40      # 1차 후보 종목 수
    deep_k: int = 15              # Trends·YouTube까지 조회할 상위 종목 수
    top_n: int = 15               # 최종 출력 종목 수
    macro_top_n: int = 10         # 거시·상시 키워드 출력 수
    news_hours: int = 48          # 이 시간 안의 기사만 사용
    use_trends: bool = True
    use_youtube: bool = True

    # 항상 후보에 넣는 종목(한국 투자자 관심 높은 대형주)
    watchlist: tuple = (
        "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "AVGO", "AMD",
        "PLTR", "MU", "TSM", "NFLX", "COIN", "ORCL", "INTC", "QCOM", "SMCI",
    )

    # 핫함 점수 가중치 (합이 1일 필요는 없음, 내부에서 정규화)
    weights: dict = field(default_factory=lambda: {
        "news": 0.22,       # 기사 수
        "outlets": 0.12,    # 보도 매체 수
        "move": 0.18,       # 주가 등락 폭(절댓값)
        "volume": 0.10,     # 거래량 급증 배율
        "trending": 0.08,   # Yahoo 트렌딩 여부
        "reddit": 0.06,     # Reddit 언급
        "filing": 0.04,     # 최근 8-K 공시
        "trends": 0.10,     # Google Trends 상승세
        "youtube": 0.05,    # 최근 YouTube 영상 관심도
        "kr": 0.05,         # 한국 투자자 관심 종목 가산점
    })

    # 거시·상시 키워드 시드 (한국 독자용)
    macro_seeds: tuple = (
        "기준금리", "환율 전망", "연말정산", "청약", "퇴직연금", "ETF 투자",
        "배당주", "국민연금", "대출 규제", "물가 상승", "해외주식 양도세",
        "금투세", "IRP", "ISA 계좌", "달러 투자",
    )


KR_FAVORITES = {
    "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "GOOGL", "GOOG", "META", "AVGO",
    "AMD", "PLTR", "MU", "TSM", "NFLX", "COIN", "ORCL", "SMCI", "QCOM", "INTC",
    "MSTR", "ARM", "TQQQ", "SOXL", "RDDT", "HOOD",
}
