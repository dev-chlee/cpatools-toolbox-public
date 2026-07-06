# land-price-query

부동산공시가격 알리미(realtyprice.kr)에서 **개별공시지가**를 조회해, **실제 웹페이지 스크린샷**(감사 증빙)과
**감사 워크페이퍼(엑셀)** 를 자동 생성하는 Claude Skill. **로컬 실행 전용(Windows 기본).**

## 무엇을 하나
- 필지(주소 + 지번) → realtyprice 개별공시지가 조회 (연도별 전체, 무인증 내부 API)
- 실제 조회 화면을 **그대로 스크린샷**(재현물 아님 — 감사 증빙용)
- 요약 시트 + 물건별 시트 + 스크린샷 임베드 **엑셀 워크페이퍼** 생성
- **다수 필지 일괄 조회** (한 건 실패가 전체를 막지 않음)

## 설치 (AI가 대신 실행)
개발 지식이 없어도 **Claude 에게 "이 스킬 설치해줘"** 라고 하면 아래를 대신 실행한다. API 키·계정·시스템
바이너리 없이 로컬에서 완결된다(필요: Python ≥ 3.10).

```bash
cd <skill-dir>
python scripts/setup_venv.py            # 스킬-로컬 .venv + 의존성(openpyxl·pillow·playwright)
python -m playwright install chromium   # 스크린샷용 Chromium 1회 설치(~130MB)
```
> `setup_venv.py` 로 `.venv` 를 만들면 이후 실행은 그 venv 파이썬으로 한다
> (Windows `.venv\Scripts\python.exe …`). 자세한 준비 절차는 `SKILL.md` 의 "실행 환경 & 최초 준비".

## 사용법
### Claude 에게 (권장 — 자연어)
> "서울 중구 충무로1가 24-2 공시지가 조회해서 워크페이퍼로 정리해줘"

SKILL.md 절차에 따라 Claude 가 조회 → 실제 스크린샷 → 엑셀 생성까지 수행한다. 여러 필지를 한 번에도 가능.

### CLI
```bash
# 조회 데이터
python scripts/query_api.py --sido 서울특별시 --sigungu 중구 --dong 충무로1가 --bun1 24 --bun2 2
# 실제 웹페이지 스크린샷
python scripts/render_screenshots.py --sido 서울특별시 --sigungu 중구 --dong 충무로1가 \
    --bun1 24 --bun2 2 --out ./output/01_충무로1가_24-2.png
```

## 아키텍처
- **조회 데이터**: 표준 라이브러리 `urllib` 로 realtyprice.kr 내부 API 직접 호출(빠름, 무인증)
- **스크린샷**: `Playwright`(headless Chromium)로 실제 웹페이지 조작·캡처
- **엑셀**: `openpyxl` (+ `pillow` 로 임베드 이미지 비율 계산)

## 문서
- [`SKILL.md`](./SKILL.md) — 입력·조회·스크린샷·엑셀 단계, env, CLI, 에러 처리 (단일 기준)

## 라이선스
MIT
