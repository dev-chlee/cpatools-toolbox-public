#!/usr/bin/env python3
"""부동산등기부등본 검토 워크페이퍼 생성 (5시트 엑셀 + 옵션 1시트)

사용법:
    python generate_workpaper.py <properties_json> <mortgages_json> <output_xlsx> \
        --company "피감사회사명" --period "감사기간" [--company-keywords kw1 kw2]

입력:
    properties_json — parse_registry_pdfs.py가 생성한 부동산 기본정보
    mortgages_json — parse_registry_pdfs.py가 생성한 근저당 상세

출력:
    5시트 구성 엑셀 워크페이퍼 (--verdict-report 지정 시 Sheet6 추가)
      1_근저당상세 / 2_부동산종합표 / 3_요약 / 4_담보금액분석 /
      5_물상보증매트릭스 / [6_LLM판단근거]
"""

import json, os, sys, argparse, math
from copy import copy
from collections import defaultdict
from datetime import date

# 작성일 — --as-of 로 주입 가능(재현성 검증: 같은 입력+같은 as-of → 같은 셀 값). 기본 오늘.
ASOF = date.today().strftime('%Y.%m.%d')

# UTF-8 콘솔 (Windows cp949 콘솔에서 한글·화살표 출력 시 UnicodeEncodeError 방지)
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError as e:
    raise ImportError(
        "openpyxl 가 필요합니다. 먼저 'python scripts/setup_venv.py' 로 설치하세요 "
        "(또는 'pip install pdfplumber openpyxl')."
    ) from e


# ===== 스타일 정의 =====
thin = Side(style='thin')
border = Border(left=thin, right=thin, top=thin, bottom=thin)
hdr_fill = PatternFill('solid', fgColor='2F5496')
hdr_font = Font(name='맑은 고딕', bold=True, color='FFFFFF', size=9)
dfont = Font(name='맑은 고딕', size=9)
bold9 = Font(name='맑은 고딕', bold=True, size=9)
bold10 = Font(name='맑은 고딕', bold=True, size=10)
norm10 = Font(name='맑은 고딕', size=10)
amt_fmt = '#,##0'

# 소유 구분 색상
company_fill = PatternFill('solid', fgColor='D6E4F0')       # 피감사회사 소유 (파란)
company_joint_fill = PatternFill('solid', fgColor='B4C7E7')  # 피감사회사 공동소유 (진파란)
other_fill = PatternFill('solid', fgColor='FFF2CC')           # 제3자 (노란)
unknown_fill = PatternFill('solid', fgColor='E7E6E6')         # 분류 근거 미상 (회색)
sum_fill = PatternFill('solid', fgColor='E2EFDA')             # 요약 (녹색)
group_fill = PatternFill('solid', fgColor='FCE4D6')           # 공동담보 (주황)
total_fill = PatternFill('solid', fgColor='D9E2F3')           # 합계 (하늘)


def classify_ownership(prop, company_keywords):
    """소유 구분 판정 (표시용 라벨·지분·배경색).

    회사귀속 여부 자체는 guarantee_matrix.owner_is_company 가 SSOT — Sheet1 의 '회사소유'
    표시와 Sheet5 매트릭스의 소유축이 갈라지지 않게 한 곳에서만 판정한다.
    """
    owners = prop.get('소유자목록') or []
    is_company = owner_is_company(prop, company_keywords)

    if not owners:
        own_type = '미상'
    elif len(owners) == 1:
        own_type = '단독'
    else:
        own_type = '공동'

    if is_company is None:
        fill = unknown_fill
        label = '미상'
    elif own_type == '공동' and is_company:
        fill = company_joint_fill
        label = '공동'
    elif is_company:
        fill = company_fill
        label = 'Y'
    else:
        fill = other_fill
        label = 'N'

    # 지분
    if own_type == '공동' and owners:
        share = '\n'.join(f"{o['이름']}: {o.get('지분', '미상')}" for o in owners)
    elif is_company and own_type == '단독':
        share = '단독'
    else:
        share = '-'

    return is_company, own_type, label, share, fill


def target_owner_unresolved(mortgage, prop):
    """소유자 자체 미확정과 피감사회사 귀속 미확정을 구별한다."""
    return bool(mortgage.get('대상소유자확인필요') or prop.get('소유자확인필요') or
                not (mortgage.get('소유자') or prop.get('현재소유자')))


# 공동담보 그룹핑(순 담보금액 dedup)은 grouping.py 가 단일 SSOT — 파서 미리보기와 로직 공유.
from grouping import build_joint_groups, group_label as _group_label  # noqa: E402
import cpa_storage  # noqa: E402
# 물상보증 매트릭스(Net 의 소유x채무자 분해)와 회사귀속 판정은 guarantee_matrix.py 가 단일 SSOT.
from guarantee_matrix import (  # noqa: E402
    owner_is_company, mortgage_owner_axis, build_matrix, summarize,
    OWNER_AXIS_ORDER, DEBTOR_AXIS_ORDER, COMPANY, THIRD, MIXED,
)


