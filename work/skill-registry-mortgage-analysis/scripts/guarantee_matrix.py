#!/usr/bin/env python3
"""물상보증 매트릭스 — 순 담보금액(Net)을 소유축 × 채무자축으로 분해. 단일 SSOT 모듈.

Net 단일 숫자는 감사 판단을 오도한다. 같은 합계 안에 성격이 정반대인 두 가지가 섞이기 때문이다:

- **물상보증 제공** (회사 자산 ← 제3자 채무): 회사가 타인 채무를 위해 담보를 제공한 것.
  우발부채 검토 대상(K-IFRS 1037), 특수관계자면 담보·보증 주석(K-IFRS 1024).
- **물상보증 수령** (제3자 자산 ← 회사 채무): 타인이 회사 채무를 위해 담보를 제공한 것.
  회사 부채의 담보이지 회사 자산의 부담이 아니다 — 담보제공자의 특수관계자 여부를 대조한다.

이 모듈은 grouping.build_joint_groups 가 만든 공동담보 그룹을 그대로 받아 **그룹 단위로**
4분면에 배정한다.

불변식(반드시 유지):
1. **금액 안분 없음** — 그룹은 쪼개지 않는다. 한 그룹이 회사 물건과 제3자 물건에 걸치면
   금액을 나누지 않고 소유축을 '혼합'으로 표시한다. 안분은 근거 없는 숫자를 만들어내고,
   그 숫자가 조서에 남으면 검토자가 실재하지 않는 배분을 사실로 읽는다.
2. **셀 금액 합계 ≡ Net 총액** — 모든 그룹이 정확히 한 셀에 배정된다(build_matrix 가 검증).
3. **금액 산술은 Python 100%** — 이 모듈은 그룹의 amt 를 더하기만 한다.

회사귀속 판정(owner_is_company / debtor_is_company)의 SSOT 도 여기다.
generate_workpaper.classify_ownership 이 이 함수를 호출한다 — 판정 규칙이 두 벌로 갈라지면
Sheet1 의 '회사소유' 표시와 매트릭스 분면이 어긋난 조서가 나온다.
"""

from collections import defaultdict
import re

# 축 라벨 (표시 순서 = 아래 상수 순서)
COMPANY = '회사'
THIRD = '제3자'
MIXED = '혼합'
UNKNOWN = '미상'

OWNER_AXIS_ORDER = (COMPANY, THIRD, MIXED, UNKNOWN)
DEBTOR_AXIS_ORDER = (COMPANY, THIRD, MIXED, UNKNOWN)

# 4분면 해석 — (소유축, 채무자축) → (구분, 감사 조치)
QUADRANT = {
    (COMPANY, COMPANY): ('자기담보',
                         '회사 자산이 회사 채무의 담보 — 차입금 담보 주석과 대사'),
    (COMPANY, THIRD): ('물상보증 제공',
                       '회사 자산이 타인 채무의 담보 — 우발부채(K-IFRS 1037) 검토, '
                       '특수관계자면 담보·보증 주석(K-IFRS 1024)'),
    (THIRD, COMPANY): ('물상보증 수령',
                       '타인 자산이 회사 채무의 담보 — 담보제공자의 특수관계자 여부 대조'),
    (THIRD, THIRD): ('회사 무관',
                     '회사 소유도 회사 채무도 아님 — 검토 세트에 편입된 사유를 확인'),
}
# 혼합 = 한 근저당(공동담보)이 회사 물건과 제3자 물건에 함께 걸린 경우. 실데이터에서 물상보증이
# 실제로 발생하는 지점이므로 '구분 불가'로 묻지 않고 채무자축 기준으로 승격해 표시한다.
# 금액은 여전히 안분하지 않는다 — 물건별 구분은 원본 대조의 몫이다.
MIXED_LABEL = {
    (MIXED, COMPANY): ('혼합 — 회사채무',
                       '회사 물건과 제3자 물건이 한 근저당의 담보 — 제3자 물건분은 물상보증 수령. '
                       '담보제공자의 특수관계자 여부와 물건별 구성을 원본으로 확인'),
    (MIXED, THIRD): ('혼합 — 제3자채무',
                     '회사 물건이 타인 채무의 담보에 포함 — 물상보증 제공(우발부채) 가능성. '
                     '원본 대조 필수'),
}
UNCLASSIFIED = ('구분 불가', '소유자 또는 채무자가 그룹 내에서 섞이거나 미파싱 — 원본 대조 필요')


