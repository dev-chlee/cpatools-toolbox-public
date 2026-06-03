---
name: ocr-google-layout
title: Google OCR (Document AI 레이아웃 파서)
category: utility
tags: [OCR, PDF, Document AI]
description: GCP Document AI Layout Parser 기반 PDF OCR 스킬. `.ocr` 커맨드 또는 자연어 OCR 요청으로 `$OCR_INBOX_DIR`의 PDF를 배치 처리하고 `$OCR_OUTPUT_ROOT`에 결과를 저장할 때 사용한다.
---

# OCR Google Layout

## 목적
- `.ocr` 운영 호출 전용
- `$OCR_INBOX_DIR/` 내 PDF 배치 OCR
- 결과를 `$OCR_OUTPUT_ROOT/YYYY-MM-DD-HHMM_대표파일명/`에 정리

## 운영 경로 정책

```bash
WORK_ROOT=/opt/data/_external/gd/hermes-mount/work
OCR_BASE_DIR=$WORK_ROOT/02_ocr
OCR_INBOX_DIR=$WORK_ROOT/02_ocr/_inbox
OCR_OUTPUT_ROOT=$WORK_ROOT/02_ocr
AGENT_CREDENTIALS_DIR=/opt/data/credentials
MY_SKILLS_VENV_ROOT=/opt/data/venvs/my-skills
GOOGLE_APPLICATION_CREDENTIALS=$AGENT_CREDENTIALS_DIR/google_docai.json
```

Windows에서 직접 실행할 때는 Linux venv를 공유하지 않는다. Windows 전용 venv는 예를 들어 아래처럼 별도로 둔다.

```text
D:\00_Infra\venvs\my-skills\ocr-google-layout
```

## 1회 초기화
```bash
cd <skill-dir>
python3 scripts/setup_venv.py
cp .env.example .env
```

`.env` 필수값:
- `GCP_PROJECT_ID`
- `DOCUMENTAI_PROCESSOR_ID`
- `GOOGLE_APPLICATION_CREDENTIALS` (`$AGENT_CREDENTIALS_DIR/google_docai.json` 권장)

## . 커맨드

### `.ocr`
```bash
cd <skill-dir>
/opt/data/venvs/my-skills/ocr-google-layout/bin/python scripts/run_inbox_batch.py   --inbox "$OCR_INBOX_DIR"   --output-root "$OCR_OUTPUT_ROOT"
```

환경변수 기본값을 사용할 수도 있다.

```bash
WORK_ROOT=/opt/data/_external/gd/hermes-mount/work AGENT_CREDENTIALS_DIR=/opt/data/credentials GOOGLE_APPLICATION_CREDENTIALS=/opt/data/credentials/google_docai.json /opt/data/venvs/my-skills/ocr-google-layout/bin/python scripts/run_inbox_batch.py
```

## 실동작 기준 (OCR 공통 정책)
- 기본 inbox: `OCR_INBOX_DIR` 또는 `$WORK_ROOT/02_ocr/_inbox`
- 기본 output root: `OCR_OUTPUT_ROOT` 또는 `$WORK_ROOT/02_ocr`
- 배치 결과 폴더명: `YYYY-MM-DD-HHMM_대표이름` (KST)
- 파일별 분리 저장: 각 PDF마다 배치 폴더 하위에 독립 폴더 생성
- 성공 파일: 결과 저장 후 원본 PDF를 해당 파일 폴더로 이동
- 실패 파일: inbox에 유지
- 출력 파일: `*.html`, `*.md`

## 단건/폴더 직접 실행
```bash
/opt/data/venvs/my-skills/ocr-google-layout/bin/python scripts/run_ocr_google.py --file "<pdf1>" "<pdf2>" --output "<output_dir>"
/opt/data/venvs/my-skills/ocr-google-layout/bin/python scripts/run_ocr_google.py --dir "<folder>" --output "<output_dir>"
/opt/data/venvs/my-skills/ocr-google-layout/bin/python scripts/run_ocr_google.py --gcs gs://<bucket>/<path>
```

## 의존성 / venv 정책
- Hermes/Docker 실행용 venv는 스킬 소스 트리 밖에 둔다: `/opt/data/venvs/my-skills/ocr-google-layout`
- Windows 직접 실행용 venv는 별도 생성한다: `D:_Dev_skills\.venvs\ocr-google-layout`
- `skill-*/.venv` 또는 `.venv-openclaw`를 만들거나 마이그레이션하지 않는다.
- `scripts/setup_venv.py`는 기본적으로 외부 venv root를 사용한다.

## 보안 원칙
- Google service account JSON은 코드·설정파일·.env에 직접 붙여넣지 않는다.
- `GOOGLE_APPLICATION_CREDENTIALS`에는 credential 파일 경로만 설정한다.
- 권장 위치: `$AGENT_CREDENTIALS_DIR/google_docai.json`
- `.env`는 gitignore 대상이며 migration artifact가 아니다.

## 트러블슈팅 로드 기준
아래 상황에서만 `references/troubleshooting.md`를 읽는다.
- venv/uv 환경 준비 실패
- 의존성 누락 (`ModuleNotFoundError`)
- `.env` 필수값 누락
- GCS 처리 실패
