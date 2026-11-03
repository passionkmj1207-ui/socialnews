"""파이프라인 실행기.

비서실장(기획) → 리서치(팩트시트) → 작성 → [검수 → 수정]×최대 2회 → 발행정보 → 사용자 보고.
단계 사이에는 산출물 파일만 오가고, 마지막 사용자 승인 전까지 멈추지 않는다. 자동 발행은 하지 않는다.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import validate  # noqa: E402

from .backends import Backend  # noqa: E402
from .prompts import system_prompt  # noqa: E402

MAX_ROUNDS = validate.MAX_REWORK + 1
MAX_RETRIES = 2  # 스키마·규칙 오류 시 같은 역할에 오류를 알려 다시 요청하는 횟수


class PipelineError(RuntimeError):
    pass


def extract_json(text: str) -> dict:
    """응답에서 JSON 객체 하나를 꺼낸다. 코드 펜스나 앞뒤 설명이 있어도 처리한다."""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = [fence.group(1)] if fence else []
    start = text.find("{")
    if start >= 0:
        candidates.append(text[start:])
    for c in candidates:
        try:
            obj, _ = json.JSONDecoder().raw_decode(c.lstrip())
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    raise ValueError("응답에서 JSON 객체를 찾지 못함")


def dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


class Pipeline:
    def __init__(self, backend: Backend, runs_dir: Path | str = "runs", log=print):
        self.backend = backend
        self.runs_dir = Path(runs_dir)
        self.log = log

    # ---------------------------------------------------------- 역할 호출

    def _ask_json(self, role: str, kind: str, user: str, web_search: bool = False, fixed: dict | None = None) -> dict:
        system = system_prompt(role)
        prompt = user
        errors: list[str] = []
        for attempt in range(MAX_RETRIES + 1):
            raw = self.backend.complete(role, system, prompt, web_search=web_search)
            try:
                data = extract_json(raw)
                data.update(fixed or {})
                res = validate.validate_data(kind, data)
                errors = res.errors
            except ValueError as e:
                data, errors = {}, [str(e)]
            if not errors:
                return data
            self.log(f"  ! {role}: 검증 오류 {len(errors)}건, 재요청 {attempt + 1}/{MAX_RETRIES}")
            prompt = user + "\n\n# 이전 출력의 오류 (모두 고쳐서 JSON 전체를 다시 출력)\n" + "\n".join(f"- {e}" for e in errors)
        raise PipelineError(f"{role}: {MAX_RETRIES}회 재요청 후에도 오류가 남음\n" + "\n".join(errors))

    def _ask_text(self, role: str, user: str) -> str:
        text = self.backend.complete(role, system_prompt(role), user).strip()
        if not text:
            raise PipelineError(f"{role}: 빈 응답")
        return text + "\n"

    # ---------------------------------------------------------- 단계

    def plan(self, topic: str | None) -> tuple[dict, Path]:
        today = date.today().strftime("%Y%m%d")
        if topic:
            ask = f"사용자 지정 주제: {topic}"
        else:
            ask = "사용자가 주제를 지정하지 않았습니다. 웹 검색으로 지금 독자가 궁금해할 경제 이슈를 찾아 직접 선정하세요."
        user = f"{ask}\n오늘 날짜: {date.today().isoformat()}\nrun_id는 '{today}-영문소문자-슬러그' 형식으로 정합니다."
        brief = self._ask_json("chief", "brief", user, web_search=topic is None)
        run_dir = self.runs_dir / brief["run_id"]
        if run_dir.exists():
            raise PipelineError(f"이미 존재하는 작업 폴더: {run_dir}")
        run_dir.mkdir(parents=True)
        (run_dir / "brief.json").write_text(dumps(brief), encoding="utf-8")
        return brief, run_dir

    def research(self, brief: dict, run_dir: Path) -> dict:
        user = "기획서:\n" + dumps(brief) + f"\n오늘 날짜: {date.today().isoformat()}"
        fs = self._ask_json("researcher", "factsheet", user, web_search=True, fixed={"run_id": brief["run_id"]})
        (run_dir / "factsheet.json").write_text(dumps(fs), encoding="utf-8")
        return fs

    def draft(self, brief: dict, fs: dict, run_dir: Path) -> str:
        user = "기획서:\n" + dumps(brief) + "\n팩트시트:\n" + dumps(fs)
        text = self._ask_text("writer", user)
        (run_dir / "article.md").write_text(text, encoding="utf-8")
        return text

    def revise(self, brief: dict, fs: dict, article: str, review: dict, run_dir: Path) -> str:
        user = (
            "기획서:\n" + dumps(brief) + "\n팩트시트:\n" + dumps(fs)
            + "\n현재 원고:\n" + article
            + "\n검수 리포트의 수정 지시(이 항목만 고치고 나머지는 유지):\n" + dumps({"fix_instructions": review["fix_instructions"]})
        )
        text = self._ask_text("writer", user)
        (run_dir / "article.md").write_text(text, encoding="utf-8")
        return text

    def review(self, rnd: int, brief: dict, fs: dict, article: str, run_dir: Path) -> dict:
        pre = validate.check_article(article, brief, fs)
        pre_note = "\n".join(f"- {w}" for w in pre.warnings) or "- 없음"
        user = (
            f"검수 라운드: {rnd}\n기획서:\n" + dumps(brief) + "\n팩트시트:\n" + dumps(fs)
            + "\n원고:\n" + article + "\n자동 사전 점검 경고(참고용, 최종 판정은 검수가 함):\n" + pre_note
        )
        rv = self._ask_json("reviewer", "review", user, fixed={"run_id": brief["run_id"], "round": rnd})
        (run_dir / f"review_r{rnd}.json").write_text(dumps(rv), encoding="utf-8")
        return rv

    def publish(self, brief: dict, fs: dict, article: str, run_dir: Path) -> dict:
        user = "기획서:\n" + dumps(brief) + "\n팩트시트:\n" + dumps(fs) + "\n검수 통과 원고:\n" + article
        pub = self._ask_json("publisher", "publish_info", user, fixed={"run_id": brief["run_id"]})
        (run_dir / "publish_info.json").write_text(dumps(pub), encoding="utf-8")
        return pub

    # ---------------------------------------------------------- 전체 실행

    def run(self, topic: str | None = None) -> Path:
        self.log("1-2. 주제·기획")
        brief, run_dir = self.plan(topic)
        self.log(f"   run_id={brief['run_id']}  주제={brief['topic']}")
        self.log("3. 자료 수집·검증")
        fs = self.research(brief, run_dir)
        self.log("4. 초안 작성")
        article = self.draft(brief, fs, run_dir)

        verdict = "rework"
        for rnd in range(1, MAX_ROUNDS + 1):
            self.log(f"5. 검수 round {rnd}")
            rv = self.review(rnd, brief, fs, article, run_dir)
            verdict = rv["verdict"]
            self.log(f"   {rv['total']}/40점, 판정 {verdict}")
            if verdict != "rework":
                break
            self.log(f"6. 수정 {rnd}회")
            article = self.revise(brief, fs, article, rv, run_dir)

        if verdict in validate.PUBLISHABLE:
            self.log("7. 발행정보")
            self.publish(brief, fs, article, run_dir)
        else:
            self.log(f"7. 판정 {verdict}: 발행정보를 만들지 않고 보고로 넘어감")

        (run_dir / "report.md").write_text(build_report(run_dir), encoding="utf-8")
        self.log("8. 사용자 승인 대기: report.md 확인 (자동 발행하지 않음)")
        return run_dir


# ---------------------------------------------------------------- 사용자 보고


def build_report(run_dir: Path) -> str:
    run_dir = Path(run_dir)
    brief = json.loads((run_dir / "brief.json").read_text(encoding="utf-8"))
    rounds = sorted(int(m.group(1)) for f in run_dir.glob("review_r*.json") if (m := validate.REVIEW_FILE.match(f.name)))
    last = json.loads((run_dir / f"review_r{rounds[-1]}.json").read_text(encoding="utf-8")) if rounds else None
    pub_path = run_dir / "publish_info.json"
    pub = json.loads(pub_path.read_text(encoding="utf-8")) if pub_path.exists() else None
    res = validate.validate_run(run_dir, complete=bool(pub))

    lines = [f"# 사용자 보고: {brief['run_id']}", ""]
    topic = f"- 주제: {brief['topic']}"
    if brief.get("topic_selection_reason"):
        topic += f" (직접 선정 사유: {brief['topic_selection_reason']})"
    lines += [topic, f"- 핵심 질문: {brief['core_question']}"]
    if last:
        lines.append(f"- 검수: {len(rounds)}라운드, 최종 {last['total']}/40점, 판정 {last['verdict']}, 수정 {len(rounds) - 1}회")
        failed = [k for k, v in last["gate_a"].items() if not v["pass"]]
        if last["verdict"] == "below_standard":
            lines.append("- 기준 미달: 수정 2회 후에도 34점에 못 미침. 현재 버전을 '기준 미달'로 올림")
        if last["verdict"] == "hold" or failed:
            lines.append(f"- 발행 보류 사유(게이트 A Fail): {', '.join(failed)}")
    if pub and pub["needs_verification"]:
        lines.append("- 추가 확인 필요: " + "; ".join(pub["needs_verification"]))
    if brief.get("assumptions"):
        lines.append("- 적용한 가정: " + "; ".join(brief["assumptions"]))
    lines.append(f"- 자동 검증: 오류 {len(res.errors)}건, 경고 {len(res.warnings)}건")
    lines += [f"  - ✗ {e}" for e in res.errors] + [f"  - △ {w}" for w in res.warnings]
    lines += ["", "승인 전에는 발행하지 않습니다. 원고는 `article.md`, 발행 정보는 `publish_info.json`입니다."]
    return "\n".join(lines) + "\n"
