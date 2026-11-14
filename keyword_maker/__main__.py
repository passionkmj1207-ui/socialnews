"""실행: python -m keyword_maker [--demo] [--top 15] [--out output]"""
from __future__ import annotations

import argparse
import logging
from dataclasses import replace
from pathlib import Path

from .config import Config
from .output import write_all
from .pipeline import run


def main() -> None:
    ap = argparse.ArgumentParser(description="경제·비즈니스 블로그 키워드 생성기 (무료 소스)")
    ap.add_argument("--demo", action="store_true", help="모의 데이터로 오프라인 실행(동작 확인용)")
    ap.add_argument("--top", type=int, default=None, help="미국주식 키워드 출력 개수")
    ap.add_argument("--out", default="output", help="결과 저장 폴더")
    ap.add_argument("--no-trends", action="store_true", help="Google Trends 조회 생략")
    ap.add_argument("--no-youtube", action="store_true", help="YouTube 조회 생략")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config()
    if a.top:
        cfg = replace(cfg, top_n=a.top)
    if a.no_trends:
        cfg = replace(cfg, use_trends=False)
    if a.no_youtube:
        cfg = replace(cfg, use_youtube=False)

    if a.demo:
        from .sources.demo import DemoSources
        src = DemoSources()
    else:
        from .sources.live import LiveSources
        src = LiveSources(cfg)

    result = run(src, cfg, demo=a.demo)
    out = write_all(result, Path(a.out))
    print(f"완료: 미국주식 {len(result.stock_ideas)}개 · 거시 {len(result.macro_ideas)}개 → {out}/")
    for w in result.warnings:
        print("경고:", w)
    if not result.stock_ideas and result.warnings:
        print("※ 수집이 거의 실패했습니다. 인터넷 연결이나 방화벽을 확인하세요. (--demo로 동작 확인 가능)")


if __name__ == "__main__":
    main()