def create_sheet1(wb, mortgages, properties, company_keywords, company_name, period):
    """Sheet 1: 근저당 상세"""
    ws = wb.active
    ws.title = "1_근저당상세"

    prop_by_uid = {p['고유번호']: p for p in properties}

    ws.merge_cells('A1:Q1')
    ws['A1'] = '부동산등기부등본 근저당 상세 검토표'
    ws['A1'].font = Font(name='맑은 고딕', bold=True, size=12)
    ws.merge_cells('A2:Q2')
    ws['A2'] = f'피감사회사: {company_name} | 감사기간: {period} | 작성일: {ASOF} | 현행 근저당 (을구 표 기반: 설정 − 말소, 요약표 유무 무관)'
    ws['A2'].font = Font(name='맑은 고딕', size=8, color='666666')

    headers = ['No', '고유번호', '유형', '소재지', '소유자', '회사소유', '지분',
               '순위번호', '설정일자', '접수정보', '채권최고액', '근저당권자', '채무자',
               '공동담보목록', '공동담보구분', '공동담보', '비고']
    headers[4:7] = ['담보 대상 소유자', '대상 회사소유', '대상 지분']
    widths = [5, 18, 5, 32, 18, 7, 14, 7, 12, 22, 18, 18, 18, 22, 8, 22, 12]

    for col, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=3, column=col, value=h)
        c.font = hdr_font; c.fill = hdr_fill
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = border
        ws.column_dimensions[get_column_letter(col)].width = w

    # 부동산별 그룹핑
    mort_by_uid = defaultdict(list)
    for m in mortgages:
        mort_by_uid[m['고유번호']].append(m)

    row = 4
    for prop in sorted(properties, key=lambda x: x['No']):
        uid = prop['고유번호']
        morts = mort_by_uid.get(uid, [])
        is_co, own_type, co_label, share, rfill = classify_ownership(prop, company_keywords)
        owner_disp = prop.get('현재소유자', '')

        if not morts:
            vals = [prop['No'], uid, prop.get('유형', '-'), prop.get('소재지', '-'),
                    owner_disp or '-', co_label, share,
                    '-', '-', '-', 0, '-', '-', '-', '-', '-', '근저당 없음']
            for col, v in enumerate(vals, 1):
                c = ws.cell(row=row, column=col, value=v)
                c.font = dfont; c.fill = rfill; c.border = border
                if col == 11: c.number_format = amt_fmt; c.alignment = Alignment(horizontal='right')
                elif col in (1, 3, 6, 8): c.alignment = Alignment(horizontal='center')
            row += 1
        else:
            for m in morts:
                axis = mortgage_owner_axis(m, prop, company_keywords)
                co_label = {COMPANY: 'Y', THIRD: 'N', MIXED: '혼합'}.get(axis, '미상')
                rfill = {COMPANY: company_fill, THIRD: other_fill, MIXED: company_joint_fill}.get(axis, unknown_fill)
                target_unknown = target_owner_unresolved(m, prop)
                owner_disp = m.get('소유자', prop.get('현재소유자', '')) if not target_unknown else ''
                targets = m.get('대상소유자목록') or []
                share = '\n'.join(f"{o['이름']}: {o.get('지분', '미상')}" for o in targets) if targets else '-'
                jt_list = m.get('공동담보목록', '')
                jt_raw = m.get('공동담보', '')
                if jt_list:
                    jt_type = '목록'
                elif jt_raw:
                    jt_type = '접수'
                else:
                    jt_type = '단독'

                vals = [
                    prop['No'], uid,
                    prop.get('유형', '') or '-', prop.get('소재지', '') or '-',
                    owner_disp or '-', co_label, share,
                    int(m['순위번호']) if str(m['순위번호']).isdigit() else str(m['순위번호']),
                    m.get('설정일자', '') or '-',
                    m.get('접수정보', '') or '-',
                    m['채권최고액'],
                    m.get('근저당권자', '') or '-',
                    m.get('채무자', '') or '-',
                    jt_list or '-', jt_type, jt_raw or '-',
                    ('목록연도<설정연도 — 오매핑 의심, 원본 확인' if m.get('공동담보목록_연도의심')
                     else ('담보 대상 소유자 확인 필요' if target_unknown
                           else ('회사 귀속 확인 필요' if axis == '미상'
                                 else ('지분 대상' if m.get('지분대상') else '-')))),
                ]
                for col, v in enumerate(vals, 1):
                    c = ws.cell(row=row, column=col, value=v)
                    c.font = dfont; c.fill = rfill; c.border = border
                    if col == 11: c.number_format = amt_fmt; c.alignment = Alignment(horizontal='right')
                    elif col in (1, 3, 6, 8, 15): c.alignment = Alignment(horizontal='center')
                row += 1

    # 합계
    ws.cell(row=row, column=10, value='합계').font = bold9
    ws.cell(row=row, column=10).border = border
    ws.cell(row=row, column=10).alignment = Alignment(horizontal='center')
    c = ws.cell(row=row, column=11)
    c.value = f'=SUM(K4:K{row - 1})' if row > 4 else 0
    c.font = bold9; c.number_format = amt_fmt; c.border = border
    c.alignment = Alignment(horizontal='right')

    ws.auto_filter.ref = f'A3:Q{row - 1}'
    ws.freeze_panes = 'A4'
    return ws


def create_sheet2(wb, mortgages, properties, company_keywords, company_name, period):
    """Sheet 2: 부동산 종합표"""
    ws = wb.create_sheet("2_부동산종합표")

    mort_by_uid = defaultdict(list)
    for m in mortgages:
        mort_by_uid[m['고유번호']].append(m)

    ws.merge_cells('A1:R1')
    ws['A1'] = '부동산등기부등본 검토 종합표'
    ws['A1'].font = Font(name='맑은 고딕', bold=True, size=12)
    ws.merge_cells('A2:R2')
    ws['A2'] = f'피감사회사: {company_name} | 감사기간: {period} | 작성일: {ASOF}'
    ws['A2'].font = Font(name='맑은 고딕', size=8, color='666666')

    headers = ['No', '고유번호', '유형', '소재지', '소유자', '회사소유', '지분',
               '현행근저당(건)', '현행채권최고액합계', '근저당권자', '채무자', '공동담보',
               '현행가압류(건)', '가압류상세', '비고', '원본 열람/발급일']
    widths = [5, 18, 9, 40, 24, 9, 28, 7, 18, 20, 18, 20, 7, 32, 24, 16]

    for col, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=3, column=col, value=h)
        c.font = hdr_font; c.fill = hdr_fill
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = border
        ws.column_dimensions[get_column_letter(col)].width = w

    row = 4
    for prop in sorted(properties, key=lambda x: x['No']):
        uid = prop['고유번호']
        morts = mort_by_uid.get(uid, [])
        is_co, own_type, co_label, share, rfill = classify_ownership(prop, company_keywords)

        cred_list = ', '.join(sorted(set(m.get('근저당권자', '') for m in morts if m.get('근저당권자'))))
        debt_list = ', '.join(sorted(set(m.get('채무자', '') for m in morts if m.get('채무자'))))
        jt_list = ', '.join(sorted(set(m.get('공동담보목록', '') for m in morts if m.get('공동담보목록'))))
        if any((m.get('공동담보') or m.get('공동담보여부')) and not m.get('공동담보목록') for m in morts):
            jt_list = ', '.join(filter(None, [jt_list, '직접명시 공동담보']))

        # 기타 부담(전세권·지상권·경매개시·신탁·가등기·환매) 키워드 감지 — 말소 여부 미판별,
        # 자동화 범위 밖이므로 감지 시 반드시 원본 대조.
        enc = prop.get('기타부담_감지') or []
        enc_note = ('기타부담 감지: ' + ', '.join(enc) + ' — 원본 확인 필요') if enc else '-'

        vals = [
            prop['No'], uid, prop.get('유형', ''), prop.get('소재지', ''),
            prop.get('현재소유자', '') or '-', co_label, share,
            len(morts), sum(m['채권최고액'] for m in morts),
            cred_list or '-', debt_list or '-', jt_list or '-',
            prop.get('현행_가압류_건수', 0), prop.get('갑구_특이사항', '-'), enc_note,
            prop.get('원본열람일') or '확인 필요',
        ]

        for col, v in enumerate(vals, 1):
            c = ws.cell(row=row, column=col, value=v)
            c.font = dfont; c.fill = rfill; c.border = border
            if col == 9: c.number_format = amt_fmt; c.alignment = Alignment(horizontal='right')
            elif col in (1, 3, 6, 8, 13): c.alignment = Alignment(horizontal='center')
        row += 1

    # 합계
    ws.cell(row=row, column=7, value='합계').font = bold9
    ws.cell(row=row, column=7).border = border
    c = ws.cell(row=row, column=9)
    c.value = f'=SUM(I4:I{row - 1})' if row > 4 else 0
    c.font = bold9; c.number_format = amt_fmt; c.border = border

    ws.auto_filter.ref = f'A3:P{row - 1}'
    ws.freeze_panes = 'A4'
    return ws


