"""등기 구역·순위·등기목적에 기반한 평문 행 복원. 파일/회사 식별자는 사용하지 않는다.

표 셀 추출이 놓친 행만 보완한다. 명확한 순위·등기목적 앵커가 없으면 복원하지
않으며 합쳐진 복수 설정이나 금액을 추측해서 분리하지 않는다.
"""
import re

SECTION = re.compile(r'[【\[]\s*(표\s*제\s*부|갑\s*구|을\s*구)\s*[】\]]')
STOP = re.compile(r'주요\s*등기사항\s*요약|[【\[]\s*공동담보목록')
PURPOSE = (r'(?:소유권|공유자전원지분전부|근저당권|저당권|전세권|지상권|지역권|가압류|압류|'
           r'가처분|강제경매|임의경매|경매개시|신탁|가등기|환매)')
REFERENCE_ATOM = r'\d+번?(?:\(\d+\))?'
REFERENCE = REFERENCE_ATOM + r'(?:(?:,|·|및|내지|~)' + REFERENCE_ATOM + r')*'
START = re.compile(r'^\s*(\d+(?:-\d+)?(?:\s*\(\d+\))?)(?:\s*\(\s*전\s*\d+\s*\))?\s*'
                   r'((?:\d+\s*번?(?:\s*(?:,|·|및|내지|~)\s*\d+\s*번?)*\s*)?' + PURPOSE + r'.*)$')
HEADER = re.compile(r'순\s*위\s*번\s*호\s*등\s*기\s*목\s*적\s*접\s*수\s*'
                    r'등\s*기\s*원\s*인\s*권\s*리\s*자(?:\s*및\s*기\s*타\s*사\s*항)?')


def rank_key(rank):
    match = re.match(r'(\d+)(?:-(\d+))?(?:\s*\((\d+)\))?', str(rank))
    return tuple(int(p or 0) for p in match.groups())


def entry_identity(rank, purpose):
    rank = re.match(r'\d+(?:-\d+)?(?:\(\d+\))?', compact(rank))[0]
    item = re.match(r'^\((\d+)\)', normalize_purpose(purpose))
    return rank + f'({item[1]})' if item and '(' not in rank else rank


def compact(text):
    return re.sub(r'\s+', '', text or '')


def normalize_purpose(text):
    text = re.sub(r'등\s*기\s*목\s*적|권\s*리\s*자\s*및\s*기\s*타\s*사\s*항|접\s*수', '', text or '')
    return compact(text)


def rank_references(reference):
    reference = compact(reference)
    span = re.fullmatch(r'(\d+)번?(?:내지|~)(\d+)번?', reference)
    if span:
        first, last = map(int, span.groups())
        if first > last or last - first > 1000:
            raise ValueError('말소 대상 순위 범위를 확인할 수 없습니다.')
        return [str(n) for n in range(first, last + 1)]
    if '내지' in reference or '~' in reference:
        raise ValueError('목록과 범위가 혼합된 말소 순위는 원본 대조 후 분리하세요.')
    return [str(int(n)) + (f'({int(item)})' if item else '')
            for n, item in re.findall(r'(\d+)번?(?:\((\d+)\))?', reference)]


def cancellation_pattern(kind_pattern):
    unit = r'(?:' + REFERENCE + r')(?:\([^)]*\))?(?:' + kind_pattern + r')'
    return re.compile(r'(' + unit + r'(?:(?:,|·|및)' + unit + r')*)(?:등기)?말소(?:회복)?')


def cancellation_refs(purpose, kind_pattern):
    # '1,2번압류등기말소'와 '1번압류,2번압류등기말소' 모두 각 순위를 취소한다.
    unit = r'(' + REFERENCE + r')(?:\([^)]*\))?(' + kind_pattern + r')'
    return [(rank, kind) for match in cancellation_pattern(kind_pattern).finditer(normalize_purpose(purpose))
            for refs, kind in re.findall(unit, match.group(1)) for rank in rank_references(refs)]


