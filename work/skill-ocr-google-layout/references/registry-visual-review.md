# 등기부 이미지 판독과 현행 정보 분리

일반 OCR의 HTML·Markdown은 말소 이력을 포함한 원문이다. 이 절차는 이미지를 볼 수 있는 AI 또는 사람이 취소선 범위를 판단하고, 코드가 그 판독을 정확히 적용하는 후처리다. 특정 OCR 서비스의 취소선 태그나 텍스트 추출 순서를 신뢰하지 않는다.

## 1. 취소선 존재 여부 사전 판독

`<보관소>` 는 `$CPA_SKILLS_STORAGE/skill-ocr-google-layout`(없으면 `~/cpa-skills-data/skill-ocr-google-layout`)다. `--output` 을 빼면 판독 중간물은 `<보관소>/work`, 현행본은 `<보관소>/output` 에 생긴다. git 저장소 안 경로는 거부한다(종료 코드 2).

먼저 파일 전체의 취소선 유무만 확인한다. 취소선이 없는 문서에 행별 삭제 범위 판독을 요구하지 않는다. **존재 여부 확인도 원본 이미지에서 수행**하며, 상세 범위 판독과 구분한다.

```bash
python scripts/registry_visual_review.py screen --pdf <보관소>/input/registry.pdf --ocr <보관소>/input/registry.html --output <보관소>/work/screen
```

| 옵션 | 의미 | 기본값 |
|---|---|---|
| `--pdf` | 전체 원본 PDF. 일부 쪽만 선택하지 않음 | 필수 |
| `--ocr` | 기존 HTML·MD·TXT. 있으면 서식 단서와 원문 보존에 사용 | 생략 가능 |
| `--dpi` | 이미지 해상도, 150~600 | 200 |
| `--output` | 새 사전 판독 폴더 | `<보관소>/work/registry-screen` |

`screen-bundle.json`은 원본·페이지 이미지 해시와 OCR 서식 단서를 보관한다. `screen.html` 또는 `pages/*.png`의 **모든 페이지**를 실제로 보고 `screening.json`을 작성한다.

- `reviewer`: 실제 판독한 AI 또는 사람. `method`는 `image`.
- `document_complete`: 전체 페이지를 확인한 뒤에만 `true`.
- `pages[].image_reviewed`: 해당 이미지 전체를 확인했으면 `true`.
- `pages[].presence`: `present`(존재), `absent`(없음), `uncertain`(불확실). 기본 `unreviewed`는 분기를 차단한다.
- `pages[].note`: 그 페이지에서 확인한 내용. 표제부·갑구·을구·목록, 취소된 주소·금액 또는 선 없는 영역 등 실제 관찰을 기록한다.
- `pages[].evidence`: 존재·불확실일 때 `bbox`(좌상단 기준 0~1의 사각형 좌표)와 `note`를 기록한다. 이 단계는 존재 여부의 근거 위치이며 상세 삭제 문자 범위가 아니다.
- 준비본과 이미지 해시는 수정하지 않는다.

빨간 선뿐 아니라 검은 선·가는 선도 확인한다. 표 경계선, 밑줄, 도장, 필기는 취소선과 구별한다. 작은 글자나 스캔 품질 때문에 판단하기 어려우면 확대해 확인하거나 `uncertain`으로 남긴다. 취소선 단서가 없는 MD는 이미지의 부재 증거가 아니다.

## 2. 상세 이미지 판독 또는 텍스트 분석으로 분기

```bash
python scripts/registry_visual_review.py route --bundle <보관소>/work/screen/screen-bundle.json --screening <보관소>/work/screen/screening.json --output <보관소>/work/route
```

`--output`의 기본값은 `<보관소>/work/registry-route`다. 분기 결과·근거는 `route.json`에 남는다.

