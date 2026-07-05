# land-price-query

한국 개별공시지가 조회 자동화 Claude Skill. **로컬 실행 전용(Windows 기본).**

## 언제 쓰나
- 토지 평가·세무·감사용 개별공시지가 조회
- 다수 필지 batch 조회 + 감사 워크페이퍼(엑셀) 생성
- 조회결과 스크린샷(PNG) 캡처로 증빙 보관

## 아키텍처
weasyprint·poppler 없이 동작한다. 조회 데이터와 스크린샷의 역할을 분리한다.
- **조회 데이터**: 표준 라이브러리 `urllib` 로 realtyprice.kr 내부 API 직접 호출 (무인증 GET, 빠름).
- **스크린샷**: `Playwright`(headless Chromium)로 **실제 웹페이지**를 조작·캡처 (재현물 아님 — 감사 증빙).
- **엑셀**: `openpyxl` (+ `pillow` 로 임베드 이미지 비율 계산).

## 의존성
- Python ≥ 3.10
- `openpyxl` ≥ 3.1, `pillow` ≥ 10.0, `playwright` ≥ 1.40
- API 키·별도 시스템 바이너리: 없음. (Chromium 은 playwright 가 관리)

```bash
pip install -r skills/work/skill-land-price-query/requirements.lock
python -m playwright install chromium          # 스크린샷용 Chromium 1회 설치(~130MB)
# 또는 스킬-로컬 .venv 로:
python skills/work/skill-land-price-query/scripts/setup_venv.py
python -m playwright install chromium
```
> `setup_venv.py` 로 `.venv` 를 만들면, 이후 실행은 그 venv 파이썬으로 한다
> (Windows `.venv\Scripts\python.exe …`, Linux/macOS `.venv/bin/python …`). 맨 `python` 은
> 시스템 파이썬을 잡아 `ModuleNotFoundError` 가 날 수 있다.

## 사용법

### Claude Code에서
필지 목록을 입력하고 "공시지가 조회해서 정리해줘". SKILL.md 절차에 따라 LLM이 조회·집계·결과지 생성.

### CLI
```bash
# 조회 데이터
python scripts/query_api.py --sido 서울특별시 --sigungu 중구 --dong 충무로1가 --bun1 24 --bun2 2
# 실제 웹페이지 스크린샷
python scripts/render_screenshots.py --sido 서울특별시 --sigungu 중구 --dong 충무로1가 \
    --bun1 24 --bun2 2 --out ./output/01_충무로1가_24-2.png
# 엑셀 (stdin JSON, SKILL.md 참고)
python scripts/create_excel.py < workpaper_data.json
```

### 모듈 예시
```python
import sys; sys.path.insert(0, 'skills/work/skill-land-price-query/scripts')
from query_api import lookup
from render_screenshots import capture

res = lookup("서울특별시", "중구", "충무로1가", 24, 2)          # 데이터(urllib)
capture("서울특별시", "중구", "충무로1가", 24, 2,
        "./output/01_충무로1가_24-2.png")                      # 실제 웹페이지 캡처(Playwright)
```

## 자세한 사용법
[`SKILL.md`](./SKILL.md) — 입력 형식, 조회/렌더/엑셀 단계, 결과지 포맷.

## 라이선스
MIT
