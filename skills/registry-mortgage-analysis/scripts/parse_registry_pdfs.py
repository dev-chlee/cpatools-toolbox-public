#!/usr/bin/env python3
"""부동산등기부등본 PDF 일괄 파싱 — 부동산 기본정보 + 현행 근저당 + 공동담보목록 추출

사용법:
    python parse_registry_pdfs.py <PDF_폴더> <출력_JSON> [--company <피감사회사명>]

출력:
    두 개의 JSON 파일:
    1. <출력_JSON>_properties.json — 부동산 기본정보 (고유번호, 유형, 소재지, 소유자 등)
    2. <출력_JSON>_mortgages.json — 현행 근저당 상세 (순위번호, 채권최고액, 공동담보목록 등)
"""

import json, re, os, sys, argparse
from collections import defaultdict

try:
    import pdfplumber
except ImportError:
    os.system('pip install pdfplumber --break-system-packages -q')
    import pdfplumber


def extract_full_text(pdf_path):
    """PDF 전체 텍스트 추출"""
    text = ''
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + '\n'
    return text


def find_summary_section(text):
    """하단 '주요 등기사항 요약' 섹션 분리"""
    markers = ['주요 등기사항 요약', '주 요 등 기 사 항 요 약', '주요등기사항요약']
    for m in markers:
        idx = text.find(m)
        if idx != -1:
            return text[idx:]
    return ''


def parse_unique_id(text):
    """고유번호 추출"""
    m = re.search(r'고유번호\s*(\d{4}-\d{4}-\d{6})', text)
    return m.group(1) if m else ''


def parse_property_type(text):
    """부동산 유형 판별 (토지/건물)"""
    summary = find_summary_section(text)
    if '[토지]' in summary or '[ 토지 ]' in summary:
        return '토지'
    elif '[건물]' in summary or '[ 건물 ]' in summary:
        return '건물'
    # 본문 기준
    if '표 제 부' in text:
        after = text[text.find('표 제 부'):]
        if '토 지' in after[:200] or '토지' in after[:200]:
            return '토지'
        elif '건 물' in after[:200] or '건물' in after[:200]:
            return '건물'
    return ''


def parse_location(text):
    """소재지 추출 (하단 요약 기준)"""
    summary = find_summary_section(text)
    m = re.search(r'\[(토지|건물)\]\s*(.+?)(?:\n|$)', summary)
    if m:
        return m.group(2).strip()
    return ''


def parse_owner_from_summary(text, company_keywords=None):
    """하단 요약 갑구에서 소유자 정보 추출"""
    summary = find_summary_section(text)
    owners = []

    # 소유지분현황 섹션 찾기
    own_idx = summary.find('소유지분현황')
    if own_idx == -1:
        own_idx = summary.find('소 유 지 분 현 황')
    if own_idx == -1:
        return [], False

    own_section = summary[own_idx:]
    # 갑구 시작 전까지
    gap_idx = own_section.find('소유지분을 제외한')
    if gap_idx == -1:
        gap_idx = own_section.find('소유지분을제외한')
    if gap_idx != -1:
        own_section = own_section[:gap_idx]

    # 소유자 행 파싱 (이름 + 등록번호 + 지분 + 주소 + 순위번호)
    lines = own_section.split('\n')
    for line in lines:
        # 단독소유
        if '단독소유' in line:
            parts = line.split()
            if parts:
                name = parts[0]
                owners.append({'이름': name, '지분': '단독소유', '등록번호': ''})
        # 지분 패턴
        share_match = re.search(r'(\d+분의\d+)', line)
        if share_match and not '단독소유' in line:
            parts = line.split()
            if parts:
                name = parts[0]
                owners.append({'이름': name, '지분': share_match.group(1), '등록번호': ''})

    # 피감사회사 관련 여부 판정
    is_company_owned = False
    if company_keywords and owners:
        for o in owners:
            for kw in company_keywords:
                if kw in o['이름']:
                    o['ON관련'] = True
                    is_company_owned = True

    return owners, is_company_owned


