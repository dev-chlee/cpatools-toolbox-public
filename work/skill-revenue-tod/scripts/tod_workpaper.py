"""
매출 TOD 워크페이퍼 생성기 - 프로파일 구동
==========================================
tod_engine.py 의 결과(JSON)를 읽어 엑셀 워크페이퍼를 생성한다.
Summary + 프로파일별 상세 시트(해외매출/국내매출/용역매출 등)를 자동 구성한다.
각 상세 시트의 검증 열은 결과의 checks(프로파일 체크 순서)에서 **동적으로** 만들어진다.

사용법:
  python3 tod_workpaper.py <results.json> <output.xlsx> [회사명] [감사기간]
"""

import json
import sys
import argparse
import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import cpa_storage


# ========================
# 스타일 정의
# ========================

header_font = Font(name='맑은 고딕', bold=True, size=9, color='FFFFFF')
header_fill = PatternFill('solid', fgColor='2F5496')
pass_fill = PatternFill('solid', fgColor='C6EFCE')
fail_fill = PatternFill('solid', fgColor='FFC7CE')
exception_fill = PatternFill('solid', fgColor='FFEB9C')
na_fill = PatternFill('solid', fgColor='D9E2F3')
title_font = Font(name='맑은 고딕', bold=True, size=14)
subtitle_font = Font(name='맑은 고딕', bold=True, size=11)
data_font = Font(name='맑은 고딕', size=8)
data_font_bold = Font(name='맑은 고딕', size=8, bold=True)
border = Border(
    left=Side(style='thin'), right=Side(style='thin'),
    top=Side(style='thin'), bottom=Side(style='thin'))
center = Alignment(horizontal='center', vertical='center', wrap_text=True)
wrap = Alignment(vertical='top', wrap_text=True)
wrap_center = Alignment(horizontal='center', vertical='top', wrap_text=True)


# 프로파일별 기본정보(base) 컬럼: (표시명, base 키)
BASE_COLS = {
    'overseas': [
        ('CI No.', 'ci_no_excel'), ('거래처', 'customer_excel'),
        ('운임조건', 'incoterms_excel'), ('통화', 'currency_excel'),
        ('FC금액', 'fc_amount_excel'), ('KRW금액', 'krw_amount_excel'),
    ],
    'default': [
        ('거래처', 'customer_excel'), ('공급가액(KRW)', 'krw_amount_excel'),
    ],
}
_NUMERIC_BASE_KEYS = {'fc_amount_excel', 'krw_amount_excel'}


