#!/usr/bin/env python3
"""LLM verdict 확정 적용기 (v0.4) — "식별=LLM, 최종확정=Python 재계산"의 확정 단계.

사용법:
    python apply_verdicts.py <bundle.json> <verdicts.json> <properties.json> <mortgages.json> \
        [--out-prefix <접두사>]

동작:
    1. 무결성 검증(verify_integrity): verdict.번들해시 == 번들 재계산 해시, 번들.파서버전 ==
       현재 파서 버전, **properties/mortgages JSON sha256 == 번들 기록값**(재파싱/수기수정 차단),
       verdict 판단ID 중복·잉여 없음, 근저당 (고유번호,순위번호) 중복 없음. 실패 → 적용 거부.
       ※ 입력PDF sha256 은 기록용 — 여기서 재검증하지 않는다(SKILL.md 명시).
    2. 필드별 guard (authority 는 Python):
       - 공담: self·멤버 모두 목록·LLM 그룹 미소속 + 채권최고액·근저당권자(정규화) 일치 +
         서술문-소재지 결정형 상호검증. 설정일자 상이는 병합하되 **검토필요**(담보추가 확인).
         기승인 그룹의 역방향 재제안은 '중복제안'으로 재분류(검토 불요 — 경보 피로 방지).
       - 소재지: closed-set 후보 값 복원 + 주소 형식검증 + 을구 어휘 오염 검사 → 원자적 전파.
         선택 0 = '판단불가' — 현재값이 옳다는 뜻이 아니므로 **검토필요**로 플래그.
       - 소유자: enum(본인/제3자). 본인만 피감사회사소유=True.
    3. 신뢰도: {'high','med'} 만 적용. low·형식 위반 = 미적용(기존값 유지) + 검토필요.

출력:
    <접두사>_properties.final.json / <접두사>_mortgages.final.json /
    <접두사>_apply_report.json (Sheet6 원천 — 검토필요 bool·비고·PDF파일 포함)
"""

import json, re, os, sys, argparse
from datetime import datetime

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, 'reconfigure'):
        try:
            _s.reconfigure(encoding='utf-8')
        except (AttributeError, OSError):
            pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parse_registry_pdfs as P               # 파서버전·_ADDR·bundle_hash·해시 재사용
from grouping import build_joint_groups
import cpa_storage


def _norm_name(s):
    return re.sub(r'\s+', '', s or '')


def _loc_token(loc):
    """소재지의 말단 식별 토큰(동/리 + 지번) — 서술문 상호검증용. 예: '합성리 849' → '합성리849'."""
    m = re.search(r'([가-힣]+[동리]\s*산?\s*[\d-]+)', loc or '')
    return re.sub(r'\s+', '', m.group(1)) if m else ''