def name_matches_company(name, company_keywords):
    """상호/성명 문자열이 피감사회사 키워드에 걸리는가."""
    if not name or not company_keywords:
        return False
    return any(re.sub(r'\s+', '', kw) in re.sub(r'\s+', '', name)
               for kw in company_keywords if kw and kw.strip())


def owner_is_company(prop, company_keywords):
    """회사=True, 확인된 제3자=False, 분류 근거 없음=None. 회사귀속 판정의 SSOT.

    LLM 이 '제3자'로 확정한 건은 키워드 매칭으로 되돌리지 않는다. 유사 상호(바로 그 애매
    케이스)에서 키워드가 판정을 무효화하면 LLM 증적과 본문 표시가 모순된다.
    """
    if prop.get('소유자확인필요'):
        return None
    if prop.get('LLM소유자분류') == '제3자':
        return False
    if prop.get('LLM소유자분류') == '본인' or prop.get('피감사회사소유') is True:
        return True
    names = [str(o.get('이름') or '').strip() for o in (prop.get('소유자목록') or [])]
    names = [name for name in names if name not in ('', '-')]
    if not names:
        current = str(prop.get('현재소유자') or '').strip()
        if current not in ('', '-'):
            names = [current]
    if not names or not any(kw and kw.strip() for kw in (company_keywords or [])):
        return None
    return any(name_matches_company(name, company_keywords) for name in names)


def debtor_is_company(debtor, company_keywords):
    """근저당의 채무자가 피감사회사인가. 미파싱은 None(=미상) 으로 돌려 '제3자' 오분류를 막는다."""
    d = (debtor or '').strip()
    if not d or d == '-' or not any(kw and kw.strip() for kw in (company_keywords or [])):
        return None
    return name_matches_company(d, company_keywords)


def _axis(flags):
    """그룹 구성원의 bool/None 집합 → 축 라벨. 미상이 하나라도 섞이면 단정하지 않는다."""
    if not flags:
        return UNKNOWN
    if None in flags:
        return UNKNOWN
    if len(flags) > 1:
        return MIXED
    return COMPANY if True in flags else THIRD


def classify_group(items, prop_by_uid, company_keywords):
    """공동담보 그룹 하나의 (소유축, 채무자축) 판정."""
    owner_flags, debtor_flags = set(), set()
    for m in items:
        prop = prop_by_uid.get(m.get('고유번호')) or {}
        owner_flags.update(mortgage_owner_flags(m, prop, company_keywords))
        debtor_flags.add(debtor_is_company(m.get('채무자'), company_keywords))
    return _axis(owner_flags), _axis(debtor_flags)


def mortgage_owner_flags(mortgage, prop, company_keywords):
    """담보 대상 지분의 소유축. 부동산에 회사 지분이 있다는 이유로 전부 귀속시키지 않는다."""
    if mortgage.get('대상소유자확인필요') or prop.get('소유자확인필요'):
        return {None}
    targets = mortgage.get('대상소유자목록')
    if targets:
        if len(prop.get('소유자목록') or []) == 1 and prop.get('LLM소유자분류'):
            return {owner_is_company(prop, company_keywords)}
        return {owner_is_company({'소유자목록': [o]}, company_keywords) for o in targets}
    if len(prop.get('소유자목록') or []) > 1:
        return {None}
    return {owner_is_company(prop, company_keywords) if prop else None}


def mortgage_owner_axis(mortgage, prop, company_keywords):
    return _axis(mortgage_owner_flags(mortgage, prop, company_keywords))


def quadrant_of(owner_axis, debtor_axis):
    """(소유축, 채무자축) → (구분명, 감사 조치). 4분면 → 혼합 → 구분 불가 순으로 조회."""
    axes = (owner_axis, debtor_axis)
    if axes in QUADRANT:
        return QUADRANT[axes]
    return MIXED_LABEL.get(axes, UNCLASSIFIED)


