# 샘플 엑셀 mapping

클라이언트마다 샘플 엑셀의 시트·행·열 구조가 다르다. 실행 중인 Claude/Codex가 통합문서를 먼저 읽고 각 열의 의미를 확인한 뒤, 아래 형식의 UTF-8 JSON을 작업 출력 폴더에 작성한다. 스킬 코드를 클라이언트별로 수정하지 않는다.

```json
{
  "sections": [
    {
      "sheet": "해외매출",
      "start_row": 5,
      "end_row": 104,
      "columns": {
        "folder": "B",
        "customer": "C",
        "ci_no": "D",
        "account_date": "E",
        "incoterms": "F",
        "currency": "G",
        "fc_amount": "H",
        "krw_amount": "I"
      },
      "constants": {
        "type": "직수출"
      }
    },
    {
      "sheet": "국내매출",
      "start_row": 5,
      "columns": {
        "folder": "B",
        "customer": "C",
        "account_date": "D",
        "voucher_no": "E",
        "krw_amount": "F"
      },
      "constants": {
        "type": "국내매출",
        "currency": "KRW"
      }
    }
  ]
}
```

## 계약

- `sections`: 서로 다른 시트나 하위표마다 한 항목을 둔다. 한 통합문서 안에서 매출유형별 스키마가 달라도 처리할 수 있다.
- `sheet`: 생략하면 활성 시트를 사용한다.
- `start_row`: 첫 데이터 행이다. 필수이며 1 이상이어야 한다.
- `end_row`: 마지막 데이터 행이다. 생략하면 해당 시트의 마지막 사용 행까지 읽는다.
- `columns`: 필드와 열의 대응이다. 열은 `A`, `B` 같은 문자 또는 1부터 시작하는 정수로 지정한다.
- `constants`: 해당 구간의 모든 행에 적용할 고정값이다. `columns`와 같은 필드를 중복 지정할 수 없다.
- 필수 필드: `folder`, `type`, `customer`, `krw_amount`. `folder`가 빈 행은 건너뛴다.
- 해외 권장 필드: `ci_no`, `account_date`, `incoterms`, `currency`, `fc_amount`.
- 국내 권장 필드: `account_date`, `voucher_no`, `currency`.
- `folder`는 표본마다 고유해야 하며 증빙 폴더명과 정확히 일치해야 한다.
- `krw_amount`와 값이 있는 `fc_amount`는 Excel 숫자 셀이어야 한다. 쉼표나 통화기호가 포함된 문자열은 mapping 단계에서 오류로 처리한다.
- 금액이 수식이면 Excel에서 계산·저장된 값이 있어야 한다. `data_only`로 읽었을 때 값이 없으면 필수값 또는 숫자 검증 오류가 된다.

원본에 값이 있는데 `--mapping`을 생략했거나 mapping 결과가 0건이면 엔진은 종료코드 2로 실패한다. 실제로 값이 전혀 없는 통합문서만 정상적인 0건 입력으로 구분한다.

```bash
python scripts/tod_engine.py sample.xlsx --mapping <보관소>/output/sample-mapping.json --evidence <보관소>/input/evidence --bundles-out <보관소>/output/bundles.json
```
