#!/usr/bin/env python3
"""socialnews 산출물 검증기.

사용법
    python scripts/validate.py runs/20261104-oil-shipbuilding             # 작업 폴더 전체
    python scripts/validate.py runs/20261104-oil-shipbuilding --complete  # 사용자 승인 직전 점검
    python scripts/validate.py runs/20261104-oil-shipbuilding/brief.json  # 파일 하나

검증은 두 겹으로 이루어진다.
  1) JSON Schema: 필드와 형식
  2) 교차 규칙: 지침서에서 코드로 판정할 수 있는 규칙(수치 등급, 재작업 상한, 판정 일관성 등)

오류가 하나라도 있으면 종료 코드 1을 반환한다.
경고(△)는 사람이 확인할 사항이며, 본문 수치 대조는 정규식 기반의 거친 사전 점검이다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schemas"

PASS_SCORE = 34  # 권장 발행 기준 (40점 만점)
MAX_REWORK = 2  # 수정 최대 횟수. 검수 라운드는 최대 MAX_REWORK + 1
PUBLISHABLE = ("pass", "below_standard")  # 사용자 승인 단계로 넘어갈 수 있는 판정
REVIEW_FILE = re.compile(r"^review_r(\d+)\.json$")
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


@dataclass
class Result:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def merge(self, other: "Result", prefix: str = "") -> None:
        tag = f"{prefix}: " if prefix else ""
        self.errors += [tag + e for e in other.errors]
        self.warnings += [tag + w for w in other.warnings]


# ---------------------------------------------------------------- schema


def _schema(kind: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{kind}.schema.json").read_text(encoding="utf-8"))


def schema_errors(kind: str, data: object) -> list[str]:
    validator = Draft202012Validator(_schema(kind))
    out = []
    for e in sorted(validator.iter_errors(data), key=lambda e: [str(p) for p in e.path]):
        loc = "/".join(str(p) for p in e.path) or "(root)"
        out.append(f"{loc}: {e.message}")
    return out


# ---------------------------------------------------------------- 교차 규칙


def check_brief(d: dict) -> Result:
    r = Result()
    tl = d["target_length"]
    if tl["min_chars"] > tl["max_chars"]:
        r.error("target_length: min_chars가 max_chars보다 큼")
    rev = d.get("revision")
    if rev and rev["count"] == 1 and not rev["note"].strip():
        r.error("revision: 기획을 변경했다면(count=1) 변경 내용을 note에 기록해야 함")
    return r


def check_factsheet(d: dict) -> Result:
    r = Result()
    ids = [i["id"] for i in d["items"]]
    for dup in sorted({x for x in ids if ids.count(x) > 1}):
        r.error(f"items: id {dup}가 중복됨")

    core_usable = 0
    for it in d["items"]:
        tag = f"items[id={it['id']}]"
        names = {s["name"] for s in it["sources"]}
        official_opened = any(s["tier"] <= 3 and s["opened"] for s in it["sources"])
        numeric = it.get("value") is not None

        if it["original_checked"] and not official_opened:
            r.error(f"{tag}: original_checked=true이나 1~3순위 출처를 직접 열어 확인한 기록(opened)이 없음")

        if it["usable"]:
            if it["grade"] == "core":
                core_usable += 1
                if not it["original_checked"]:
                    r.error(f"{tag}: 핵심 수치는 1~3순위 원자료를 직접 확인해야 사용 가능")
            if numeric and not it["original_checked"] and len(names) < 2:
                r.error(f"{tag}: 원문 미확인이고 출처가 1곳뿐인 수치는 사용 불가(usable=false)여야 함")
            if numeric and not it.get("base_date"):
                r.error(f"{tag}: 수치에는 기준일(base_date)이 필요함")
            if numeric and not it.get("unit"):
                r.warn(f"{tag}: 수치에 단위(unit)가 비어 있음")

    if core_usable == 0:
        r.warn("items: 사용 가능한 핵심 수치(core)가 없음")
    elif not 3 <= core_usable <= 7:
        r.warn(f"items: 사용 가능한 핵심 수치가 {core_usable}개 (기본값 3~7개)")
    return r


def check_review(d: dict) -> Result:
    r = Result()
    scores = d["scores"]
    total = sum(v["score"] for v in scores.values())
    if total != d["total"]:
        r.error(f"total: {d['total']}이나 항목 합계는 {total}")

    failed = [k for k, v in d["gate_a"].items() if not v["pass"]]
    for k in failed:
        if not d["gate_a"][k].get("locations"):
            r.warn(f"gate_a.{k}: Fail인데 문장 위치(locations)가 없음")
    low = [k for k, v in scores.items() if v["score"] < 4]

    meets = total >= PASS_SCORE and not failed
    verdict, rnd = d["verdict"], d["round"]
    if meets:
        if verdict != "pass":
            r.error(f"verdict: 게이트 A 전부 Pass이고 {total}점(기준 {PASS_SCORE}점 이상)이므로 pass여야 함")
    else:
        if rnd <= MAX_REWORK:
            expected = "rework"
        else:
            expected = "hold" if failed else "below_standard"
        if verdict != expected:
            r.error(f"verdict: round {rnd}, 게이트 Fail {len(failed)}건, {total}점이므로 {expected}여야 함 (현재 {verdict})")

    # 수정 지시는 게이트 Fail 항목과 4점 미만 항목에 한정한다.
    if failed or low:
        allowed = set(failed) | set(low)
    else:
        lowest = min(v["score"] for v in scores.values())
        allowed = {k for k, v in scores.items() if v["score"] == lowest} if not meets else set()
    origins = {f["origin"] for f in d["fix_instructions"]}
    for o in sorted(origins - allowed):
        r.error(f"fix_instructions: '{o}'는 게이트 Fail 또는 4점 미만 항목이 아님")
    if verdict == "rework":
        if not d["fix_instructions"]:
            r.error("fix_instructions: rework 판정에는 수정 지시가 필요함")
        for o in sorted(allowed - origins):
            r.error(f"fix_instructions: '{o}'에 대한 수정 지시가 없음")
    return r


def check_publish_info(d: dict) -> Result:
    r = Result()
    if not d.get("internal_link_candidates") and not d.get("followup_topics"):
        r.warn("internal_link_candidates/followup_topics: 둘 다 비어 있음")
    return r


CHECKS = {
    "brief": check_brief,
    "factsheet": check_factsheet,
    "review": check_review,
    "publish_info": check_publish_info,
}


def validate_data(kind: str, data: object) -> Result:
    r = Result()
    errs = schema_errors(kind, data)
    if errs:
        r.errors += [f"[스키마] {e}" for e in errs]
        return r
    r.merge(CHECKS[kind](data))  # type: ignore[arg-type]
    return r


# ---------------------------------------------------------------- 본문 대조


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _figure_tokens(text: str) -> list[tuple[str, str]]:
    """본문에서 수치로 볼 만한 토큰만 추린다. (원문, 숫자만 남긴 값)"""
    out = []
    for m in NUM.finditer(text):
        raw = m.group()
        nxt = text[m.end() : m.end() + 1]
        prev = text[m.start() - 1 : m.start()] if m.start() > 0 else ""
        if prev and "가" <= prev <= "힣":  # '아이뉴스24'처럼 한글에 붙은 숫자는 이름의 일부로 보고 제외
            continue
        d = _digits(raw)
        if "." in raw or "," in raw or len(d) >= 3 or (nxt and nxt in "%배"):
            out.append((raw, d))
    return out


def check_article(text: str, brief: dict | None, factsheet: dict | None) -> Result:
    r = Result()
    if brief:
        n = len(re.sub(r"\s", "", text))
        tl = brief["target_length"]
        if not tl["min_chars"] <= n <= tl["max_chars"]:
            r.warn(f"article.md: 공백 제외 {n}자 (목표 {tl['min_chars']}~{tl['max_chars']}자)")
    if not factsheet:
        return r

    pool = []
    for it in factsheet["items"]:
        if it["usable"]:
            parts = [str(it["value"]) if it.get("value") is not None else "", it["content"], it.get("base_date") or ""]
            pool += [_digits(p) for p in parts]
    pool = [p for p in pool if p]

    tokens = _figure_tokens(text)
    seen: set[str] = set()
    for raw, d in tokens:
        if d in seen:
            continue
        seen.add(d)
        if not any(d in p for p in pool):
            r.warn(f"article.md: 수치 '{raw}'가 사용 가능한 팩트시트 항목에서 확인되지 않음 (게이트 A: 팩트시트에 없는 수치)")

    token_digits = {d for _, d in tokens}
    usable_values = {_digits(str(i["value"])) for i in factsheet["items"] if i["usable"] and i.get("value") is not None}
    for it in factsheet["items"]:
        if it["usable"] or it.get("value") is None:
            continue
        dv = _digits(str(it["value"]))
        if dv and dv in token_digits and dv not in usable_values:
            r.warn(f"article.md: 사용 불가 항목 id={it['id']}의 수치 '{it['value']}'가 본문에 있는 것으로 보임")
    return r


# ---------------------------------------------------------------- 파일·폴더


def _load_json(path: Path, r: Result) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        r.error(f"{path.name}: JSON 문법 오류 ({e})")
        return None


def kind_of(path: Path) -> str | None:
    if path.stem in ("brief", "factsheet", "publish_info"):
        return path.stem
    if REVIEW_FILE.match(path.name):
        return "review"
    return None


def validate_file(path: Path) -> Result:
    r = Result()
    kind = kind_of(path)
    if kind is None:
        r.error(f"{path.name}: 알 수 없는 파일 이름 (brief / factsheet / review_rN / publish_info)")
        return r
    data = _load_json(path, r)
    if data is not None:
        r.merge(validate_data(kind, data), path.name)
    return r


def validate_run(path: Path, complete: bool = False) -> Result:
    p = Path(path)
    r = Result()
    run_id = p.resolve().name
    docs: dict[str, dict] = {}

    for kind in ("brief", "factsheet", "publish_info"):
        f = p / f"{kind}.json"
        if not f.exists():
            if complete:
                r.error(f"{f.name}: 파일이 없음")
            continue
        data = _load_json(f, r)
        if data is None:
            continue
        sub = validate_data(kind, data)
        r.merge(sub, f.name)
        if not sub.errors:
            docs[kind] = data  # type: ignore[assignment]
            if data["run_id"] != run_id:  # type: ignore[index]
                r.error(f"{f.name}: run_id '{data['run_id']}'가 폴더 이름 '{run_id}'와 다름")  # type: ignore[index]

    reviews: dict[int, dict] = {}
    for f in sorted(p.glob("review_r*.json")):
        m = REVIEW_FILE.match(f.name)
        if not m:
            r.error(f"{f.name}: 파일 이름은 review_r1.json 형식이어야 함")
            continue
        n = int(m.group(1))
        if n > MAX_REWORK + 1:
            r.error(f"{f.name}: 검수는 최대 {MAX_REWORK + 1}라운드(수정 {MAX_REWORK}회)까지 허용")
            continue
        data = _load_json(f, r)
        if data is None:
            continue
        sub = validate_data("review", data)
        r.merge(sub, f.name)
        if sub.errors:
            continue
        if data["round"] != n:  # type: ignore[index]
            r.error(f"{f.name}: round({data['round']})가 파일 이름의 번호({n})와 다름")  # type: ignore[index]
        if data["run_id"] != run_id:  # type: ignore[index]
            r.error(f"{f.name}: run_id '{data['run_id']}'가 폴더 이름 '{run_id}'와 다름")  # type: ignore[index]
        reviews[n] = data  # type: ignore[assignment]

    last = None
    if reviews:
        rounds = sorted(reviews)
        if rounds != list(range(1, len(rounds) + 1)):
            r.error(f"review: 라운드가 1부터 연속되지 않음 {rounds}")
        for n in rounds[:-1]:
            if reviews[n]["verdict"] != "rework":
                r.error(f"review_r{n}.json: 이후 라운드가 있는데 verdict가 rework가 아님 ({reviews[n]['verdict']})")
        last = reviews[rounds[-1]]
    elif complete:
        r.error("review_r1.json: 검수 리포트가 없음")

    if last and docs.get("publish_info") and last["verdict"] not in PUBLISHABLE:
        r.error(f"publish_info.json: 마지막 검수 판정이 {last['verdict']}인데 발행 정보가 작성됨")
    if complete and last and last["verdict"] not in PUBLISHABLE:
        r.error(f"review: 마지막 검수 판정이 {last['verdict']}이므로 사용자 승인 단계로 넘길 수 없음")

    pub, brief, fact = docs.get("publish_info"), docs.get("brief"), docs.get("factsheet")
    if pub and brief and pub["primary_keyword"] != brief["keywords"]["primary"]:
        r.warn("publish_info.json: primary_keyword가 기획서의 핵심 키워드와 다름")
    if pub and fact:
        known = {s["name"] for it in fact["items"] for s in it["sources"]}
        for s in pub["sources"]:
            if s["name"] not in known:
                r.error(f"publish_info.json: 출처 '{s['name']}'가 팩트시트에 없음")

    article = p / "article.md"
    if article.exists():
        r.merge(check_article(article.read_text(encoding="utf-8"), brief, fact))
    elif complete:
        r.error("article.md: 원고 파일이 없음")
    return r


# ---------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="socialnews 산출물 검증기")
    ap.add_argument("path", help="작업 폴더(runs/<run_id>) 또는 JSON 파일")
    ap.add_argument("--complete", action="store_true", help="사용자 승인 직전 점검: 모든 산출물과 발행 가능 판정을 요구")
    args = ap.parse_args(argv)

    p = Path(args.path)
    if not p.exists():
        print(f"✗ 경로가 없음: {p}")
        return 2
    res = validate_run(p, args.complete) if p.is_dir() else validate_file(p)

    for e in res.errors:
        print(f"✗ {e}")
    for w in res.warnings:
        print(f"△ {w}")
    if res.errors:
        print(f"\n오류 {len(res.errors)}건, 경고 {len(res.warnings)}건")
        return 1
    print(f"✓ 통과 (경고 {len(res.warnings)}건)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
