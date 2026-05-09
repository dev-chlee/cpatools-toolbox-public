#!/usr/bin/env python3
"""
개별공시지가 조회결과를 realtyprice.kr 레이아웃으로 렌더링하여 PNG 이미지를 생성한다.

사용법:
    이 스크립트를 직접 실행하거나, generate_screenshot() 함수를 import하여 사용.

    직접 실행 시: stdin으로 JSON 데이터를 받는다.
    python scripts/render_screenshots.py < properties.json

    JSON 형식:
    {
        "properties": [
            {
                "filename": "01_OO동_X-X.png",
                "sido_options": [{"text": "경기도", "selected": true}, ...],
                "sigungu_options": [...],
                "dong_options": [...],
                "jibun_type": "일반",
                "jibun_main": "792",
                "jibun_sub": "2",
                "total_count": "38",
                "area_text": "경기도 OO시 OO구 OO동 X-X",
                "rows": [
                    {"year": "2025", "location": "경기도 OO시 OO구 OO동 X-X",
                     "jibun": "X-X번지", "price": "1,234,567 원/㎡",
                     "base_date": "01월01일", "announce_date": "20250430"}
                ]
            }
        ],
        "output_dir": "/path/to/output"
    }
"""
import weasyprint
import subprocess
import os
import sys
import json

# ──────────────────────────────────────────────
# 한글 폰트 경로 (VM 환경에서 사용 가능한 한글 폰트)
# 주의: DroidSansFallbackFull.ttf (in /usr/share/fonts/truetype/droid/)는 한글 3자만 포함.
#       아래 경로의 DroidSansFallback.ttf는 11,172개 한글 음절 포함.
# ──────────────────────────────────────────────
KOREAN_FONT_PATH = "/usr/share/fonts-droid-fallback/truetype/DroidSansFallback.ttf"

COMMON_CSS = """
@font-face {
    font-family: 'KoreanFont';
    src: url('file://""" + KOREAN_FONT_PATH + """') format('truetype');
    font-weight: normal;
    font-style: normal;
}
@page {
    size: 1200px 750px;
    margin: 0;
}
* {
    font-family: 'KoreanFont', 'DejaVu Sans', sans-serif !important;
}
body {
    font-family: 'KoreanFont', 'DejaVu Sans', sans-serif;
    margin: 0; padding: 0; background: #fff; color: #333; font-size: 13px;
}
.page-wrapper { width: 1200px; padding: 15px 20px; }
.search-area {
    background: #f9f9f9; border: 1px solid #ddd;
    padding: 15px 20px; margin-bottom: 10px;
}
.search-title { font-size: 18px; font-weight: bold; color: #333; margin-bottom: 10px; }
.search-select {
    border: 1px solid #bbb; padding: 4px 8px; font-size: 12px;
    background: #fff; min-width: 120px; height: 100px; overflow-y: auto;
}
.search-select .selected { background: #316AC5; color: #fff; padding: 1px 4px; }
.search-select .item { padding: 1px 4px; color: #333; }
.jibun-input {
    border: 1px solid #bbb; padding: 3px 6px; font-size: 12px;
    width: 60px; text-align: center;
}
.search-btn {
    display: block; margin: 10px auto 0; background: #4a6fa5; color: #fff;
    border: none; padding: 6px 40px; font-size: 13px; border-radius: 3px;
    text-align: center; width: 100px;
}
.tab-active { background: #4a6fa5; color: #fff; padding: 8px 30px; font-size: 13px; text-align: center; flex: 1; }
.tab-inactive { background: #888; color: #fff; padding: 8px 30px; font-size: 13px; text-align: center; flex: 1; }
.result-header { font-size: 13px; color: #333; padding: 8px 0; margin-bottom: 5px; }
.result-header .checkbox {
    display: inline-block; width: 12px; height: 12px;
    border: 1px solid #999; vertical-align: middle; margin-right: 3px;
    background: #fff; position: relative;
}
.result-header .checkbox.checked::after {
    content: '✓'; position: absolute; top: -3px; left: 1px; font-size: 11px; color: #333;
}
.print-link { float: right; color: #666; font-size: 12px; text-decoration: none; }
table.result-table { width: 100%; border-collapse: collapse; margin-top: 5px; font-size: 13px; }
table.result-table thead tr:first-child th {
    background-color: #e8e8e8; border: 1px solid #ccc;
    padding: 8px 5px; font-weight: bold; text-align: center; color: #333;
}
table.result-table thead tr:nth-child(2) th {
    background-color: #f0f0f0; border: 1px solid #ccc;
    padding: 7px 5px; font-weight: bold; text-align: center; font-size: 12px; color: #555;
}
table.result-table tbody td {
    border: 1px solid #ccc; padding: 7px 10px;
    text-align: center; font-size: 12px; color: #333; background: #fff;
}
.footer-area {
    margin-top: 10px; padding: 8px 0;
    font-size: 11px; color: #888; border-top: 1px solid #eee;
}
"""


