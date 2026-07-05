#!/usr/bin/env python3
"""
realtyprice.kr **실제 웹페이지**를 Playwright(headless Chromium)로 구동해 개별공시지가
조회결과 화면을 그대로 스크린샷한다. (재현 렌더가 아니라 실제 사이트 DOM 캡처)

동작:
  1) query_api 로 시/도·시/군/구·읍/면/동 코드를 해석(사이트 select 의 option value 와 동일)
  2) 실제 페이지에서 캐스케이드 드롭다운 선택 → 지번 입력 → 사이트 조회함수(goPage) 실행
  3) 결과 렌더 후 화면을 PNG 로 캡처(full_page: 검색폼+결과 전체 / 아니면 결과영역 크롭)

전제:
    pip install playwright
    python -m playwright install chromium      # Chromium 1회 설치(~130MB)
한글은 OS 시스템 폰트로 렌더된다(Windows=맑은 고딕 기본).

사용(모듈):
    from render_screenshots import capture
    capture("서울특별시", "중구", "충무로1가", 24, 2, "./output/01_충무로1가_24-2.png")

사용(CLI):
    python scripts/render_screenshots.py --sido 서울특별시 --sigungu 중구 --dong 충무로1가 \
        --bun1 24 --bun2 2 --out ./output/01_충무로1가_24-2.png
    python scripts/render_screenshots.py < properties.json     # 배치
    # {"properties":[{"filename":"01_..png","sido":..,"sigungu":..,"dong":..,
    #                 "bun1":24,"bun2":2,"jibun_type":"일반"}], "output_dir":"./output", "full_page":true}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import query_api  # noqa: E402  (동일 폴더 — 지역코드 해석·SAN 코드 재사용)

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

URL = "https://www.realtyprice.kr/notice/gsindividual/search.htm"
RESULT_READY_JS = (
    "() => { const el=document.querySelector('#dataList');"
    " return el && el.innerText && el.innerText.replace(/\\s/g,'').length > 30; }"
)


class ScreenshotError(RuntimeError):
    """스크린샷 단계 실패(Playwright/Chromium 미설치·렌더 타임아웃 등) — 한국어 안내 포함."""


def _wait_options(page, sel_id, min_count=2, timeout=15000):
    page.wait_for_function(
        f"() => {{ const s=document.querySelector('#{sel_id}');"
        f" return s && s.options.length >= {min_count}; }}",
        timeout=timeout)


def capture(sido, sigungu, dong, bun1, bun2=0,
            output_path="./output/shot.png", jibun_type="일반",
            full_page=True, headless=True, timeout=30000, scale=2):
    """
    실제 realtyprice 페이지를 구동해 조회결과를 PNG 로 캡처한다.

    Args:
        sido/sigungu/dong: 행정구역명 (query_api 로 코드 해석)
        bun1/bun2: 본번/부번
        output_path: 출력 PNG 경로
        jibun_type: 지번유형(일반/산 …)
        full_page: True=검색폼+결과 전체, False=결과영역(#contents) 크롭
        headless/timeout/scale: Playwright 옵션(scale=device_scale_factor)
    Returns:
        output_path (성공), None (실패)
    Raises:
        query_api.LandPriceError: 지역 매칭 실패
    """
    try:
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as PWTimeoutError
        from playwright.sync_api import Error as PWError
    except ImportError as e:
        raise ScreenshotError(
            "스크린샷 기능에 playwright 패키지가 필요합니다. 설치:\n"
            "    pip install playwright\n"
            "    python -m playwright install chromium") from e

    # 1) 지역코드 해석 (사이트 select option value 와 동일한 코드)
    opener = query_api.open_session()
    sido_code, _ = query_api._match(query_api.list_sido(opener), sido, "시/도")
    sgg_code, _ = query_api._match(query_api.list_sigungu(opener, sido_code), sigungu, "시/군/구")
    eub_code, _ = query_api._match(query_api.list_eub(opener, sido_code, sgg_code), dong, "읍/면/동")
    san = query_api.SAN_CODES.get((jibun_type or "일반").strip(), "1")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=headless)
        except PWError as e:
            if "install" in str(e).lower() or "executable" in str(e).lower():
                raise ScreenshotError(
                    "Chromium 브라우저가 설치되지 않았습니다. 실행:\n"
                    "    python -m playwright install chromium") from e
            raise ScreenshotError(f"브라우저 실행 실패: {e}") from e
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 1024},
                                    device_scale_factor=scale)
            # domcontentloaded: 사이트가 지속 연결(analytics 등)을 열어 networkidle 이 안 잡히는 경우가 있어
            # DOM 로드까지만 대기하고, 시/도 옵션 로드는 아래에서 별도로 기다린다.
            page.goto(URL, wait_until="domcontentloaded", timeout=timeout)

            # 시/도 옵션 로드(자동 로드 안 되면 트리거)
            try:
                _wait_options(page, "sido_list", 2, 8000)
            except Exception:
                page.evaluate("getSubListBjd('', true)")
                _wait_options(page, "sido_list", 2)

            # 캐스케이드: 실제 select_option = change 이벤트 → 사이트 onChange AJAX
            page.select_option("#sido_list", sido_code)
            _wait_options(page, "sgg_list", 2)
            page.select_option("#sgg_list", sgg_code)
            _wait_options(page, "eub_list", 2)
            page.select_option("#eub_list", eub_code)
            try:
                page.select_option("#bjdForm select[name='san']", san)
            except Exception:
                pass  # san select 기본값(일반)이면 무시

            page.fill("#bjdForm input[name='bun1']", str(bun1))
            page.fill("#bjdForm input[name='bun2']", str(bun2) if bun2 else "")

            # 실제 조회 실행(검색 버튼과 동일 경로) → 결과 렌더 대기
            page.evaluate("goPage(1)")
            page.wait_for_function(RESULT_READY_JS, timeout=timeout)
            time.sleep(1.2)  # 렌더 안정화

            if full_page:
                page.screenshot(path=output_path, full_page=True)
            else:
                el = page.query_selector("#contents") or page.query_selector("#dataList")
                (el or page).screenshot(path=output_path)
        except PWTimeoutError as e:
            # 페이지 로드·옵션 로드·조회결과 렌더 어디서든 시간 초과 → 한국어 안내
            raise ScreenshotError(
                "realtyprice 페이지 로드 또는 조회결과 렌더 대기 시간을 초과했습니다. "
                "네트워크 지연이거나(회사 프록시/방화벽), 지번·지번유형(일반/산)이 부정확해 결과가 0건일 수 "
                "있습니다. 인터넷 연결을 확인하고, 필요하면 timeout 을 늘려 재시도하세요.") from e
        finally:
            browser.close()

    return output_path if os.path.exists(output_path) else None


def _run_cli(argv=None):
    ap = argparse.ArgumentParser(
        description="realtyprice.kr 실제 웹페이지 조회결과 스크린샷 (Playwright)")
    ap.add_argument("--sido")
    ap.add_argument("--sigungu")
    ap.add_argument("--dong")
    ap.add_argument("--bun1", type=int)
    ap.add_argument("--bun2", type=int, default=0)
    ap.add_argument("--jibun-type", default="일반")
    ap.add_argument("--out", default="./output/shot.png", help="출력 PNG 경로")
    ap.add_argument("--result-only", action="store_true",
                    help="검색폼 제외, 결과영역만 크롭")
    ap.add_argument("--no-headless", action="store_true")
    args = ap.parse_args(argv)

    # 배치: stdin JSON
    if args.sido is None and not sys.stdin.isatty():
        data = json.load(sys.stdin)
        output_dir = data.get("output_dir") or os.getenv("OUTPUT_DIR", "./output")
        full_page = data.get("full_page", True)
        os.makedirs(output_dir, exist_ok=True)
        for prop in data["properties"]:
            filename = prop["filename"]
            path = os.path.join(output_dir, filename)
            try:
                res = capture(prop["sido"], prop["sigungu"], prop["dong"],
                              prop["bun1"], prop.get("bun2", 0), path,
                              prop.get("jibun_type", "일반"), full_page=full_page)
                if res:
                    print(f"[OK] {filename}: {os.path.getsize(res):,} bytes")
                else:
                    print(f"[FAIL] {filename}: 캡처 실패")
            except (query_api.LandPriceError, ScreenshotError) as e:
                print(f"[FAIL] {filename}: {e}")
        return 0

    if not (args.sido and args.sigungu and args.dong and args.bun1):
        ap.error("--sido/--sigungu/--dong/--bun1 이 모두 필요합니다(또는 stdin 배치 JSON).")

    res = capture(args.sido, args.sigungu, args.dong, args.bun1, args.bun2,
                  args.out, args.jibun_type, full_page=not args.result_only,
                  headless=not args.no_headless)
    if res:
        print(f"[OK] {res}: {os.path.getsize(res):,} bytes")
        return 0
    print("[FAIL] 캡처 실패", file=sys.stderr)
    return 1


if __name__ == "__main__":
    import urllib.error
    try:
        raise SystemExit(_run_cli())
    except query_api.LandPriceError as e:
        print(f"[조회 실패] {e}", file=sys.stderr)
        raise SystemExit(2)
    except ScreenshotError as e:
        print(f"[스크린샷 실패] {e}", file=sys.stderr)
        raise SystemExit(4)
    except urllib.error.URLError as e:
        print("[네트워크 오류] realtyprice.kr 에 접속할 수 없습니다 "
              f"({getattr(e, 'reason', e)}). 인터넷 연결·회사 방화벽/프록시를 확인하세요.",
              file=sys.stderr)
        raise SystemExit(3)