def verify_integrity(bundle, verdicts, props, morts, prop_path=None, mort_path=None):
    """적용 전 무결성 검증. 오류 문자열 리스트 반환(비면 통과)."""
    errs = []
    items = bundle.get('판단항목', [])
    calc = P.bundle_hash(items)
    if bundle.get('메타', {}).get('번들해시') != calc:
        errs.append('번들 파일이 변조/손상됨(내부 해시 불일치)')
    if verdicts.get('메타', {}).get('번들해시') != calc:
        errs.append('verdict 가 이 번들에 대한 판정이 아님(번들해시 불일치) — 번들 재생성 후 재판정 필요')
    if bundle.get('메타', {}).get('파서버전') != P.__version__:
        errs.append(f"파서버전 불일치(번들 {bundle.get('메타', {}).get('파서버전')} ≠ "
                    f"현재 {P.__version__}) — 재파싱+번들 재생성 필요")
    # 파싱 JSON 바인딩 — 번들 생성 시점의 JSON 과 동일 파일인지 (재파싱/수기수정 차단)
    jh = bundle.get('메타', {}).get('입력JSON') or {}
    for label, path, key in (('properties', prop_path, 'properties_sha256'),
                             ('mortgages', mort_path, 'mortgages_sha256')):
        if jh.get(key) and path:
            if P._pdf_sha256(path) != jh[key]:
                errs.append(f'{label} JSON 이 번들 생성 시점과 다름(sha256 불일치) — '
                            f'재파싱·수기수정 후에는 번들 재생성부터 다시')
    uid_set = {p['고유번호'] for p in props}
    missing = [it['판단ID'] for it in items if it['고유번호'] not in uid_set]
    if missing:
        errs.append(f'번들 항목의 고유번호가 properties 에 없음: {missing[:5]}')
    # verdict 판단ID 중복/잉여 — 상충 판정의 침묵 덮어쓰기 방지
    vids = [v.get('판단ID') for v in verdicts.get('판정', [])]
    dups = sorted({x for x in vids if vids.count(x) > 1})
    if dups:
        errs.append(f'verdict 에 중복 판단ID: {dups} — 상충 판정 정리 후 재시도')
    item_ids = {it['판단ID'] for it in items}
    extra = sorted(set(vids) - item_ids - {None})
    if extra:
        errs.append(f'번들에 없는 판단ID 가 verdict 에 있음: {extra[:5]}')
    # 근저당 키 중복(동일 물건 등기부 사본 이중 입력 등) — dict 화 시 침묵 소실 방지
    mkeys = [(m['고유번호'], m['순위번호']) for m in morts]
    mdup = sorted({k for k in mkeys if mkeys.count(k) > 1})
    if mdup:
        errs.append(f'mortgages 에 (고유번호,순위번호) 중복: {mdup[:3]} — 입력 PDF 중복 여부 확인')
    return errs


def verify_joint(item, choice_nums, mortgages_by_key):
    """공담 guard. 반환: (승인 멤버 키 리스트, 기각 사유 리스트, 노트 리스트)"""
    approved, reasons, notes = [], [], []
    self_key = (item['고유번호'], item['순위번호'])
    self_m = mortgages_by_key.get(self_key)
    if self_m is None:
        return [], ['자기 근저당 레코드 없음'], []
    # self 도 목록·LLM 그룹에 미소속이어야 함 — 체인 병합(A–B 후 B–C)이 그룹키를 덮어써
    # 증적과 final 이 어긋나는 것을 차단(전이 병합 미지원 — 명시적 기각).
    if self_m.get('공동담보목록') or self_m.get('LLM공담그룹'):
        return [], ['자기 근저당이 이미 공담 그룹 소속 — 전이 병합 미지원, 기각'], []
    desc = re.sub(r'\s+', '', item.get('원문발췌') or '')
    cand_by_no = {c['번호']: c for c in item.get('후보', [])}
    for n in choice_nums:
        c = cand_by_no.get(n)
        if c is None:
            reasons.append(f'후보 {n} 없음(closed-set 위반)')
            continue
        mk = (c['고유번호'], c['순위번호'])
        mm = mortgages_by_key.get(mk)
        if mm is None:
            reasons.append(f'후보 {n}: 근저당 레코드 없음')
            continue
        # guard a: 목록·LLM 그룹 재병합 금지. 접수 그룹은 아래에서 전체 확장한다.
        if mm.get('공동담보목록') or mm.get('LLM공담그룹'):
            reasons.append(f'후보 {n}: 이미 다른 공담 그룹 소속 — 이중 dedup 방지 기각')
            continue
        # guard b: 금액·권리자 일치
        if mm['채권최고액'] != self_m['채권최고액']:
            reasons.append(f'후보 {n}: 채권최고액 불일치')
            continue
        if _norm_name(mm.get('근저당권자')) != _norm_name(self_m.get('근저당권자')):
            reasons.append(f'후보 {n}: 근저당권자 불일치')
            continue
        # guard c: 서술문-소재지 결정형 상호검증
        tok = _loc_token(mm.get('소재지'))
        if not tok:
            reasons.append(f'후보 {n}: 상대 소재지에서 지번 토큰 추출 실패 — 검증 불가 기각')
            continue
        if not re.search(re.escape(tok) + r'(?![\d-])', desc):
            reasons.append(f'후보 {n}: 공동담보 서술 원문에 상대 소재지 토큰 미등장 — 기각')
            continue
        # 동일 지번에 전유 호실이 여럿이면 지번만으로 병합할 수 없다.
        unit_tokens = [n + suffix for n, suffix in re.findall(
            r'(?:제\s*)?([가-힣A-Za-z]*\d+)\s*(동|층|호)', mm.get('소재지') or '')]
        if mm.get('유형') == '집합건물' and not any(t.endswith('호') for t in unit_tokens):
            reasons.append(f'후보 {n}: 전유 호실 식별정보 없음 — 기각')
            continue
        if any(not re.search(r'(?<![\dA-Za-z])(?:제)?' + re.escape(t), desc) for t in unit_tokens):
            reasons.append(f'후보 {n}: 공동담보 서술에 상대 동·층·호 불일치 — 기각')
            continue
        # guard d: 설정일자 상이 = 병합하되 검토필요(담보추가 vs 별건 근저당 — 원본 대조 필수)
        if (mm.get('설정일자') or '') != (self_m.get('설정일자') or ''):
            notes.append(f'후보 {n}: 설정일자 상이 — 담보추가 여부 원본·금융조회서 대조 필수')
        approved.append(mk)
    if approved:
        # 접수번호로 이미 묶인 그룹은 일부만 떼면 남은 물건이 다시 Net에 계상된다.
        # 검증된 상대가 속한 접수 그룹 전체를 원자적으로 확장한다(목록·LLM 그룹은 제외).
        touched = set(approved + [self_key])
        expanded = set(touched)
        for group in build_joint_groups(list(mortgages_by_key.values())).values():
            keys = {(m['고유번호'], m['순위번호']) for m in group['items']}
            if group['key_type'] == '접수' and keys & touched:
                if any(m['채권최고액'] != self_m['채권최고액'] or
                       _norm_name(m.get('근저당권자')) != _norm_name(self_m.get('근저당권자'))
                       for m in group['items']):
                    return [], reasons + ['접수 그룹 구성원의 금액·권리자 불일치 — 전체 병합 기각'], notes
                expanded.update(keys)
        approved = sorted(expanded - {self_key})
    return approved, reasons, notes


