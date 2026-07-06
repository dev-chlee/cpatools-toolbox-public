# GCP 온보딩 (AI 실행형 런북)

이 문서는 **AI(Claude)가 사용자를 대신해 실행**하는 최초 1회 GCP 설정 가이드다. 대상 사용자는
개발 지식이 없는 회계사이므로, **AI 가 각 명령을 직접 실행**하고(또는 사용자에게 `!` 프리픽스로
실행하게 하고), 출력을 확인하며 `.env` 까지 채운 뒤 스모크 테스트로 마무리한다.

> 사용자가 "이 스킬 온보딩 해줘"라고 하면 이 문서 순서대로 진행한다.

## AI 실행 원칙
- **각 단계마다**: ① 무엇을 하는지 1줄 설명 → ② 명령 실행 → ③ 출력에서 필요한 값(프로젝트ID·프로세서ID
  등)을 추출·기록 → ④ 실패 시 원인과 다음 행동을 한국어로 안내.
- **대화형/브라우저 명령**(`gcloud auth login`, gcloud 설치)은 AI 가 직접 못 하므로, 사용자에게
  **`! <명령>`** 로 실행하도록 요청하고 결과를 받는다.
- **비용 주의**: Document AI Layout Parser 는 **유료**(대략 문서당 과금, 프리티어 크레딧 소진 후 청구).
  대량 처리 전 [요금표](https://cloud.google.com/document-ai/pricing)를 사용자에게 알린다.
- **리전**: Layout Parser 는 `us` 또는 `eu` 만 지원. 기본 `us`.

---

## 0. 사전 점검

```bash
gcloud --version          # gcloud CLI 설치 여부
gcloud auth list          # 로그인 계정
gcloud config get-value project 2>/dev/null   # 현재 프로젝트
```

- **gcloud 미설치**: 사용자에게 설치 안내 → https://cloud.google.com/sdk/docs/install (Windows 설치 프로그램).
  설치가 어려우면 **브라우저 [Cloud Shell](https://shell.cloud.google.com)** 에서 아래 명령을 그대로
  실행하는 방법을 안내(Cloud Shell 엔 gcloud 내장).
- **미로그인**: 사용자에게 `! gcloud auth login` (브라우저 인증) 요청.

수집·기록할 값(대화로 확정): `PROJECT_ID`, `LOCATION`(기본 us), 대용량 처리 필요 시 `BUCKET_NAME`.

---

## 1. 프로젝트 준비 (기존 사용 또는 신규)

기존 프로젝트 사용:
```bash
gcloud config set project <PROJECT_ID>
```
신규 생성(전역 유일 ID):
```bash
gcloud projects create <PROJECT_ID> --name="OCR Document AI"
gcloud config set project <PROJECT_ID>
```

**결제 연결(Document AI 필수)** — 결제 미연결이면 API 호출이 거부된다:
```bash
gcloud billing accounts list                       # 결제 계정 ID 확인
gcloud billing projects link <PROJECT_ID> --billing-account=<BILLING_ACCOUNT_ID>
```
> 콘솔 대안: console.cloud.google.com → 결제 → 프로젝트에 결제 계정 연결.

---

## 2. API 활성화

```bash
gcloud services enable documentai.googleapis.com --project=<PROJECT_ID>
# 15p 초과 대용량(GCS batch)도 쓸 거면:
gcloud services enable storage.googleapis.com --project=<PROJECT_ID>
```

---

## 3. Layout Parser 프로세서 생성

gcloud 에 안정 서브커맨드가 없으므로 REST(curl)로 만든다:
```bash
LOCATION=us
curl -s -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "x-goog-user-project: <PROJECT_ID>" \
  -H "Content-Type: application/json" \
  "https://${LOCATION}-documentai.googleapis.com/v1/projects/<PROJECT_ID>/locations/${LOCATION}/processors" \
  -d '{"type":"LAYOUT_PARSER_PROCESSOR","displayName":"layout-parser"}'
```
응답의 `"name": "projects/NNN/locations/us/processors/XXXXXXXX"` 에서 **마지막 세그먼트 `XXXXXXXX` 가
`DOCUMENTAI_PROCESSOR_ID`** 다. AI 는 이 값을 추출해 기록한다.

> 콘솔 대안: console.cloud.google.com/ai/document-ai → "프로세서 만들기" → **Layout Parser** 선택 →
> 리전 `us` → 생성 후 프로세서 세부정보의 ID 복사.
>
> 이미 만든 프로세서가 있으면 목록으로 ID 확인:
> ```bash
> curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
>   -H "x-goog-user-project: <PROJECT_ID>" \
>   "https://us-documentai.googleapis.com/v1/projects/<PROJECT_ID>/locations/us/processors"
> ```

---

## 4. 서비스 계정 + 키 발급

```bash
# 4-1) 서비스 계정 생성
gcloud iam service-accounts create docai-ocr \
  --display-name="Document AI OCR" --project=<PROJECT_ID>

# 4-2) Document AI 호출 권한 부여
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="serviceAccount:docai-ocr@<PROJECT_ID>.iam.gserviceaccount.com" \
  --role="roles/documentai.apiUser"

# 4-3) (GCS 대용량 쓸 때만) 버킷 읽기/쓰기 권한
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="serviceAccount:docai-ocr@<PROJECT_ID>.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# 4-4) 키 JSON 발급 — 반드시 gitignore 되는 secrets/ 안에 저장 (스킬 폴더 기준)
cd <skill-dir>
mkdir -p secrets
gcloud iam service-accounts keys create ./secrets/service-account.json \
  --iam-account=docai-ocr@<PROJECT_ID>.iam.gserviceaccount.com
```

> **보안(중요)**: 키 JSON 내용을 코드·`.env`·채팅에 붙여넣지 않는다. `.env` 에는 **경로만** 넣는다.
> `secrets/` 와 `*.json` 은 `.gitignore` 로 차단되어 있으니 그 위치를 벗어나지 않는다.
> AI 는 발급 후 `git check-ignore secrets/service-account.json` 로 추적 제외를 재확인한다.

---

## 5. (선택) GCS 버킷 — 15p 초과 대용량 batch 용

```bash
gcloud storage buckets create gs://<BUCKET_NAME> --location=us --project=<PROJECT_ID>
```
15p 이하 문서만 다룰 거면 건너뛴다(온라인 병렬 처리로 버킷 없이 동작).

---

## 6. `.env` 작성

AI 가 스킬 폴더에 `.env` 를 만들고 수집한 값으로 채운다(SKILL.md `## 설정` 블록 기준):
```ini
GCP_PROJECT_ID=<PROJECT_ID>
DOCUMENTAI_PROCESSOR_ID=<프로세서 ID (3단계에서 추출)>
GOOGLE_APPLICATION_CREDENTIALS=./secrets/service-account.json
GCP_LOCATION=us
# GCS_BUCKET=<BUCKET_NAME>   # 5단계에서 만들었을 때만
```

---

## 7. 설치 + 스모크 테스트

```bash
cd <skill-dir>
python scripts/setup_venv.py            # .venv 생성 + 의존성 설치

# 설정 검증만 먼저(자격증명 경로·필수값) — 에러 나면 해당 값 교정
python -c "import sys; sys.path.insert(0,'.'); from src.config import DocumentAIConfig; DocumentAIConfig.from_env(); print('[OK] 설정 로드 성공')"

# 실제 1건 테스트: inbox 에 PDF 1개 넣고
python scripts/run_inbox_batch.py
# 기대: DONE total=1 success=1 ... / output 폴더에 *.html, *.md 생성
```

- `필수 환경변수가 설정되지 않았습니다: ...` → 해당 키를 `.env` 에 채운다.
- `GOOGLE_APPLICATION_CREDENTIALS 경로에 파일이 없습니다` → 4-4 키 경로 확인.
- `PERMISSION_DENIED`/`403` → 2단계 API 활성화, 4단계 역할 부여, 1단계 결제 연결 재확인.
- `Layout Parser` 관련 400 → 3단계 프로세서 타입/리전(us) 확인.

성공하면 온보딩 완료 — 이후는 SKILL.md 의 사용법대로 배치/단건 실행한다.
