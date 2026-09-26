---
name: ocr-google-layout
title: 표·레이아웃 보존 PDF OCR
category: utility
tags: [OCR, PDF, Document AI]
version: 0.4.0
description: GCP Document AI Layout Parser 기반 PDF OCR. inbox 폴더의 PDF를 배치 처리해 레이아웃·표 구조를 보존한 HTML·Markdown으로 변환한다. PDF OCR·문서 레이아웃 인식·표 인식·스캔 문서 텍스트 추출이 필요할 때 사용한다. 등기부 OCR은 이미지에서 취소선 존재 여부를 먼저 확인하고, 존재하거나 불확실하면 상세 범위 판독을, 없다고 확인되면 텍스트 분석을 진행한다. 근저당 합계·공동담보 분석 자체는 이 스킬의 범위가 아니다.
---

# OCR Google Layout

## 목적
- inbox 폴더 내 PDF를 배치 OCR (GCP Document AI Layout Parser)
- 결과를 `YYYY-MM-DD-HHMM_대표파일명/` (KST) 폴더로 정리
- 레이아웃·표 구조를 보존한 `*.html` / `*.md` 출력

## 등기부 취소선 판독·현행본 생성

등기부 OCR 결과의 분석·현행 정보 추출에는 [references/registry-visual-review.md](references/registry-visual-review.md)를 읽고 `scripts/registry_visual_review.py`의 **사전 판독 → 조건별 분기**를 사용한다. 이미 OCR 결과가 있으면 재차 클라우드 OCR을 호출할 필요가 없다. 이 후처리는 로컬에서 동작하며 GCP 자격증명이 필요하지 않다.

실자료와 산출물은 저장소 밖 **보관소**에 둔다. `<보관소>` 는 환경변수 `CPA_SKILLS_STORAGE` 가 있으면 `$CPA_SKILLS_STORAGE/skill-ocr-google-layout`, 없으면 `~/cpa-skills-data/skill-ocr-google-layout` 이고 그 아래 `input`(받은 PDF `inbox/`, 등기부 원본)·`work`(판독 중간물)·`output`(OCR 결과·현행본)·`logs` 칸을 쓴다. **git 저장소 안 경로에는 쓰지 않는다** — 스크립트가 종료코드 2로 거부한다.

이 절차는 OCR 결과에서 취소선 범위를 판독하고 현행 정보를 분리하는 단계까지만 담당한다. 근저당 합계, 공동담보 중복 제거, 담보 여력 계산은 별도의 등기부 분석 절차에서 수행한다.

1. `screen`이 만든 **문서 전체 페이지 이미지**를 AI가 보고 취소선 존재 여부를 `screening.json`에 기록한다. MD의 취소선 마커 부재만으로 없음이라고 판단하지 않는다.
2. `route`는 **한 쪽이라도 존재·불확실이면 상세 이미지 판독**으로 보낸다. OCR 서식 단서와 이미지의 없음 판정이 충돌해도 상세 판독한다. OCR HTML이 있으면 기존 상세 판독 대장까지 생성한다.
3. **모든 쪽에서 없음이 확인되면 텍스트 분석**으로 진행한다. 기존 OCR 원문을 보존해 사용하고, OCR이 없으면 PDF 텍스트를 추출한다. 텍스트도 없는 페이지는 일반 OCR이 필요하다고 반환한다. 이 분기 결과는 현행 확정본이 아니며 후속 변경·말소·소유권이전은 텍스트 분석에서 판단한다.

```bash
python scripts/registry_visual_review.py screen --pdf <보관소>/input/registry.pdf --ocr <보관소>/input/registry.html --output <보관소>/work/screen
# 전체 페이지 이미지를 보고 <보관소>/work/screen/screening.json 작성
python scripts/registry_visual_review.py route --bundle <보관소>/work/screen/screen-bundle.json --screening <보관소>/work/screen/screening.json --output <보관소>/work/route
```

일반 OCR 실행 파일만 호출하면 이 AI 판독이 자동 수행되지는 않는다. 스킬을 실행하는 AI가 사전 이미지 판독과 필요한 상세 판독을 수행해야 한다. 미검토 기록은 텍스트 경로로 통과하지 못한다.

