"""검증기 테스트. 예시 작업 폴더를 복사해 일부러 규칙을 깨뜨리고 잡아내는지 확인한다."""
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import validate  # noqa: E402

SAMPLE = ROOT / "examples" / "20261104-sample-topic"


@pytest.fixture
def run(tmp_path):
    dst = tmp_path / "20261104-sample-topic"
    shutil.copytree(SAMPLE, dst)
    return dst


def edit(path: Path, fn):
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def errors_of(run, complete=True):
    return validate.validate_run(run, complete=complete).errors


def test_sample_run_is_clean():
    res = validate.validate_run(SAMPLE, complete=True)
    assert res.errors == []
    assert res.warnings == []


def test_unopened_single_source_figure_cannot_be_usable(run):
    def f(d):
        item = next(i for i in d["items"] if i["id"] == 5)
        item["usable"] = True

    edit(run / "factsheet.json", f)
    assert any("출처가 1곳뿐" in e for e in errors_of(run))


def test_core_figure_requires_original_check(run):
    def f(d):
        item = next(i for i in d["items"] if i["id"] == 1)
        item["original_checked"] = False
        item["sources"][0]["opened"] = False

    edit(run / "factsheet.json", f)
    assert any("핵심 수치" in e for e in errors_of(run))


def test_review_total_must_match_scores(run):
    edit(run / "review_r2.json", lambda d: d.update(total=40))
    assert any("항목 합계" in e for e in errors_of(run))


def test_pass_verdict_not_allowed_with_gate_fail(run):
    def f(d):
        d["gate_a"]["logic_error"] = {"pass": False, "locations": ["4단계"]}

    edit(run / "review_r2.json", f)
    assert any("verdict" in e for e in errors_of(run))


def test_rework_round_three_is_rejected(run):
    def f(d):
        d["round"] = 3
        d["verdict"] = "rework"
        d["total"] = 30
        for v in d["scores"].values():
            v["score"] = 3
        d["total"] = 24

    shutil.copy(run / "review_r2.json", run / "review_r3.json")
    edit(run / "review_r3.json", f)
    errs = errors_of(run)
    assert any("below_standard" in e for e in errs)


def test_fourth_review_round_is_rejected(run):
    shutil.copy(run / "review_r2.json", run / "review_r4.json")
    assert any("최대 3라운드" in e for e in errors_of(run))


def test_fix_instructions_limited_to_failed_or_low_items(run):
    def f(d):
        d["fix_instructions"].append(
            {"location": "도입", "problem": "p", "direction": "d", "origin": "clarity"}
        )

    edit(run / "review_r1.json", f)
    assert any("4점 미만" in e for e in errors_of(run))


def test_publish_sources_must_exist_in_factsheet(run):
    def f(d):
        d["sources"].append({"name": "출처 불명 보고서", "base_date": "2026-09"})

    edit(run / "publish_info.json", f)
    assert any("팩트시트에 없음" in e for e in errors_of(run))


def test_run_id_must_match_folder(run):
    edit(run / "brief.json", lambda d: d.update(run_id="20261104-other"))
    assert any("폴더 이름" in e for e in errors_of(run))


def test_article_figure_not_in_factsheet_is_warned(run):
    article = run / "article.md"
    article.write_text(article.read_text(encoding="utf-8") + "\n재고는 7.7% 늘었습니다.\n", encoding="utf-8")
    warnings = validate.validate_run(run, complete=True).warnings
    assert any("7.7" in w for w in warnings)


def test_digits_attached_to_hangul_are_not_treated_as_figures(run):
    article = run / "article.md"
    article.write_text(article.read_text(encoding="utf-8") + "\n- 출처: 아이뉴스24 보도\n", encoding="utf-8")
    assert validate.validate_run(run, complete=True).warnings == []


def test_incomplete_run_requires_files_only_when_complete(run):
    (run / "publish_info.json").unlink()
    assert errors_of(run, complete=False) == []
    assert any("publish_info.json" in e for e in errors_of(run, complete=True))