- **존재 또는 불확실한 페이지가 하나라도 있으면** `route: detailed_image_review`. 다음 쪽 계속 행과 후속 변경을 놓치지 않도록 문서 전체를 상세 판독한다. 페이지별 OCR HTML이 있으면 `detail-review/`의 기존 `bundle.json`·`review.json`·이미지까지 자동 준비한다. Markdown이나 텍스트만 있으면 `detailed_review_required`와 OCR HTML 준비 안내를 반환한다. 상세 판독이 끝난 것으로 표시하지 않는다.
- **모든 페이지가 없음이고 서식 단서도 없으면** `route: text_analysis`. 기존 OCR은 `input.html`·`input.md`·`input.txt`로 바이트 그대로 보존한다. OCR이 없고 모든 페이지에 PDF 텍스트가 있으면 `input.txt`를 추출한다. 텍스트가 없는 페이지가 있으면 `status: text_ocr_required`로 일반 OCR을 요청한다. 이 스크립트는 클라우드 OCR을 호출하지 않는다.
- `<s>`·`<del>`·`<strike>`·`line-through`·`~~...~~` 등 원문 서식 단서가 이미지의 없음 판정과 충돌하면 상세 판독으로 보낸다. 서식을 평문으로 변환해 단서를 버린 뒤 분기하지 않는다.
- 미검토, 페이지 누락·중복, 원본/이미지/판독 기록 변경은 실패하며 새 결과 폴더를 남기지 않는다.

**텍스트 경로는 현행본 생성이 아니다.** `scope: source_for_analysis`, `history_removed: false`, `current_status_evaluated: false`를 보존한다. 취소선이 없어도 과거 소유자·변경·말소 등기는 텍스트의 등기 순서와 후속 기록으로 분석한다.

## 3. 상세 범위 판독의 입력과 준비

`route`가 만든 `detail-review/`를 사용한다. 여러 물건이 섞였거나 OCR 페이지가 누락된 입력은 아래의 기존 `prepare`로 입력 범위를 맞춘다. 이미 취소선 존재가 확인된 문서는 사전 판독을 반복하지 않고 상세 판독으로 바로 진행해도 된다.

원본 PDF와 페이지별 `<section id="page-N"><div class="text-col">` 구조가 있는 OCR HTML을 지정한다. 원문에서 문단과 표의 각 행에 고정 ID가 부여된다. 병합 셀·중첩 표·닫히지 않은 HTML은 조용히 누락시키지 않고 거절한다. 이 경우 원본 이미지로 확인한 OCR 사본을 만들어 행·열을 복구한 뒤 다시 준비한다. 이미지에 있는 등기 내용이 OCR에서 누락된 경우에도 먼저 전사 사본을 보완한다.

```bash
python scripts/registry_visual_review.py prepare --pdf <보관소>/input/registry.pdf --ocr <보관소>/input/registry.html --output <보관소>/work/review
```

| 옵션 | 의미 | 기본값 |
|---|---|---|
| `--pdf` / `--ocr` | 원본 PDF / OCR HTML | 필수 |
| `--source-pages` | OCR 페이지 순서에 대응하는 PDF 물리 쪽수 목록 | HTML의 page-N 번호 |
| `--dpi` | 이미지 해상도, 150~600 | 200 |
| `--output` | 새 검토 폴더 | `<보관소>/work/registry-review` |

여러 물건이 합쳐진 PDF는 고유번호별 OCR을 나누고 원본 쪽수를 명시한다. 예를 들어 두 번째 물건의 OCR이 page-1부터 시작하고 원본 4~7쪽에 해당하면 `--source-pages 4,5,6,7`을 지정한다. 계약서 등 다른 문서가 앞에 붙어 있어도 등기부 본체의 인쇄 쪽수가 모두 있어야 한다. 원본의 일부 쪽만 보고 본체 전체 쪽수를 줄이지 않는다.

출력 `pages/*.png`는 Poppler로 생성하며, Poppler가 없으면 스킬 의존성 PyMuPDF를 사용한다. `review.html`은 원본 이미지와 행 ID별 OCR을 나란히 보여준다. `bundle.json`은 원본·이미지 해시와 전체 검토 대상을 담는다. 수정 대상은 `review.json`이다.

## 이미지 판독 순서