def create_sheet3(wb, mortgages, properties, jt_groups, company_name, llm_pending=0,
                  matrix=None, company_keywords=None):
    """Sheet 3: 요약"""
    ws = wb.create_sheet("3_요약")
    ws.merge_cells('A1:C1')
    ws['A1'] = '부동산등기부등본 검토 요약'
    ws['A1'].font = Font(name='맑은 고딕', bold=True, size=14)

    total_gross = sum(m['채권최고액'] for m in mortgages)
    total_net = sum(g['amt'] for g in jt_groups.values())

    ownership = [owner_is_company(p, company_keywords) for p in properties]
    co_count = sum(flag is True for flag in ownership)
    third_count = sum(flag is False for flag in ownership)
    unknown_count = sum(flag is None for flag in ownership)
    seizure_count = sum(1 for p in properties if p.get('현행_가압류_건수', 0) > 0)

    r = 3
    prop_by_uid = {p['고유번호']: p for p in properties}
    unresolved_targets = sum(target_owner_unresolved(m, prop_by_uid.get(m.get('고유번호'), {}))
                             for m in mortgages)
    if unresolved_targets:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        c = ws.cell(row=r, column=1, value=f'⚠ 담보 대상 소유자 미상 {unresolved_targets}건 — Sheet1·5 원본 대조 필요')
        c.font = Font(name='맑은 고딕', bold=True, size=11, color='C00000')
        c.fill = unknown_fill
        r += 2
    if unknown_count:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        c = ws.cell(row=r, column=1,
                    value=f'⚠ 소유자 분류 미상 {unknown_count}건 — 원본·회사 키워드 확인 (Sheet1·2·5)')
        c.font = Font(name='맑은 고딕', bold=True, size=11, color='C00000')
        c.fill = unknown_fill
        r += 2
    # LLM 판정 강제 게이트: 미채택·검토필수 건이 있으면 요약 최상단에 경고(누락 방지)
    if llm_pending:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        c = ws.cell(row=r, column=1, value=f'⚠ LLM 판정 검토 필요 {llm_pending}건 — Sheet6 확인')
        c.font = Font(name='맑은 고딕', bold=True, size=11, color='C00000')
        ws.cell(row=r, column=1).fill = group_fill
        r += 2
    items = [
        ('총 부동산 건수', len(properties)),
        (f'  {company_name} 소유', co_count),
        ('  제3자 소유', third_count),
        ('  소유자 분류 미상', unknown_count),
        ('', ''),
        ('현행 근저당 건수', len(mortgages)),
        ('현행 채권최고액 합계 (Gross)', total_gross),
        ('', ''),
        ('순 담보금액 (공동담보 중복 제거)', ''),
        ('  총 채권최고액 (Gross)', total_gross),
        ('  공동담보 중복금액', total_gross - total_net),
        ('  순 담보금액 (Net)', total_net),
        ('  공동담보 그룹 수', len(jt_groups)),
        ('', ''),
        ('물상보증 구분 (Net 기준 · 상세는 Sheet5)', ''),
        ('  물상보증 제공 (회사자산 ← 제3자채무)', _mx(matrix, COMPANY, THIRD)),
        ('  물상보증 수령 (제3자자산 ← 회사채무)', _mx(matrix, THIRD, COMPANY)),
        ('  자기담보 (회사자산 ← 회사채무)', _mx(matrix, COMPANY, COMPANY)),
        ('  혼합 — 제3자채무 (제공 가능성)', _mx(matrix, MIXED, THIRD)),
        ('  혼합 — 회사채무 (수령 포함)', _mx(matrix, MIXED, COMPANY)),
        ('  회사 무관', _mx(matrix, THIRD, THIRD)),
        ('  구분 불가 (미상 — 원본 대조)', _mx_rest(matrix)),
        ('', ''),
        ('현행 가압류/압류 있는 부동산', f'{seizure_count}건' if seizure_count > 0 else '없음'),
        ('', ''),
        ('※ 유의', '채권최고액은 통상 실채무의 120~130% 설정액이며 실채무 잔액이 아님 — '
                    '금융조회서·차입금원장과 별도 대사 필요'),
        ('※ 범위', '본 표는 근저당·(가)압류만 자동 집계 — 전세권·지상권·경매개시·신탁·가등기 등 '
                    '기타 부담은 Sheet2 비고의 감지 플래그와 원본으로 확인'),
    ]

    for label, val in items:
        ws.cell(row=r, column=1, value=label).font = Font(
            name='맑은 고딕', size=10,
            bold=bool(label and not label.startswith(' '))
        )
        c = ws.cell(row=r, column=2, value=val)
        c.font = norm10
        if isinstance(val, (int, float)) and val > 1000:
            c.number_format = '#,##0'
        r += 1

    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 55

    # 근저당권자별 집계
    r += 1
    ws.cell(row=r, column=1, value='근저당권자별 집계').font = Font(name='맑은 고딕', bold=True, size=11)
    r += 1
    for h, ci in [('근저당권자', 1), ('건수', 2), ('채권최고액합계', 3)]:
        ws.cell(row=r, column=ci, value=h).font = bold9
    ws.column_dimensions['C'].width = 20
    r += 1

    cred_stats = defaultdict(lambda: {'건수': 0, '합계': 0})
    for m in mortgages:
        key = m.get('근저당권자', '') or '(미파싱)'
        cred_stats[key]['건수'] += 1
        cred_stats[key]['합계'] += m['채권최고액']
    for cred, s in sorted(cred_stats.items(), key=lambda x: -x[1]['합계']):
        ws.cell(row=r, column=1, value=cred).font = dfont
        ws.cell(row=r, column=2, value=s['건수']).font = dfont
        c = ws.cell(row=r, column=3, value=s['합계'])
        c.font = dfont; c.number_format = '#,##0'
        r += 1

    return ws


