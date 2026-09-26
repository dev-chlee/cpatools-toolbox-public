#!/usr/bin/env python3
"""공동담보 그룹핑(순 담보금액 dedup) — 단일 SSOT 모듈.

parse_registry_pdfs.py(미리보기)와 generate_workpaper.py(워크페이퍼)가 모두 이 모듈을 사용한다.
로직이 두 곳으로 갈라지면 파서 stdout 의 Net 과 워크페이퍼 Sheet4 의 Net 이 달라질 수 있다 —
그룹핑 규칙 변경은 반드시 여기서만 한다.

키 체계:
- '공동담보목록 제YYYY-NNNN호'  — 목록번호형(법 제78조 공동담보목록). 법적 식별자, 최우선.
- 'llm_<판단ID>' — apply_verdicts.py 가 guard 통과 후 부여한 LLM 판정 공담 그룹(2순위).
- 'receipt_<등기소4>_<설정일자>_<접수번호>_<채권최고액>' — 직접명시형 공담 폴백.
  접수번호는 등기소 내에서만 유일 → 등기소코드(고유번호 앞 4자리) 필수. 설정일자·채권최고액은
  동일 근저당이면 반드시 같으므로 오병합을 막는 안전벨트. 설정일자 미파싱 건은 receipt 병합을
  포기하고 단독으로 강등한다(연도 불명 오병합 방지).
- 'solo_<No>_<순위번호>' — 단독담보. 물건·순위별 고유 키(빈 키 병합에 의한 과소계상 방지).
"""

from collections import defaultdict
import re


def build_joint_groups(mortgages):
    """공동담보 그룹 구성 (하이브리드: 공동담보목록 우선, 등기소+일자+접수번호+금액 폴백)."""
    groups = defaultdict(lambda: {'amt': 0, 'items': [], 'key_type': ''})
    for m in mortgages:
        key = m.get('공동담보목록', '')
        if key:
            kt = '목록'
        elif m.get('LLM공담그룹'):
            key = m['LLM공담그룹']
            kt = 'LLM'
        else:
            receipt = (m.get('접수번호') or '').strip()
            setdate = (m.get('설정일자') or '').strip()
            if m.get('공동담보') and receipt and setdate:
                office = (m.get('고유번호') or '')[:4]
                key = f"receipt_{office}_{setdate}_{receipt}_{m.get('채권최고액', 0)}"
                item = re.search(r'\((\d+)\)$', str(m.get('순위번호', '')))
                if item:
                    key += '_item' + item[1]
                kt = '접수'
            else:
                # 고유번호 기반 키 — No(폴더 정렬 순번)는 파일 추가/삭제 시 밀려 회차 간
                # 그룹 대사가 깨진다. 고유번호는 등기부 불변 식별자.
                key = f"solo_{m.get('고유번호') or m.get('No')}_{m.get('순위번호')}"
                kt = '단독'
        if groups[key]['amt'] == 0:
            groups[key]['amt'] = m['채권최고액']
            groups[key]['key_type'] = kt
        groups[key]['items'].append(m)
    return groups


def group_label(key):
    """그룹 식별자 → 사람이 읽는 라벨.
    receipt 키는 '접수 <번호>호 (<등기소코드>)' — 타 등기소 동일 접수번호와 라벨이 겹치지 않게
    등기소코드를 병기한다. 구버전 JSON 의 짧은 키('receipt_<번호>')도 하위호환 처리."""
    if key.startswith('solo_'):
        return '단독담보'
    if key.startswith('llm_'):
        return f'LLM판정 공담 ({key[4:]})'
    if key.startswith('receipt_'):
        parts = key.split('_')
        if len(parts) >= 5:                       # receipt_<등기소>_<일자>_<접수>_<금액>
            office, num = parts[1], parts[3]
            return f'접수 {num}호 ({office})' if num else '(식별불가)'
        num = parts[-1]                           # 구버전: receipt_<접수> / receipt_<일자>_<접수>
        return '(식별불가)' if num in ('', 'unknown') else f'접수 {num}호'
    return key
