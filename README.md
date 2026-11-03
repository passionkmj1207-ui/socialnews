# socialnews

경제 이슈 블로그 글을 여러 에이전트가 나누어 제작하는 파이프라인의 **지침서, 산출물 스키마, 검증기**를 담은 저장소입니다.

에이전트가 만든 결과물을 사람이 읽고 판단하기 전에, 지침서의 규칙(수치 등급, 재작업 상한, 판정 일관성 등)을 코드로 먼저 걸러내는 것이 목적입니다.

## 구성

```
docs/guideline.md            경제 이슈 블로그 글쓰기 지침서 (에이전트 운영용 v2)
schemas/
  brief.schema.json          기획서        (2단계, 비서실장)
  factsheet.schema.json      팩트시트      (3단계, 리서치)
  review.schema.json         검수 리포트   (5단계, 검수)
  publish_info.schema.json   발행 관리 정보 (7단계, 발행정보)
scripts/validate.py          스키마 + 교차 규칙 검증기
examples/20261104-sample-topic/   가상 데이터로 만든 예시 작업 폴더
tests/test_validate.py       검증기 테스트
runs/                        실제 작업 폴더 (runs/<run_id>/)
```

## 파이프라인과 산출물

| 단계 | 담당 | 산출물 | 파일 |
|---|---|---|---|
| 1. 주제·유형 확정 | 비서실장 | (기획서에 포함) | |
| 2. 기획 | 비서실장 | 기획서 | `brief.json` |
| 3. 자료 수집·검증 | 리서치 (병렬) | 팩트시트 | `factsheet.json` |
| 4. 초안 작성 | 작성 | 원고 | `article.md` |
| 5. 검수 | 검수 | 검수 리포트 | `review_r1.json` |
| 6. 수정 (최대 2회) | 작성 | 수정 원고 → 재검수 | `article.md`, `review_r2.json`, `review_r3.json` |
| 7. 발행정보 작성 | 발행정보 | 발행 관리 정보 | `publish_info.json` |
| 8. 사용자 승인 | 비서실장 | 보고 | |

단계별 상세, 역할별로 읽을 섹션, 막혔을 때의 처리 규칙은 [docs/guideline.md](docs/guideline.md)를 봅니다.

## 작업 폴더 규칙

작업 하나는 `runs/<run_id>/` 폴더 하나입니다. `run_id`는 `YYYYMMDD-영문-슬러그` 형식이며 모든 산출물의 `run_id`와 폴더 이름이 일치해야 합니다.

```
runs/20261104-oil-shipbuilding/
  brief.json
  factsheet.json
  article.md
  review_r1.json   (수정 후 review_r2.json, review_r3.json)
  publish_info.json
```

## 검증기 사용

```bash
pip install -r requirements.txt

# 진행 중인 작업 점검 (있는 파일만 검증)
python scripts/validate.py runs/20261104-oil-shipbuilding

# 사용자 승인 직전 점검 (모든 산출물과 발행 가능 판정을 요구)
python scripts/validate.py runs/20261104-oil-shipbuilding --complete

# 파일 하나만
python scripts/validate.py runs/20261104-oil-shipbuilding/factsheet.json

# 예시 확인
python scripts/validate.py examples/20261104-sample-topic --complete

# 테스트
python -m pytest
```

오류(✗)가 있으면 종료 코드 1을 반환합니다. 경고(△)는 사람이 확인할 사항입니다.

### 코드로 판정하는 규칙

| 대상 | 규칙 |
|---|---|
| 팩트시트 | 핵심(core) 수치를 쓰려면 1~3순위 출처를 직접 열어 확인해야 함 |
| 팩트시트 | 원문 미확인이고 출처가 1곳뿐인 수치는 `usable=false` |
| 팩트시트 | 사용하는 수치에는 기준일 필요, 단위는 없으면 경고 |
| 팩트시트 | 사용 가능한 핵심 수치는 3~7개 권장 (벗어나면 경고) |
| 검수 | `total`은 항목 점수 합계와 일치해야 함 |
| 검수 | 게이트 A 전부 Pass이고 34점 이상이면 `pass`, 아니면 `pass` 불가 |
| 검수 | 1·2라운드 미달은 `rework`, 3라운드 미달은 Fail이 있으면 `hold`, 없으면 `below_standard` |
| 검수 | 수정 지시는 게이트 Fail 항목과 4점 미만 항목에 한정, `rework`면 빠짐없이 작성 |
| 폴더 | 검수는 최대 3라운드, 마지막 라운드만 `rework`가 아닐 수 있음 |
| 폴더 | 발행 정보의 출처는 팩트시트에 있는 출처여야 함 |
| 폴더 | 마지막 검수가 `pass` 또는 `below_standard`일 때만 발행 정보 작성·승인 단계 진행 |
| 원고 | 본문 수치가 사용 가능한 팩트시트 항목에서 확인되지 않거나, 사용 불가 항목의 수치가 있으면 경고 |
| 원고 | 글자 수가 기획서의 목표 범위를 벗어나면 경고 |

본문 수치 대조는 정규식 기반의 거친 사전 점검입니다. 게이트 A의 최종 판정은 검수 에이전트와 사람이 합니다.

## 예시 데이터에 대해

`examples/` 아래의 기관, 출처, 수치는 모두 구조를 보여 주기 위한 **가상 데이터**입니다. 실제 글 작성에 인용하지 마세요.
