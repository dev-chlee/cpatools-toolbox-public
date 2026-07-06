# ocr-google-layout

GCP **Document AI Layout Parser** 기반 PDF OCR Claude Skill. `inbox/` 의 PDF 를 배치 처리해
표·레이아웃 구조를 보존한 **HTML / Markdown** 으로 변환한다(스캔 문서·표 인식에 강함).

## 무엇을 하나
- `inbox/` PDF 를 **파일 단위 독립** 배치 OCR (한 건 실패가 전체를 막지 않음)
- 출력: `YYYY-MM-DD-HHMM_대표파일명/` (KST) 폴더에 `*.html` / `*.md`
- 15p 초과 대용량은 GCS 버킷 경유 batch 로 자동 처리

## 설치 & 최초 설정 (AI가 대신 실행)
이 스킬은 **GCP 프로젝트 + Document AI Layout Parser 프로세서 + 서비스 계정**이 필요하다. 개발 지식이
없어도 **Claude 에게 "이 스킬 온보딩 해줘"** 라고 하면 [`references/gcp-onboarding.md`](./references/gcp-onboarding.md)
를 따라 `gcloud`/`curl` 로 프로젝트·API·프로세서·서비스계정 키·`.env` 까지 대신 만든다.

의존성만 먼저 설치하려면:
```bash
cd <skill-dir>
python scripts/setup_venv.py   # 스킬-로컬 .venv + 의존성 (uv 있으면 uv sync 도 가능)
```
> GCP 리소스가 아직 없으면 **먼저** 위 온보딩 가이드를 따른다. 자격증명은 `secrets/` 안 JSON 파일 경로만
> `.env` 에 넣는다(키 내용을 붙여넣지 않는다 — `secrets/`·`*.json` 은 gitignore 로 차단).

## 사용법
### Claude 에게 (권장 — 자연어)
> `inbox/` 에 PDF 를 넣고 "OCR 돌려줘"

배치 처리 후 결과 폴더(HTML/MD)를 안내한다.

### CLI
```bash
python scripts/run_inbox_batch.py                         # inbox/ → output/ 배치
python scripts/run_ocr_google.py --file "<pdf>" --output "<dir>"   # 단건
python scripts/run_ocr_google.py --dir "<folder>" --output "<dir>" # 폴더
```

## 문서
- [`SKILL.md`](./SKILL.md) — 설정·CLI·env (단일 기준)
- [`references/gcp-onboarding.md`](./references/gcp-onboarding.md) — GCP 최초 설정 (AI 실행형)
- [`references/troubleshooting.md`](./references/troubleshooting.md) — 문제 해결

## 라이선스
MIT