def _utf8_console():
    """Windows 기본 콘솔에서도 한글 도움말과 진행 메시지를 UTF-8로 출력한다."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8')
            except (AttributeError, OSError):
                pass


def _safe_excel_value(value):
    """외부 문자열이 Excel 수식으로 해석되지 않도록 텍스트로 고정한다."""
    if isinstance(value, str) and value.startswith('='):
        return "'" + value
    return value


def style_header(ws, row, max_col):
    for c in range(1, max_col + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border


def style_data(ws, row, max_col, font=None):
    for c in range(1, max_col + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = font or data_font
        cell.border = border
        cell.alignment = wrap


def color_result(cell, value):
    cell.alignment = center
    if value == 'Pass':
        cell.fill = pass_fill
    elif value == 'Exception':
        cell.fill = exception_fill
    elif value == 'Fail':
        cell.fill = fail_fill
    elif value == 'N/A':
        cell.fill = na_fill


def _group_label(r):
    return r.get('profile_display') or r.get('type') or '(미분류)'


def _doc_list(r):
    out = []
    for doc_type, docs in r.get('docs', {}).items():
        for d in docs:
            out.append(f"[{doc_type}] {d['filename']}")
    return '\n'.join(out)


def _build_summary(wb, results, company_name, audit_period):
    ws = wb.active
    ws.title = 'Summary'
    ws['A1'] = _safe_excel_value(f'매출 TOD 워크페이퍼 - {company_name}')
    ws['A1'].font = title_font
    ws['A2'] = _safe_excel_value(f'감사대상기간: {audit_period}')
    ws['A2'].font = subtitle_font

    ws['A5'] = '1. 테스트 요약'
    ws['A5'].font = subtitle_font
    headers = ['구분', '총 샘플수', 'Pass', 'Exception', 'Fail', 'Pass Rate']
    for i, h in enumerate(headers, 1):
        ws.cell(row=6, column=i, value=h)
    style_header(ws, 6, 6)

    groups = {}
    for r in results:
        groups.setdefault(_group_label(r), []).append(r)

    row = 7
    for cat, items in sorted(groups.items()):
        total = len(items)
        p = sum(1 for r in items if r['overall'] == 'Pass')
        e = sum(1 for r in items if r['overall'] == 'Exception')
        f = sum(1 for r in items if r['overall'] == 'Fail')
        ws.cell(row=row, column=1, value=_safe_excel_value(cat))
        ws.cell(row=row, column=2, value=total)
        ws.cell(row=row, column=3, value=p)
        ws.cell(row=row, column=4, value=e)
        ws.cell(row=row, column=5, value=f)
        ws.cell(row=row, column=6, value=f'{p / total * 100:.1f}%' if total else 'N/A')
        style_data(ws, row, 6)
        for c in range(2, 7):
            ws.cell(row=row, column=c).alignment = center
        row += 1

    # 합계
    total = len(results)
    ws.cell(row=row, column=1, value='합계').font = data_font_bold
    ws.cell(row=row, column=2, value=total)
    ws.cell(row=row, column=3, value=sum(1 for r in results if r['overall'] == 'Pass'))
    ws.cell(row=row, column=4, value=sum(1 for r in results if r['overall'] == 'Exception'))
    ws.cell(row=row, column=5, value=sum(1 for r in results if r['overall'] == 'Fail'))
    tp = sum(1 for r in results if r['overall'] == 'Pass')
    ws.cell(row=row, column=6, value=f'{tp / total * 100:.1f}%' if total else 'N/A')
    style_data(ws, row, 6, data_font_bold)
    for c in range(2, 7):
        ws.cell(row=row, column=c).alignment = center

    # Exception/Fail 목록
    row += 2
    ws.cell(row=row, column=1, value='2. Exception / Fail 목록').font = subtitle_font
    row += 1
    exc_headers = ['No.', '폴더명', '구분', '종합결과', 'Exception/Fail 사유']
    for i, h in enumerate(exc_headers, 1):
        ws.cell(row=row, column=i, value=h)
    style_header(ws, row, len(exc_headers))
    row += 1
    exc_no = 1
    for r in results:
        if r['overall'] in ('Exception', 'Fail'):
            ws.cell(row=row, column=1, value=exc_no)
            ws.cell(row=row, column=2, value=_safe_excel_value(r.get('folder', '')))
            ws.cell(row=row, column=3, value=_safe_excel_value(_group_label(r)))
            cell = ws.cell(row=row, column=4, value=r['overall'])
            color_result(cell, r['overall'])
            ws.cell(row=row, column=5,
                    value=_safe_excel_value('\n'.join(r.get('exceptions', []))))
            style_data(ws, row, len(exc_headers))
            row += 1
            exc_no += 1

    for col, w in zip('ABCDE', (22, 16, 12, 12, 60)):
        ws.column_dimensions[col].width = w


# 섹션 그룹 헤더/배경 (검증대상 vs 검증결과 시각 구획)
target_group_fill = PatternFill('solid', fgColor='404040')   # ① 검증대상(전표) — 회색
result_group_fill = PatternFill('solid', fgColor='2F5496')   # ② 검증결과 — 파랑(체크헤더와 한 블록)
target_band_fill = PatternFill('solid', fgColor='F2F2F2')    # ① 데이터 열 옅은 배경
group_font = Font(name='맑은 고딕', bold=True, size=9, color='FFFFFF')


def _build_detail(wb, title, rows, base_cols):
    ws = wb.create_sheet(title[:31])  # 시트명 31자 제한
    ws['A1'] = _safe_excel_value(f'{title} TOD 상세 워크페이퍼')
    ws['A1'].font = title_font

    # 검증 열은 첫 행의 checks(프로파일 체크 순서)에서 동적 생성
    check_items = list(rows[0].get('checks', {}).items())  # [(cid, {label,result,detail}), ...]

    headers = ['No.', '폴더명'] + [name for name, _ in base_cols]
    check_start = len(headers) + 1
    for _cid, c in check_items:
        headers += [f"{c.get('label', _cid)}\n결과", f"{c.get('label', _cid)} 상세"]
    headers += ['종합결과', 'Exception 사유', '증빙파일 목록']
    last_col = len(headers)

    # 그룹 헤더(row 3): ① 검증대상(전표 기록) | ② 증빙 검증 결과(LLM 판정+Python 재검증)
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=check_start - 1)
    g1 = ws.cell(row=3, column=1, value='① 검증대상 — 전표(장부) 기록 정보')
    g1.fill = target_group_fill; g1.font = group_font; g1.alignment = center
    ws.merge_cells(start_row=3, start_column=check_start, end_row=3, end_column=last_col)
    g2 = ws.cell(row=3, column=check_start, value='② 증빙 검증 결과 — LLM 판정 + Python 재검증')
    g2.fill = result_group_fill; g2.font = group_font; g2.alignment = center

    # 컬럼 헤더(row 4)
    for i, h in enumerate(headers, 1):
        ws.cell(row=4, column=i, value=h)
    style_header(ws, 4, last_col)

    result_cols = []  # 색상 입힐 결과 열 인덱스
    row = 5
    for no, r in enumerate(rows, 1):
        base = r.get('base', {})
        ws.cell(row=row, column=1, value=no)
        ws.cell(row=row, column=2, value=_safe_excel_value(r.get('folder', '')))
        col = 3
        for _name, key in base_cols:
            val = base.get(key)
            if key in _NUMERIC_BASE_KEYS and val not in (None, ''):
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    pass
            ws.cell(row=row, column=col,
                    value=_safe_excel_value(val if val is not None else ''))
            col += 1
        for cid, _ in check_items:
            c = r.get('checks', {}).get(cid, {})
            rc = ws.cell(row=row, column=col, value=c.get('result', ''))
            color_result(rc, c.get('result', ''))
            if col not in result_cols:
                result_cols.append(col)
            ws.cell(row=row, column=col + 1,
                    value=_safe_excel_value(c.get('detail', '')))
            col += 2
        oc = ws.cell(row=row, column=col, value=r['overall'])
        color_result(oc, r['overall'])
        overall_col = col
        ws.cell(row=row, column=col + 1,
                value=_safe_excel_value('\n'.join(r.get('exceptions', []))))
        ws.cell(row=row, column=col + 2, value=_safe_excel_value(_doc_list(r)))
        style_data(ws, row, len(headers))
        for bc in range(1, check_start):                 # ① 검증대상 열: 옅은 배경 밴드
            ws.cell(row=row, column=bc).fill = target_band_fill
        for cc in [1, overall_col] + result_cols:
            ws.cell(row=row, column=cc).alignment = wrap_center
        row += 1

    # 열 너비: No/폴더/base/(결과8·상세50)*n/종합·사유·증빙
    ws.column_dimensions['A'].width = 5
    ws.column_dimensions['B'].width = 22
    for i in range(3, check_start):
        ws.column_dimensions[get_column_letter(i)].width = 15
    i = check_start
    for _ in check_items:
        ws.column_dimensions[get_column_letter(i)].width = 8       # 결과
        ws.column_dimensions[get_column_letter(i + 1)].width = 52   # 상세
        i += 2
    ws.column_dimensions[get_column_letter(i)].width = 10      # 종합결과
    ws.column_dimensions[get_column_letter(i + 1)].width = 38  # 사유
    ws.column_dimensions[get_column_letter(i + 2)].width = 55  # 증빙목록


def generate_workpaper(results, output_path, company_name="", audit_period=""):
    wb = openpyxl.Workbook()
    _build_summary(wb, results, company_name, audit_period)

    # 프로파일별 상세 시트 (등장 순서 유지)
    order = []
    groups = {}
    for r in results:
        pid = r.get('profile') or r.get('type') or 'detail'
        if pid not in groups:
            order.append(pid)
            groups[pid] = []
        groups[pid].append(r)

    for pid in order:
        rows = groups[pid]
        title = f"{rows[0].get('profile_display') or pid} 상세"
        base_cols = BASE_COLS.get(pid, BASE_COLS['default'])
        _build_detail(wb, title, rows, base_cols)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    wb.save(output_path)
    print(f"워크페이퍼 저장: {output_path}")


def main(argv=None):
    _utf8_console()
    parser = argparse.ArgumentParser(
        description='매출 TOD 검증 결과 JSON을 엑셀 워크페이퍼로 변환한다.')
    parser.add_argument('results_json', help='tod_engine.py가 생성한 결과 JSON')
    parser.add_argument('output_xlsx', help='생성할 엑셀 워크페이퍼 경로')
    parser.add_argument('company_name', nargs='?', default='', help='회사명')
    parser.add_argument('audit_period', nargs='?', default='', help='감사대상기간')
    args = parser.parse_args(argv)
    try:
        cpa_storage.guard(args.output_xlsx)
    except cpa_storage.StorageError as exc:
        parser.error(str(exc))

    with open(args.results_json, 'r', encoding='utf-8') as f:
        results = json.load(f)

    generate_workpaper(results, args.output_xlsx, args.company_name, args.audit_period)


if __name__ == '__main__':
    main()
