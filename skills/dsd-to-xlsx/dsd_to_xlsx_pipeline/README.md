# dsd-to-xlsx

DSD (DART 감사보고서 포맷) → xlsx **단방향** 변환 파이프라인.
다른 프로젝트로 이식 가능한 독립 패키지.

## 무엇을 하는가

- 입력: `.dsd` 파일 (CP949 파일명을 가진 ZIP — 내부에 `contents.xml`, `meta.xml`, 이미지 포함)
- 출력: `.xlsx` 파일 (재무제표 4종 + 주석 N개를 시트별로, 라운드트립용 숨김 메타 시트 5개 포함)
- **자동 검증**: 변환 직후 시트 구조·누락·메타 추출 자동 점검

xlsx → DSD 역변환과 DART 호환 빌더는 **포함하지 않습니다**.

## 의존성

- Python ≥ 3.10
- `lxml` ≥ 4.9
- `openpyxl` ≥ 3.1

## 설치

### 표준 (권장)

```bash
cd dsd_to_xlsx_pipeline
pip install .
```

설치 후:

```bash
dsd2xlsx input.dsd output.xlsx          # 단일 변환 + 자동 검증
dsd2xlsx --verify converted.xlsx        # 검증만
dsd2xlsx --batch input_dir/ output_dir/ # 폴더 일괄
dsd2xlsx --version
```

### Install 없이 (단독 실행)

`examples/*.py` 와 `python -m dsd_to_xlsx` 모두 자동으로 `src/` 를 `sys.path`에 추가하므로 install 없이도 동작:

```bash
python examples/convert_one.py input.dsd output.xlsx
python examples/verify_xlsx.py converted.xlsx
python examples/convert_batch.py input_dir/ output_dir/
python examples/test_self.py input.dsd                   # self-test
```

또는 PYTHONPATH로:

```bash
PYTHONPATH=src python -m dsd_to_xlsx input.dsd output.xlsx
```

> ⚠️ **Windows 한글 경로 주의**: 패키지 자체가 한글 폴더 안에 있으면 `pip install -e` (editable) 시
> site-packages의 `.pth` 파일 인코딩 충돌이 발생할 수 있다 (Python `site` 모듈이 cp949로 read).
> editable 대신 일반 `pip install` 또는 `python -m dsd_to_xlsx` (sys.path 자동 패치) 사용 권장.

## 사용법 (Python API)

```python
from dsd_to_xlsx import convert, verify

out = convert("audit.dsd", "audit.xlsx")
report = verify(out)
print(report.format())

if not report.ok:
    print("누락 항목:", report.missing_fs, report.missing_meta, report.missing_note_numbers)
```

저수준 API:

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

`VerifyReport.ok` 가 False면 누락 항목 있음. 종료 코드도 `2` 반환 (스크립트 분기 가능).

## 폴더 구조

```
dsd_to_xlsx_pipeline/
├── README.md
├── pyproject.toml          # [project.scripts] dsd2xlsx
├── requirements.txt        # lxml>=4.9, openpyxl>=3.1
├── examples/
│   ├── convert_one.py      # 변환 + 자동 검증
│   ├── convert_batch.py    # 폴더 일괄 + 자동 검증
│   ├── verify_xlsx.py      # 검증만
│   └── test_self.py        # 회귀 self-test
└── src/
    └── dsd_to_xlsx/
        ├── __init__.py     # convert / parse / render_xlsx / verify / __version__
        ├── __main__.py     # CLI (python -m dsd_to_xlsx)
        ├── verify.py       # 자동 검증 모듈
        ├── models.py
        ├── core/           # ZIP + XML 파싱
        ├── parsers/        # XML → DocumentNode
        ├── extractors/     # 도메인 데이터 추출
        └── renderers/      # → xlsx 출력
```

## 산출되는 xlsx 시트 구성

- **표지** 1개 (`보고서정보` 등)
- **재무제표 4개**: 재무상태표 / 포괄손익계산서 / 자본변동표 / 현금흐름표
- **주석** N개: `1. 일반사항`, `2. 중요한 회계정책`, …
- **숨김 메타 시트 5개** (`_STRUCTURE`, `_META`, `_EXTRACTIONS`, `_ACODES`, `_CELLMAP`) — 라운드트립 정보. 제거하면 xlsx → DSD 역변환 시 fidelity 손실.

## 한계

- DART 뷰어가 요구하는 5가지 조건(스키마 선언, ACODE, DOCUMENT-INFO id, USERMARK-on-TITLE 금지, COMPANY-NAME AREGCIK)에 대한 **검증 / 빌더는 미포함**. 본 패키지는 읽기 + xlsx 출력만 담당.

## 라이선스

MIT
