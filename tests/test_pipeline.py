"""오케스트레이터 제어 흐름 테스트. 모델 호출은 예시 산출물을 돌려주는 가짜 백엔드로 대체한다."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import validate  # noqa: E402
from pipeline.orchestrator import Pipeline, PipelineError, extract_json  # noqa: E402
from pipeline.prompts import system_prompt  # noqa: E402

SAMPLE = ROOT / "examples" / "20261104-sample-topic"
RUN_ID = "20261104-fake"


def load(name):
    return (SAMPLE / name).read_text(encoding="utf-8")


def as_json(name):
    return json.loads(load(name))


class FakeBackend:
    def __init__(self, script):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls = []

    def complete(self, role, system, user, web_search=False):
        self.calls.append((role, web_search))
        return self.script[role].pop(0)


def brief_text():
    b = as_json("brief.json")
    b["run_id"] = RUN_ID
    return json.dumps(b, ensure_ascii=False)


def base_script(**over):
    s = {
        "chief": [brief_text()],
        "researcher": [load("factsheet.json")],
        "writer": [load("article.md")],
        "reviewer": [load("review_r2.json")],
        "publisher": [load("publish_info.json")],
    }
    s.update(over)
    return s


def test_happy_path_single_review(tmp_path):
    be = FakeBackend(base_script())
    run_dir = Pipeline(be, tmp_path, log=lambda *_: None).run()
    assert run_dir.name == RUN_ID
    assert (run_dir / "report.md").exists()
    # 주제를 안 주면 비서실장이 웹 검색을 쓰고, 리서치도 웹 검색을 쓴다
    assert ("chief", True) in be.calls and ("researcher", True) in be.calls
    # 모델이 낸 run_id가 달라도 오케스트레이터가 폴더 이름으로 고정한다
    res = validate.validate_run(run_dir, complete=True)
    assert res.errors == []


def test_rework_then_pass(tmp_path):
    bad_article = load("article.md") + "\n재고는 7.7% 늘었습니다.\n"
    be = FakeBackend(
        base_script(
            writer=[bad_article, load("article.md")],
            reviewer=[load("review_r1.json"), load("review_r2.json")],
        )
    )
    run_dir = Pipeline(be, tmp_path, log=lambda *_: None).run("지정 주제")
    assert [r for r, _ in be.calls].count("writer") == 2  # 초안 + 수정 1회
    assert ("chief", False) in be.calls  # 주제를 주면 비서실장은 검색하지 않음
    assert (run_dir / "review_r1.json").exists() and (run_dir / "review_r2.json").exists()
    assert (run_dir / "publish_info.json").exists()
    assert "7.7" not in (run_dir / "article.md").read_text(encoding="utf-8")
    assert validate.validate_run(run_dir, complete=True).errors == []


def test_below_standard_after_two_reworks_is_reported_with_publish_info(tmp_path):
    r1 = as_json("review_r1.json")
    r3 = as_json("review_r1.json")
    for v in r3["scores"].values():
        v["score"] = 4
    r3["gate_a"] = {k: {"pass": True} for k in r3["gate_a"]}
    r3["total"] = 32
    r3["fix_instructions"] = []
    r3["verdict"] = "below_standard"
    be = FakeBackend(
        base_script(
            writer=[load("article.md")] * 3,
            reviewer=[json.dumps(r1), json.dumps(r1), json.dumps(r3)],
        )
    )
    run_dir = Pipeline(be, tmp_path, log=lambda *_: None).run()
    assert (run_dir / "review_r3.json").exists()
    assert not (run_dir / "review_r4.json").exists()  # 수정은 최대 2회
    assert (run_dir / "publish_info.json").exists()  # 기준 미달은 표시하고 사용자에게 올림
    assert "기준 미달" in (run_dir / "report.md").read_text(encoding="utf-8")


def test_hold_after_two_reworks_skips_publish(tmp_path):
    r1 = as_json("review_r1.json")  # 게이트 A Fail 포함
    r3 = as_json("review_r1.json")
    r3["verdict"] = "hold"
    be = FakeBackend(
        base_script(
            writer=[load("article.md")] * 3,
            reviewer=[json.dumps(r1), json.dumps(r1), json.dumps(r3)],
        )
    )
    run_dir = Pipeline(be, tmp_path, log=lambda *_: None).run()
    assert not (run_dir / "publish_info.json").exists()
    assert "publisher" not in [r for r, _ in be.calls]
    assert "발행 보류" in (run_dir / "report.md").read_text(encoding="utf-8")


def test_invalid_output_is_retried_with_errors(tmp_path):
    be = FakeBackend(base_script(researcher=["JSON이 아닌 응답", load("factsheet.json")]))
    Pipeline(be, tmp_path, log=lambda *_: None).run()
    assert [r for r, _ in be.calls].count("researcher") == 2


def test_gives_up_after_retries(tmp_path):
    be = FakeBackend(base_script(researcher=["x", "y", "z"]))
    with pytest.raises(PipelineError):
        Pipeline(be, tmp_path, log=lambda *_: None).run()


def test_extract_json_handles_fence_and_prose():
    assert extract_json('설명입니다\n```json\n{"a": 1}\n```\n끝') == {"a": 1}
    assert extract_json('앞말 {"a": {"b": 2}} 뒷말') == {"a": {"b": 2}}
    with pytest.raises(ValueError):
        extract_json("객체 없음")


def test_prompts_contain_only_role_sections():
    writer = system_prompt("writer")
    assert "## Ⅴ." in writer and "## Ⅶ." not in writer
    researcher = system_prompt("researcher")
    assert "## Ⅶ." in researcher and "$schema" in researcher
    assert "## Ⅴ." not in researcher