def parse_garnishment_from_summary(text):
    """하단 요약 갑구에서 가압류/압류 현존 여부 확인"""
    summary = find_summary_section(text)

    # "소유지분을 제외한 소유권에 관한 사항 (갑구)" 섹션
    gap_patterns = [
        r'소유지분을\s*제외한.*?갑\s*구\s*\)',
        r'2\.\s*소유지분을\s*제외한',
    ]
    gap_start = -1
    for pat in gap_patterns:
        m = re.search(pat, summary)
        if m:
            gap_start = m.end()
            break

    if gap_start == -1:
        return 0, '확인불가'

    # 을구 시작 전까지
    eul_patterns = [r'을\s*구\s*\)', r'3\.\s*\(근\)저당권']
    gap_end = len(summary)
    for pat in eul_patterns:
        m = re.search(pat, summary[gap_start:])
        if m:
            gap_end = gap_start + m.start()
            break

    gap_text = summary[gap_start:gap_end].strip()

    if '기록사항 없음' in gap_text or '기록사항없음' in gap_text:
        return 0, '기록사항 없음'

    # 가압류 건수 파악
    seizure_count = len(re.findall(r'가압류|압류', gap_text))
    return seizure_count, gap_text


def parse_current_mortgages_from_summary(text):
    """하단 요약 을구에서 현행 근저당 목록 추출"""
    summary = find_summary_section(text)
    mortgages = []

    # 을구 섹션 찾기
    eul_match = re.search(r'을\s*구\s*\)', summary)
    if not eul_match:
        return mortgages

    eul_text = summary[eul_match.end():]
    # 참고사항 이전까지
    ref_idx = eul_text.find('참 고 사 항')
    if ref_idx == -1:
        ref_idx = eul_text.find('참고사항')
    if ref_idx != -1:
        eul_text = eul_text[:ref_idx]

    if '기록사항 없음' in eul_text or '기록사항없음' in eul_text:
        return mortgages

    # 순위번호 + 근저당권설정 패턴
    lines = eul_text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        rank_match = re.match(r'\s*(\d+)\s+근저당권설정', line)
        if rank_match:
            rank = rank_match.group(1)
            # 이 행과 다음 행들을 합쳐서 파싱
            block = line
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                if re.match(r'\s*\d+\s+근저당권', next_line):
                    break
                block += ' ' + next_line
                j += 1

            mort = parse_mortgage_block(rank, block)
            if mort:
                mortgages.append(mort)
            i = j
        else:
            i += 1

    return mortgages


def parse_mortgage_block(rank, block):
    """근저당 블록에서 상세 정보 추출"""
    mort = {
        '순위번호': rank,
        '설정일자': '',
        '접수정보': '',
        '접수번호': '',
        '채권최고액': 0,
        '근저당권자': '',
        '채무자': '',
        '공동담보목록': '',
        '공동담보': '',
    }

    # 접수정보: YYYY년MM월DD일 제NNNNN호
    receipt_match = re.search(r'(\d{4}년\d{1,2}월\d{1,2}일)\s*제?(\d+)호', block)
    if receipt_match:
        mort['설정일자'] = receipt_match.group(1).replace('년', '.').replace('월', '.').replace('일', '')
        mort['접수번호'] = receipt_match.group(2)
        mort['접수정보'] = f"{receipt_match.group(1)} 제{receipt_match.group(2)}호"

    # 채권최고액
    amt_match = re.search(r'채권최고액\s*금?\s*([\d,]+)\s*원', block)
    if amt_match:
        mort['채권최고액'] = int(amt_match.group(1).replace(',', ''))

    # 근저당권자
    cred_match = re.search(r'근저당권자\s+(\S+)', block)
    if cred_match:
        mort['근저당권자'] = cred_match.group(1)

    return mort


def parse_debtors_from_body(text):
    """본문 을구에서 순위번호별 채무자 추출"""
    result = {}

    # 을구 본문 시작점
    eulgu_start = None
    for pat in [r'【\s*을\s*구\s*】', r'\[\s*을\s*구\s*\]']:
        m = re.search(pat, text)
        if m:
            eulgu_start = m.end()
            break
    if eulgu_start is None:
        return result

    # 요약 시작 전까지
    summary_idx = text.find('주요 등기사항 요약', eulgu_start)
    if summary_idx == -1:
        summary_idx = text.find('주 요 등 기 사 항', eulgu_start)
    eulgu_body = text[eulgu_start:summary_idx] if summary_idx != -1 else text[eulgu_start:]

    # 순위번호별 블록 분리
    blocks = re.split(r'(\d+)\s+근저당권설정', eulgu_body)
    for i in range(1, len(blocks) - 1, 2):
        rank = blocks[i]
        content = blocks[i + 1]
        next_block = re.search(r'\d+\s+근저당권', content)
        if next_block:
            content = content[:next_block.start()]

        debt_match = re.search(r'채\s*무\s*자\s+(\S+)', content)
        if debt_match:
            debtor = debt_match.group(1).strip()
            debtor = re.sub(r'^[열람용\s]+', '', debtor)
            debtor = re.sub(r'[열람용\s]+$', '', debtor)
            # 주소가 붙은 경우 제거 (예: "주식회사ABC OO도...")
            addr_match = re.search(r'\s+(충청|서울|경기|전라|경상|강원|제주|부산|대구|인천|광주|대전|울산|세종)', debtor)
            if addr_match:
                debtor = debtor[:addr_match.start()]
            result[rank] = debtor

    return result