def main():
    ap = argparse.ArgumentParser(description='LLM verdict 확정 적용 (guard + 병합)')
    ap.add_argument('bundle')
    ap.add_argument('verdicts')
    ap.add_argument('properties')
    ap.add_argument('mortgages')
    ap.add_argument('--out-prefix', default=None,
                    help='출력 접두사 (기본: properties 경로에서 _properties.json 제거)')
    args = ap.parse_args()
    out_prefix = args.out_prefix or re.sub(r'_properties\.json$', '', args.properties)
    try:
        cpa_storage.guard(out_prefix)
    except cpa_storage.StorageError as exc:
        ap.error(str(exc))

    from registry_image_gate import verify_proof, write_proof, proof_path
    try:
        image_proof = verify_proof(args.properties, args.mortgages)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'이미지 검토 미완료 — 판정 적용 거부: {exc}')
        sys.exit(5)

    bundle = json.load(open(args.bundle, encoding='utf-8'))
    verdicts = json.load(open(args.verdicts, encoding='utf-8'))
    props = json.load(open(args.properties, encoding='utf-8'))
    morts = json.load(open(args.mortgages, encoding='utf-8'))

    errs = verify_integrity(bundle, verdicts, props, morts,
                            prop_path=args.properties, mort_path=args.mortgages)
    if errs:
        print('적용 거부 — 무결성 검증 실패:')
        for e in errs:
            print(f'  ✗ {e}')
        sys.exit(1)

    items = bundle.get('판단항목', [])
    item_by_id = {it['판단ID']: it for it in items}
    v_by_id = {v['판단ID']: v for v in verdicts.get('판정', [])}
    mort_by_key = {(m['고유번호'], m['순위번호']): m for m in morts}
    prop_by_uid = {p['고유번호']: p for p in props}

    net_before = sum(v['amt'] for v in build_joint_groups(morts).values())

    report = {'메타': {'적용시각': datetime.now().strftime('%Y-%m-%d %H:%M KST'),
                       '번들해시': P.bundle_hash(items), '파서버전': P.__version__,
                       '판단주체': verdicts.get('메타', {}).get('판단주체', ''),
                       '판단시각': verdicts.get('메타', {}).get('판단시각', ''),
                       '루브릭': verdicts.get('메타', {}).get('루브릭', ''),
                       # 사후 재구성용 — 이 적용에 실제 사용된 입력 4파일의 지문
                       '입력파일_sha256': {
                           'bundle': P._pdf_sha256(args.bundle),
                           'verdicts': P._pdf_sha256(args.verdicts),
                           'properties': P._pdf_sha256(args.properties),
                           'mortgages': P._pdf_sha256(args.mortgages)}},
              '기록': []}

    def rec(item, status, chosen='', reason='', conf='', extra='', review=False):
        cand_summary = '; '.join(
            f"{c['번호']}={c.get('값') or (str(c.get('고유번호', ''))[-6:] + '/' + str(c.get('순위번호', '')))}"
            for c in item.get('후보', []))[:300]
        report['기록'].append({
            '판단ID': item['판단ID'], '필드': item['필드'], '고유번호': item['고유번호'],
            '순위번호': item.get('순위번호'),
            'PDF파일': prop_by_uid.get(item['고유번호'], {}).get('PDF파일', ''),
            '기존값': item.get('현재값', ''),
            '선택값': chosen, '근거': reason, '신뢰도': conf, '채택여부': status,
            '검토필요': bool(review), '비고': extra,
            '후보목록': cand_summary,
            '원문발췌': (item.get('원문발췌') or '')[:600],
        })

    for it in items:
        v = v_by_id.get(it['판단ID'])
        if v is None:
            rec(it, '미판정(기존값 유지)', review=True)
            continue
        conf = v.get('신뢰도', '')
        reason = v.get('근거', '')
        sel = v.get('선택')
        # 신뢰도 화이트리스트 — 'High'·오타 등 임의 문자열이 적용 경로를 타지 않게 한다.
        if conf not in ('high', 'med'):
            status = ('미적용(저신뢰 — 검토필수)' if conf == 'low'
                      else f'미적용(신뢰도 형식 위반: {conf!r})')
            rec(it, status, str(sel), reason, conf, review=True)
            continue

        if it['필드'] == '공담':
            nums = sel if isinstance(sel, list) else ([] if not sel else [sel])
            if not nums:
                rec(it, '해당없음(세트 외/매칭 불가 — 기존 그룹 유지)', '[]', reason, conf,
                    '공동담보 상대물건 세트 외 가능성 — 수동확인', review=True)
                continue
            approved, rejected, notes = verify_joint(it, nums, mort_by_key)
            if approved:
                gkey = f"llm_{it['판단ID']}"
                self_key = (it['고유번호'], it['순위번호'])
                for k in approved + [self_key]:
                    mort_by_key[k]['LLM공담그룹'] = gkey
                extra = '; '.join(notes + ([f'기각 {len(rejected)}건'] if rejected else []))
                rec(it, '채택(병합)', str(nums), reason, conf, extra,
                    review=bool(notes or rejected))  # 일부 기각도 검토표시에 남긴다.
            else:
                # 기승인 그룹의 역방향/잔여 재제안(전 후보가 '이미 그룹 소속')은 시스템이
                # 정상 처리한 대칭 아티팩트 — 진짜 검토필요와 분리해 경보 피로를 막는다.
                only_dup = all('이미' in r or '자기 근저당이 이미' in r for r in rejected)
                absorbed = ''
                if only_dup:
                    for n in nums:
                        c = next((c for c in it.get('후보', []) if c['번호'] == n), None)
                        if c:
                            g = mort_by_key.get((c['고유번호'], c['순위번호']), {}).get('LLM공담그룹')
                            if g:
                                absorbed = f'{g} 병합으로 흡수'
                                break
                    rec(it, '중복제안(기승인 그룹 소속 — 검토 불요)', str(nums), reason, conf,
                        absorbed, review=False)
                else:
                    rec(it, f'기각({"; ".join(rejected)})', str(nums), reason, conf, review=True)

        elif it['필드'] == '소재지':
            try:
                n = int(sel)
            except (TypeError, ValueError):
                n = -1
            if n == 0:
                # 0 은 '현재값이 옳다'가 아니라 '판단 불가' — 현재값 자체가 의심 신호이므로 검토필요.
                rec(it, '판단불가(현재값 미확정 — 원본 대조 필요)', '0', reason, conf, review=True)
                continue
            cand = next((c for c in it.get('후보', []) if c['번호'] == n), None)
            if cand is None:
                rec(it, f'기각(후보 {sel} 없음 — closed-set 위반)', str(sel), reason, conf, review=True)
                continue
            val = cand['값']
            if not re.search(P._ADDR, val):
                rec(it, '기각(주소 형식검증 실패)', val, reason, conf, review=True)
                continue
            if P._EUL_VOCAB_RE.search(it.get('원문발췌', '')) and cand.get('출처') == '표시번호 불명':
                rec(it, '기각(을구 오염 의심 후보 — 출처 불명)', val, reason, conf, review=True)
                continue
            p = prop_by_uid[it['고유번호']]
            p['소재지'] = val
            p['LLM판정_소재지'] = True
            for m in morts:                       # 원자적 전파 — 시트 간 불일치 방지
                if m['고유번호'] == it['고유번호']:
                    m['소재지'] = val
            rec(it, '채택', val, reason, conf, cand.get('출처', ''))

        elif it['필드'] == '소유자':
            try:
                n = int(sel)
            except (TypeError, ValueError):
                n = -1
            label = {1: '본인', 2: '제3자'}.get(n)
            if n == 0:
                rec(it, '판단불가(현재값 미확정 — 원본 대조 필요)', '0', reason, conf, review=True)
                continue
            if label is None:
                rec(it, f'기각(enum 위반: {sel})', str(sel), reason, conf, review=True)
                continue
            p = prop_by_uid[it['고유번호']]
            if p.get('소유자확인필요'):
                rec(it, '기각(현 소유자·지분 미확정)', label, reason, conf,
                    '회사 여부 선택만으로 현 소유자 목록·잔여 지분을 복원할 수 없음', review=True)
                continue
            p['LLM소유자분류'] = label
            p['피감사회사소유'] = (label == '본인')
            # 근거에 '관계사 의심'이 있으면 특수관계자 대조 검토필요로 승격
            related = '관계사' in (reason or '')
            rec(it, '채택', label, reason, conf,
                '관계사 의심 — 관계사 리스트 대조 필요' if related else '', review=related)

    p_out = f'{out_prefix}_properties.final.json'
    m_out = f'{out_prefix}_mortgages.final.json'
    r_out = f'{out_prefix}_apply_report.json'
    net_after = sum(v['amt'] for v in build_joint_groups(morts).values())
    report['메타']['Net_적용전'] = net_before
    report['메타']['Net_적용후'] = net_after
    json.dump(props, open(p_out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    json.dump(morts, open(m_out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    json.dump(report, open(r_out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    image_context = {'manifest': image_proof['manifest'], 'dependencies': dict(image_proof['dependencies'])}
    for key in ('document_classifications', 'classification_report'):
        if key in image_proof:
            image_context[key] = image_proof[key]
    for path in (args.bundle, args.verdicts, args.properties, args.mortgages, r_out):
        image_context['dependencies'][str(__import__('pathlib').Path(path).resolve())] = P._pdf_sha256(path)
    write_proof(p_out, m_out, image_context, image_proof['sources'], parent=proof_path(args.properties))

    stats = {}
    for r in report['기록']:
        k = r['채택여부'].split('(')[0]
        stats[k] = stats.get(k, 0) + 1
    n_review = sum(1 for r in report['기록'] if r['검토필요'])
    print(f'적용 완료: {len(report["기록"])}항목 — {stats} | 검토필요 {n_review}건')
    print(f'순 담보금액 (Net): 적용 전 {net_before:,}원 → 적용 후 {net_after:,}원')
    if net_after != net_before:
        print('  ⚠ LLM 병합이 Net 을 변경 — 확정 전 원본 을구·금융조회서 대사 필수(Sheet6 참조)')
    print(f'출력: {p_out} / {m_out} / {r_out}')
    print('워크페이퍼 생성 시 --verdict-report 로 report 를 전달하면 Sheet6(LLM 판단근거)가 추가됩니다.')


if __name__ == '__main__':
    main()
