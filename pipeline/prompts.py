"""역할별 시스템 프롬프트. 지침서에서 역할에 필요한 섹션만 뽑아 넣는다."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDELINE = ROOT / "docs" / "guideline.md"
SCHEMA_DIR = ROOT / "schemas"

# 지침서 0장의 '역할별 읽을 섹션' 표와 같은 내용
ROLE_SECTIONS = {
    "chief": ["Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅷ", "Ⅺ"],
    "researcher": ["Ⅲ", "Ⅳ", "Ⅶ", "Ⅺ"],
    "writer": ["Ⅱ", "Ⅴ", "Ⅵ", "Ⅹ"],
    "reviewer": ["Ⅱ", "Ⅳ", "Ⅶ", "Ⅸ"],
    "publisher": ["Ⅷ", "Ⅹ"],
}

ROLE_TASK = {
    "chief": (
        "당신은 비서실장(총괄)입니다. 주제와 글 유형을 정하고 기획서(brief)를 작성합니다. "
        "사용자가 주제를 주지 않았다면 지침서 Ⅲ의 선정 기준으로 직접 고르고 topic_selection_reason을 적습니다. "
        "사용자에게 질문하지 말고, 비어 있는 정보는 기본값과 가정으로 채워 assumptions에 기록합니다."
    ),
    "researcher": (
        "당신은 분야별 전문가 리서치 에이전트입니다. 기획서의 핵심 질문에 답하는 데 필요한 자료만 수집·검증해 "
        "팩트시트(factsheet)를 작성합니다. 검증하지 못한 수치는 usable=false로 두고 unverified에 사유를 적습니다. "
        "출처에서 확인하지 않은 수치나 URL을 만들어내지 않습니다. opened는 원문을 실제로 열어 확인한 경우에만 true입니다."
    ),
    "writer": (
        "당신은 경제 칼럼니스트 작성 에이전트입니다. 기획서와 팩트시트만 근거로 블로그 원고를 마크다운으로 작성합니다. "
        "팩트시트에서 usable=true인 수치만 쓰고, 보조 수치는 출처를 본문에 표기합니다. "
        "메타 설명이나 작성 과정 설명은 넣지 말고, 원고 본문만 출력합니다."
    ),
    "reviewer": (
        "당신은 검수 에이전트입니다. 작성자와 분리된 독립 시각에서 원고를 팩트시트와 대조해 검수 리포트(review)를 "
        "JSON으로 작성합니다. 게이트 A를 먼저 판정하고 게이트 B 점수를 매깁니다. 수정 지시는 게이트 Fail과 4점 미만 "
        "항목에 한정합니다."
    ),
    "publisher": (
        "당신은 발행정보 에이전트입니다. 검수를 통과한 원고를 기준으로 발행 관리 정보(publish_info)를 JSON으로 작성합니다. "
        "출처는 팩트시트에서 본문에 실제 사용한 것만 적습니다."
    ),
}

ROLE_SCHEMA = {
    "chief": "brief",
    "researcher": "factsheet",
    "reviewer": "review",
    "publisher": "publish_info",
}


def load_sections(path: Path = GUIDELINE) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^## (?=[Ⅰ-Ⅻ]\.)", text)
    return {p[0]: "## " + p.strip() for p in parts[1:]}


def system_prompt(role: str) -> str:
    sections = load_sections()
    guide = "\n\n".join(sections[k] for k in ROLE_SECTIONS[role])
    out = [ROLE_TASK[role], "# 지침서 (역할별 발췌)", guide]
    if role in ROLE_SCHEMA:
        schema = (SCHEMA_DIR / f"{ROLE_SCHEMA[role]}.schema.json").read_text(encoding="utf-8")
        schema = json.dumps(json.loads(schema), ensure_ascii=False)
        out += [
            "# 출력 형식",
            "아래 JSON Schema를 정확히 따르는 JSON 객체 하나만 출력합니다. 설명 문장은 쓰지 않습니다.",
            schema,
        ]
    else:
        out += ["# 출력 형식", "원고 마크다운만 출력합니다. 코드 펜스로 감싸지 않습니다."]
    return "\n\n".join(out)