def create_sheet4(wb, mortgages, properties, jt_groups, company_name, period):
    """Sheet 4: 담보금액 분석"""
    ws = wb.create_sheet("4_담보금액분석")

    total_gross = sum(m['채권최고액'] for m in mortgages)
    total_net = sum(g['amt'] for g in jt_groups.values())

    ws.merge_cells('A1:L1')
    ws['A1'] = '공동담보 고려 순 담보금액 분석'
    ws['A1'].font = Font(name='맑은 고딕', bold=True, size=12)
    ws.merge_cells('A2:L2')
    ws['A2'] = f'피감사회사: {company_name} | 감사기간: {period} | 산출방식: 공동담보목록 번호 우선, 미파싱시 접수번호 기준'
    ws['A2'].font = Font(name='맑은 고딕', size=8, color='666666')

    # Section A: 요약
    r = 4
    for label, val in [('총 채권최고액 (Gross)', total_gross),
                        ('공동담보 중복금액', total_gross - total_net),
                        ('순 담보금액 (Net)', total_net)]:
        c1 = ws.cell(row=r, column=1, value=label)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        c1.font = bold10; c1.border = border; c1.fill = sum_fill
        c2 = ws.cell(row=r, column=4, value=val)
        ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=6)
        c2.font = bold10 if '순' in label else norm10
        c2.number_format = '#,##0'; c2.border = border; c2.fill = sum_fill
        c2.alignment = Alignment(horizontal='right')
        r += 1

    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 22

    # Section B: 그룹별 상세
    r += 1
    ws.merge_cells(f'A{r}:L{r}')
    ws.cell(row=r, column=1, value='공동담보 그룹별 순 담보금액 산출 내역').font = Font(name='맑은 고딕', bold=True, size=11)
    r += 1

    h4 = ['No', '공동담보 그룹', '식별방식', '근저당권자', '채무자',
          '채권최고액(건당)', '대상물건수', '대상물건(No)', 'Gross합계', '순담보금액', '중복제거액', '비고']
    w4 = [4, 28, 8, 18, 18, 18, 8, 25, 18, 18, 18, 15]

    for col, (h, w) in enumerate(zip(h4, w4), 1):
        c = ws.cell(row=r, column=col, value=h)
        c.font = hdr_font; c.fill = hdr_fill
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = border
        ws.column_dimensions[get_column_letter(col)].width = w

    hdr_row = r
    r += 1
    data_start = r

    group_no = 0
    for key, g in sorted(jt_groups.items(), key=lambda x: -x[1]['amt']):
        group_no += 1
        items = g['items']
        creds = ', '.join(sorted(set(m.get('근저당권자', '') for m in items if m.get('근저당권자'))))
        debts = ', '.join(sorted(set(m.get('채무자', '') for m in items if m.get('채무자'))))
        nos = sorted(set(m['No'] for m in items))
        nos_str = ', '.join(str(n) for n in nos)
        gross = sum(m['채권최고액'] for m in items)
        net = g['amt']
        dedup = gross - net

        row_fill = group_fill if len(items) > 1 else PatternFill('solid', fgColor='FFFFFF')
        remark = (f'{len(items)}건 공동담보 → 1건 인정' if len(items) > 1 else
                  ('공동담보 — 입력 물건 1건, 다른 담보물건 확인 필요'
                   if any(m.get('공동담보여부') or m.get('공동담보') or m.get('공동담보목록') for m in items)
                   else '단독담보'))

        vals = [group_no, _group_label(key), g['key_type'], creds, debts,
                net, len(items), nos_str, gross, net, dedup, remark]

        for col, v in enumerate(vals, 1):
            c = ws.cell(row=r, column=col, value=v)
            c.font = dfont; c.fill = row_fill; c.border = border
            if col in (6, 9, 10, 11):
                c.number_format = '#,##0'; c.alignment = Alignment(horizontal='right')
            elif col in (1, 3, 7):
                c.alignment = Alignment(horizontal='center')
        r += 1

    # 합계
    ws.cell(row=r, column=2, value='합계').font = bold9
    ws.cell(row=r, column=2).border = border; ws.cell(row=r, column=2).fill = total_fill
    ws.cell(row=r, column=2).alignment = Alignment(horizontal='center')
    ws.cell(row=r, column=7, value=len(mortgages)).font = bold9
    ws.cell(row=r, column=7).border = border; ws.cell(row=r, column=7).fill = total_fill
    ws.cell(row=r, column=7).alignment = Alignment(horizontal='center')

    for ci, cl in [(9, 'I'), (10, 'J'), (11, 'K')]:
        c = ws.cell(row=r, column=ci)
        c.value = f'=SUM({cl}{data_start}:{cl}{r - 1})' if r > data_start else 0
        c.font = bold9; c.number_format = '#,##0'; c.border = border
        c.fill = total_fill; c.alignment = Alignment(horizontal='right')

    for ci in [1, 3, 4, 5, 6, 8, 12]:
        ws.cell(row=r, column=ci).border = border
        ws.cell(row=r, column=ci).fill = total_fill

    r += 2
    # Section C: 공동담보 그룹 상세 전개
    ws.merge_cells(f'A{r}:L{r}')
    ws.cell(row=r, column=1, value='공동담보 그룹별 대상 물건 상세').font = Font(name='맑은 고딕', bold=True, size=11)
    r += 1

    h4b = ['그룹No', '공동담보 그룹', '물건No', '고유번호', '유형', '소재지',
           '순위번호', '설정일자', '접수정보', '채권최고액', '근저당권자', '채무자']
    for col, h in enumerate(h4b, 1):
        c = ws.cell(row=r, column=col, value=h)
        c.font = hdr_font; c.fill = hdr_fill
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = border
    r += 1

    group_no = 0
    for key, g in sorted(jt_groups.items(), key=lambda x: -x[1]['amt']):
        group_no += 1
        if len(g['items']) < 2:
            continue
        for m in g['items']:
            vals = [group_no, _group_label(key), m['No'], m['고유번호'],
                    m.get('유형', ''), m.get('소재지', ''),
                    int(m['순위번호']) if str(m['순위번호']).isdigit() else str(m['순위번호']), m.get('설정일자', '-'),
                    m.get('접수정보', '-'), m['채권최고액'],
                    m.get('근저당권자', '-'), m.get('채무자', '-')]
            for col, v in enumerate(vals, 1):
                c = ws.cell(row=r, column=col, value=v)
                c.font = dfont; c.fill = group_fill; c.border = border
                if col == 10:
                    c.number_format = '#,##0'; c.alignment = Alignment(horizontal='right')
                elif col in (1, 3, 5, 7):
                    c.alignment = Alignment(horizontal='center')
            r += 1

    ws.auto_filter.ref = f'A{hdr_row}:L{hdr_row + group_no}'
    ws.freeze_panes = f'A{hdr_row + 1}'
    return ws