상세 이미지 판독 경로의 규칙:

- 원본 PDF의 **등기부 본체 전체 페이지 이미지를 직접 판독**한다. OCR 텍스트·HTML의 `<s>` 표시·수평선 탐지만으로 취소 여부를 확정하지 않는다. 가는 선·숫자가 불명확하면 확대 이미지를 확인한다.
- 표제부·갑구·을구·담보 목록 모두 검토한다. 취소 범위가 항목 전체인지 금액·주소·담보 일부인지 구분하고, 후속 말소·변경·소유권이전 및 다음 쪽 계속 행을 연결한다. 취소선이 없는 과거 소유자를 현 소유자로 남기거나, 일부 변경 때문에 유효한 권리 전체를 지우지 않는다.
- 현행 내용은 원본 발행·열람일 기준이다. 미판독·누락 페이지·불확실한 범위가 있으면 `export`가 실패해야 한다. 통과시키기 위해 `image_reviewed`·`text_complete`를 일괄 참으로 설정하지 않는다.
- 원본 PDF와 원문 OCR은 보존한다. 검증된 현행 정보만 `current.html`·`current.json`·`current.txt`에 실제로 남기고, 삭제된 원문·이유·이미지 좌표는 `audit.json`으로 분리한다. 원문 OCR을 현행본으로 표시하거나 이전 결과를 덮어쓰지 않는다.

```bash
# route가 상세 판독 대장을 생성한 경우 이미지 범위를 보고 review.json 작성
python scripts/registry_visual_review.py validate --bundle <보관소>/work/route/detail-review/bundle.json --review <보관소>/work/route/detail-review/review.json
python scripts/registry_visual_review.py export --bundle <보관소>/work/route/detail-review/bundle.json --review <보관소>/work/route/detail-review/review.json --output <보관소>/output/current
```

코드는 판독 완료 여부·문자 범위·원본 해시·항목 간 상태의 모순을 검증한다. **이미지를 보는 일과 등기 상태 판단은 이미지 판독이 가능한 AI 또는 사람이 수행**한다. 자동 선 탐지의 정확도나 검토자 판단 자체를 코드가 보증하는 것은 아니다.

로컬 회귀 검증(스킬 루트): `python -m unittest discover -s tests -v`. CLI 확인: `python scripts/registry_visual_review.py --help`.

## 설정

우선순위: **CLI flag > 환경변수(.env) > 기본값**. 셸 환경변수로 설정하거나,
스킬 폴더에 `.env` 파일로 둔다 — 이 스킬은 `.env` 를 **자동 로드한다**(`config.py`
의 `load_dotenv`). `.env` 는 아래 예시 블록을 그대로 복사해 값만 채우면 된다. 이
스킬은 GCP Document AI를 호출하므로 GCP 프로젝트·프로세서·서비스 계정이 반드시 있어야 한다.

> **최초 1회 GCP 설정이 안 되어 있으면** `references/gcp-onboarding.md` 를 따른다 — AI(Claude)가
> 사용자와 함께 `gcloud`/`curl` 명령으로 프로젝트·API·Layout Parser 프로세서·서비스계정 키·`.env`
> 까지 만들어 준다. (개발 지식 없는 사용자는 Claude 에게 "이 스킬 온보딩 해줘"라고 요청.)

| 변수 | 의미 | 필수 | 기본값 |
|---|---|---|---|
| `GCP_PROJECT_ID` | GCP 프로젝트 ID | ✓ | (없음) |
| `DOCUMENTAI_PROCESSOR_ID` | Document AI Layout Parser 프로세서 ID | ✓ | (없음) |
| `GOOGLE_APPLICATION_CREDENTIALS` | 서비스 계정 JSON 파일 **경로** (값/내용 아님) | ✓ | (없음) |
| `GCP_LOCATION` | 프로세서 리전 | ✗ | `us` |
| `GCS_BUCKET` | 15p 초과 배치 처리용 GCS 버킷명 | ✗(대용량만) | (없음) |
| `CPA_SKILLS_STORAGE` | 보관소 루트. 받은 PDF 는 `<루트>/skill-ocr-google-layout/input/inbox`(`--inbox`), 결과는 `.../output`(`--output-root`·`--output`) | ✗ | `~/cpa-skills-data` |