1. 모든 페이지의 고유번호·인쇄 쪽수·발행 또는 열람일을 대조한다. 별도 물건이 섞였는지, 앞뒤가 잘렸는지 확인한다.
2. 페이지 전체 이미지를 보고 표제부·갑구·을구·목록의 내용이 OCR에 모두 있는지 확인한다. 가는 취소선과 표 테두리를 구분하고 숫자·취소 범위가 불명확하면 원본을 고해상도로 다시 렌더하거나 확대해서 판독한다.
3. 각 행·문단에 현행/말소/후속 대체/이력/문맥/잡음 상태와 이미지 위치를 기록한다. 삭제된 표제부 주소, 과거 소유자, 가압류·신탁·전세권·지상권 등도 포함한다.
4. 전체 말소와 부분 말소를 구분한다. 금액만 취소되었으면 그 금액 구간만 삭제하고 유효한 근저당 본체·채무자·권리자는 유지한다. 변경된 금액은 원본 후속 변경 행에 남긴다. 담보 일부가 빠졌다가 다시 추가되면 최종 추가 내용을 유지한다.
5. 다음 페이지의 계속 행도 동일한 `entry`에 연결한다. 취소된 근저당의 뒷부분이 고아 행으로 남지 않도록 한다. 지분 일부 이전은 전체 소유권 이전으로 추정하지 않는다. 취소선 없는 가등기도 후속 말소 근거 없이 지우지 않는다.

판독할 수 없으면 해당 결정을 `unreviewed`로 남긴다. 범위가 불확실한데 검증 통과를 위해 근거·상태를 만들어 넣지 않는다. 텍스트 누락이 있으면 `text_complete: false`로 유지한다.

## review.json 계약

상위 필드:

- `bundle_sha256`: 준비된 원본 묶음의 해시. 준비본 변경 시 다시 판독한다.
- `reviewer`: 실제 판독한 AI 또는 사람. `method`는 `image`.
- `registry_id`, `as_of`: 이미지에서 확인한 고유번호와 원본 기준일(`YYYY-MM-DD`). 오늘 날짜로 대체하지 않는다.
- `registry_page_count`: 해당 물건 본체에 인쇄된 총 쪽수.
- `pages`: 모든 입력 쪽의 `image_reviewed`, `text_complete`, `printed_page`, `note`. `printed_page`는 순서대로 1부터 총 쪽수까지 있어야 한다. 이미지 해시는 준비값을 보존한다.
- `entries`: 등기 항목 ID별 상태와 이미지 근거. 예: `gap:5`, `eul:2`, `title:2`. 필요한 경우 구분을 더한다. 순위번호가 같아도 갑구·을구를 혼동하지 않는다.
- `decisions`: 모든 행·문단 ID에 대한 결정. 빈 행도 `noise`로 판단해야 하며 목록을 삭제하지 않는다.

각 결정의 필드:

| 필드 | 값과 적용 |
|---|---|
| `state` | `current` 현행, `context` 제목·표 머리글 등 유지. `cancelled` 말소, `superseded` 후속 대체, `history` 효력이 소진된 사건·변경 이력, `noise` 여백·워터마크 등 제외 |
| `entry` | 내용 행의 등기 항목 ID. `context`·`noise`만 빈 값 허용. 현재 항목의 과거 변경 행은 `history`로 제외할 수 있음 |
| `strike_scope` | `none` 취소선 없음, `whole` 행 전체 말소, `partial` 일부 문자만 취소. `whole` 행은 유지 불가 |
| `reason` | 현행 유지 또는 제외 판단의 구체적 이유 |
| `evidence` | `page`, `bbox`, `note` 목록. 해당 행이 있는 쪽의 이미지 근거 필수; 후속 말소·변경 쪽도 추가 |
| `edits` | 부분 취소·후속 대체 문자 삭제 및 이미지로 확인한 OCR 오인식 수정 목록 |

`bbox`는 페이지 전체 이미지의 좌상단을 원점으로 하는 `[x0, y0, x1, y1]` 정규화 좌표다(각 값 0~1). 실제 취소선/글자 범위를 감싸도록 잡는다. 전체 페이지 좌표만 반복해서 넣어 부분 취소 범위를 대신하지 않는다.