def generate_html(prop):
    """realtyprice.kr 레이아웃을 재현한 HTML을 생성한다."""
    def render_options(options):
        html = ""
        for opt in options:
            cls = "selected" if opt.get("selected") else "item"
            html += f'<div class="{cls}">{opt["text"]}</div>\n'
        return html

    sido_html = render_options(prop["sido_options"])
    sigungu_html = render_options(prop["sigungu_options"])
    dong_html = render_options(prop["dong_options"])

    rows_html = ""
    for r in prop["rows"]:
        rows_html += f"""    <tr>
      <td>{r['year']}</td>
      <td>{r['location']}</td>
      <td>{r['jibun']}</td>
      <td>{r['price']}</td>
      <td>{r['base_date']}</td>
      <td>{r['announce_date']}</td>
      <td></td>
    </tr>\n"""

    jibun_sub_html = f' - <span class="jibun-input">{prop["jibun_sub"]}</span>' if prop.get("jibun_sub") else ""

    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><style>{COMMON_CSS}</style></head>
<body>
<div class="page-wrapper">
  <div style="display:flex;gap:15px;align-items:flex-start;">
    <div style="flex:1;">
      <div style="display:flex;">
        <div class="tab-active">텍스트검색</div>
        <div class="tab-inactive">지도검색</div>
      </div>
      <div class="search-area">
        <div style="display:flex;align-items:center;gap:5px;margin-bottom:8px;">
          <span class="search-title">Search</span>
          <span style="background:#4a6fa5;color:#fff;padding:2px 8px;font-size:11px;border-radius:2px;">지번 검색</span>
          <span style="background:#888;color:#fff;padding:2px 8px;font-size:11px;border-radius:2px;">도로명 검색</span>
        </div>
        <div style="display:flex;gap:10px;">
          <div>
            <div style="font-size:11px;color:#666;margin-bottom:3px;">시/도 선택</div>
            <div class="search-select" style="width:130px;">{sido_html}</div>
          </div>
          <div>
            <div style="font-size:11px;color:#666;margin-bottom:3px;">시/군/구 선택</div>
            <div class="search-select" style="width:110px;">{sigungu_html}</div>
          </div>
          <div>
            <div style="font-size:11px;color:#666;margin-bottom:3px;">읍/면/동 선택</div>
            <div class="search-select" style="width:130px;">{dong_html}</div>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:5px;justify-content:center;margin-top:12px;">
          <span class="jibun-input">{prop['jibun_type']}</span>
          <span>▼</span>
          <span class="jibun-input">{prop['jibun_main']}</span>
          {jibun_sub_html}
        </div>
        <div class="search-btn">검색</div>
      </div>
    </div>
  </div>

  <div class="result-header" style="margin-top:10px;">
    <span><span class="checkbox checked"></span> 개별공시지가</span>
    <span><span class="checkbox"></span> 총 : {prop['total_count']}개</span>
    <span><span class="checkbox"></span> 열람지역 : {prop['area_text']}</span>
    <a class="print-link" href="#">🖨 인쇄</a>
  </div>

  <table class="result-table">
    <thead>
      <tr><th colspan="3">신청대상 토지</th><th colspan="4">확인내용</th></tr>
      <tr>
        <th style="width:100px">가격기준년도</th>
        <th style="width:300px">토지소재지</th>
        <th style="width:100px">지번</th>
        <th style="width:120px">개별공시지가</th>
        <th style="width:80px">기준일자</th>
        <th style="width:90px">공시일자</th>
        <th style="width:100px">비고</th>
      </tr>
    </thead>
    <tbody>
{rows_html}
    </tbody>
  </table>

  <div class="footer-area">
    (우)41068 대구광역시 동구 이노밸리로 291 (신서동) 한국부동산원
  </div>
</div>
</body></html>"""


def generate_screenshot(prop, output_path, temp_dir="/tmp"):
    """
    단일 물건의 조회결과를 PNG 이미지로 렌더링한다.

    Args:
        prop: 물건 데이터 dict (generate_html의 인자와 동일)
        output_path: 출력 PNG 파일 경로
        temp_dir: 임시 파일 저장 디렉토리
    Returns:
        output_path (성공 시), None (실패 시)
    """
    basename = os.path.splitext(os.path.basename(output_path))[0]
    html_path = os.path.join(temp_dir, f"temp_{basename}.html")
    pdf_path = os.path.join(temp_dir, f"temp_{basename}.pdf")
    png_base = output_path.replace(".png", "")

    html_content = generate_html(prop)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    doc = weasyprint.HTML(filename=html_path)
    doc.write_pdf(pdf_path)

    subprocess.run(
        ["pdftoppm", "-png", "-r", "150", "-singlefile", pdf_path, png_base],
        check=True,
    )

    # 정리
    for tmp in [html_path, pdf_path]:
        if os.path.exists(tmp):
            os.remove(tmp)

    return output_path if os.path.exists(output_path) else None


if __name__ == "__main__":
    data = json.load(sys.stdin)
    output_dir = data.get("output_dir", ".")
    os.makedirs(output_dir, exist_ok=True)

    for prop in data["properties"]:
        filename = prop.pop("filename")
        output_path = os.path.join(output_dir, filename)
        result = generate_screenshot(prop, output_path)
        if result:
            size = os.path.getsize(result)
            print(f"✅ {filename}: {size:,} bytes")
        else:
            print(f"❌ {filename}: 렌더링 실패")