처리 옵션(`CHUNK_SIZE`, `RETURN_IMAGES`, `MAX_ONLINE_PAGES` 등)은 모두 기본값이
최고 품질이며 대개 그대로 둔다 — 필수 키는 아래 예시 블록 참조.

```ini
# .env (아래 키를 그대로 복사해 값 채우기 — config.py 가 자동 로드)
GCP_PROJECT_ID=your-project-id
DOCUMENTAI_PROCESSOR_ID=your-processor-id
GOOGLE_APPLICATION_CREDENTIALS=./secrets/service-account.json
GCP_LOCATION=us
# GCS_BUCKET=your-gcs-bucket-name   # 15p 초과 배치 처리 시
```

### 외부 전제 (preflight — 실행 전 확인)
- **Python deps**: `python scripts/setup_venv.py` (스킬-로컬 `.venv` 생성 + 의존성 설치).
  uv 있으면 `uv sync` 로도 가능(`run_ocr_google.py` 는 uv 런타임 우선).
- **system 바이너리**: 없음
- **cloud 자격증명**: GCP 서비스 계정 JSON. `GOOGLE_APPLICATION_CREDENTIALS`에
  **파일 경로만** 설정(키 내용을 코드·.env에 붙여넣지 않는다). 서비스 계정에
  Document AI 호출 권한(필요 시 대상 GCS 버킷 읽기/쓰기)을 부여한다.
- **GCP 리소스**: Document AI **Layout Parser** 프로세서를 생성하고 그
  프로세서 ID를 `DOCUMENTAI_PROCESSOR_ID`로 설정. 프로젝트의 Document AI API 활성화.
  → 위 세 가지(프로젝트·프로세서·서비스계정) 최초 설정은 **`references/gcp-onboarding.md`**(AI 실행형) 참고.
- **network/API**: Document AI 엔드포인트 접근(아웃바운드 네트워크 필요).

