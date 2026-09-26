#!/usr/bin/env python3
"""부동산등기부등본 PDF 일괄 파싱 — 부동산 기본정보 + 현행 근저당 + 공동담보목록 추출

사용법:
    python parse_registry_pdfs.py <PDF_폴더> <출력_JSON> --image-review <manifest.json> [--company <피감사회사명>]

출력:
    두 개의 JSON 파일:
    1. <출력_JSON>_properties.json — 부동산 기본정보 (고유번호, 유형, 소재지, 소유자 등)
    2. <출력_JSON>_mortgages.json — 현행 근저당 상세 (순위번호, 채권최고액, 공동담보목록 등)
"""

import json, re, os, sys, argparse, hashlib
from collections import defaultdict
import cpa_storage
from registry_document import open_document
from registry_entries import supplement, current_seizures, normalize_purpose, other_encumbrances, mortgage_blocks, rank_key

# 파서 버전 — 판단번들 무결성 검증에 사용(apply_verdicts 가 대조). 파싱 로직 변경 시 올릴 것.
__version__ = '0.8.1'

# CLI 종료 상태. 일부 성공 결과를 저장한 경우도 배치 완료와 구별한다.
EXIT_SUCCESS = 0
EXIT_ALL_FAILED = 1
EXIT_INPUT_ERROR = 2
EXIT_PARTIAL_FAILED = 3
EXIT_NO_INPUT = 4

# UTF-8 콘솔 (Windows cp949 콘솔에서 한글·화살표 출력 시 UnicodeEncodeError 방지)
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

try:
    import pdfplumber
except ImportError as e:
    raise ImportError(
        "pdfplumber 가 필요합니다. 먼저 'python scripts/setup_venv.py' 로 설치하세요 "
        "(또는 'pip install pdfplumber openpyxl')."
    ) from e