def _mx(matrix, owner_axis, debtor_axis):
    """매트릭스 셀 금액 (없으면 0) — Sheet3 요약용."""
    if not matrix:
        return 0
    cell = matrix['셀'].get((owner_axis, debtor_axis))
    return cell['금액'] if cell else 0


def _mx_rest(matrix):
    """4분면에 들어가지 않은(혼합·미상) 셀 금액 합계."""
    if not matrix:
        return 0
    named = {(COMPANY, COMPANY), (COMPANY, THIRD), (THIRD, COMPANY), (THIRD, THIRD),
             (MIXED, COMPANY), (MIXED, THIRD)}
    return sum(c['금액'] for axes, c in matrix['셀'].items() if axes not in named)


def create_sheet5(wb, matrix, company_name, period):
    """Sheet 5: 물상보증 매트릭스 — Net 을 소유(담보제공자) x 채무자로 분해.

    단일 Net 숫자는 '회사가 타인 채무를 위해 제공한 담보'(우발부채)와 '타인이 회사 채무를 위해
    제공한 담보'를 구분하지 못한다. 이 시트가 그 분해를 조서에 남긴다.
    금액 안분은 하지 않는다 — 그룹이 분면에 걸치면 '혼합'으로 표시하고 원본 대조로 넘긴다.
    """
    ws = wb.create_sheet("5_물상보증매트릭스")

    ws.merge_cells('A1:K1')
    ws['A1'] = '물상보증 매트릭스 — 순 담보금액(Net)의 소유 x 채무자 분해'
    ws['A1'].font = Font(name='맑은 고딕', bold=True, size=12)
    ws.merge_cells('A2:K2')
    ws['A2'] = (f'피감사회사: {company_name} | 감사기간: {period} | 작성일: {ASOF} | '
                f'배정단위: 공동담보 그룹(금액 안분 없음) | 셀 합계 = Net')
    ws['A2'].font = Font(name='맑은 고딕', size=8, color='666666')

    for col, w in enumerate([26, 18, 18, 18, 18, 18, 7, 9, 8, 9, 9, 22, 26, 26, 26], 1):
        ws.column_dimensions[get_column_letter(col)].width = w

    # Section A: 매트릭스
    r = 4
    ws.cell(row=r, column=1, value='A. 매트릭스 (금액 = 순 담보금액 Net, 원)').font = Font(
        name='맑은 고딕', bold=True, size=11)
    r += 1

    hdr = ['소유 \\ 채무자'] + list(DEBTOR_AXIS_ORDER) + ['합계']
    for col, h in enumerate(hdr, 1):
        c = ws.cell(row=r, column=col, value=h)
        c.font = hdr_font; c.fill = hdr_fill; c.border = border
        c.alignment = Alignment(horizontal='center', vertical='center')
    r += 1
    mx_start = r

    for oax in OWNER_AXIS_ORDER:
        c = ws.cell(row=r, column=1, value=oax)
        c.font = bold9; c.fill = sum_fill; c.border = border
        c.alignment = Alignment(horizontal='center')
        for ci, dax in enumerate(DEBTOR_AXIS_ORDER, 2):
            cell = matrix['셀'].get((oax, dax))
            amt = cell['금액'] if cell else 0
            cc = ws.cell(row=r, column=ci, value=amt)
            cc.font = dfont; cc.border = border; cc.number_format = amt_fmt
            cc.alignment = Alignment(horizontal='right')
            # 물상보증 제공(회사자산 <- 제3자채무)은 우발부채 — 금액이 있으면 눈에 띄게.
            if (oax, dax) in ((COMPANY, THIRD), (MIXED, THIRD)) and amt:
                cc.fill = group_fill
                cc.font = Font(name='맑은 고딕', bold=True, size=9, color='C00000')
            elif (oax, dax) == (THIRD, COMPANY) and amt:
                cc.fill = other_fill
            elif amt and oax in (COMPANY, THIRD) and dax in (COMPANY, THIRD):
                cc.fill = company_fill
        tot = ws.cell(row=r, column=len(hdr))
        tot.value = f'=SUM(B{r}:{get_column_letter(len(hdr) - 1)}{r})'
        tot.font = bold9; tot.border = border; tot.number_format = amt_fmt
        tot.fill = total_fill; tot.alignment = Alignment(horizontal='right')
        r += 1

    c = ws.cell(row=r, column=1, value='합계')
    c.font = bold9; c.fill = total_fill; c.border = border
    c.alignment = Alignment(horizontal='center')
    for ci in range(2, len(hdr) + 1):
        cl = get_column_letter(ci)
        cc = ws.cell(row=r, column=ci, value=f'=SUM({cl}{mx_start}:{cl}{r - 1})')
        cc.font = bold9; cc.border = border; cc.number_format = amt_fmt
        cc.fill = total_fill; cc.alignment = Alignment(horizontal='right')
    r += 1

    # 검증 라인 — 셀 합계와 Net 이 어긋나면 배정 로직이 깨진 것이다(조서에 남긴다).
    v = matrix['검증']
    ws.cell(row=r, column=1, value='검증: 매트릭스 합계 = Net').font = bold9
    cc = ws.cell(row=r, column=2, value=v['Net'])
    cc.font = bold9; cc.number_format = amt_fmt; cc.alignment = Alignment(horizontal='right')
    cc = ws.cell(row=r, column=3,
                 value=('일치' if v['일치'] else f"불일치 (셀합계 {v['셀합계']:,})"))
    cc.font = Font(name='맑은 고딕', bold=True, size=9,
                   color=('006100' if v['일치'] else 'C00000'))
    r += 2

    # Section B: 해석
    ws.cell(row=r, column=1, value='B. 구분별 해석 및 감사 조치').font = Font(
        name='맑은 고딕', bold=True, size=11)
    r += 1
    for col, h in enumerate(['구분', '순 담보금액', '그룹수', '물건수', '근저당건수',
                             '감사 조치'], 1):
        c = ws.cell(row=r, column=col, value=h)
        c.font = hdr_font; c.fill = hdr_fill; c.border = border
        c.alignment = Alignment(horizontal='center', vertical='center')
    r += 1
    for s in summarize(matrix):
        emph = s['구분'] in ('물상보증 제공', '혼합 — 제3자채무') and s['금액'] > 0
        vals = [s['구분'], s['금액'], s['그룹수'], s['물건수'], s['근저당건수'], s['조치']]
        for col, val in enumerate(vals, 1):
            c = ws.cell(row=r, column=col, value=val)
            c.font = bold9 if emph else dfont
            c.border = border
            if emph:
                c.fill = group_fill
            if col == 2:
                c.number_format = amt_fmt; c.alignment = Alignment(horizontal='right')
            elif col in (3, 4, 5):
                c.alignment = Alignment(horizontal='center')
            elif col == 6:
                c.alignment = Alignment(vertical='top', wrap_text=True)
        r += 1
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
    ws.cell(row=r, column=1,
            value='※ 채권최고액은 실채무가 아니다 — 금융조회서·차입금원장과 대사한 뒤 주석 금액을 '
                  '확정한다. 그룹이 분면에 걸친 건(혼합·미상)은 금액을 안분하지 않았으므로 '
                  '원본으로 직접 구분한다.').font = Font(name='맑은 고딕', size=8, color='666666')
    r += 2

    # Section C: 그룹별 상세
    ws.cell(row=r, column=1, value='C. 공동담보 그룹별 판정 내역').font = Font(
        name='맑은 고딕', bold=True, size=11)
    r += 1
    hc = ['No', '공동담보 그룹', '구분', '소유축', '채무자축', '순 담보금액',
          '물건수', '근저당건수', '회사물건', '제3자물건', '미상물건', '물건No', '소유자', '채무자',
          '근저당권자', '혼합물건']
    for col, h in enumerate(hc, 1):
        c = ws.cell(row=r, column=col, value=h)
        c.font = hdr_font; c.fill = hdr_fill; c.border = border
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    hdr_row = r
    r += 1

    for i, rec in enumerate(matrix['그룹'], 1):
        emph = rec['구분'] in ('물상보증 제공', '혼합 — 제3자채무')
        vals = [i, _group_label(rec['그룹키']), rec['구분'], rec['소유축'], rec['채무자축'],
                rec['금액'], rec['물건수'], rec['근저당건수'],
                rec['회사물건수'], rec['제3자물건수'], rec['미상물건수'],
                ', '.join(str(n) for n in rec['물건No']) or '-',
                ', '.join(rec['소유자']) or '-',
                ', '.join(rec['채무자']) or '-',
                ', '.join(rec['근저당권자']) or '-', rec['혼합물건수']]
        for col, val in enumerate(vals, 1):
            c = ws.cell(row=r, column=col, value=val)
            c.font = bold9 if emph else dfont
            c.border = border
            if emph:
                c.fill = group_fill
            elif rec['구분'] == '구분 불가':
                c.fill = unknown_fill
            if col == 6:
                c.number_format = amt_fmt; c.alignment = Alignment(horizontal='right')
            elif col in (1, 3, 4, 5, 7, 8, 9, 10, 11):
                c.alignment = Alignment(horizontal='center')
            else:
                c.alignment = Alignment(vertical='top', wrap_text=(col in (13, 14, 15)))
        r += 1

    ws.auto_filter.ref = f'A{hdr_row}:P{r - 1}'
    ws.column_dimensions['P'].width = 12
    ws.freeze_panes = f'A{hdr_row + 1}'
    return ws