## 1회 초기화
```bash
cd <skill-dir>
python scripts/setup_venv.py            # 기본: 스킬 폴더 .venv 생성 + 의존성 설치
# (다른 위치를 원하면) python scripts/setup_venv.py --venv <경로>
# 위 `## 설정` 의 .env 예시 블록을 복사해 `.env` 파일을 만들고 값 채우기
# (또는 동일 키를 셸 환경변수로 export)
```
GCP 리소스(프로젝트·프로세서·서비스계정 키)가 아직 없으면 **먼저** `references/gcp-onboarding.md` 를
따른다(AI 실행형 — Claude 가 명령을 대신 실행하며 `.env` 까지 채운다).

## inbox 배치 실행
```bash
cd <skill-dir>
python scripts/run_inbox_batch.py --inbox "<받은 PDF 폴더>" --output-root "<결과 루트>"
```

옵션 없이 실행하면 보관소를 쓴다(`<보관소>/input/inbox` → `<보관소>/output`).

```bash
python scripts/run_inbox_batch.py
```

원응답(Document AI 응답 JSON)을 모든 파일에 남기려면 `--save-response` 를 붙인다(기본 꺼짐).
원응답은 문서 내용을 담은 고객 자료이므로 결과 폴더 밖으로 옮기지 않는다.

## 실동작 기준
- 기본 inbox: `--inbox` 또는 `<보관소>/input/inbox`
- 기본 output root: `--output-root` 또는 `<보관소>/output` (git 저장소 안이면 거부)
- 배치 결과 폴더명: `YYYY-MM-DD-HHMM_대표이름` (KST)
- 파일별 분리 저장: 각 PDF마다 배치 폴더 하위에 독립 폴더 생성
- 성공 파일: 결과 저장 후 원본 PDF를 해당 파일 폴더로 이동
- 실패 파일: inbox에 유지 (배치는 파일 단위 독립 — 하나 실패가 전체를 중단시키지 않음)
- 출력 파일: `*.html`, `*.md`
- 변환 직후 검증: HTML·MD를 쓰기 전에 원응답의 모든 텍스트 블록(페이지 하단 문구 제외)과 대조한다.
  허용차는 없다. 아래 중 하나라도 해당하면 그 파일은 **검증 실패**다.
  - 텍스트 없음: 원응답에 비교할 텍스트 블록이 없다.
  - MD 누락: 블록 텍스트가 문서 순서대로 MD에 없다.
  - HTML 누락: 블록 텍스트가 HTML 본문 칸에 없다.
  - HTML 페이지 오배치: 블록이 원래 페이지가 아닌 곳에 놓였다. 원래 빈 페이지와 여러 페이지에 걸친
    표·목록 내부는 예외다.
  - 표 구조 불일치: 표 개수, 표마다 행·열 수, 칸별 텍스트가 원응답과 다르다(MD·HTML 각각).
  - 표 구조 확인 불가: 병합 셀이나 표 안의 표가 있다. 변환이 이 구조를 표현하지 못하므로 확인된 것으로
    세지 않는다.
  - 이 검사는 출력이 **구글 OCR 응답**과 같은지를 본다. PDF 원본과의 대조가 아니므로, 구글이 표를
    잘못 나눠 인식한 경우는 잡지 못한다.
- 검증 실패 파일:
  - 실패로 집계하고 원본 PDF는 inbox에 남긴다. 다음 배치 때 다시 OCR한다.
  - 결과 폴더 이름 끝에 `_검증실패` 를 붙인다. 옛 실패 폴더는 재처리 뒤에도 지우지 않는다.
  - MD·HTML 맨 위에 경고를 넣는다.
  - `<파일명>_verify_failed.json`(누락·오배치·표 구조 불일치 목록)과 `<파일명>_response.json`(원응답)을 남긴다.
  - 직접 실행(`run_ocr_google.py` — 단건·여러 파일·폴더)은 검증 실패가 하나라도 있으면 종료 코드 3으로 끝난다.
- 검증 결과 한 줄(검사한 블록 수, 대조한 표 수, 하단 문구 제외 건수·글자 수, 페이지 확인 불가 건수)은 결과 폴더의
  `processing.log` 에 남는다.
- 배치 요약: `DONE total=.. success=.. failed=.. file_moved=.. batch=.. verify_failed=..`
  (`failed` 는 검증 실패를 포함한 전체 실패 수)

## 단건/폴더 직접 실행
```bash
python scripts/run_ocr_google.py --file "<pdf1>" "<pdf2>" --output "<output_dir>"
python scripts/run_ocr_google.py --dir "<folder>" --output "<output_dir>"
python scripts/run_ocr_google.py --gcs gs://<bucket>/<path>
```

- `--output` 을 빼면 `<보관소>/output` 에 쓴다. git 저장소 안 경로는 거부한다.

- `--save-response`: 검증 결과와 관계없이 `<파일명>_response.json` 을 결과 폴더에 남긴다.
- 원응답으로 다시 변환하기(API 호출 없음): `--file "<pdf>" --output "<새 출력 폴더>" --cache "<파일명>_response.json"`.
  GCP 환경변수는 여전히 필요하다(설정을 먼저 읽는다). 온라인 한도(`MAX_ONLINE_PAGES`, 기본 15쪽)를 넘는 PDF에 `--no-parallel` 을 붙이면
  캐시를 쓰지 않고 API를 호출하므로 재변환에는 쓰지 않는다.

## 보안 원칙
- Google service account JSON은 코드·설정파일·.env에 직접 붙여넣지 않는다.
- `GOOGLE_APPLICATION_CREDENTIALS`에는 credential 파일 **경로만** 설정한다.
- `.env`는 gitignore 대상이다.

## 트러블슈팅 로드 기준
아래 상황에서만 `references/troubleshooting.md`를 읽는다.
- venv/uv 환경 준비 실패
- 의존성 누락 (`ModuleNotFoundError`)
- `.env` 필수값 누락
- GCS 처리 실패
- 검증 실패(`_검증실패` 폴더, 종료 코드 3, 텍스트 누락·페이지 오배치)
