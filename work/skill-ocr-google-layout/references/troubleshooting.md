# OCR2 Troubleshooting

## 1) 환경 준비 실패

### 증상
- `uv: command not found`
- `pip install` 실패

### 조치
1. 우선 실행:
```bash
cd <skills-root>/skill-ocr-google-layout
python3 scripts/setup_venv.py --recreate
```
2. `uv` 미설치면 fallback venv를 사용합니다.
3. 계속 실패하면 오류 마지막 30줄을 첨부해 원인(네트워크/권한/패키지)을 분리합니다.

## 2) `.env` 누락/필수값 누락

### 증상
- `Required environment variable(s) not set: ...`

### 조치
```bash
cd <skills-root>/skill-ocr-google-layout
# SKILL.md 의 `## 설정` .env 예시 블록을 복사해 .env 생성 (또는 아래 값을 셸 env로 export)
```
필수값:
- `GCP_PROJECT_ID`
- `DOCUMENTAI_PROCESSOR_ID`
- `GOOGLE_APPLICATION_CREDENTIALS`

## 3) GCS/대용량 처리 실패

### 증상
- 15p 초과 문서 처리 중 batch 관련 오류
- 버킷/권한 오류

### 조치
- `.env`의 `GCS_BUCKET` 값 확인
- 서비스 계정에 버킷 읽기/쓰기 권한 확인
- 일시 오류는 1회 재시도

## 4) 배치에서 일부 파일 실패

### 증상
- `DONE total=N success=M failed=K`

### 조치
- 실패 파일은 inbox에 남아 있습니다.
- 파일명/문서 손상 여부 확인 후 재실행합니다.
- 필요 시 `--max-workers 1`로 낮춰 재시도합니다.