def fit_readable_rows(wb):
    """명시적 줄바꿈과 한글 폭을 반영한다. 병합 제목은 병합 전체 폭으로 계산."""
    for ws in wb:
        for row in ws:
            lines = 1
            for cell in row:
                if not isinstance(cell.value, str) or cell.data_type == 'f':
                    continue
                width = ws.column_dimensions[cell.column_letter].width or 13
                merged = next((r for r in ws.merged_cells.ranges if cell.coordinate in r), None)
                if merged:
                    width = sum(ws.column_dimensions[get_column_letter(c)].width or 13
                                for c in range(merged.min_col, merged.max_col + 1))
                count = sum(max(1, math.ceil(sum(2 if ord(ch) > 127 else 1 for ch in part) / max(1, width - 2)))
                            for part in cell.value.split('\n'))
                lines = max(lines, count)
                alignment = copy(cell.alignment)
                alignment.wrap_text = True
                alignment.vertical = 'center'
                cell.alignment = alignment
            ws.row_dimensions[row[0].row].height = min(409, max(22, lines * 14 + 6))


def _needs_review(r):
    """검토필요 판정 — 신형 report 는 '검토필요' bool, 구형은 채택여부 문자열로 폴백."""
    if '검토필요' in r:
        return bool(r['검토필요'])
    return not r.get('채택여부', '').startswith(('채택', '해당없음'))