def extract_full_text(pdf_path):
    """PDF 전체 텍스트 추출"""
    text = ''
    with open_document(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if not (t or '').strip() and getattr(page, 'images', []):
                raise ValueError('이미지 페이지의 텍스트가 누락되었습니다. 기존 OCR HTML을 사용하거나 해당 페이지를 보완하세요.')
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
    ids = list(dict.fromkeys('-'.join(m) for m in re.findall(
        r'고\s*유\s*번\s*호\s*[:：]?\s*(\d{4})\s*[-－–]\s*(\d{4})\s*[-－–]\s*(\d{6})(?!\d)', text)))
    if len(ids) > 1:
        raise ValueError('여러 부동산 고유번호가 포함된 문서입니다. 물건별로 분리한 뒤 실행하세요.')
    return ids[0] if ids else ''


def parse_property_type(text):
    """부동산 유형 판별 (토지/건물)"""
    header = re.search(r'\[\s*(집합건물|건물|토지)\s*\]', text)
    if header:
        return header.group(1)
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
    if parse_property_type(text) == '집합건물':
        # 등기부 머리말의 전유 물건 식별자. 대지권 표의 토지 주소로 덮어쓰지 않는다.
        for m in re.finditer(r'\[\s*집합건물\s*\]\s*([^\n]+)(?:\n(제?[^\s]+호)(?=\s|$))?', text):
            value = m.group(1).strip() + (' ' + m.group(2) if m.group(2) else '')
            if re.search(r'\S+호(?:\s|$)', value) and not re.search(r'\.{3}|…', value):
                return value
        return ''
    summary = find_summary_section(text)
    m = re.search(r'\[\s*(토지|건물)\s*\]\s*([^\n]+)', summary or text)
    if m:
        return re.split(r'고\s*유\s*번\s*호', m.group(2))[0].strip()
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
                    o['피감사회사관련'] = True
                    is_company_owned = True

    return owners, is_company_owned


def parse_summary_tables(tables, include_receipts=False):
    """요약표 셀 경계를 보존해 현 소유자·지분과 근저당 대상 소유자를 읽는다.

    페이지를 넘긴 행은 순위번호가 빈 다음 행과 연결한다. 금액은 이 함수에서
    읽지 않는다: 현행 금액은 본문 변경·말소 처리를 거친 결과를 유지한다.
    """
    owners, targets, receipts = [], {}, {}
    last_rank = None
    for table in tables:
        if not table:
            continue
        header = [re.sub(r'\s+', '', c or '') for c in table[0]]
        share_header = next((h for h in ('최종지분', '소유지분') if h in header), None)
        if share_header and '등기명의인' in header:
            ni, si = header.index('등기명의인'), header.index(share_header)
            for row in table[1:]:
                if len(row) <= max(ni, si):
                    continue
                name = re.sub(r'\s+', '', row[ni] or '')
                name = re.sub(r'\((?:소유자|공유자)\)', '', name)
                share = re.sub(r'\s+', '', row[si] or '')
                if name and re.fullmatch(r'단독소유|\d+분의\d+', share):
                    owners.append({'이름': name, '지분': share, '등록번호': ''})
        elif '대상소유자' in header and '순위번호' in header:
            ni, ri = header.index('대상소유자'), header.index('순위번호')
            pi = header.index('등기목적') if '등기목적' in header else None
            receipt_i = header.index('접수정보') if '접수정보' in header else None
            for row in table[1:]:
                if len(row) <= max(ni, ri):
                    continue
                rank = re.sub(r'\s+', '', row[ri] or '')
                purpose = re.sub(r'\s+', '', row[pi] or '') if pi is not None else ''
                if rank:
                    last_rank = rank if re.fullmatch(r'\d+', rank) and '근저당권설정' in purpose else None
                if last_rank:
                    targets[last_rank] = targets.get(last_rank, '') + re.sub(r'\s+', '', row[ni] or '')
                    if receipt_i is not None:
                        receipts[last_rank] = receipts.get(last_rank, '') + (row[receipt_i] or '')
    return (owners, targets, receipts) if include_receipts else (owners, targets)


def read_summary_tables(pdf_path, include_receipts=False):
    tables, active = [], False
    with open_document(pdf_path) as pdf:
        for page in pdf.pages:
            active = active or bool(find_summary_section(page.extract_text() or ''))
            if active:
                tables.extend(page.extract_tables() or [])
    return parse_summary_tables(tables, include_receipts)


def receipt_fields(text):
    """접수 셀만 읽는다. 변경 부기·다른 권리자의 날짜를 설정일로 채택하지 않는다."""
    normalized = re.sub(r'접수', '', re.sub(r'\s+', '', _strip_watermark(text or '')))
    match = re.search(r'(\d{4})년(\d{1,2})월(\d{1,2})일제?(\d+)호', normalized)
    if not match:
        return None
    y, mo, d, number = match.groups()
    return {'설정일자': f'{y}.{int(mo)}.{int(d)}',
            '접수정보': f'{y}년{int(mo)}월{int(d)}일 제{number}호', '접수번호': number}


def ownership_complete(owners):
    """현황표 지분 합계가 1인 경우에만 전체 소유자 목록으로 인정한다."""
    from fractions import Fraction
    if len(owners) == 1 and owners[0].get('지분') == '단독소유':
        return True
    total = Fraction(0)
    for owner in owners:
        match = re.fullmatch(r'(\d+)분의(\d+)', owner.get('지분', ''))
        if not match or int(match[1]) == 0:
            return False
        total += Fraction(int(match[2]), int(match[1]))
    return bool(owners) and total == 1


def attach_target_owners(mortgage, owners, raw_target, complete):
    """요약표 대상소유자와 현 소유자를 완전 일치시킨다. 부분 상호 추측은 금지."""
    names = {re.sub(r'\s+', '', o['이름']): o for o in owners}
    raw = re.sub(r'\s+', '', raw_target or '')
    parts = [p for p in re.split(r'[,、;·]+', raw) if p]
    if raw and parts and all(p in names for p in parts) and complete:
        selected = [dict(names[p]) for p in parts]
    elif not raw and len(owners) == 1 and complete and not mortgage.get('지분대상'):
        selected = [dict(owners[0])]
    else:
        selected = []
    mortgage['대상소유자원문'] = raw
    mortgage['대상소유자목록'] = selected
    mortgage['대상소유자확인필요'] = not bool(selected)
    mortgage['소유자'] = ', '.join(o['이름'] for o in selected)


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

    # 순위번호별 블록 분리.
    # 복잡·다페이지 등기부는 pdfplumber 추출 시 '순위번호'와 '근저당권설정'의 인접이 깨져
    # r'(\d+)\s+근저당권설정' 로는 블록이 안 잡힌다. 그래서 '줄 시작의 순위번호'(부기 N-M 포함)를
    # 기준으로 블록 경계를 잡되, 그 줄이 근저당권 관련 행(근저당권/채권최고액 포함)일 때만 새 블록으로 본다.
    def _extract_debtor(block):
        dm = re.search(r'채\s*무\s*자\s+(\S+)', block)
        if not dm:
            return ''
        debtor = dm.group(1).strip()
        # '열람용' 워터마크는 단어 단위로만 제거 — 문자클래스([열람용])는 '용가나상사'→'가나상사' 훼손
        debtor = re.sub(r'^(?:열\s*람\s*용\s*)+', '', debtor).strip()
        debtor = re.sub(r'(?:\s*열\s*람\s*용)+$', '', debtor).strip()
        # 주소가 붙은 경우 제거 (예: "주식회사ABC 충청남도...")
        addr_match = re.search(r'\s+(충청|서울|경기|전라|경상|강원|제주|부산|대구|인천|광주|대전|울산|세종)', debtor)
        if addr_match:
            debtor = debtor[:addr_match.start()]
        return debtor

    cur_rank, cur_lines = None, []
    for ln in eulgu_body.split('\n'):
        m = re.match(r'\s*(\d+)(?:-\d+)?\s+\S', ln)
        if m and ('근저당권' in ln or '채권최고액' in ln):
            # 이전 블록 마감 (설정 채무자를 우선: 변경/부기가 덮어쓰지 않게 setdefault)
            if cur_rank is not None:
                d = _extract_debtor('\n'.join(cur_lines))
                if d:
                    result.setdefault(cur_rank, d)
            cur_rank = m.group(1)  # 부기(N-M)는 메인 순위 N 에 귀속
            cur_lines = [ln]
        elif cur_rank is not None:
            cur_lines.append(ln)
    if cur_rank is not None:
        d = _extract_debtor('\n'.join(cur_lines))
        if d:
            result.setdefault(cur_rank, d)

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


# ============================================================
# 표 기반 파서 (요약표 없이도 동작)
#   등기부에 하단 '주요 등기사항 요약'이 없을 때 사용한다. pdfplumber 의 표 추출로
#   을구/갑구/표제부를 셀 단위로 읽어 '설정 − 근저당권설정 말소 = 현행'을 계산한다.
#   표에서 빠진 행은 구역·순위·등기목적이 명확한 평문으로 보완한다.
#   (소재지·소유자·가압류는 본문 추정 — 수동확인 권장.)
# ============================================================

def _tbl_norm(c):
    return re.sub(r'\s+', ' ', (c or '').replace('\n', ' ')).strip()


# 법인격 접두어만 남은(표 분할로 뒤 상호가 끊긴) 근저당권자 조각 — 온전한 실명이 있으면 배제한다.
_CORP_PREFIXES = {'주식회사', '유한회사', '유한책임회사', '(주)', '(유)',
                  '재단법인', '사단법인', '합자회사', '합명회사', '농업회사법인', '주식회사()'}


def _tbl_clean_party(s):
    """당사자명 정리: 열람용 워터마크·뒤따르는 주소 제거.
    - 워터마크는 '열람용' **단어 단위**로만 제거한다. 문자 클래스([열람용])로 지우면
      '용가나상사'→'가나상사', '가나다용'→'가나다' 처럼 정상 상호가 훼손된다.
    - 시도명은 **뒤에 시/군/구(주소 토큰)가 이어질 때만** 주소로 보고 절단한다. 그래야 상호에
      포함된 지명('주식회사경남은행'의 '경남', '대구은행'의 '대구')을 주소로 오인해 자르지 않는다.
      세종특별자치시는 시군구가 없으므로 읍/면/동/로 토큰으로 절단한다.
    - 절단 위치가 문자열 선두면 자르지 않는다('서울가나시스템' 전체를 주소로 오인해 빈 이름이 되는
      것을 방지 — 이름이 통째로 주소인 경우보다 주소형 상호가 실무상 더 흔하다)."""
    s = re.sub(r'^(?:열\s*람\s*용\s*)+', '', s or '').strip()
    s = re.sub(r'(?:\s*열\s*람\s*용)+$', '', s).strip()
    am = re.search(
        r'(?:(?:서울|부산|대구|인천|광주|대전|울산|경기|강원|제주|'
        r'충청[남북]|전라[남북]|경상[남북]|충[남북]|전[남북]|경[남북])'
        r'(?:특별자치도|특별시|광역시|도)?\s*[가-힣]+[시군구]'
        r'|세종특별자치시\s*[가-힣]+[읍면동로])', s)
    return s[:am.start()] if am and am.start() > 0 else s


# 근저당 '설정' 등기목적: 통상형 + 지분근저당('갑구N번 ○○지분(전부|일부)근저당권설정').
# 지분근저당을 startswith 로만 보면 통누락된다(무플래그 탈락 — 감사상 치명).
# ※ 정규화된(공백 제거) 목적 문자열에 매칭한다 — 다페이지 표에서 목적 셀에 '등 기 목 적' 헤더가
#   침투해 '…지분 등 기 목 적 전부근저당권설정' 처럼 깨지는 실서식이 있다.
_MORT_SET_RE = re.compile(r'^(?:(?:갑구)?\d*번?\S*?지분(?:전부|일부)?)?근저당권설정')

def _norm_purpose(s):
    """등기목적 셀 정규화: 침투한 표 헤더('등기목적'/'권리자및기타사항') 제거 + 전 공백 제거."""
    return normalize_purpose(s)


def _strip_watermark(t):
    """'열람용' 워터마크가 토큰 내부에 침투한 텍스트 복원.
    실서식에서 '채권최고액'→'채용권최고액', '2024년'→'202열4년' 처럼 글자 사이에 박힌다.
    - 숫자 사이에 낀 열/람/용 제거('202열4' → '2024').
    - 핵심 키워드는 글자 사이 열람용·공백 허용 fuzzy 매칭으로 원형 복원."""
    # 페이지 경계에 반복된 표 머리글이 당사자명과 등록번호 사이에 들어갈 수 있다.
    header = '순위번호 등기목적 접수 등기원인 권리자및기타사항'
    t = re.sub(r'\s*'.join(re.escape(ch) for ch in header.replace(' ', '')), ' ', t)
    t = re.sub(r'(?<=\d)[열람용](?=\d)', '', t)
    for kw in ('채권최고액', '근저당권설정', '근저당권변경', '근저당권자', '채무자',
               '공동담보목록', '공동담보'):
        pat = r'[열람용\s]*'.join(re.escape(ch) for ch in kw)
        t = re.sub(pat, kw, t)
    return re.sub(r'\s+', ' ', t)


def parse_current_mortgages_from_table(pdf_path):
    """을구 표에서 현행 근저당(설정 − 근저당권설정 말소)을 추출한다(요약표 불필요).
    표 수집은 을구 시작 이후로 격리하고, 하단 요약표('대상소유자' 헤더)·공동담보목록 별지
    ('일련번호'/'담보의 목적' 헤더)는 제외해 갑구/요약/별지 텍스트가 을구 순위에 오염되는 것을 막는다."""
    entries = []
    expected_ranks = set()
    mortgage_text_seen = False
    pages_text = []
    with open_document(pdf_path) as pdf:
        in_eul = False
        for pg in pdf.pages:
            page_text = pg.extract_text() or ''
            pages_text.append(page_text)
            mortgage_text_seen |= bool(re.search(r'근\s*저\s*당\s*권\s*설\s*정', page_text))
            eul_header = re.search(r'【\s*을\s*구\s*】', page_text)
            if eul_header:
                in_eul = True
            if not in_eul:
                continue                                  # 표제부·갑구 페이지의 표는 수집하지 않음
            eul_text = page_text[eul_header.end():] if eul_header else page_text
            eul_text = re.split(r'【\s*공동담보목록\s*】|주요\s*등기사항\s*요약', eul_text)[0]
            expected_ranks.update(re.findall(r'(?m)^\s*(\d+)\s+근저당권설정(?:\s|$)', eul_text))
            for tb in (pg.extract_tables() or []):
                tbl_text = ' '.join(_tbl_norm(x) for r in tb if r for x in r)
                if re.search(r'대상소유자|주요\s*등\s*기\s*사\s*항|일련번호|담보의\s*목적', tbl_text):
                    continue                              # 요약표·공동담보목록 별지 제외
                for row in tb:
                    if not row:
                        continue
                    c0 = _tbl_norm(row[0]); c1 = _tbl_norm(row[1]) if len(row) > 1 else ''
                    call = ' '.join(_tbl_norm(x) for x in row)
                    if re.match(r'^\d', c0):
                        entries.append([c0, c1, call, _tbl_norm(row[2]) if len(row) > 2 else ''])
                    elif entries:
                        entries[-1][1] += ' ' + c1
                        entries[-1][2] += ' ' + call
                        entries[-1][3] += ' ' + (_tbl_norm(row[2]) if len(row) > 2 else '')
    if mortgage_text_seen and not in_eul:
        raise ValueError('근저당 설정 내용이 있으나 을구 제목을 인식하지 못했습니다. 이미지와 OCR 표 구조를 대조하세요.')
    entries = supplement(entries, '\n'.join(pages_text), '을구')
    blocks, set_ranks = mortgage_blocks(entries, _MORT_SET_RE)
    missing = expected_ranks - set_ranks
    if missing:
        raise ValueError('을구 표에서 근저당 설정행 누락: ' + ', '.join(sorted(missing, key=int)) +
                         '번. 원본 표/OCR 구조를 보완한 뒤 재실행하세요.')
    out = []
    for rank, block in blocks.items():
        t = _strip_watermark(block['text'])
        # 채권최고액: 감액/증액 '근저당권변경' 부기가 있으면 마지막(변경 후) 금액이 현행(D3).
        amts = re.findall(r'채권최고액\s*금?\s*([\d,]+)', t)
        if not amts:
            raise ValueError('근저당 채권최고액을 원화 정수로 읽을 수 없습니다. 외화·금액 누락·OCR을 확인하세요.')
        amt_init = int(amts[0].replace(',', '')) if amts else 0
        if len(amts) > 1 and re.search(r'근저당권\s*변경', t):
            amt_cur = int(amts[-1].replace(',', ''))
        else:
            amt_cur = amt_init
        # 근저당권자 — 1차: 등록번호(4자리+) 앵커(정확). 표가 상호에 끼운 공백('주식회사 경남은행')을
        # 넘어 등록번호 앞까지 캡처하되 채무자/공동담보/부기 텍스트는 넘지 않는다(경계 tempered).
        # 다페이지 표는 순위 블록이 여러 조각으로 병합돼 근저당권자가 여러 번(온전 실명 + 법인격만
        # 남은 조각) 잡힌다 → 잘린 조각 배제, 온전한 이름 우선. 여럿이면 마지막=이전(移轉) 반영.
        creds = [c for c in (re.sub(r'\s+', '', _tbl_clean_party(c)) for c in re.findall(
            r'근저당권자\s+([가-힣()A-Za-z](?:(?!채\s*무\s*자|공동담보|근저당권)[가-힣()A-Za-z0-9 ])*?)\s*\d{4,}',
            t)) if c and not c.isdigit()]
        creds_full = [c for c in creds if c not in _CORP_PREFIXES]
        cred_name = creds_full[-1] if creds_full else ''
        # 2차 폴백: 등록번호가 셀 분할로 빠져 1차에 온전한 이름이 없으면, 채무자/부기/공동담보
        # 경계까지 캡처하되 금융기관 접미(은행/조합/금고 등)에서 끊어 채무자명 병합을 막는다.
        # 접미 뒤 법인격(농협은행'주식회사')은 유지해 1차 경로와 표기 일관성 확보.
        if not cred_name:
            _FIN = (r'은행|축산업협동조합|농업협동조합|수산업협동조합|산림조합|협동조합|새마을금고|'
                    r'신용협동조합|신용금고|저축은행|보험|캐피탈|카드|공사|기금|중앙회')
            fb = []
            for c in re.findall(r'근저당권자\s+(.+?)\s*(?:\d{4,}|채\s*무\s*자|근저당권[가-힣]|공동담보|$)', t):
                c = re.sub(r'[*\-]+', '', re.sub(r'\s+', '', _tbl_clean_party(c.strip())))
                mfin = re.match(r'(.*(?:' + _FIN + r')(?:주식회사)?)', c)
                if mfin:
                    c = mfin.group(1)
                if c and not c.isdigit() and c not in _CORP_PREFIXES:
                    fb.append(c)
            cred_name = fb[-1] if fb else (creds[-1] if creds else '')   # 최후수단: 잘린 조각이라도
        debts = re.findall(r'채\s*무\s*자\s+(.+?)(?=근저당권자|공동담보|$)', t)
        jl = re.search(r'공동담보목록\s*제\s*(\d{4}-\d+)\s*호', t)
        rc = re.search(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*제?(\d+)호', t)
        # 공동담보 여부: 목록번호(제YYYY-NNNN호)뿐 아니라 직접명시형('공동담보 토지/건물 …')·
        # 공장저당 제6조 목록도 인정. 단 '공동담보 일부 소멸' 류 부기만으로는 오탐하지 않도록
        # '공동담보' 뒤에 목적물(토지/건물/전세권/목록)이 오는 서식으로 좁힌다(S4).
        # '공동담보 (일부) 소멸' 부기는 공담 지표가 아님 — 감지 전에 제거(오탐 차단).
        t_j = re.sub(r'공동담보[가-힣\s]{0,20}?(?:일부\s*)?소멸', '', t)
        joint = bool(jl) or bool(re.search(r'공동담보\s*(?:목록|토지|건물|전세권)', t_j)) \
            or bool(re.search(r'저당법\s*제?\s*6\s*조', t_j))
        # 공동담보 서술 원문 발췌 보존 — LLM 판단번들·apply guard(서술문-소재지 상호검증)용.
        # 발생 전부를 수집한다: 첫 160자만 취하면 다필지 공담의 뒤쪽 물건 주소가 잘려나가
        # guard 가 정당한 병합을 기각한다(Net 과대).
        jms = re.findall(r'공동담보[\s\S]{0,400}?(?=공동담보|$)', t_j)
        joint_desc = _tbl_norm(' … '.join(jms))[:1500] if (joint and jms) else ''
        out.append({
            '순위번호': rank,
            '설정일자': f"{rc.group(1)}.{rc.group(2)}.{rc.group(3)}" if rc else '',
            '접수정보': (f"{rc.group(1)}년{rc.group(2)}월{rc.group(3)}일 제{rc.group(4)}호"
                         if rc else ''),
            '접수번호': rc.group(4) if rc else '',
            '채권최고액': amt_cur,
            '설정시채권최고액': amt_init if amt_cur != amt_init else amt_cur,
            '근저당권자': cred_name,
            '채무자': re.sub(r'\s+', '', _tbl_clean_party(debts[-1])) if debts else '',
            '공동담보목록': f'공동담보목록 제{jl.group(1)}호' if jl else '',
            '공동담보여부': joint,
            '공동담보서술': joint_desc,
            '지분대상': block['share'],
            # 시간 일관성 자동검증: 목록번호 연도가 설정 접수연도보다 과거면 말소 항목의 목록이
            # 현행 순위에 오매핑됐을 가능성(취소선 유실) — 수동 가이드였던 검증을 기계화.
            '공동담보목록_연도의심': bool(
                jl and rc and int(jl.group(1).split('-')[0]) < int(rc.group(1))),
        })
        # 본문 전체의 첫 날짜가 아니라 해당 설정 행의 접수 칸이 기준이다.
        out[-1].update(receipt_fields(block['receipt']) or {'설정일자': '', '접수정보': '', '접수번호': ''})
    return out


# 2단계 행정구역은 시뿐 아니라 군(郡)도 허용 — '[가-힣]+시' 만 요구하면 홍천군·칠곡군·강화군 등
# 군 소재지(공장·임야·농지 담보에 다수)가 통째로 미인식되어 소재지가 공란이 된다.
_ADDR = (r'(?:충청[남북]도|서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|'
         r'울산광역시|세종특별자치시|경기도|강원[가-힣]*도|전라[남북]도|경상[남북]도|제주[가-힣]*도)'
         r'\s*[가-힣]+[시군](?:\s*[가-힣]+구)?\s*(?:[가-힣]+[읍면]\s*)?[가-힣]+[동리]\s*산?\s*[\d-]+')
_JIMOK = (r'(?:공장용지|학교용지|주차장|창고용지|잡종지|과수원|목장용지|철도용지|주유소용지|'
          r'수도용지|체육용지|유원지|종교용지|광천지|양어장|염전|사적지|대|전|답|임야|묘지|'
          r'도로|제방|하천|구거|유지|공원)')


def _location_from_row(cells, typ):
    """표제부 한 행에서 (표시번호, 소재지 후보 문자열, 원문) 을 추출. 주소가 없으면 None."""
    nc = [_tbl_norm(c) for c in cells]
    addr_i = addr = None
    for i, c in enumerate(nc):
        am = re.search(_ADDR, c)
        if am:
            addr_i, addr = i, am.group(0)
            # 소재지번 칸이 등기원인 칸보다 앞에 있다. 뒤의 분할·합병 유래 주소로
            # 덮어쓰면 현행 주소가 후보에서 사라지고 면적도 누락된다.
            break
    if addr_i is None:
        return None
    marker = nc[0] if nc and re.match(r'^\d', nc[0] or '') else ''
    raw = ' '.join(x for x in nc if x)
    if typ == '건물':
        joined = ' '.join(nc)
        parts = [_tbl_norm(addr)]
        pil = re.search(r'외\s*\d+\s*필지', joined)
        if pil:
            parts.append(_tbl_norm(pil.group(0)))
        dong = re.search(r'제?\s*(주?\s*\d+\s*동)', joined)
        if dong:
            parts.append(_tbl_norm(dong.group(1)))
        return (marker, ' '.join(parts), raw)
    jimok = area = ''
    for c in nc[addr_i:]:
        if not jimok:
            jm = re.search(_JIMOK, c)
            if jm and len(c) <= 8:
                jimok = jm.group(0)
        am = re.search(r'([\d,]+(?:\.\d+)?)\s*㎡', c)
        if am and not area:
            area = am.group(1) + '㎡'
    if addr and jimok and area:
        return (marker, f"{_tbl_norm(addr)} {jimok} {area}", raw)
    return (marker, _tbl_norm(addr), raw)


def location_candidates(pyo_cells, typ):
    """표제부의 주소 포함 행 전부를 (표시번호, 값, 원문) 후보 리스트로 반환 — LLM 판단번들용."""
    out = []
    for cells in pyo_cells:
        r = _location_from_row(cells, typ)
        if r and r[1] and all(r[1] != x[1] for x in out):
            out.append(r)
    return out


def _extract_location(pyo_cells, typ):
    """표제부 표의 셀에서 현행 소재지를 추출한다. 변경 이력이 있으면 '마지막(현행)' 표시행을 취한다.
    토지: 소재지번 셀 + 지목 셀 + 면적 셀(같은 행의 인접 칸)을 결합해 요약표 형식과 정합.
    건물: 소재지번(+외 N필지 +N동) 셀."""
    best = ''
    for cells in pyo_cells:
        r = _location_from_row(cells, typ)
        if not r:
            continue
        marker, val, _raw = r
        if typ == '건물':
            best = val
            continue
        if ' ' in val and '㎡' in val:
            best = val
        elif val and not best:
            best = val
    return best


def _extract_owners(call):
    """소유권 등기의 권리자및기타사항 셀에서 소유자/공유자를 추출.
    이름 = '소유자/공유자[ 지분 X]' 뒤 ~ 등록번호(4자리+ 숫자) 앞. 표 추출이 회사명 안에
    끼운 공백('주식회사 예시산업')은 제거하고, 법인등록번호가 셀 분할로 잘려도('100011-…'→
    '1000') 4자리 숫자 앵커로 이름 끝을 잡는다."""
    out = []
    # 소유자 표지에 침투한 워터마크만 복원하고 상호 자체의 열/람/용은 보존한다.
    for kw in ('소유자', '공유자', '수탁자'):
        call = re.sub(r'[열람용\s]*'.join(kw), kw, call)
    # 구서식의 전산이기 번호·접수번호·원인 열이 성명과 주소 사이에 끼어든 경우.
    # 명확한 열 표지의 조합만 제거한다. 등록번호가 없다는 이유로 접수번호를 신원번호로 쓰지 않는다.
    call = re.sub(r'\s+\(\s*전\s*\d+\s*\)\s*제\s*\d+\s*호\s+'
                  r'(?:매매|증여|상속|협의분할에의한상속)\s+', ' ', call)
    # '소유자 <이름> <등록번호…> …' / '공유자 지분 <지분> <이름> <등록번호…> …'
    # 지분 표기는 'N분의 M'(내부 공백 가능)을 우선 매칭 — \S+ 만 쓰면 '2분의 1'에서 '2분의'만
    # 잡히고 백트래킹으로 이름에 '지분...'이 섞여 들어간다.
    for m in re.finditer(
            r'(소유자|공유자|수탁자)\s+(?:지분\s+(\d+\s*분의\s*\d+|\S+)\s+)?'
            r'([가-힣()A-Za-z][가-힣()A-Za-z0-9 ]*?)\s*\d{4,}', call):
        name = _tbl_clean_party(re.sub(r'\s+', '', m.group(3)))
        if not name or name.isdigit():
            continue
        share = re.sub(r'\s+', '', m.group(2)) if m.group(2) else '단독소유'
        out.append({'이름': name, '지분': share})
    if not out:
        # 등록번호가 없는 구서식: 명시된 소유자 표지와 뒤 주소 경계가 모두 있어야 한다.
        # 성명 길이나 특정 상호를 정답으로 가정하지 않는다. 주소/경계가 없으면 미확정.
        for m in re.finditer(r'(?:소유자|공유자|수탁자)\s+(?:지분\s+(\d+\s*분의\s*\d+)\s+)?'
                             r'(.+?)(?=\s+(?:소유자|공유자|수탁자)\s+|$)', call):
            raw = m.group(2).strip()
            name = _tbl_clean_party(raw).strip()
            if name != raw and re.fullmatch(r'[가-힣A-Za-z()·&.\s]+', name) and name not in _CORP_PREFIXES:
                out.append({'이름': re.sub(r'\s+', '', name),
                            '지분': re.sub(r'\s+', '', m.group(1)) if m.group(1) else '단독소유'})
    return out


def parse_property_from_table(pdf_path):
    """표제부(유형·소재지)·갑구(소유자·가압류)를 표 기반으로 추출한다(요약표 불필요).
    실데이터 검증 기준으로 요약표 기반과 일치하도록 설계."""
    gap_rows, pyo_cells = [], []
    with open_document(pdf_path) as pdf:
        pages_text = [(pg.extract_text() or '') for pg in pdf.pages]
        ft = '\n'.join(pages_text)
        typ = parse_property_type(ft) or ('건물' if re.search(r'【\s*표\s*제\s*부\s*】[\s\S]{0,60}건\s*물', ft)
               else ('토지' if re.search(r'【\s*표\s*제\s*부\s*】[\s\S]{0,60}토\s*지', ft) else ''))
        state = 'before'
        for pi, pg in enumerate(pdf.pages):
            gap_first_page = False
            if re.search(r'【\s*갑\s*구\s*】', pages_text[pi]):
                gap_first_page = (state == 'before')     # 표제부 끝+갑구 시작 전환 페이지
                state = 'gap'
            for tb in (pg.extract_tables() or []):
                rows = [r for r in tb if r]
                if not rows:
                    continue
                tbl_text = ' '.join(' '.join(_tbl_norm(x) for x in r) for r in rows)
                # 표제부 표(면적 있음) — 소재지용. 표제부는 갑구 앞이므로 갑구 진입 전(전환
                # 페이지 포함)까지만 수집하고, 요약표·별지·을구 어휘 행은 제외한다 — 을구
                # 공동담보 서술의 타물건 주소가 '마지막 표시행'으로 오인되는 오염 차단.
                if ('㎡' in tbl_text and (state == 'before' or gap_first_page)
                        and not re.search(r'대상소유자|주요\s*등\s*기\s*사\s*항|일련번호|담보의\s*목적',
                                          tbl_text)):
                    pyo_cells.extend(r for r in rows
                                     if not _EUL_VOCAB_RE.search(' '.join(_tbl_norm(x) for x in r)))
                if state == 'gap':                       # 갑구 표 — 소유자·가압류용
                    for row in rows:
                        gap_rows.append([_tbl_norm(row[0]),
                                         _tbl_norm(row[1]) if len(row) > 1 else '',
                                         ' '.join(_tbl_norm(x) for x in row)])
            if re.search(r'【\s*을\s*구\s*】', pages_text[pi]):
                state = 'eul'

    loc = parse_location(ft) if typ == '집합건물' else (_extract_location(pyo_cells, typ) or parse_location(ft))

    # 갑구 entries (부기 병합)
    entries = []
    for c0, c1, call in gap_rows:
        if re.match(r'^\d', c0):
            entries.append([c0, c1, call])
        elif entries:
            entries[-1][1] += ' ' + c1
            entries[-1][2] += ' ' + call
    entries = [row[:3] for row in supplement(entries, ft, '갑구')]
    seizures = current_seizures(entries)
    owners, own_cancel = {}, set()
    for c0, purpose, call in entries:
        main = re.match(r'(\d+)', c0).group(1)
        purpose = _norm_purpose(purpose)
        # 전원 지분 전부 이전은 종전 공유자의 잔여 지분이 남는 일부 이전과 구분한다.
        if purpose == '공유자전원지분전부이전':
            purpose = '소유권이전'
        # 이전행에 붙은 'N번신탁등기말소'는 소유권이전의 취소가 아니다.
        ownership_entry = bool(re.match(r'^소유권(?:보존|이전(?!청구권)|일부이전)', purpose))
        if '말소' in purpose:
            if '소유권' in purpose and not ownership_entry:
                own_cancel.update(re.findall(r'(\d+)\s*번', purpose))
            if not ownership_entry:
                continue
        if '-' in c0.split()[0]:
            continue
        if ownership_entry:
            owners[main] = (purpose, call)
    cur = sorted([r for r in owners if r not in own_cancel], key=int)
    ownlist, 현재소유자 = [], ''
    # 마지막 소유권 등기가 '일부이전'이면 직전 소유권 등기의 권리자(잔여 지분 보유자)도 현행
    # 공유자다 — 마지막 등기만 보면 순차 지분이전 공유가 누락된다. 일부이전이 이어지는 동안
    # 거슬러 올라가며 합산하고, 전부이전/보존을 만나면 멈춘다.
    take, i = [], len(cur) - 1
    while i >= 0:
        take.append(cur[i])
        if '일부' not in owners[cur[i]][0]:
            break
        i -= 1
    seen = set()
    for r in reversed(take):        # 취득 순서대로
        for o in _extract_owners(owners[r][1]):
            if o['이름'] not in seen:
                seen.add(o['이름'])
                ownlist.append(o)
    # 일부이전의 잔여 지분은 단순 역순 합산으로 확정할 수 없다. 과거 소유자를
    # 현재 소유자로 반환하지 않고 현황표 또는 별도 원본 확인을 요구한다.
    uncertain = len(take) > 1 or any('지분' in owners[r][0] or '일부' in owners[r][0] for r in take)
    if uncertain:
        ownlist = []
    if ownlist:
        현재소유자 = ', '.join(o['이름'] for o in ownlist)
    return {'유형': typ, '소재지': loc, '소유자목록': ownlist,
            '현재소유자': 현재소유자, '소유자확인필요': uncertain or not ownership_complete(ownlist),
            '가압류건수': len(seizures), '현행압류목록': seizures}


# 자동화 범위 밖의 기타 부담(을구 제한물권·갑구 중대사건). 존재 키워드만 감지해 플래그한다 —
# 명시적인 순위별 말소는 반영한다. 취소선 범위와 불확실한 문맥은 원본 대조가 필요하다.
_ENCUMBRANCE_KEYWORDS = [
    ('전세권', r'전세권설정'),
    ('지상권', r'지상권설정'),
    ('경매개시', r'경매개시결정'),
    ('신탁', r'신\s*탁\s*원\s*부|신탁등기|담보신탁'),
    ('가등기', r'소유권이전청구권가등기'),
    ('환매특약', r'환매특약'),
]


def detect_other_encumbrances(text):
    """근저당·(가)압류 외 부담의 감지 경고. 명시된 순위별 말소는 제외한다."""
    return other_encumbrances(text, _ENCUMBRANCE_KEYWORDS)


def parse_single_pdf(pdf_path, company_keywords=None, assume_no_summary=False):
    """단일 PDF 전체 파싱.
    - 현행 근저당은 **항상 표(을구) 기반**으로 추출 → 요약표 유무와 무관하게 동일한 담보금액.
    - 부동산 기본정보(유형·소재지·소유자·가압류)는 요약표 있으면 요약(정확), 없으면 표(본문추정+플래그).
    - assume_no_summary=True 면 요약표가 있어도 없는 것처럼 표 기반 경로를 강제(검증·요약없는 서식 테스트용).
    """
    text = extract_full_text(pdf_path)
    if not text:
        return None, []

    uid = parse_unique_id(text)
    if not uid:
        return None, []

    has_summary = (not assume_no_summary) and bool(find_summary_section(text))
    target_map, summary_receipts = {}, {}

    # ── 부동산 기본정보 ──
    if has_summary:
        owners, target_map, summary_receipts = read_summary_tables(pdf_path, include_receipts=True)
        is_company = bool(company_keywords and any(
            kw and kw.strip() and kw.strip() in o['이름'] for o in owners for kw in company_keywords))
        fallback_note = ''
        # 요약이 소유자를 통째로 놓쳤거나 법인격 조각('주식회사')만 잡은 경우 표 기반으로 폴백.
        if not owners or all((o.get('이름') or '') in _CORP_PREFIXES for o in owners):
            pt_own = parse_property_from_table(pdf_path)['소유자목록']
            if pt_own:
                owners = pt_own
                is_company = bool(company_keywords and any(
                    kw in o.get('이름', '') for o in owners for kw in company_keywords))
                fallback_note = ' | 소유자 표 기반 폴백(본문추정 — 수동확인 권장)'
        seizure_count, seizure_detail = parse_garnishment_from_summary(text)
        body_rights = parse_property_from_table(pdf_path)
        seizure_count = body_rights['가압류건수']
        prop = {
            '고유번호': uid,
            '유형': parse_property_type(text),
            '소재지': parse_location(text),
            'PDF파일': os.path.basename(pdf_path),
            '소유자목록': owners,
            '피감사회사소유': is_company,
            '현재소유자': ', '.join(o['이름'] for o in owners),
            '소유자확인필요': not ownership_complete(owners),
            '현행_가압류_건수': seizure_count,
            '현행압류목록': body_rights['현행압류목록'],
            '갑구_특이사항': (seizure_detail or '') + fallback_note,
        }
    else:
        pt = parse_property_from_table(pdf_path)
        prop = {
            '고유번호': uid,
            '유형': pt['유형'] or parse_property_type(text),
            '소재지': pt['소재지'],
            'PDF파일': os.path.basename(pdf_path),
            '소유자목록': pt['소유자목록'],
            '현재소유자': pt['현재소유자'],
            '현행_가압류_건수': pt['가압류건수'],
            '현행압류목록': pt['현행압류목록'],
            '갑구_특이사항': '요약표 없음 — 소재지·소유자·가압류 본문추정(수동확인 권장)',
            '요약표없음': True,
            '소유자확인필요': pt.get('소유자확인필요', True),
            '피감사회사소유': bool(company_keywords and pt['소유자목록'] and any(
                kw in o.get('이름', '') for o in pt['소유자목록'] for kw in company_keywords)),
        }

    stamp = re.search(r'(?:열람|발급)일시\s*[:：]?\s*(\d{4})년\s*(\d{2})월\s*(\d{2})일', text)
    prop['원본열람일'] = '.'.join(stamp.groups()) if stamp else ''
    if prop['소유자확인필요']:
        prop['피감사회사소유'] = None
        prop['갑구_특이사항'] += ' | 현 소유자·잔여 지분 확인 필요'

    # ── 현행 근저당: 항상 표 기반(일관성·정확). 표가 비고 요약 있으면 요약으로 폴백(안전). ──
    mortgages = parse_current_mortgages_from_table(pdf_path)
    if not mortgages and has_summary:
        mortgages = parse_current_mortgages_from_summary(text)
        if mortgages:
            body_debtors = parse_debtors_from_body(text)
            jt_map = parse_joint_collateral_from_body(text, [m['순위번호'] for m in mortgages])
            for m in mortgages:
                if not m.get('채무자'):
                    m['채무자'] = body_debtors.get(m['순위번호'], '')
                m['공동담보목록'] = jt_map.get(m['순위번호'], '')

    for m in mortgages:
        receipt = receipt_fields(summary_receipts.get(str(m['순위번호'])))
        if receipt:
            m.update(receipt)
            year = re.search(r'제(\d{4})-', m.get('공동담보목록') or '')
            m['공동담보목록_연도의심'] = bool(year and int(year[1]) < int(receipt['설정일자'][:4]))
        m['고유번호'] = uid
        m['유형'] = prop['유형']
        m['소재지'] = prop['소재지']
        attach_target_owners(m, prop['소유자목록'], target_map.get(str(m['순위번호'])),
                             not prop['소유자확인필요'])
        # 공동담보 플래그: 목록번호 우선, 없으면 직접명시형('공동담보 토지/건물 …') 감지 결과로.
        m['공동담보'] = m.get('공동담보목록', '') or ('공동담보' if m.get('공동담보여부') else '')
    prop['현행근저당_건수'] = len(mortgages)
    # 기타부담 감지 경고: 명시된 순위별 말소를 반영하되 법률상 효력 전반을 확정하지 않는다.
    prop['기타부담_감지'] = detect_other_encumbrances(text)
    if str(pdf_path).lower().endswith(('.html', '.htm')):
        prop['입력형식'] = 'OCR HTML'
        prop['OCR검토필요'] = True
        prop['갑구_특이사항'] += ' | OCR 결과 사용 — 원본의 순위·말소·금액·표 병합 대조 필요'

    return prop, mortgages


# ─────────────────────────────────────────────────────────────────────────────
# LLM 판단번들 (v0.4) — 규칙이 확신하지 못한 필드를 closed-set 후보와 함께 수집.
# LLM 은 후보 '번호'로만 답한다(자유문자열 금지 — 환각 차단). 확정은 apply_verdicts.py.
# ─────────────────────────────────────────────────────────────────────────────

def _pdf_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def bundle_hash(items):
    """판단항목 배열의 결정형 해시 — verdict 와의 바인딩(무결성) 검증용."""
    blob = json.dumps(items, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha256(blob).hexdigest()


# 을구 어휘 — 표제부 후보 행에 섞이면 을구(근저당) 오염이다. closed-set 의 전제(후보=표제부)를
# 지키기 위해 후보 생성·검증 양쪽에서 배제한다.
_EUL_VOCAB_RE = re.compile(r'채권최고액|근저당권|채\s*무\s*자|공동담보|전세권|지상권')


def _collect_pyo_cells(pdf_path):
    """표제부 표(면적 ㎡ 포함) 행 수집 — 소재지 후보 생성용.
    갑구 진입 이후 페이지는 수집하지 않고(표제부는 항상 갑구 앞), 요약표·별지 표와
    을구 어휘가 든 행을 제외한다 — 을구 공동담보 서술의 타물건 주소가 '표시번호 N'으로
    위장해 후보에 들어가는 오염(closed-set 붕괴)을 차단."""
    rows_out = []
    with open_document(pdf_path) as pdf:
        for pg in pdf.pages:
            txt = pg.extract_text() or ''
            gap_here = bool(re.search(r'【\s*갑\s*구\s*】', txt))
            for tb in (pg.extract_tables() or []):
                rows = [r for r in tb if r]
                if not rows:
                    continue
                tbl_text = ' '.join(' '.join(_tbl_norm(x) for x in r) for r in rows)
                if '㎡' not in tbl_text:
                    continue
                if re.search(r'대상소유자|주요\s*등\s*기\s*사\s*항|일련번호|담보의\s*목적', tbl_text):
                    continue                              # 요약표·공동담보목록 별지 제외
                for r in rows:
                    if not _EUL_VOCAB_RE.search(' '.join(_tbl_norm(x) for x in r)):
                        rows_out.append(r)
            if gap_here:
                return rows_out                            # 갑구 등장 페이지까지 처리 후 종료
    return rows_out


def _norm_name(s):
    return re.sub(r'\s+', '', s or '')


def build_judgment_bundle(all_properties, all_mortgages, pdf_dir, company_keywords=None,
                          json_hashes=None, source_paths=None):
    """LLM 판단항목 수집 (3필드):
    - 소재지: '요약표없음' 물건 중 소재지 공란 또는 표제부 복수 주소 후보(변경이력)
    - 공담: 직접명시형 공동담보의 서로 다른 접수·단독 그룹 사이 추가담보 —
      동일 근저당권자·동일 채권최고액 조건으로 필터하고 목록·LLM 그룹은 제외한다.
    - 소유자: 소유자 공란/법인격 조각/표 기반 폴백 물건 (회사 키워드가 있을 때만)
    """
    from grouping import build_joint_groups
    items, jid = [], 0

    def nid():
        nonlocal jid
        jid += 1
        return f'J{jid:03d}'

    prop_by_uid = {p['고유번호']: p for p in all_properties}

    # ── 소재지 ──
    for p in all_properties:
        if not p.get('요약표없음'):
            continue
        if p.get('유형') == '집합건물':
            # 전유 물건의 머리말이 현행 식별자. 토지 표 행은 대체 후보가 아니다.
            continue
        try:
            cands = location_candidates(_collect_pyo_cells(
                (source_paths or {}).get(p['고유번호'], os.path.join(pdf_dir, p['PDF파일']))), p.get('유형', ''))
        except Exception:
            cands = []
        if (not p.get('소재지') and cands) or len(cands) > 1:
            items.append({
                '판단ID': nid(), '필드': '소재지', '고유번호': p['고유번호'], '순위번호': None,
                '현재값': p.get('소재지', ''),
                '원문발췌': ' || '.join(r[2] for r in cands)[:1200],
                '질문': '표제부 변경이력에서 말소되지 않은 현행 소재지는 어느 후보인가? '
                        '(0=판단불가·현재값 유지)',
                '후보': [{'번호': i, '값': r[1],
                          '출처': f'표시번호 {r[0]}' if r[0] else '표시번호 불명'}
                         for i, r in enumerate(cands, 1)],
            })

    # ── 공담 (직접명시형 미병합) ──
    groups = build_joint_groups(all_mortgages)
    eligible, group_of = set(), {}
    for group_key, v in groups.items():
        for m0 in v['items']:
            mk = (m0['고유번호'], m0['순위번호'])
            group_of[mk] = group_key
            if v['key_type'] in ('접수', '단독'):
                eligible.add(mk)
    for m in all_mortgages:
        k = (m['고유번호'], m['순위번호'])
        if not (m.get('공동담보') and not m.get('공동담보목록') and k in eligible
                and m.get('공동담보서술')):
            continue
        cands = []
        for mm in all_mortgages:
            kk = (mm['고유번호'], mm['순위번호'])
            # 목록번호 보유 건은 후보 제외 — 짝이 배치에 없어 1건 그룹이어도 apply guard 가
            # 100% 기각하므로 LLM 에게 불가능한 후보를 제시하지 않는다.
            if (kk != k and mm['고유번호'] != m['고유번호'] and kk in eligible
                    and group_of.get(kk) != group_of.get(k)
                    and not mm.get('공동담보목록')
                    and mm['채권최고액'] == m['채권최고액']
                    and _norm_name(mm.get('근저당권자')) == _norm_name(m.get('근저당권자'))):
                cands.append(mm)
        if not cands:
            continue
        items.append({
            '판단ID': nid(), '필드': '공담', '고유번호': m['고유번호'], '순위번호': m['순위번호'],
            '현재값': (f"접수 그룹 {len(groups[group_of[k]]['items'])}건(추가담보 확인)"
                       if len(groups[group_of[k]]['items']) > 1 else '단독(자동 병합 없음)'),
            '원문발췌': m['공동담보서술'][:600],
            '질문': '이 근저당의 공동담보 서술이 지칭하는 상대 물건을 후보에서 고르라 '
                    '(복수 가능, []=세트 외/매칭 불가 — 확신 없으면 빈 배열)',
            '후보': [{'번호': i, '고유번호': mm['고유번호'], '순위번호': mm['순위번호'],
                      '유형': mm.get('유형', ''), '소재지': mm.get('소재지', ''),
                      '채권최고액': mm['채권최고액'], '근저당권자': mm.get('근저당권자', ''),
                      '설정일자': mm.get('설정일자', ''), '접수번호': mm.get('접수번호', '')}
                     for i, mm in enumerate(cands, 1)],
        })

    # ── 소유자 분류 ──
    if company_keywords:
        for p in all_properties:
            cur = p.get('현재소유자') or ''
            suspicious = (not cur or cur in _CORP_PREFIXES
                          or '폴백' in (p.get('갑구_특이사항') or ''))
            if not suspicious:
                continue
            items.append({
                '판단ID': nid(), '필드': '소유자', '고유번호': p['고유번호'], '순위번호': None,
                '현재값': cur,
                '원문발췌': json.dumps(p.get('소유자목록', []), ensure_ascii=False)[:600],
                '질문': f"소유자 '{cur or '(공란)'}' 는 피감사회사({'/'.join(company_keywords)}) "
                        f"기준으로 무엇인가? (0=판단불가·현재값 유지. 확신 없으면 반드시 0)",
                '후보': [{'번호': 1, '값': '본인'}, {'번호': 2, '값': '제3자'}],
            })

    meta = {
        '파서버전': __version__,
        # 입력PDF sha256 은 **기록용**(사후 재구성용) — apply 는 재검증하지 않는다.
        '입력PDF': [{'PDF파일': p['PDF파일'], 'sha256': _pdf_sha256(
            os.path.join(pdf_dir, p['PDF파일']))} for p in all_properties],
        '분석입력': [{'고유번호': p['고유번호'], '경로': source_paths[p['고유번호']],
                    'sha256': _pdf_sha256(source_paths[p['고유번호']])} for p in all_properties] if source_paths else [],
        # 파싱 JSON 해시는 apply 가 **검증**한다 — 번들 생성 후 재파싱/수기수정된 JSON 에
        # 구 verdict 를 적용하는 사고 차단.
        '입력JSON': json_hashes or {},
        '번들해시': bundle_hash(items),
    }
    return {'메타': meta, '판단항목': items}


def main(argv=None):
    from registry_image_gate import prepare_analysis, check_result, write_proof, inventory, ReviewError
    parser = argparse.ArgumentParser(
        description='부동산등기부등본 PDF 일괄 파싱',
        epilog='종료코드: 0=전체 성공, 1=전부 실패, 2=입력/인자 오류, 3=일부 실패, 4=PDF 없음, 5=이미지 검토 미완료')
    parser.add_argument('pdf_dir', help='PDF 폴더 경로')
    parser.add_argument('output_prefix', help='출력 JSON 파일 접두사')
    parser.add_argument('--company', nargs='+', default=[], help='피감사회사 관련 키워드 (예: ABC)')
    parser.add_argument('--assume-no-summary', action='store_true',
                        help='요약표가 있어도 없는 것처럼 표 기반 경로를 강제(검증/요약없는 서식 테스트용)')
    parser.add_argument('--emit-bundle', action='store_true',
                        help='LLM 판단번들(<접두사>_judgment_bundle.json) 생성 — 규칙이 확신하지 '
                             '못한 소재지/공담/소유자 항목을 closed-set 후보와 함께 수집')
    parser.add_argument('--include-ocr-html', action='store_true',
                        help='이전 호출 호환용. OCR 입력은 --image-review의 원본 PDF·판독 기록으로만 선택')
    parser.add_argument('--image-review', help='전체 PDF 이미지 판독 manifest.json (필수)')
    args = parser.parse_args(argv)
    try:
        cpa_storage.guard(args.output_prefix)
    except cpa_storage.StorageError as exc:
        parser.error(str(exc))

    pdf_dir = args.pdf_dir
    if not os.path.isdir(pdf_dir):
        print(f"오류: {pdf_dir} 폴더를 찾을 수 없습니다.")
        return EXIT_INPUT_ERROR

    pdf_files = [p['file'] for p in inventory(pdf_dir)]
    print(f"PDF 파일 {len(pdf_files)}건 발견: {pdf_dir}")
    if not pdf_files:
        print('PDF 입력 없음 — 결과 JSON을 생성하지 않습니다.')
        return EXIT_NO_INPUT

    try:
        if any(os.path.exists(f'{args.output_prefix}_{kind}.json') for kind in ('properties', 'mortgages')):
            raise ReviewError('기존 분석 결과가 있습니다. 새 출력 접두사를 사용하세요.')
        sources, image_context = prepare_analysis(args.image_review, pdf_dir, args.output_prefix)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'이미지 검토 필요: {exc}')
        return 5

    all_properties = []
    all_mortgages = []
    exclusions = [p for p in image_context['document_classifications'] if p['kind'] == 'non_registry']
    if exclusions:
        print(f"비등기 문서 제외: {len(exclusions)}쪽 — 근거는 {args.output_prefix}_image_inputs/document-classification.json")
    if not sources:
        print('등기부 분석 대상 없음: 전체 페이지가 이미지 판독에서 비등기 문서로 확인되었습니다. 담보 0건 결과는 생성하지 않습니다.')
        return 0
    company_kw = args.company if args.company else None

    failed = []
    source_paths = {}
    for i, source in enumerate(sources, 1):
        fname, pdf_path = source['file'], source['path']
        print(f"  [{i:3d}/{len(sources)}] {fname} (원본 {source['pages']}쪽)...", end=' ')

        # 파일 단위 독립: 손상·암호화·비정형 PDF 1건이 배치 전체를 중단시키지 않는다.
        try:
            prop, morts = parse_single_pdf(pdf_path, company_kw,
                                           assume_no_summary=args.assume_no_summary)
            if prop:
                check_result(source, prop, morts)
                if prop['고유번호'] in source_paths:
                    raise ReviewError('동일 고유번호의 중복 물건입니다. 기준일·중복 입력을 확인하세요.')
        except Exception as e:
            failed.append(fname)
            print(f"[FAIL] 파싱 오류 — 건너뜀 ({type(e).__name__}: {e})")
            continue

        if prop:
            source_paths[prop['고유번호']] = pdf_path
            prop['No'] = i
            all_properties.append(prop)
            for j, m in enumerate(morts):
                m['No'] = i
            all_mortgages.extend(morts)
            print(f"[OK] 근저당 {len(morts)}건")
        else:
            failed.append(fname)
            print('[FAIL] 등기부 고유번호 또는 텍스트 인식 불가 — 입력·OCR 결과를 확인하세요.')

    print(f"\n=== 처리 상태: PDF {len(pdf_files)}건 / 물건 {len(sources)}건 / 성공 {len(all_properties)}건 / 실패 {len(failed)}건 ===")
    if not all_properties:
        print(f"전부 실패: {', '.join(failed)} — 결과 JSON을 생성하지 않습니다.")
        return EXIT_ALL_FAILED

    # 저장 (출력 폴더가 없으면 자동 생성 — 문서 예시 './output/...' 대로 실행해도 crash 하지 않게)
    prop_path = f"{args.output_prefix}_properties.json"
    mort_path = f"{args.output_prefix}_mortgages.json"
    os.makedirs(os.path.dirname(os.path.abspath(prop_path)), exist_ok=True)

    with open(prop_path, 'w', encoding='utf-8') as f:
        json.dump(all_properties, f, ensure_ascii=False, indent=2)
    with open(mort_path, 'w', encoding='utf-8') as f:
        json.dump(all_mortgages, f, ensure_ascii=False, indent=2)

    print(f"\n=== 결과 ===")
    if failed:
        print(f"실패/건너뜀: {len(failed)}건 — {', '.join(failed)}")
    print(f"부동산: {len(all_properties)}건 → {prop_path}")
    print(f"현행 근저당: {len(all_mortgages)}건 → {mort_path}")
    print(f"가압류 있는 부동산: {sum(1 for p in all_properties if p['현행_가압류_건수'] > 0)}건")
    print(f"공동담보목록 파싱: {sum(1 for m in all_mortgages if m.get('공동담보목록'))}건")

    # 순 담보금액 미리보기 — 그룹핑은 grouping.build_joint_groups 단일 SSOT 를 그대로 사용
    # (로직이 갈라지면 미리보기 Net ≠ 워크페이퍼 Net 이 된다).
    from grouping import build_joint_groups
    groups = build_joint_groups(all_mortgages)

    gross = sum(m['채권최고액'] for m in all_mortgages)
    net = sum(g['amt'] for g in groups.values())
    print(f"\n총 채권최고액 (Gross): {gross:>20,}원")
    print(f"공동담보 중복:         {gross - net:>20,}원")
    print(f"순 담보금액 (Net):     {net:>20,}원")
    print(f"공동담보 그룹:         {len(groups)}개")

    # LLM 판단번들 (v0.4)
    if args.emit_bundle:
        json_hashes = {'properties_sha256': _pdf_sha256(prop_path),
                       'mortgages_sha256': _pdf_sha256(mort_path)}
        bundle = build_judgment_bundle(all_properties, all_mortgages, pdf_dir, company_kw,
                                       json_hashes=json_hashes, source_paths=source_paths)
        bundle_path = f"{args.output_prefix}_judgment_bundle.json"
        with open(bundle_path, 'w', encoding='utf-8') as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)
        n_by = defaultdict(int)
        for it in bundle['판단항목']:
            n_by[it['필드']] += 1
        print(f"\nLLM 판단번들: {len(bundle['판단항목'])}항목 "
              f"({dict(n_by) if n_by else '없음'}) → {bundle_path}")
        if bundle['판단항목']:
            print("  → SKILL.md 'LLM 판단 워크플로'에 따라 판정 후 apply_verdicts.py 로 확정하세요.")

    if failed:
        print('\n일부 실패 — 성공한 물건의 중간 JSON만 저장했습니다. 완료 증거가 없어 최종 조서 생성은 차단됩니다.')
        return EXIT_PARTIAL_FAILED
    try:
        # 파싱 중 원본/판독이 변경된 경우에도 완료 증거를 발행하지 않는다.
        from registry_image_gate import validate_job
        _, current_dependencies = validate_job(args.image_review, pdf_dir)
        if current_dependencies != image_context['dependencies']:
            raise ReviewError('분석 중 이미지 판독 기록이 변경되었습니다.')
        write_proof(prop_path, mort_path, image_context, sources)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'이미지 검토 필요 — 최종 조서 생성 차단: {exc}')
        return 5
    return EXIT_SUCCESS


if __name__ == '__main__':
    sys.exit(main())
