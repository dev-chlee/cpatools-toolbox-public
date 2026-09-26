# ocr-google-layout


GCP **Document AI Layout Parser** 기반 PDF OCR Claude Skill. 보관소 `input/inbox/` 의 PDF 를 배치 처리해
표·레이아웃 구조를 보존한 **HTML / Markdown** 으로 변환한다(스캔 문서·표 인식에 강함).

## 무엇을 하나
- 보관소 `input/inbox/` PDF 를 **파일 단위 독립** 배치 OCR (한 건 실패가 전체를 막지 않음)
- 출력: `YYYY-MM-DD-HHMM_대표파일명/` (KST) 폴더에 `*.html` / `*.md`
- 15p 초과 대용량은 GCS 버킷 경유 batch 로 자동 처리
- 등기부 OCR은 원본 페이지 이미지에서 취소선 존재 여부를 먼저 판독하고 현행 정보 검토 경로를 분리

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
> 보관소 `input/inbox/` 에 PDF 를 넣고 "OCR 돌려줘"

배치 처리 후 결과 폴더(HTML/MD)를 안내한다.

### CLI
```bash
python scripts/run_inbox_batch.py                         # <보관소>/input/inbox → <보관소>/output 배치
python scripts/run_ocr_google.py --file "<pdf>" --output "<dir>"   # 단건
python scripts/run_ocr_google.py --dir "<folder>" --output "<dir>" # 폴더
```

`<보관소>` 는 `$CPA_SKILLS_STORAGE/skill-ocr-google-layout`, 환경변수가 없으면 `~/cpa-skills-data/skill-ocr-google-layout` 이다.
실자료와 산출물은 저장소 밖 보관소에 둔다. git 저장소 안 경로에는 쓰지 않는다. 자세한 표는 `SKILL.md` 「설정」.

| 환경변수 | 의미 | 기본값 |
|---|---|---|
| `CPA_SKILLS_STORAGE` | 보관소 루트. 받은 PDF 는 `<루트>/skill-ocr-google-layout/input/inbox`(`--inbox`), 결과는 `.../output`(`--output-root`·`--output`) | `~/cpa-skills-data` |

### 등기부 취소선 사전 판독

이미 OCR 결과가 있으면 GCP를 다시 호출하지 않고 로컬 후처리만 실행할 수 있다. 먼저 전체 페이지 이미지를 만든 뒤 AI 또는 사람이 `screening.json`에 쪽별 판독을 기록하고, 라우터가 상세 이미지 검토 또는 텍스트 분석 경로를 결정한다.

```bash
python scripts/registry_visual_review.py screen --pdf <보관소>/input/registry.pdf --ocr <보관소>/input/registry.html --output <보관소>/work/screen
python scripts/registry_visual_review.py route --bundle <보관소>/work/screen/screen-bundle.json --screening <보관소>/work/screen/screening.json --output <보관소>/work/route
```

검토 계약과 현행본 내보내기 절차는 [`references/registry-visual-review.md`](./references/registry-visual-review.md)를 따른다.

## 문서
- [`SKILL.md`](./SKILL.md) — 설정·CLI·env (단일 기준)
- [`references/gcp-onboarding.md`](./references/gcp-onboarding.md) — GCP 최초 설정 (AI 실행형)
- [`references/registry-visual-review.md`](./references/registry-visual-review.md) — 등기부 취소선 판독·현행본 검증
- [`references/troubleshooting.md`](./references/troubleshooting.md) — 문제 해결

## 라이선스
MIT