def create_sheet6(wb, report):
    """Sheet 6: LLM 판단근거 — apply_verdicts.py 의 apply_report 를 감사증적으로 조서에 내장.
    기존값→선택값 diff·후보목록(closed-set 증적)·근거·비고에 검토자/검토일 수기 컬럼까지.
    ※ 원문발췌는 절단본 — 번들·verdict·report JSON 3종을 조서 폴더에 함께 보존한다."""
    ws = wb.create_sheet("6_LLM판단근거")
    ws.merge_cells('A1:O1')
    ws['A1'] = 'LLM 판단근거 (자동수용 + 사후검토 — 검토필요 표시 건은 반드시 원본 대조)'
    ws['A1'].font = Font(name='맑은 고딕', bold=True, size=12)
    meta = report.get('메타', {})
    net_b, net_a = meta.get('Net_적용전'), meta.get('Net_적용후')
    net_str = (f" | Net: 적용전 {net_b:,} → 적용후 {net_a:,}"
               if isinstance(net_b, int) and isinstance(net_a, int) else '')
    ws.merge_cells('A2:O2')
    ws['A2'] = (f"판단주체: {meta.get('판단주체', '-')} | 판단시각: {meta.get('판단시각', '-')} | "
                f"루브릭: {meta.get('루브릭', '-')} | 적용시각: {meta.get('적용시각', '-')} | "
                f"파서버전: {meta.get('파서버전', '-')} | "
                f"번들해시(앞16): {str(meta.get('번들해시', ''))[:16]} (전문은 apply_report.json)"
                f"{net_str}")
    ws['A2'].font = Font(name='맑은 고딕', size=8, color='666666')

    headers = ['판단ID', '필드', 'PDF파일', '고유번호', '순위', '기존값', '선택값', '후보목록',
               '근거', '신뢰도', '채택여부', '비고', '원문발췌', '검토자', '검토일']
    widths = [8, 6, 22, 18, 5, 22, 26, 30, 36, 7, 24, 26, 45, 10, 10]
    for col, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=3, column=col, value=h)
        c.font = hdr_font; c.fill = hdr_fill; c.border = border
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        ws.column_dimensions[get_column_letter(col)].width = w

    row = 4
    for r in report.get('기록', []):
        review = _needs_review(r)
        vals = [r.get('판단ID'), r.get('필드'), r.get('PDF파일') or '-',
                r.get('고유번호'), r.get('순위번호') or '-',
                r.get('기존값') or '-', r.get('선택값') or '-', r.get('후보목록') or '-',
                r.get('근거') or '-', r.get('신뢰도') or '-', r.get('채택여부'),
                r.get('비고') or '-', (r.get('원문발췌') or '-')[:500], '', '']
        for col, v in enumerate(vals, 1):
            c = ws.cell(row=row, column=col, value=v)
            c.font = dfont; c.border = border
            c.alignment = Alignment(vertical='top', wrap_text=(col in (6, 7, 8, 9, 11, 12, 13)))
            if review:
                c.fill = group_fill          # 검토필요 = 주황
        row += 1
    ws.freeze_panes = 'A4'
    return ws


def verify_final_inputs(report, properties, mortgages):
    """--verdict-report 가 주어졌는데 비-final JSON 을 넘긴 실수를 차단한다.
    report 의 '채택' 흔적(LLM공담그룹·LLM판정_소재지·LLM소유자분류)이 입력 JSON 에 실재하는지 대조 —
    불일치면 Sheet6(증적)와 본문 시트(미반영)가 모순되는 조서가 조용히 생성된다."""
    errs = []
    prop_by_uid = {p['고유번호']: p for p in properties}
    llm_groups = {m.get('LLM공담그룹') for m in mortgages if m.get('LLM공담그룹')}
    for r in report.get('기록', []):
        status = r.get('채택여부', '')
        if status.startswith('채택'):
            uid = r.get('고유번호')
            if r.get('필드') == '공담' and f"llm_{r.get('판단ID')}" not in llm_groups:
                errs.append(f"{r.get('판단ID')}(공담 채택)의 LLM공담그룹이 mortgages 에 없음")
            elif r.get('필드') == '소재지' and not prop_by_uid.get(uid, {}).get('LLM판정_소재지'):
                errs.append(f"{r.get('판단ID')}(소재지 채택)의 LLM판정 흔적이 properties 에 없음")
            elif r.get('필드') == '소유자' and not prop_by_uid.get(uid, {}).get('LLM소유자분류'):
                errs.append(f"{r.get('판단ID')}(소유자 채택)의 LLM소유자분류가 properties 에 없음")
    return errs