def purpose_of(body):
    # 접수일·권리자 표지 앞을 등기목적으로 구분하며 값을 보간하지 않는다.
    return re.split(r'\d{4}\s*년|소\s*유\s*자\s|공\s*유\s*자\s|수\s*탁\s*자\s|'
                    r'채\s*권\s*최\s*고\s*액|채\s*무\s*자\s|근\s*저\s*당\s*권\s*자\s|권\s*리\s*자\s', body, maxsplit=1)[0].strip()


def text_entries(text, section):
    """페이지의 반복 머리말과 구역 경계를 지키며 [순위, 목적, 원문, 접수] 반환."""
    state, blocks, current = None, [], None
    for raw in text.splitlines():
        line = HEADER.sub('', raw).strip()
        heading = SECTION.search(line)
        if heading:
            state = compact(heading.group(1))
            current = None
            line = line[heading.end():].strip()
        if STOP.search(line):
            state, current = None, None
        if state != section or not line:
            continue
        match = START.match(line)
        if match:
            rank, body = match.groups()
            current = [rank, body, [line]]
            blocks.append(current)
        elif current is not None:
            # 본문 계속 행은 보존하지만 페이지 번호/발급 안내는 권리 내용에 넣지 않는다.
            if not re.search(r'열람일시|발급일시|관할등기소|이\s*하\s*여\s*백|^\d+\s*/\s*\d+$|^\[', line):
                current[2].append(line)
    rows = []
    for rank, first, lines in blocks:
        body = '\n'.join(lines)
        receipt = re.search(r'\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일\s*제?\s*\d+\s*호', body)
        receipt_text = receipt.group() if receipt else ''
        if not receipt_text:
            # 표의 첫 줄에 접수일/원인일, 다음 줄에 접수번호가 있는 서식.
            date = re.search(r'\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일', first)
            numbers = re.findall(r'제\s*\d+\s*호', body)
            if date and len(numbers) == 1:
                receipt_text = date.group() + ' ' + numbers[0]
        purpose = purpose_of(first)
        if compact(purpose) == '공유자전원지분전부' and len(lines) > 1 and re.match(r'^이전(?:\s|$)', lines[1]):
            purpose += '이전'
        rows.append([rank, purpose, body, receipt_text])
    return rows


def belongs(purpose, section):
    p = compact(purpose)
    if section == '갑구':
        return bool(re.search(r'소유권|공유자전원지분전부|가압류|압류|가처분|경매|신탁|가등기|환매', p))
    return bool(re.search(r'근저당|저당|전세권|지상권|지역권', p))


def supplement(entries, text, section):
    """인식된 표 행은 유지하고, 같은 구역에서 빠진 순위만 평문으로 복원한다."""
    present = {entry_identity(row[0], row[1])
               for row in entries if re.match(r'^\d', row[0]) and belongs(row[1], section)}
    additions = [row for row in text_entries(text, section) if compact(row[0]) not in present]
    return sorted([*entries, *additions], key=lambda row: rank_key(row[0]))


def mortgage_blocks(entries, setting_pattern):
    """主순위와 (항목번호)를 함께 식별하여 설정·부기·말소를 각각 연결한다."""
    settings = {}
    for rank, purpose, call, receipt in entries:
        p = normalize_purpose(purpose)
        identity = entry_identity(rank, p)
        p = re.sub(r'^\(\d+\)', '', p)
        if '-' not in rank.split()[0] and setting_pattern.match(p):
            if identity in settings:
                raise ValueError('동일 근저당 항목이 중복되었습니다: ' + identity)
            settings[identity] = {'text': call, 'receipt': receipt, 'share': '지분' in p.split('근저당권설정')[0]}
    active = set(settings)
    def resolve(reference):
        if '(' in reference:
            return [reference] if reference in settings else []
        return [k for k in settings if re.match(r'\d+', k)[0] == reference]
    for rank, purpose, call, receipt in sorted(entries, key=lambda row: rank_key(row[0])):
        p = normalize_purpose(purpose)
        refs = cancellation_refs(p, r'(?:[^,·]*?지분(?:전부|일부)?)?근저당권설정')
        if refs and not re.search(r'가처분|예고|청구', p):
            for reference, _ in refs:
                targets = resolve(reference)
                if '회복' in p:
                    if not targets:
                        raise ValueError('근저당 말소회복의 원 설정행이 없습니다. 원본 전체 행을 확인하세요.')
                    active.update(targets)
                else:
                    active.difference_update(targets)
            continue
        if '-' in rank.split()[0] and '근저당권' in p:
            match = re.match(r'(\d+)번?(?:\((\d+)\))?', p)
            reference = (match[1] + (f'({match[2]})' if match[2] else '')) if match else rank.split('-')[0]
            targets = resolve(reference)
            if len(targets) > 1:
                raise ValueError('복수 근저당 부기의 대상 항목번호를 확인할 수 없습니다: ' + rank)
            for target in targets:
                settings[target]['text'] += ' ' + call
    return {k: settings[k] for k in sorted(active, key=rank_key)}, set(settings)


