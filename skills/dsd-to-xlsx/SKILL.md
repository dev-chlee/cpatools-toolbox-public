---
name: dsd-to-xlsx
published: true
title: DSD → XLSX 변환
description: |
  DART 감사보고서·검토보고서 포맷인 .dsd 파일을 시트별 구조의 xlsx로 변환하는 스킬.
  단일 파일 변환과 폴더 일괄 변환을 모두 지원하며, 변환 직후 시트 구조·메타·주석 번호 누락을 자동 검증한다.
  사용 시점: (1) DART에 제출된 .dsd 파일을 엑셀로 열어 검토할 때, (2) 감사보고서·검토보고서를 표 구조로 추출하여 후속 분석(풋팅·교차검증·집계)에 사용할 때, (3) 분기·반기·기말 보고서를 일괄 변환해 비교 대조할 때.
  "DSD", ".dsd", "DART", "감사보고서 변환", "검토보고서 변환", "DSD 변환", "dsd to xlsx", "DART 보고서" 등의 표현이 나오면 이 스킬을 사용한다.
---

# DSD → XLSX 변환 스킬

## 개요

이 스킬은 DART에 제출된 `.dsd` (감사보고서·검토보고서 포맷) 파일을 시트별로 구조화된 `.xlsx` 파일로 변환한다. 단방향(.dsd → .xlsx) 변환이며, 변환 직후 시트 구조·메타·주석 누락을 자동 점검한다.

내부 구조는 `dsd_to_xlsx_pipeline/` 하위 독립 Python 패키지로 분리되어 있어, 다른 프로젝트에 그대로 이식 가능하다.

## 입력 / 출력

### 입력
- `.dsd` 파일 (CP949 파일명 ZIP — 내부에 `contents.xml`, `meta.xml`, 이미지 포함)
- 일괄 변환 시 `.dsd`가 들어 있는 폴더 경로

### 출력 (xlsx 시트 구성)
- **표지** 1개 (`보고서정보` 등)
- **재무제표 4개**: 재무상태표 / 포괄손익계산서 / 자본변동표 / 현금흐름표
- **주석** N개: `1. 일반사항`, `2. 중요한 회계정책`, …
- **숨김 메타 시트 5개** (`_STRUCTURE`, `_META`, `_EXTRACTIONS`, `_ACODES`, `_CELLMAP`) — 라운드트립 정보. 제거 시 xlsx → DSD 역변환 fidelity 손실

## 의존성

```
Python ≥ 3.10
lxml ≥ 4.9
openpyxl ≥ 3.1
```

설치:

```bash
cd skills/dsd-to-xlsx/dsd_to_xlsx_pipeline
pip install .
```

설치 없이 단독 실행도 가능. `examples/*.py`와 `python -m dsd_to_xlsx`가 `src/`를 자동으로 `sys.path`에 추가한다.

> ⚠️ **Windows 한글 경로 주의**: 패키지 경로에 한글이 포함되면 `pip install -e` (editable) 시 site-packages의 `.pth` cp949 인코딩 충돌이 발생할 수 있다. editable 대신 일반 `pip install` 또는 `python -m dsd_to_xlsx` (sys.path 자동 패치) 사용 권장.

## 사용법

### CLI (설치 후)

```bash
dsd2xlsx input.dsd output.xlsx          # 단일 변환 + 자동 검증
dsd2xlsx --verify converted.xlsx        # 검증만
dsd2xlsx --batch input_dir/ output_dir/ # 폴더 일괄
dsd2xlsx --version
```

### 단독 실행 (install 없이)

```bash
cd skills/dsd-to-xlsx/dsd_to_xlsx_pipeline
python examples/convert_one.py input.dsd output.xlsx
python examples/verify_xlsx.py converted.xlsx
python examples/convert_batch.py input_dir/ output_dir/
python examples/test_self.py input.dsd                   # 회귀 self-test
```

또는 PYTHONPATH로:

```bash
PYTHONPATH=src python -m dsd_to_xlsx input.dsd output.xlsx
```

### Python API

```python
from dsd_to_xlsx import convert, verify

out = convert("audit.dsd", "audit.xlsx")
report = verify(out)
print(report.format())

if not report.ok:
    print("누락 항목:", report.missing_fs, report.missing_meta, report.missing_note_numbers)
```

저수준 API (직접 파싱·렌더링):

```python
from dsd_to_xlsx import parse, render_xlsx

doc = parse("audit.dsd")              # DsdDocument
render_xlsx(doc, "audit.xlsx")
```

## 자동 검증 (`verify`)

변환 직후 또는 별도로 호출하여 다음을 체크:

