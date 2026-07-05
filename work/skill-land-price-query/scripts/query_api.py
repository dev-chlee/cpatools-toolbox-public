#!/usr/bin/env python3
"""
부동산공시가격 알리미(realtyprice.kr) 개별공시지가 조회 — 브라우저 없이 내부 API 직접 호출.

이 모듈은 사이트가 내부적으로 쓰는 AJAX 엔드포인트를 그대로 호출한다(공개·무인증 GET):
  1) 세션 쿠키 확보:   GET /notice/gsindividual/search.htm
  2) 지역코드 캐스케이드: GET /notice/bjd/searchBjdApi.bjd  (시도→시군구→읍면동)
  3) 개별공시지가 조회:  GET /notice/search/gsiSearchListApi.search

브라우저 자동화(Chrome MCP)·weasyprint·poppler·특정 OS 폰트에 의존하지 않는다.
표준 라이브러리(urllib)만 사용 → Windows/Linux/macOS 동일 동작.

사용(모듈):
    from query_api import lookup
    result = lookup("서울특별시", "중구", "충무로1가", 24, 2)   # 지번유형 기본 '일반'
    print(result["rows"][0])   # 최신 연도부터

사용(CLI):
    python scripts/query_api.py --sido 서울특별시 --sigungu 중구 --dong 충무로1가 --bun1 24 --bun2 2
    python scripts/query_api.py < batch.json     # {"properties":[{...}, ...]}  배치
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

# ── UTF-8 콘솔 (Windows cp949 콘솔에서 한글/em-dash 출력 시 UnicodeEncodeError 방지) ──
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

BASE = "https://www.realtyprice.kr"
SEARCH_PAGE = "/notice/gsindividual/search.htm"
BJD_API = "/notice/bjd/searchBjdApi.bjd"
LIST_API = "/notice/search/gsiSearchListApi.search"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 25

# 지번유형 → san 코드 (사이트 searchSanApi.bjd 기준: 1=일반, 2=산, 3=가지번 …)
SAN_CODES = {
    "일반": "1", "산": "2", "가지번": "3", "가지번(부번세분)": "4",
    "블럭지번": "5", "블럭지번(롯트세분)": "6", "블럭지번(지구)": "7",
    "블럭지번(롯트)": "8", "기타지번": "9",
}


class LandPriceError(RuntimeError):
    """조회 실패(지역 미매칭·결과 없음·네트워크)."""


def open_session():
    """쿠키를 유지하는 urllib opener 를 만들고, 검색 페이지를 한 번 열어 JSESSIONID 를 확보한다."""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [("User-Agent", UA)]
    opener.open(BASE + SEARCH_PAGE, timeout=TIMEOUT).read()
    return opener


def _get_json(opener, path, params):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    with opener.open(url, timeout=TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    return data.get("model", {}) or {}


def list_sido(opener):
    """시/도 목록 [{code, name, ...}]."""
    return _get_json(opener, BJD_API, {"gbn": "1", "gubun": ""}).get("list") or []


def list_sigungu(opener, sido_code):
    """시/군/구 목록."""
    m = _get_json(opener, BJD_API, {
        "gbn": "1", "gubun": "sgg", "sido": sido_code, "sido_list": sido_code})
    return m.get("list") or []


def list_eub(opener, sido_code, sgg_code):
    """읍/면/동 목록."""
    m = _get_json(opener, BJD_API, {
        "gbn": "1", "gubun": "eub",
        "sido": sido_code, "sido_list": sido_code,
        "sgg": sgg_code, "sgg_list": sgg_code})
    return m.get("list") or []


def _match(options, name, kind):
    """이름으로 코드 매칭: 정확 일치 우선, 없으면 부분 일치(유일할 때만)."""
    name = (name or "").strip()
    exact = [o for o in options if o["name"] == name]
    if exact:
        return exact[0]["code"], exact[0]["name"]
    partial = [o for o in options if name and (name in o["name"] or o["name"] in name)]
    if len(partial) == 1:
        return partial[0]["code"], partial[0]["name"]
    if len(partial) > 1:
        cand = ", ".join(o["name"] for o in partial[:8])
        raise LandPriceError(f"{kind} '{name}' 후보 다수 — 정확한 명칭 필요: {cand}")
    cand = ", ".join(o["name"] for o in options[:12])
    raise LandPriceError(f"{kind} '{name}' 매칭 실패. 선택지 예: {cand}")


def resolve_region(opener, sido_name, sigungu_name, dong_name):
    """행정구역명 3단 → (reg=시군구코드, eub=읍면동코드, 해석된 이름 dict)."""
    sido_code, sido_matched = _match(list_sido(opener), sido_name, "시/도")
    sgg_code, sgg_matched = _match(list_sigungu(opener, sido_code), sigungu_name, "시/군/구")
    eub_code, eub_matched = _match(list_eub(opener, sido_code, sgg_code), dong_name, "읍/면/동")
    return sgg_code, eub_code, {
        "sido": sido_matched, "sigungu": sgg_matched, "dong": eub_matched}


def query_price(opener, reg, eub, bun1, bun2=0, san="1", year=""):
    """지번(코드 확정 상태)으로 개별공시지가 연도별 목록을 조회한다. 최신 연도부터 정렬해 반환."""
    params = {
        "page_no": "1", "gbn": "1", "year": str(year),
        "reg": reg, "eub": eub, "san": str(san),
        "bun1": str(bun1).zfill(4), "bun2": str(bun2 or 0).zfill(4),
        "tabGbn": "Text",
    }
    m = _get_json(opener, LIST_API, params)
    rows = m.get("list") or []
    rows.sort(key=lambda x: str(x.get("base_year", "")), reverse=True)
    return rows, int(m.get("totalCnt") or 0)


def lookup(sido, sigungu, dong, bun1, bun2=0, jibun_type="일반"):
    """
    편의 함수: 행정구역명+지번으로 개별공시지가를 조회한다(세션 자동 생성).

    Returns dict:
      {addr, sido, sigungu, dong, jibun, jibun_type,
       total_records, rows:[{base_year, gakuka_w, notice_ymd, addr, jibun, base_md}...],
       price_latest(int), latest_year(str)}
    """
    san = SAN_CODES.get((jibun_type or "일반").strip(), "1")
    opener = open_session()
    reg, eub, names = resolve_region(opener, sido, sigungu, dong)
    rows, total = query_price(opener, reg, eub, bun1, bun2, san=san)
    if not rows:
        jibun = f"{bun1}-{bun2}" if bun2 else f"{bun1}"
        raise LandPriceError(
            f"결과 없음: {names['sido']} {names['sigungu']} {names['dong']} "
            f"{jibun} (지번유형 {jibun_type}). 지번·유형을 확인하세요.")
    latest = rows[0]
    price_latest = int(str(latest.get("gakuka_w", "0")).replace(",", "").strip() or 0)
    jibun_disp = f"{bun1}-{bun2}" if bun2 else f"{bun1}"
    return {
        "addr": latest.get("addr", "").strip(),
        "sido": names["sido"], "sigungu": names["sigungu"], "dong": names["dong"],
        "jibun": jibun_disp, "jibun_type": jibun_type,
        "total_records": total or len(rows),
        "rows": rows,
        "price_latest": price_latest,
        "latest_year": str(latest.get("base_year", "")),
    }


def _run_cli(argv=None):
    ap = argparse.ArgumentParser(
        description="realtyprice.kr 개별공시지가 조회 (브라우저 불필요, urllib API)")
    ap.add_argument("--sido", help="시/도 (예: 서울특별시)")
    ap.add_argument("--sigungu", help="시/군/구 (예: 중구)")
    ap.add_argument("--dong", help="읍/면/동 (예: 충무로1가)")
    ap.add_argument("--bun1", type=int, help="본번")
    ap.add_argument("--bun2", type=int, default=0, help="부번 (없으면 0)")
    ap.add_argument("--jibun-type", default="일반", help="지번유형 (기본: 일반)")
    args = ap.parse_args(argv)

    # 배치: stdin JSON {"properties":[{sido,sigungu,dong,bun1,bun2,jibun_type}, ...]}
    if args.sido is None and not sys.stdin.isatty():
        payload = json.load(sys.stdin)
        out = []
        for p in payload.get("properties", []):
            try:
                out.append(lookup(p["sido"], p["sigungu"], p["dong"],
                                   p["bun1"], p.get("bun2", 0),
                                   p.get("jibun_type", "일반")))
            except LandPriceError as e:
                out.append({"error": str(e), "input": p})
        json.dump({"results": out}, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    if not (args.sido and args.sigungu and args.dong and args.bun1):
        ap.error("--sido/--sigungu/--dong/--bun1 이 모두 필요합니다(또는 stdin 배치 JSON).")

    res = lookup(args.sido, args.sigungu, args.dong, args.bun1, args.bun2, args.jibun_type)
    json.dump(res, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_run_cli())
    except LandPriceError as e:
        print(f"[조회 실패] {e}", file=sys.stderr)
        raise SystemExit(2)
    except urllib.error.URLError as e:
        print("[네트워크 오류] realtyprice.kr 에 접속할 수 없습니다 "
              f"({getattr(e, 'reason', e)}). 인터넷 연결·회사 방화벽/프록시를 확인하세요.",
              file=sys.stderr)
        raise SystemExit(3)