def current_seizures(entries):
    """갑구의 압류/가압류 설정·말소·말소회복을 순위별로 대조한다."""
    active, known = {}, {}
    for rank, purpose, *_ in sorted(entries, key=lambda row: rank_key(row[0])):
        p = normalize_purpose(purpose)
        refs = cancellation_refs(p, r'(?:가)?압류')
        if refs and not re.search(r'가처분|예고|청구', p):
            for target, kind in refs:
                if '회복' in p:
                    if target not in known:
                        raise ValueError('압류 말소회복의 원 설정행이 없습니다. 원본 전체 행을 확인하세요.')
                    active[target] = known[target]
                else:
                    active.pop(target, None)
            continue
        setting = re.fullmatch(r'(가압류|압류)', p)
        if setting and '-' not in rank:
            key = str(int(re.match(r'\d+', rank).group()))
            known[key] = setting.group(1)
            active[key] = setting.group(1)
    return [{'순위번호': rank, '종류': active[rank]} for rank in sorted(active, key=int)]


def other_encumbrances(text, patterns):
    """기타부담의 명시된 순위별 말소를 반영하되 확인 불가 문구는 감지 경고로 남긴다."""
    triggers = {'전세권': '전세권', '지상권': '지상권', '경매개시': '(?:강제|임의)?경매개시결정',
                '신탁': '신탁', '가등기': '(?:소유권이전청구권)?가등기', '환매특약': '환매특약'}
    cancel_patterns = {kind: cancellation_pattern(trigger + r'(?:설정)?')
                       for kind, trigger in triggers.items()}
    active, known = set(), set()
    entries = [(section, row) for section in ('갑구', '을구') for row in text_entries(text, section)]
    if not entries:
        # 구역/순위 없는 단편은 권리 상태를 확정하지 않는다. 명확한 말소 표현 자체만 제외한다.
        clean = compact(text)
        for pattern in cancel_patterns.values():
            clean = pattern.sub(lambda m: m.group() if '회복' in m.group() else '', clean)
        return [kind for kind, pattern in patterns if re.search(pattern, clean)]
    for section, (rank, purpose, call, _) in entries:
        source = compact(re.sub(r'^\s*\d+(?:-\d+)?\s*', '', call).replace('\n', ';'))
        purpose = normalize_purpose(purpose)
        for kind, pattern in patterns:
            cancellations = list(cancel_patterns[kind].finditer(source))
            positive = cancel_patterns[kind].sub('', source if kind == '신탁' else purpose)
            key = (section, kind, rank)
            if re.search(pattern, positive):
                active.add(key)
                known.add(key)
            for match in cancellations:
                # 말소청구 가처분/예고 문맥은 소멸로 단정하지 않는다.
                if re.search(r'가처분|예고|말소청구', purpose):
                    continue
                for target_rank, _ in cancellation_refs(match.group(), triggers[kind] + r'(?:설정)?'):
                    target = (section, kind, target_rank)
                    if '회복' in match.group():
                        if target not in known:
                            raise ValueError('기타부담 말소회복의 원 설정행이 없습니다. 원본 전체 행을 확인하세요.')
                        active.add(target)
                    else:
                        active.discard(target)
    return [kind for kind, _ in patterns if any(key[1] == kind for key in active)]
