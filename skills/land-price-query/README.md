# land-price-query

한국 부동산 공시지가·실거래가 조회 자동화 Claude Skill.

## 언제 쓰나
- 토지 평가·세무 신고용 공시지가 일괄 조회
- 다수 필지 batch 조회 + 결과지(엑셀·PDF) 생성
- 스크린샷 캡처로 증빙 보관

## 의존성
- Python ≥ 3.10
- `openpyxl` ≥ 3.1
- `weasyprint` ≥ 60 (HTML → PDF 렌더)
- (외부) **Google Chrome** — 스크린샷용(`render_screenshots.py` 사용 시)

```bash
pip install -r skills/land-price-query/requirements.txt
```

> Windows에서 `weasyprint` 설치 시 GTK 런타임 필요. WSL/Linux 환경 권장.

## 사용법

### Claude Code에서
필지 목록을 입력하고 "공시지가 조회해서 정리해줘". SKILL.md 절차에 따라 LLM이 조회·집계·결과지 생성.

### 결과지 생성 (CLI)
```bash
python skills/land-price-query/scripts/create_excel.py
python skills/land-price-query/scripts/render_screenshots.py
```

## 예시
```python
import sys; sys.path.insert(0, 'skills/land-price-query/scripts')
from create_excel import build_workbook
build_workbook(records, 'land_prices.xlsx')
```

## 자세한 사용법
[`SKILL.md`](./SKILL.md) — 입력 형식, 조회 단계, 결과지 포맷.

## 라이선스
MIT