def build_matrix(jt_groups, properties, company_keywords):
    """Net 을 소유축 × 채무자축으로 분해한다.

    반환:
        {
          '셀': {(소유축, 채무자축): {'금액', '그룹수', '물건수', '근저당건수', '그룹키'}},
             — 물건수는 고유번호(부동산) 기준, 근저당건수는 을구 항목 기준. 한 물건에
               근저당이 여러 건이면 둘이 다르다. 물건이 여러 그룹에 걸리면 셀 간 중복 계상된다
               (그룹 단위 집계의 성질 — 금액만 배타적으로 배정된다).
          '그룹': [그룹별 판정 레코드 — Net 내림차순],
          'Net': int,
          '검증': {'셀합계', 'Net', '일치'},
        }
    """
    prop_by_uid = {p['고유번호']: p for p in properties}
    cells = defaultdict(lambda: {'금액': 0, '그룹수': 0, '물건수': 0, '근저당건수': 0,
                                 '그룹키': []})
    records = []

    for key, g in jt_groups.items():
        items = g['items']
        oax, dax = classify_group(items, prop_by_uid, company_keywords)
        # 혼합 그룹에서 검토자가 안분 없이 구성을 파악할 수 있게 물건 수를 나눠 센다.
        uids = {m.get('고유번호') for m in items}
        ownership = [_axis(set().union(*(mortgage_owner_flags(m, prop_by_uid.get(u) or {}, company_keywords)
                                        for m in items if m.get('고유번호') == u))) for u in uids]
        co_props = ownership.count(COMPANY)
        third_props = ownership.count(THIRD)
        unknown_props = ownership.count(UNKNOWN)
        mixed_props = ownership.count(MIXED)
        label, action = quadrant_of(oax, dax)
        cell = cells[(oax, dax)]
        cell['금액'] += g['amt']
        cell['그룹수'] += 1
        cell['물건수'] += len(uids)          # 담보 부동산 수(고유번호 기준)
        cell['근저당건수'] += len(items)     # 근저당 항목 수 — 한 물건에 여러 건일 수 있다
        cell['그룹키'].append(key)
        records.append({
            '그룹키': key,
            '소유축': oax,
            '채무자축': dax,
            '구분': label,
            '조치': action,
            '금액': g['amt'],
            '물건수': len(uids),
            '근저당건수': len(items),
            '회사물건수': co_props,
            '제3자물건수': third_props,
            '미상물건수': unknown_props,
            '혼합물건수': mixed_props,
            '물건No': sorted({m.get('No') for m in items if m.get('No') is not None}),
            '소유자': sorted({m.get('소유자', (prop_by_uid.get(m.get('고유번호')) or {}).get('현재소유자', ''))
                            for m in items} - {''}),
            '채무자': sorted({(m.get('채무자') or '').strip() for m in items} - {'', '-'}),
            '근저당권자': sorted({(m.get('근저당권자') or '').strip() for m in items} - {'', '-'}),
        })

    records.sort(key=lambda r: (-r['금액'], str(r['그룹키'])))
    net = sum(g['amt'] for g in jt_groups.values())
    cell_total = sum(c['금액'] for c in cells.values())

    return {
        '셀': dict(cells),
        '그룹': records,
        'Net': net,
        '검증': {'셀합계': cell_total, 'Net': net, '일치': cell_total == net},
    }


def summarize(matrix):
    """4분면 해석 요약 — 표시 순서 고정(제공 → 수령 → 자기담보 → 무관 → 구분불가)."""
    order = [
        (COMPANY, THIRD),      # 물상보증 제공 — 우발부채, 가장 먼저 본다
        (MIXED, THIRD),        # 혼합(제3자채무) — 회사 물건이 타인 채무 담보에 포함
        (THIRD, COMPANY),      # 물상보증 수령
        (MIXED, COMPANY),      # 혼합(회사채무) — 제3자 물건분은 수령
        (COMPANY, COMPANY),    # 자기담보
        (THIRD, THIRD),        # 회사 무관
    ]
    out = []
    seen = set()
    for axes in order:
        cell = matrix['셀'].get(axes)
        label, action = quadrant_of(*axes)
        seen.add(axes)
        out.append({
            '구분': label, '조치': action,
            '금액': cell['금액'] if cell else 0,
            '그룹수': cell['그룹수'] if cell else 0,
            '물건수': cell['물건수'] if cell else 0,
            '근저당건수': cell['근저당건수'] if cell else 0,
        })
    # 혼합·미상이 섞인 나머지 셀은 '구분 불가' 한 줄로 합산한다.
    rest = [c for axes, c in matrix['셀'].items() if axes not in seen]
    label, action = UNCLASSIFIED
    out.append({
        '구분': label, '조치': action,
        '금액': sum(c['금액'] for c in rest),
        '그룹수': sum(c['그룹수'] for c in rest),
        '물건수': sum(c['물건수'] for c in rest),
        '근저당건수': sum(c['근저당건수'] for c in rest),
    })
    return out
