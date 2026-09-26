# 등기부 이미지 판독과 결과 연결

## 판독 주체와 범위

스킬을 실행하는 이미지 입력 가능한 에이전트 또는 사람이 실제 PNG를 열어 판독한다.
Python은 이미지를 만들고 기록의 완전성·원본 연결·반영 값을 검사한다. 텍스트 추출,
이미지 파일 생성, 테스트 정답 기록 주입을 실제 이미지 판독으로 보고하면 안 된다.

`registry_image_gate.py prepare`는 입력 하위 폴더의 모든 PDF를 수집하고 모든 쪽을 렌더한다.
이미지 파일은 각 `doc-NNNN/screen/pages/`에 있다. 200 DPI가 기본이며 150~600을 지정할 수 있다.
Poppler를 우선 사용하고 없으면 pdfplumber의 PDFium 렌더러를 사용한다.
원본 파일은 수정하지 않는다. 검토 폴더는 입력 폴더 밖에 둔다.

## 1. 문서 종류와 취소선 존재 여부: screening.json

모든 페이지를 전체 화면과 필요한 확대 화면으로 확인한다. 표 테두리·밑줄·도장과
글자 중앙의 취소선을 구별하고, 일부 숫자·주소와 검은색/흐린 선도 확인한다.

- 최상위 `reviewer`: 실제 판독자, `method`: `image`, `document_complete`: 전체 쪽 확인 후 `true`.
- 각 `pages` 항목의 `image_sha256`·`page`는 준비본 그대로 보존한다.
- `image_reviewed`: 실제 확인한 쪽만 `true`.
- `presence`: `present` / `absent` / `uncertain`. 미확인은 `unreviewed`를 유지한다.
- `note`: 그 쪽에서 무엇을 확인했는지 기록한다.
- `evidence`: 존재/불확실이면 `{"bbox": [x0, y0, x1, y1], "note": "범위 설명"}` 목록.
  좌표는 좌상단 기준 너비·높이에 대한 0~1 비율이다.
- `classification`: 모든 쪽의 문서 종류와 이미지 근거. `kind`는 `registry` / `non_registry` /
  `unknown`이다. `unknown` 또는 필드 누락은 분석을 차단한다. `document_type`(예: 등기부 계속),
  `reason`과 `evidence`를 채운다. 이 근거의 각 항목에는 원본 물리 `page`도 넣는다.

```json
"classification": {
  "kind": "non_registry", "document_type": "임대차계약서",
  "reason": "계약서 제목·임대인/임차인·계약 조항을 이미지에서 확인",
  "evidence": [{"page": 1, "bbox": [0.05, 0.05, 0.95, 0.9], "note": "계약서 표제와 본문"}]
}
```

준비본의 `document_hint`는 PDF 텍스트 및 페이지가 식별되는 OCR HTML의 문서 표지로 얻은
후보다. 판독 완료 값에 자동 복사하지 않는다. 등기부를 인용한 계약서처럼 단서가 충돌하거나
텍스트가 없는 경우 `unknown` 후보로 남긴다. 이미지에서 문서 종류와 앞뒤 계속 관계를 확인한다.
등기부 요약·공동담보목록·제목 없는 계속 페이지는 `registry`에 포함한다. 한 페이지에 등기부와
다른 문서가 함께 있으면 전체 페이지를 비등기로 버리지 말고 등기부 영역을 확인하여 전사한다.

비등기 PDF는 `details`에서 `excluded_non_registry`로 표시한다. 혼재 PDF는 `needs_partition`으로
분리 계획을 요구한다. `partition`의 첨부 목록은 사전 판정과 정확히 일치해야 한다.
기존 기록을 재사용할 때도 원본 이미지 근거에 따라 이 필드를 보완하고 결과를 다시 생성한다.

전체가 `absent`이며 OCR 취소선 서식 단서도 없을 때만 텍스트 경로로 진행한다.
OCR의 `<s>`·`<del>`·`line-through`·`~~` 등은 상세 판독의 추가 신호이며
서식 단서가 없다는 사실로 이미지 확인을 생략할 수 없다.

## 2. 범위 판독: detail/review.json

기존 OCR 또는 직접 전사한 HTML은 아래 구조를 사용한다. 각 원본 물리 페이지는 순서대로
`section id="page-N"` 하나와 `div class="text-col"` 하나를 갖는다. 표는 셀을 나누고 줄바꿈은
`br`로 보존한다. `rowspan`·`colspan` 병합은 먼저 이미지와 대조해 사본에서 풀어야 한다.
다음은 HTML 구조 예시이며 실제 등기 내용이나 판독 정답이 아니다.