def main():
    parser = argparse.ArgumentParser(description='부동산등기부등본 워크페이퍼 생성')
    parser.add_argument('properties', help='부동산 기본정보 JSON (LLM 확정 시 *.final.json)')
    parser.add_argument('mortgages', help='근저당 상세 JSON (LLM 확정 시 *.final.json)')
    parser.add_argument('output', help='출력 엑셀 파일 경로')
    parser.add_argument('--company', required=True, help='피감사회사명')
    parser.add_argument('--period', required=True, help='감사기간')
    parser.add_argument('--company-keywords', nargs='+', default=[], help='피감사회사 관련 키워드')
    parser.add_argument('--review-note', default='', help='모든 시트 제목에 표시할 검토 상태 (예: 부분집계·전체 금액 아님)')
    parser.add_argument('--verdict-report', default=None,
                        help='apply_verdicts.py 의 *_apply_report.json — 지정 시 Sheet6(LLM 판단근거) 추가')
    parser.add_argument('--as-of', default=None,
                        help='작성일 주입(YYYY.MM.DD) — 재현성 검증용. 기본: 오늘')
    args = parser.parse_args()
    try:
        cpa_storage.guard(args.output)
    except cpa_storage.StorageError as exc:
        parser.error(str(exc))

    from registry_image_gate import verify_proof
    try:
        image_proof = verify_proof(args.properties, args.mortgages)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'이미지 검토 미완료 — 워크페이퍼 생성 거부: {exc}')
        sys.exit(5)

    global ASOF
    if args.as_of:
        if not __import__('re').match(r'^\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}$', args.as_of):
            print(f"오류: --as-of 형식이 잘못됨({args.as_of!r}) — YYYY.MM.DD")
            sys.exit(1)
        ASOF = args.as_of

    with open(args.properties, 'r', encoding='utf-8') as f:
        properties = json.load(f)
    with open(args.mortgages, 'r', encoding='utf-8') as f:
        mortgages = json.load(f)
    report = None
    if args.verdict_report:
        with open(args.verdict_report, 'r', encoding='utf-8') as f:
            report = json.load(f)
        # 비-final 입력 차단 — Sheet6 는 '채택'인데 본문 Net 은 미반영인 자기모순 조서 방지
        fin_errs = verify_final_inputs(report, properties, mortgages)
        if fin_errs:
            print('오류: --verdict-report 가 지정됐으나 입력 JSON 에 판정 반영 흔적이 없습니다.')
            print('      (*.final.json 이 아니라 원본 JSON 을 넘긴 것으로 보임)')
            for e in fin_errs[:5]:
                print(f'  ✗ {e}')
            sys.exit(1)

    print(f"부동산: {len(properties)}건, 근저당: {len(mortgages)}건")

    jt_groups = build_joint_groups(mortgages)
    total_gross = sum(m['채권최고액'] for m in mortgages)
    total_net = sum(g['amt'] for g in jt_groups.values())

    llm_pending = 0
    if report:
        llm_pending = sum(1 for r in report.get('기록', []) if _needs_review(r))

    # 물상보증 매트릭스 — Net 을 소유x채무자로 분해(그룹 단위 배정, 금액 안분 없음)
    matrix = build_matrix(jt_groups, properties, args.company_keywords)
    if not matrix['검증']['일치']:
        print(f"오류: 매트릭스 셀 합계({matrix['검증']['셀합계']:,})가 "
              f"Net({matrix['검증']['Net']:,})과 불일치 — 그룹 배정 로직 결함")
        sys.exit(1)

    wb = Workbook()
    create_sheet1(wb, mortgages, properties, args.company_keywords, args.company, args.period)
    create_sheet2(wb, mortgages, properties, args.company_keywords, args.company, args.period)
    create_sheet3(wb, mortgages, properties, jt_groups, args.company, llm_pending=llm_pending,
                  matrix=matrix, company_keywords=args.company_keywords)
    create_sheet4(wb, mortgages, properties, jt_groups, args.company, args.period)
    create_sheet5(wb, matrix, args.company, args.period)
    if report:
        create_sheet6(wb, report)

    ws = wb.create_sheet('이미지검토근거')
    ws.append(['원본 PDF', '원본 페이지', '처리 경로', '이미지 판독자', '분석 입력', '입력 SHA256', '문서 종류', '판정 사유'])
    for source in image_proof['sources']:
        ws.append([source['file'], ', '.join(map(str, source['pages'])),
                   '취소선 상세 판독 반영' if source['route'] == 'detail' else '전체 페이지 취소선 없음 확인',
                     source['reviewer'], source['path'], source['input_sha256']])
    for page in image_proof.get('document_classifications', []):
        ws.append([page['file'], str(page['page']),
                   '비등기 문서 제외' if page['kind'] == 'non_registry' else '등기부 문서 확인',
                   page['reviewer'], '', '', page['document_type'], page['reason']])
    for row in ws:
        for cell in row:
            cell.data_type = 's'
    for column, width in [('A', 45), ('B', 22), ('C', 36), ('D', 28), ('E', 60), ('F', 35), ('G', 28), ('H', 60)]:
        ws.column_dimensions[column].width = width
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    if args.review_note:
        for ws in wb:
            ws['A1'] = f'[{args.review_note}] {ws["A1"].value or ws.title}'
    fit_readable_rows(wb)
    wb.save(args.output)
    print(f"\n워크페이퍼 저장: {args.output}")
    print(f"  Sheet1 근저당상세")
    print(f"  Sheet2 부동산종합표")
    print(f"  Sheet3 요약")
    print(f"  Sheet4 담보금액분석")
    print(f"  Sheet5 물상보증매트릭스")
    if report:
        print(f"  Sheet6 LLM판단근거 ({len(report.get('기록', []))}건, 검토필요 {llm_pending}건)")
    print(f"\n총 채권최고액 (Gross): {total_gross:>20,}원")
    print(f"공동담보 중복:         {total_gross - total_net:>20,}원")
    print(f"순 담보금액 (Net):     {total_net:>20,}원")
    print(f"공동담보 그룹:         {len(jt_groups)}개")
    print(f"\n물상보증 분해 (Net 기준 · 합계 = Net)")
    line_total = 0
    for s in summarize(matrix):
        line_total += s['금액']
        pad = ' ' * max(0, 16 - sum(2 if ord(ch) > 0x2500 else 1 for ch in s['구분']))
        print(f"  {s['구분']}{pad} {s['금액']:>18,}원  "
              f"(그룹 {s['그룹수']}, 물건 {s['물건수']}, 근저당 {s['근저당건수']})")
    print(f"  합계{' ' * 12} {line_total:>18,}원")
    prov = _mx(matrix, COMPANY, THIRD) + _mx(matrix, MIXED, THIRD)
    if prov:
        print("  ⚠ 회사 자산이 타인 채무의 담보에 포함 — 우발부채(K-IFRS 1037)·"
              "특수관계자 담보 주석(1024) 검토 필요")


if __name__ == '__main__':
    main()
