# ocr-google-layout 트러블슈팅

## 1) 환경 준비 실패

### 증상
- `uv: command not found`
- `pip install` 실패

### 조치
1. 우선 실행:
```bash
cd <skill-dir>
python scripts/setup_venv.py --recreate
```
2. `uv` 미설치면 fallback venv를 사용합니다.
3. 계속 실패하면 오류 마지막 30줄을 첨부해 원인(네트워크/권한/패키지)을 분리합니다.

## 2) `.env` 누락/필수값 누락

### 증상
- `필수 환경변수가 설정되지 않았습니다: ...`
- `GOOGLE_APPLICATION_CREDENTIALS 경로에 파일이 없습니다: ...` (서비스계정 키 경로 오류)

### 조치
```bash
cd <skill-dir>
# SKILL.md 의 `## 설정` .env 예시 블록을 복사해 .env 생성 (또는 아래 값을 셸 env로 export)
```
필수값:
- `GCP_PROJECT_ID`
- `DOCUMENTAI_PROCESSOR_ID`
- `GOOGLE_APPLICATION_CREDENTIALS` (서비스계정 JSON **파일 경로** — 값/내용 아님)

최초 GCP 설정 자체가 안 되어 있으면 `references/gcp-onboarding.md` (AI 실행형)를 따른다.

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

## 5) 검증 실패 (텍스트 누락·페이지 오배치)

### 증상
- 배치 요약의 `verify_failed=` 가 1 이상이고, 결과 폴더 이름이 `_검증실패` 로 끝난다
- 단건 실행이 종료 코드 3으로 끝난다
- MD·HTML 맨 위에 `[검증 실패]` 경고가 있다

배치는 종료 코드 3**이면서** 결과 폴더에 `*_verify_failed.json` 이 있을 때만 검증 실패로 센다. 종료 코드는
3인데 누락 목록 파일이 없으면 일반 실패로 처리한다. 오류 줄에는 "(종료 코드 3이지만 누락 목록 파일이 없어
일반 실패로 처리)"가 붙는다. 이 경우는 검증이 아니라 하위 실행의 비정상 종료일 수 있으니 로그를 먼저 본다.

### 조치
1. `<파일명>_verify_failed.json` 을 연다.
   - `reasons`: 사유별 건수
   - `md_missing` / `html_missing`: 빠진 블록(페이지·유형·텍스트 앞부분)
   - `html_misplaced`: 원래 페이지와 실제로 놓인 페이지
   - `footer_excluded`: 하단 문구로 분류돼 검사에서 뺀 블록 수·글자 수. 이 값이 비정상적으로 크면
     본문이 하단 문구로 잘못 분류된 것이 아닌지 확인한다. 검증에 성공한 파일은 결과 폴더의
     `processing.log` 검증 줄에서 같은 건수를 볼 수 있다.
   - `unknown_page_count`: 페이지 정보가 없어 배치를 확인하지 못한 블록 수
   - `table_counts`: 형식별 표 개수(원응답 기준 기대값과 실제 출력)
   - `table_mismatches`: 형식별로 표마다(같은 표가 MD·HTML 모두에서 어긋나면 2건으로 센다) 형식·표 순번(`table_index`, 문서 전체 기준 1부터)·페이지·행×열(기대/실제)과
     다른 칸 목록(`cell_diffs`). 칸 값이 옆 열로 밀린 경우가 여기에 나온다. 출력에 짝 표가 없으면
     `actual_shape` 가 null, 원응답에 없는 표가 출력에 있으면 `table_index`·`expected_shape` 가 null 이다.
   - `table_unverifiable`: 병합 셀·표 안의 표가 있어 구조를 확인하지 못한 표
2. 원인이 변환 코드라면 코드를 고친 뒤, 저장된 원응답으로 API 호출 없이 다시 변환한다.
   ```bash
   python scripts/run_ocr_google.py --file "<pdf>" --output "<새 출력 폴더>" --cache "<결과 폴더>/<파일명>_response.json"
   ```
   - GCP 환경변수(`.env`)는 여전히 필요하다. 설정을 먼저 읽기 때문이다.
   - 온라인 한도(`MAX_ONLINE_PAGES`, 기본 15쪽)를 넘는 PDF에 `--no-parallel` 을 붙이면 캐시를 쓰지 않고 API를 다시 호출한다.
3. 원본 PDF는 inbox에 남아 있다. 다음 배치 실행 때 다시 OCR된다(비용 발생).
   재처리하지 않으려면 inbox에서 옮긴다.
4. 경고가 붙은 MD·HTML은 완전한 변환본이 아니다. 완전본처럼 쓰지 말고, 누락 원인을 확인하는 데만 쓴다.
5. `table_unverifiable` 로 실패했다면 원응답에 병합 셀이나 표 안의 표가 실제로 나온 것이다. 지금 변환은
   이 구조를 표현하지 못한다. 저장된 원응답을 보고 변환을 고칠지 정한다. 그 전까지 이 표는 원본 PDF
   이미지로 대조한다.