def parse_joint_collateral_from_body(text, current_ranks):
    """본문 을구에서 현행 순위번호별 공동담보목록 번호 추출

    핵심 과제: 말소된 순위번호의 공동담보목록이 현행 순위번호에 잘못 매핑되지 않도록
    순위번호별 텍스트 범위를 정밀하게 격리해야 한다.

    전략:
    1. 을구 본문에서 모든 순위번호 블록(현행+말소)의 위치를 찾는다
    2. 현행 순위번호 블록만 격리하여 그 안에서 공동담보목록을 찾는다
    3. 부기(N-x) 항목은 메인 순위번호에 포함시킨다
    """
    result = {}

    # 공동담보목록이 아예 없으면 스킵
    if not re.search(r'공동담보목록\s*제\s*\d{4}\s*-\s*\d+\s*호', text):
        return result

    # 을구 본문 찾기
    eulgu_start = None
    for pat in [r'【\s*을\s*구\s*】', r'\[\s*을\s*구\s*\]']:
        m = re.search(pat, text)
        if m:
            eulgu_start = m.end()
            break
    if eulgu_start is None:
        return result

    summary_idx = text.find('주요 등기사항 요약', eulgu_start)
    if summary_idx == -1:
        summary_idx = text.find('주 요 등 기 사 항', eulgu_start)
    eulgu_body = text[eulgu_start:summary_idx] if summary_idx != -1 else text[eulgu_start:]

    # 모든 순위번호 위치 (현행+말소 전부)
    all_rank_positions = []
    for m in re.finditer(r'(\d+)\s+근저당권설정', eulgu_body):
        all_rank_positions.append((m.group(1), m.start()))
    # 부기 패턴도 포함 (N-1, N-2 등)
    for m in re.finditer(r'(\d+-\d+)\s+\d+번근저당권', eulgu_body):
        all_rank_positions.append((m.group(1), m.start()))

    all_rank_positions.sort(key=lambda x: x[1])

    if not all_rank_positions:
        return result

    current_rank_set = set(str(r) for r in current_ranks)

    # 각 현행 순위번호의 블록 범위 격리
    for idx, (rank, start) in enumerate(all_rank_positions):
        if rank not in current_rank_set:
            continue

        # 이 순위번호 블록의 끝: 다음 메인 순위번호 시작 전까지
        # (부기 N-x는 같은 블록에 포함)
        end = len(eulgu_body)
        for next_idx in range(idx + 1, len(all_rank_positions)):
            next_rank, next_start = all_rank_positions[next_idx]
            # 부기(N-x)가 아닌 새로운 메인 순위번호면 블록 종료
            if '-' not in next_rank:
                end = next_start
                break

        block = eulgu_body[start:end]

        # 이 블록 내에서 공동담보목록 찾기
        jt_match = re.search(r'공동담보목록\s*제\s*(\d{4})\s*-\s*(\d+)\s*호', block)
        if jt_match:
            result[rank] = f'공동담보목록 제{jt_match.group(1)}-{jt_match.group(2)}호'

    return result