부분 취소 예시(합성 데이터, 셀 번호와 문자 인덱스는 0부터):

```json
{
  "id": "p1-u8",
  "state": "current",
  "entry": "eul:2",
  "strike_scope": "partial",
  "reason": "채권최고액만 취소선. 후속 변경 행의 새 금액 적용, 근저당 본체 유지",
  "evidence": [{"page": 1, "bbox": [0.1, 0.4, 0.9, 0.55], "note": "금액만 취소되고 채무자·권리자 표시는 유지"}],
  "edits": [{
    "cell": 4, "start": 6, "end": 12,
    "before": "금5000원", "after": "", "kind": "strike",
    "evidence": [{"page": 1, "bbox": [0.53, 0.41, 0.7, 0.43], "note": "기존 금액을 관통하는 취소선"}]
  }]
}
```

`before`는 정규화된 `bundle.json`의 `cells[cell][start:end]`와 정확히 같아야 한다. 같은 글자가 반복되어도 문자열 전체 치환을 하지 않는다. 한 셀에 여러 편집이 있으면 **모두 원문 기준 인덱스**로 지정한다. 편집끼리 겹치면 실패한다.

`kind: strike`와 `superseded`는 `after: ""`로만 삭제한다. `kind: ocr`만 이미지에 있는 실제 글자로 교정할 수 있다. 단순한 새 주소/금액 전파를 OCR 오인식 교정으로 가장하지 않는다. 취소된 행은 HTML에서 CSS로 숨기는 것이 아니라 현행 데이터에서 실제로 제외한다.

## 검증과 출력

```bash
python scripts/registry_visual_review.py validate --bundle <보관소>/work/review/bundle.json --review <보관소>/work/review/review.json
python scripts/registry_visual_review.py export --bundle <보관소>/work/review/bundle.json --review <보관소>/work/review/review.json --output <보관소>/output/current
```

`export`는 같은 검증을 다시 수행한다. 원본 PDF·OCR·이미지 변경, 페이지나 행 결정 누락·중복, 취소 범위와 유지 상태 모순, 원문 불일치, 말소 항목의 계속 행 잔존, 현행 항목 전체 제외 등을 차단한다. 실패 종료 코드는 2이며 결과 폴더를 만들지 않는다. 기존 출력 경로가 있으면 실패하므로 이전 성공본과 재검토 실패를 혼동하지 않는다.

- `current.html`, `current.txt`: 검증된 현행 행과 필요한 문맥만 포함. 원문 페이지 및 순위를 보존한다.
- `current.json`: 현행 정보와 원본·검토 해시, 검토 시각(KST, 분 단위).
- `audit.json`: 제외된 원문, 판독 상태, 부분 삭제 범위, 교정, 이미지 위치. 현행본과 분리하여 보관한다.
- `audit.html`: 원본 이미지에 판독한 취소선 범위를 상자로 표시하고, 각 행의 제외·유지 이유 및 교정 전후를 비교한다. 원본 이미지를 내장하므로 단독으로 열 수 있다. 이 파일에는 과거 내용이 있으므로 현행 분석 입력으로 사용하지 않는다.

현행본의 변경 행은 원문 구조대로 남긴다. 예를 들어 기존 금액이 삭제되고 후속 금액 변경 행이 남으므로, 이를 사용하는 분석기는 변경 등기 처리를 지원해야 한다. `current.json`의 `scope: current_only`, `history_removed: true`를 보존한다. **설정 당시 금액·과거 소유자 같은 이력 항목은 현행본으로 복원할 수 없다.** 이력이 필요한 분석에는 원문 OCR과 `audit.json`을 함께 사용한다. OCR 코드가 소유 지분 계산·공동담보 묶음·금액 합산을 대신하지 않는다. 결과 보고에는 판독한 물건·쪽수와 테스트 범위를 명시한다. 일부 물건 검증을 전체 PDF 배치 완료로 표시하지 않는다.
