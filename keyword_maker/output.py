"""결과를 CSV · 마크다운 · HTML(복사 버튼) · 워크플로우 입력 JSON으로 저장."""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from .models import Idea, Result

CSV_FIELDS = ["순위", "구분", "키워드", "보조 키워드", "종목", "글 유형", "제안 주제", "점수", "연관 키워드", "참고 기사"]


def _all(result: Result):
    return [("미국주식", result.stock_ideas), ("거시·상시", result.macro_ideas)]


def _row(i: int, label: str, x: Idea) -> dict:
    return {
        "순위": i, "구분": label, "키워드": x.keyword, "보조 키워드": " | ".join(x.alt_keywords),
        "종목": f"{x.name} ({x.ticker})" if x.ticker else "", "글 유형": x.post_type, "제안 주제": x.topic,
        "점수": x.score, "연관 키워드": " | ".join(x.related),
        "참고 기사": " | ".join(h["link"] for h in x.headlines if h.get("link")),
    }


def write_csv(result: Result, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:   # utf-8-sig: 엑셀에서 한글 깨짐 방지
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for label, ideas in _all(result):
            for i, x in enumerate(ideas, 1):
                w.writerow(_row(i, label, x))


def write_workflow_json(result: Result, path: Path) -> None:
    """content-company 워크플로우의 '주제·키워드 입력' 단계에 넣을 수 있는 형식."""
    items = []
    for label, ideas in _all(result):
        for x in ideas:
            items.append({
                "keyword": x.keyword, "topic": x.topic, "post_type": x.post_type, "category": label,
                "ticker": x.ticker, "score": x.score, "related_keywords": x.related,
                "source_links": [h["link"] for h in x.headlines if h.get("link")],
                "demo": result.demo,
            })
    path.write_text(json.dumps({"date": result.date, "demo": result.demo, "items": items},
                               ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(result: Result, path: Path) -> None:
    L = [f"# 블로그 키워드 후보 — {result.date}", ""]
    if result.demo:
        L += ["> ⚠️ **DEMO 데이터입니다.** 실제 시장 데이터가 아닌 동작 확인용 모의 값이므로 글 작성에 쓰지 마세요.", ""]
    if result.warnings:
        L += ["> 수집 경고: " + " / ".join(result.warnings), ""]
    for label, ideas in _all(result):
        L += [f"## {label}", "", "| 순위 | 키워드 | 글 유형 | 점수 | 제안 주제 |", "|---|---|---|---|---|"]
        for i, x in enumerate(ideas, 1):
            L.append(f"| {i} | **{x.keyword}** | {x.post_type} | {x.score} | {x.topic} |")
        L.append("")
        for i, x in enumerate(ideas, 1):
            L.append(f"### {i}. {x.keyword}")
            if x.alt_keywords:
                L.append(f"- 보조 키워드: {', '.join(x.alt_keywords)}")
            if x.related:
                L.append(f"- 네이버 연관 검색어: {', '.join(x.related)}")
            L.append("- 지표: " + ", ".join(f"{k} {v}" for k, v in x.metrics.items()))
            for h in x.headlines[:3]:
                L.append(f"- 기사: [{h['title']}]({h['link']}) — {h['source']}")
            L.append("")
    path.write_text("\n".join(L), encoding="utf-8")


_CSS = """
body{font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;margin:0;background:#f6f7f9;color:#1d2530}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 10px}
.sub{color:#667;font-size:13px;margin-bottom:16px}
.demo{background:#fff3cd;border:1px solid #f0d98a;padding:10px 14px;border-radius:8px;margin:12px 0;font-size:14px}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px #0001}
th,td{padding:10px 12px;text-align:left;font-size:14px;border-bottom:1px solid #eef0f3;vertical-align:top}
th{background:#eef1f5;font-size:12px;color:#556}
.kw{font-weight:700}.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;background:#e8f0fe;color:#1a56c7}
.score{font-weight:700;color:#0b7a4b}.muted{color:#778;font-size:12px;margin-top:4px}
button{border:1px solid #cfd6e0;background:#fff;border-radius:6px;padding:3px 9px;font-size:12px;cursor:pointer}
button.ok{background:#0b7a4b;color:#fff;border-color:#0b7a4b}
details summary{cursor:pointer;color:#456;font-size:12px;white-space:nowrap}
td:last-child{min-width:90px}
a{color:#1a56c7;text-decoration:none}
"""

_JS = """
function cp(btn,text){navigator.clipboard.writeText(text).then(function(){btn.classList.add('ok');btn.textContent='복사됨';
setTimeout(function(){btn.classList.remove('ok');btn.textContent='복사'},1200)})}
"""


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def write_html(result: Result, path: Path) -> None:
    parts = [f"<!doctype html><html lang='ko'><meta charset='utf-8'><title>블로그 키워드 {result.date}</title>",
             f"<style>{_CSS}</style><div class='wrap'><h1>블로그 키워드 후보</h1><div class='sub'>{result.date} 기준 · 점수는 후보군 내 상대 순위(0~100)</div>"]
    if result.demo:
        parts.append("<div class='demo'>⚠️ <b>DEMO 데이터</b>입니다. 실제 시장 데이터가 아닌 동작 확인용 모의 값이므로 글 작성에 쓰지 마세요.</div>")
    if result.warnings:
        parts.append(f"<div class='demo'>수집 경고: {_esc(' / '.join(result.warnings))}</div>")
    for label, ideas in _all(result):
        parts.append(f"<h2>{label}</h2><table><tr><th>#</th><th>키워드</th><th>글 유형 · 제안 주제</th><th>점수</th><th>근거</th></tr>")
        for i, x in enumerate(ideas, 1):
            heads = "".join(f"<div class='muted'>· <a href='{_esc(h['link'])}' target='_blank' rel='noopener'>{_esc(h['title'])}</a> ({_esc(h['source'])})</div>"
                            for h in x.headlines[:3])
            alts = f"<div class='muted'>보조: {_esc(', '.join(x.alt_keywords))}</div>" if x.alt_keywords else ""
            rel = f"<div class='muted'>연관: {_esc(', '.join(x.related))}</div>" if x.related else ""
            met = _esc(" · ".join(f"{k} {v}" for k, v in x.metrics.items()))
            parts.append(
                f"<tr><td>{i}</td><td><span class='kw'>{_esc(x.keyword)}</span> "
                f"<button onclick=\"cp(this,'{_esc(x.keyword).replace(chr(39), '')}')\">복사</button>{alts}{rel}</td>"
                f"<td><span class='tag'>{_esc(x.post_type)}</span><div>{_esc(x.topic)}</div></td>"
                f"<td class='score'>{x.score}</td><td><details><summary>지표·기사</summary><div class='muted'>{met}</div>{heads}</details></td></tr>")
        parts.append("</table>")
    parts.append(f"</div><script>{_JS}</script></html>")
    path.write_text("".join(parts), encoding="utf-8")


def write_all(result: Result, out_dir: Path) -> Path:
    prefix = "demo_" if result.demo else ""
    d = out_dir / f"{prefix}{result.date}"
    d.mkdir(parents=True, exist_ok=True)
    write_csv(result, d / "keywords.csv")
    write_markdown(result, d / "keywords.md")
    write_html(result, d / "keywords.html")
    write_workflow_json(result, d / "workflow_input.json")
    return d