def parse_single_pdf(pdf_path, company_keywords=None):
    """단일 PDF 전체 파싱"""
    text = extract_full_text(pdf_path)
    if not text:
        return None, []

    uid = parse_unique_id(text)
    if not uid:
        return None, []

    # 부동산 기본정보
    prop = {
        '고유번호': uid,
        '유형': parse_property_type(text),
        '소재지': parse_location(text),
        'PDF파일': os.path.basename(pdf_path),
    }

    # 소유자
    owners, is_company = parse_owner_from_summary(text, company_keywords)
    prop['소유자목록'] = owners
    prop['피감사회사소유'] = is_company
    if owners:
        prop['현재소유자'] = owners[0]['이름']
    else:
        prop['현재소유자'] = ''

    # 가압류
    seizure_count, seizure_detail = parse_garnishment_from_summary(text)
    prop['현행_가압류_건수'] = seizure_count
    prop['갑구_특이사항'] = seizure_detail

    # 현행 근저당
    mortgages = parse_current_mortgages_from_summary(text)

    # 채무자 보충 (본문 을구)
    if mortgages:
        body_debtors = parse_debtors_from_body(text)
        current_ranks = [m['순위번호'] for m in mortgages]

        for m in mortgages:
            m['고유번호'] = uid
            m['유형'] = prop['유형']
            m['소재지'] = prop['소재지']
            m['소유자'] = prop['현재소유자']
            if not m.get('채무자'):
                m['채무자'] = body_debtors.get(m['순위번호'], '')

        # 공동담보목록 (본문 을구)
        jt_map = parse_joint_collateral_from_body(text, current_ranks)
        for m in mortgages:
            m['공동담보목록'] = jt_map.get(m['순위번호'], '')
            # 공동담보 구분
            if m['공동담보목록']:
                m['공동담보'] = m['공동담보목록']
            else:
                m['공동담보'] = ''

    prop['현행근저당_건수'] = len(mortgages)

    return prop, mortgages


def main():
    parser = argparse.ArgumentParser(description='부동산등기부등본 PDF 일괄 파싱')
    parser.add_argument('pdf_dir', help='PDF 폴더 경로')
    parser.add_argument('output_prefix', help='출력 JSON 파일 접두사')
    parser.add_argument('--company', nargs='+', default=[], help='피감사회사 관련 키워드 (예: ABC)')
    args = parser.parse_args()

    pdf_dir = args.pdf_dir
    if not os.path.isdir(pdf_dir):
        print(f"오류: {pdf_dir} 폴더를 찾을 수 없습니다.")
        sys.exit(1)

    pdf_files = sorted([f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')])
    print(f"PDF 파일 {len(pdf_files)}건 발견: {pdf_dir}")

    all_properties = []
    all_mortgages = []
    company_kw = args.company if args.company else None

    for i, fname in enumerate(pdf_files, 1):
        pdf_path = os.path.join(pdf_dir, fname)
        print(f"  [{i:3d}/{len(pdf_files)}] {fname}...", end=' ')

        prop, morts = parse_single_pdf(pdf_path, company_kw)
        if prop:
            prop['No'] = i
            all_properties.append(prop)
            for j, m in enumerate(morts):
                m['No'] = i
            all_mortgages.extend(morts)
            print(f"✓ 근저당 {len(morts)}건")
        else:
            print(f"✗ 파싱 실패")

    # 저장
    prop_path = f"{args.output_prefix}_properties.json"
    mort_path = f"{args.output_prefix}_mortgages.json"

    with open(prop_path, 'w', encoding='utf-8') as f:
        json.dump(all_properties, f, ensure_ascii=False, indent=2)
    with open(mort_path, 'w', encoding='utf-8') as f:
        json.dump(all_mortgages, f, ensure_ascii=False, indent=2)

    print(f"\n=== 결과 ===")
    print(f"부동산: {len(all_properties)}건 → {prop_path}")
    print(f"현행 근저당: {len(all_mortgages)}건 → {mort_path}")
    print(f"가압류 있는 부동산: {sum(1 for p in all_properties if p['현행_가압류_건수'] > 0)}건")
    print(f"공동담보목록 파싱: {sum(1 for m in all_mortgages if m.get('공동담보목록'))}건")

    # 순 담보금액 미리보기
    groups = defaultdict(lambda: {'amt': 0, 'items': []})
    for m in all_mortgages:
        key = m.get('공동담보목록', '')
        if not key:
            key = 'receipt_' + m.get('접수번호', 'unknown')
        if groups[key]['amt'] == 0:
            groups[key]['amt'] = m['채권최고액']
        groups[key]['items'].append(m)

    gross = sum(m['채권최고액'] for m in all_mortgages)
    net = sum(g['amt'] for g in groups.values())
    print(f"\n총 채권최고액 (Gross): {gross:>20,}원")
    print(f"공동담보 중복:         {gross - net:>20,}원")
    print(f"순 담보금액 (Net):     {net:>20,}원")
    print(f"공동담보 그룹:         {len(groups)}개")


if __name__ == '__main__':
    main()