```html
<!doctype html><html lang="ko"><meta charset="utf-8">
<section id="page-1"><div class="text-col">
  <p>원본에서 확인한 제목과 고유번호</p>
  <table><tr><td>원본 순위</td><td>원본 등기목적</td><td>원본 접수</td><td>원본 내용</td></tr></table>
</div></section>
</html>
```

원본 OCR 파일에 없는 내용을 추측해서 채우지 않는다. 새 HTML을 만들면 그 파일을 해당
PDF의 OCR 입력으로 연결해 대장을 새로 준비한다. 생성된 JSON의 키·해시·unit ID를 기준으로
판독 필드만 작성하며 아래 발췌 예시로 대장 전체를 덮어쓰지 않는다.

`registry_image_gate.py details manifest.json`은 상세 판독 대상마다 페이지·행 대장을 만든다.
네이티브 PDF는 텍스트와 표를 임시 HTML로 추출한다. 이미지 PDF는 기존 OCR HTML을 사용한다.
OCR의 병합 셀·여러 순위가 합쳐진 행·텍스트 누락은 원본 대조 후 사본에서 보완하고 다시 준비한다.

사전 판독에서 한 쪽만 `present`여도 그 PDF **전체 쪽**을 상세 판독한다. `review.html`과
`pages/*.png`, `bundle.json`의 행별 `units`를 대조하여 아래를 작성한다.

- `reviewer`, `method=image`, `registry_id`: 원본 물건 고유번호, `as_of`: 원본 기준일 `YYYY-MM-DD`.
- `registry_page_count`: 입력 물건의 전체 쪽수. `pages`마다 `printed_page`를 1부터 순서대로 기록한다.
  원본 인쇄 쪽수 누락은 완료 처리하지 않는다. 요약·별지가 별도 번호 체계이면 물건의 연속된
  전체 페이지 순서로 기록하되 `note`에 본체/요약/별지와 실제 인쇄 번호를 명시한다.
- `pages`의 `image_reviewed`, `text_complete`: 전체 이미지 판독과 전사 누락 확인 후 `true`.
- `entries`: 등기 단위 ID(예: `갑:13`, `을:9`)별 `state`와 `evidence`.
  `state`는 `current`, `cancelled`, `superseded`, `history` 중 하나.
- `decisions`: **모든** `unit.id`에 한 건씩 판정한다. 제목·안내도 빠뜨리지 않는다.
  `state`는 위 네 상태 외에 `context`(문맥 유지), `noise`(안내·여백 제외)를 사용할 수 있다.
  등기 내용은 `entry`로 연결한다. 다음 쪽의 계속 행도 같은 등기에 연결한다.
- `strike_scope`: `none`, `whole`, `partial`. 전체 취소 행은 현행으로 유지할 수 없다.
- `reason`: 유지·제외 근거. `evidence`는 `{"page": 1, "bbox": [...], "note": "..."}` 목록.
  해당 행이 있는 쪽의 근거를 반드시 포함한다.

부분 취소는 행 전체를 삭제하지 않는다. `edits`에 셀과 정확한 문자 범위를 기록한다.

```json
{
  "cell": 4,
  "start": 6,
  "end": 12,
  "before": "금500만원",
  "after": "",
  "kind": "strike",
  "evidence": [{"page": 1, "bbox": [0.60, 0.30, 0.82, 0.33], "note": "옛 금액에만 취소선"}]
}
```

`cell`, `start`는 0부터 시작하고 `end`는 제외 경계다. 위 숫자는 형식 예시로 실제 셀에 맞춰
계산한다. `before`가 해당 원문과 정확히 같아야 한다. 취소(`strike`)·후속 대체(`superseded`)는
삭제만 허용한다. OCR 오인식 수정은 `kind=ocr`와 이미지 근거로 기록한다. 새 금액을 추측하지 않는다.

취소선 없는 후속 말소 기재도 현행 권리로 유지하지 않는다. 말소된 근저당의 채무자·권리자·
공동담보 계속 행, 취소된 주소·지상권·전세권·가압류 등도 동일하게 처리한다. 후속 변경으로
대체된 옛 값은 제거하고 현행 변경값을 보존한다. 말소회복·담보 재추가를 단순 취소로 처리하지 않는다.

## 3. 물건 분할과 누락 페이지