| 검증 항목 | 누락 시 |
|---|---|
| 재무제표 4종 (재무상태표·포괄손익계산서·자본변동표·현금흐름표) | `missing_fs` |
| 메타 시트 5종 (`_STRUCTURE`/`_META`/`_EXTRACTIONS`/`_ACODES`/`_CELLMAP`) | `missing_meta` |
| 주석 번호 1~N (중간 빠짐) | `missing_note_numbers` |
| 빈 시트 (rows=0 또는 cols=0) | `empty_sheets` |
| 회사명·기수·결산일·단위 자동 추출 | 필드값 None |

`VerifyReport.ok`가 False면 누락 항목 있음. CLI 종료 코드도 `2` 반환하여 스크립트에서 분기 가능.

## 워크플로우

### Phase 1: 입력 파악
- 사용자에게 `.dsd` 파일 경로 또는 폴더 경로 확인
- 단일/일괄 여부, 출력 경로 확인

### Phase 2: 변환 실행
- 단일: `dsd2xlsx input.dsd output.xlsx` 또는 `convert(...)`
- 일괄: `dsd2xlsx --batch input_dir/ output_dir/`

### Phase 3: 자동 검증
- 변환 직후 `verify()` 결과 확인
- `report.ok == False`면 누락 항목을 사용자에게 보고

### Phase 4: 후속 작업 (선택)
- 변환된 xlsx를 `footing-verifier` 스킬에 입력으로 전달하여 풋팅 검증 가능
- `_STRUCTURE` / `_CELLMAP` 메타 시트를 활용해 셀 위치 기반 자동 분석 가능

## 한계

- **단방향 변환만**: xlsx → DSD 역변환과 DART 호환 빌더는 포함하지 않는다
- **DART 뷰어 검증 X**: DART 뷰어가 요구하는 5가지 조건(스키마 선언, ACODE, DOCUMENT-INFO id, USERMARK-on-TITLE 금지, COMPANY-NAME AREGCIK)에 대한 검증·빌더는 미포함. 본 패키지는 읽기 + xlsx 출력만 담당
- **이미지·차트**: DSD 내부 이미지·차트는 변환 시 누락될 수 있다 (xlsx 표 구조 우선)
- **CP949 한글 파일명**: ZIP 내부 파일명이 CP949면 자동 디코딩하지만, 일부 환경에서 깨질 수 있다

## 폴더 구조

```
skills/dsd-to-xlsx/
├── SKILL.md                       ← 이 파일
└── dsd_to_xlsx_pipeline/          ← 독립 Python 패키지
    ├── README.md                  ← 패키지 자체 문서
    ├── pyproject.toml             ← [project.scripts] dsd2xlsx
    ├── requirements.txt           ← lxml>=4.9, openpyxl>=3.1
    ├── examples/                  ← 설치 없이 실행 가능한 예제
    │   ├── convert_one.py
    │   ├── convert_batch.py
    │   ├── verify_xlsx.py
    │   └── test_self.py
    └── src/dsd_to_xlsx/
        ├── __init__.py            ← convert / parse / render_xlsx / verify
        ├── __main__.py            ← CLI 엔트리
        ├── verify.py              ← 자동 검증 모듈
        ├── models.py
        ├── core/                  ← ZIP + XML 파싱
        ├── parsers/               ← XML → DocumentNode
        ├── extractors/            ← 도메인 데이터 추출 (회사명·기수·결산일 등)
        └── renderers/             ← → xlsx 출력
```

## 핵심 원칙

1. **원본 보존**: `.dsd` 원본은 절대 수정하지 않는다. 변환 결과는 새 xlsx 파일
2. **숨김 메타 시트 유지**: `_STRUCTURE` 등 5개 메타 시트는 라운드트립용. 사용자 변환 결과 공유 시 함께 보존
3. **자동 검증 필수**: 모든 변환 직후 `verify()` 호출하여 누락 점검. 누락이 있으면 사용자에게 보고
4. **클라이언트 데이터 분리**: 실제 DART 보고서 .dsd / 변환 결과 .xlsx는 절대 repo에 커밋하지 않는다 (`.gitignore` 패턴 자동 차단)

## 예시 트리거

- ".dsd 파일 엑셀로 변환해줘"
- "DART 감사보고서를 시트별로 분리하고 싶어"
- "이 폴더 안의 .dsd 파일들 다 xlsx로 바꿔줘"
- "변환된 xlsx에 메타데이터(회사명·기수·결산일) 자동 추출 가능?"
- "DSD 변환 후 풋팅 검증까지 한 번에"
