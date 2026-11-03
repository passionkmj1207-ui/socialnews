"""사용법
    python -m pipeline run [--topic "주제"] [--runs-dir runs] [--model 모델명]   # 전체 실행 (ANTHROPIC_API_KEY 필요)
    python -m pipeline report runs/<run_id>                                      # 사용자 보고(report.md) 생성
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .orchestrator import Pipeline, PipelineError, build_report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline", description="경제 이슈 블로그 제작 파이프라인")
    sub = ap.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="주제 선정부터 발행정보까지 실행")
    run.add_argument("--topic", help="주제. 없으면 비서실장이 직접 선정")
    run.add_argument("--runs-dir", default="runs")
    run.add_argument("--model", help="모델명. 기본값은 SOCIALNEWS_MODEL 또는 claude-sonnet-5-5")

    rep = sub.add_parser("report", help="작업 폴더에서 사용자 보고 생성")
    rep.add_argument("run_dir")

    args = ap.parse_args(argv)
    if args.cmd == "report":
        d = Path(args.run_dir)
        (d / "report.md").write_text(build_report(d), encoding="utf-8")
        print(f"작성: {d / 'report.md'}")
        return 0

    from .backends import AnthropicBackend

    try:
        backend = AnthropicBackend(model=args.model)
        run_dir = Pipeline(backend, args.runs_dir).run(args.topic)
    except PipelineError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    print(f"완료: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
