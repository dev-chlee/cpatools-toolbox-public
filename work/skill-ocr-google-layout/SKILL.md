---
name: ocr-google-layout
title: Google OCR (Document AI 레이아웃 파서)
category: utility
tags: [OCR, PDF, Document AI]
description: GCP Document AI Layout Parser 기반 PDF OCR. inbox 폴더의 PDF를 배치 처리해 레이아웃·표 구조를 보존한 HTML·Markdown으로 변환한다. PDF OCR·문서 레이아웃 인식·표 인식·스캔 문서 텍스트 추출이 필요할 때 사용한다.
---

# OCR Google Layout

## 목적
- inbox 폴더 내 PDF를 배치 OCR (GCP Document AI Layout Parser)
- 결과를 `YYYY-MM-DD-HHMM_대표파일명/` (KST) 폴더로 정리
- 레이아웃·표 구조를 보존한 `*.html` / `*.md` 출력

## 설정

우선순위: **CLI flag > 환경변수(.env) > 기본값**. 셸 환경변수로 설정하거나,
스킬 폴더에 `.env` 파일로 둔다 — 이 스킬은 `.env` 를 **자동 로드한다**(`config.py`
의 `load_dotenv`). `.env` 는 아래 예시 블록을 그대로 복사해 값만 채우면 된다. 이
스킬은 GCP Document AI를 호출하므로 GCP 프로젝트·프로세서·서비스 계정이 반드시 있어야 한다.

| 변수 | 의미 | 필수 | 기본값 |
|---|---|---|---|
| `GCP_PROJECT_ID` | GCP 프로젝트 ID | ✓ | (없음) |
| `DOCUMENTAI_PROCESSOR_ID` | Document AI Layout Parser 프로세서 ID | ✓ | (없음) |
| `GOOGLE_APPLICATION_CREDENTIALS` | 서비스 계정 JSON 파일 **경로** (값/내용 아님) | ✓ | (없음) |
| `GCP_LOCATION` | 프로세서 리전 | ✗ | `us` |
| `GCS_BUCKET` | 15p 초과 배치 처리용 GCS 버킷명 | ✗(대용량만) | (없음) |
| `OCR_INBOX_DIR` | 입력 PDF 폴더 | ✗ | `./inbox` (호출 CWD 기준) |
| `OCR_OUTPUT_ROOT` | 산출물 루트 | ✗ | `./output` (호출 CWD 기준) |
| `WORK_ROOT` | inbox·output 공통 루트 (위 둘 미설정 시) | ✗ | `.` |

처리 옵션(`CHUNK_SIZE`, `RETURN_IMAGES`, `MAX_ONLINE_PAGES` 등)은 모두 기본값이
최고 품질이며 대개 그대로 둔다 — 필수 키는 아래 예시 블록 참조.

```ini
# .env (아래 키를 그대로 복사해 값 채우기 — config.py 가 자동 로드)
GCP_PROJECT_ID=your-project-id
DOCUMENTAI_PROCESSOR_ID=your-processor-id
GOOGLE_APPLICATION_CREDENTIALS=./secrets/service-account.json
GCP_LOCATION=us
# OCR_INBOX_DIR=./inbox
# OCR_OUTPUT_ROOT=./output
# GCS_BUCKET=your-gcs-bucket-name   # 15p 초과 배치 처리 시
```

### 외부 전제 (preflight — 실행 전 확인)
- **Python deps**: `pip install .` (pyproject 기반)
- **system 바이너리**: 없음
- **cloud 자격증명**: GCP 서비스 계정 JSON. `GOOGLE_APPLICATION_CREDENTIALS`에
  **파일 경로만** 설정(키 내용을 코드·.env에 붙여넣지 않는다). 서비스 계정에
  Document AI 호출 권한(필요 시 대상 GCS 버킷 읽기/쓰기)을 부여한다.
- **GCP 리소스**: Document AI **Layout Parser** 프로세서를 생성하고 그
  프로세서 ID를 `DOCUMENTAI_PROCESSOR_ID`로 설정. 프로젝트의 Document AI API 활성화.
- **network/API**: Document AI 엔드포인트 접근(아웃바운드 네트워크 필요).

## 1회 초기화
```bash
cd <skill-dir>
python scripts/setup_venv.py            # 기본: 스킬 폴더 .venv 생성 + 의존성 설치
# (다른 위치를 원하면) python scripts/setup_venv.py --venv <경로>
# 위 `## 설정` 의 .env 예시 블록을 복사해 `.env` 파일을 만들고 값 채우기
# (또는 동일 키를 셸 환경변수로 export)
```

## inbox 배치 실행
```bash
cd <skill-dir>
python scripts/run_inbox_batch.py --inbox "$OCR_INBOX_DIR" --output-root "$OCR_OUTPUT_ROOT"
```

환경변수/기본값을 사용할 수도 있다(인자 없이 실행하면 `./inbox` → `./output`).

```bash
python scripts/run_inbox_batch.py
```

## 실동작 기준
- 기본 inbox: `OCR_INBOX_DIR` 또는 `./inbox`
- 기본 output root: `OCR_OUTPUT_ROOT` 또는 `./output`
- 배치 결과 폴더명: `YYYY-MM-DD-HHMM_대표이름` (KST)
- 파일별 분리 저장: 각 PDF마다 배치 폴더 하위에 독립 폴더 생성
- 성공 파일: 결과 저장 후 원본 PDF를 해당 파일 폴더로 이동
- 실패 파일: inbox에 유지 (배치는 파일 단위 독립 — 하나 실패가 전체를 중단시키지 않음)
- 출력 파일: `*.html`, `*.md`

## 단건/폴더 직접 실행
```bash
python scripts/run_ocr_google.py --file "<pdf1>" "<pdf2>" --output "<output_dir>"
python scripts/run_ocr_google.py --dir "<folder>" --output "<output_dir>"
python scripts/run_ocr_google.py --gcs gs://<bucket>/<path>
```

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