서로 다른 고유번호는 하나의 상세 판독 대장에 넣지 않는다. 원본 PDF는 그대로 두고
물건별 페이지 HTML 사본을 만든다. 권장 절차는 [복합 입력 처리](complex-inputs.md)의
`registry_inputs.py partition`이며 페이지 매핑과 manifest 등록을 함께 수행한다.
이미 분리한 HTML이 있다면 다음처럼 개별 준비할 수도 있다.

```bash
python scripts/registry_image_gate.py prepare-part <보관소>/input/combined.pdf \
    <보관소>/output/part-a.html <보관소>/output/part-a-review --pages 1 2 3
python scripts/registry_image_gate.py prepare-part <보관소>/input/combined.pdf \
    <보관소>/output/part-b.html <보관소>/output/part-b-review --pages 4 5 6 7
```

`manifest.json`의 해당 `documents[].parts`에 각 `bundle.json`·`review.json` 절대경로를 넣는다.
HTML 쪽 번호와 `--pages`의 원본 물리 페이지 매핑을 보존한다. 물건별 페이지와 이미지에서
확인한 비등기 첨부 페이지의 합집합은 원본의 모든 쪽과 일치해야 하며 중복·누락은 차단된다.
첨부는 구조 분리 계획에 문서 종류·제외 사유·이미지 근거를 기록한다. OCR에서만 빠진 쪽은
원본 이미지로 전사하고, 원본 등기부 자체의 인쇄 페이지가 빠졌는지 별도로 확인한다.
원본 인쇄 페이지가 실제로 빠진 자료는 재확보하거나 사용자와
합의한 입력 범위에서 제외하고 그 범위를 보고한다. 0건 담보로 대체하지 않는다.

## 4. 판독값과 파싱·엑셀 대조

상세 `review.json` 최상위에 원본 이미지에서 확인한 기대 결과를 기록한다.

```json
{
  "analysis_expectations": {
    "owner": "주식회사예시",
    "location": "경기도 예시시 예시동 1",
    "mortgages": [{"rank": "3", "amount": 200000000}],
    "seizures": [{"rank": "2", "kind": "압류"}],
    "other_encumbrances": []
  }
}
```

`mortgages`는 현행 근저당 전부의 순위·원화 정수 금액이며 없으면 빈 목록이다.
같은 순위의 복수 설정은 `4(1)`, `4(2)`처럼 각각 기록한다. 외화·판독 불가 금액은
임의 환산/합산하지 말고 미확정 사유를 기록한다. 병합된 OCR 행은 이미지 대조로 보완 후 재분석한다.
`owner`는 최종 소유자명(공유자는 파서 표기처럼 `, `로 구분), `location`은 현행 소재지,
`other_encumbrances`는 현행본의 감지 대상 이름 목록(전세권·지상권·경매개시·신탁·가등기·환매특약).
이 값들은 **파싱 출력을 복사해 정답으로 만들지 않고 이미지에서 독립 확인**한다.

`seizures`는 갑구의 현행 압류/가압류 전부를 `rank`(순위 문자열), `kind`(`압류` 또는
`가압류`)로 기록한다. 없으면 빈 목록이며 키 생략은 허용하지 않는다. 같은 건수라도 순위나
종류가 다르면 실패한다. 이전 판독 기록에 이 필드가 없으면 기존 원본 이미지에서 확인해
추가한 뒤 새 결과를 생성한다. 이전 파서 버전의 JSON/완료 증거로 조서를 생성할 수 없다.

`check` 후 파서는 검증된 `current.html`을 출력 접두사 아래 `_image_inputs/`에 생성하여
실제 파싱 입력으로 사용한다. 삭제 이력은 같은 폴더 `audit.html/json`에 남고 현행본에는 제외된다.
기대 값과 파싱 값이 다르거나 을구 제목/설정행을 놓치면 실패한다.

전체 성공 시에만 `*_properties.json.image-review.json`이 발행된다. 최종 엑셀과 LLM 판정 적용은
원본 PDF·OCR·이미지·판독 대장·현행본·결과 JSON 해시, 현재 입력 폴더의 전체 목록을 다시 검사한다.
판정 적용 후에도 `.final.json.image-review.json`으로 증거가 이어진다. 직접 JSON 보정은 불가하며
이미지/전사/파서를 고친 뒤 새 접두사로 재실행한다. 이미지검토근거 시트와 현행본·삭제 이력을
함께 보고하고, 처리한 PDF·쪽수와 제외/보류 범위를 명시한다.
