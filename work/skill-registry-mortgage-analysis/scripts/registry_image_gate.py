"""전체 PDF 이미지 판독을 파서 입력과 최종 결과까지 연결한다.

이미지를 보는 주체는 스킬 실행 에이전트/사람이다. 이 모듈은 이미지와 판독
기록의 범위·무결성을 검증하며 미판독을 '취소선 없음'으로 바꾸지 않는다.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import html
from pathlib import Path
import sys

import pdfplumber
import cpa_storage
import registry_review as review
from registry_screening import screen, validate_screening
from registry_document_types import non_registry_pages

ReviewError = review.ReviewError
require, read_json, write_json, sha256 = review.require, review.read_json, review.write_json, review.sha256


def inventory(root):
    root = Path(root).resolve()
    require(root.is_dir(), '입력 PDF 폴더가 필요합니다.')
    return [{'file': str(p.relative_to(root)), 'sha256': sha256(p)}
            for p in sorted(root.rglob('*'), key=lambda p: str(p).casefold())
            if p.is_file() and p.suffix.lower() == '.pdf']


def prepare_batch(root, output, dpi=200):
    root, output = Path(root).resolve(), review._new_dir(output)
    require(not output.is_relative_to(root), '검토 폴더는 입력 PDF 폴더 밖에 두세요.')
    files = inventory(root)
    require(files, 'PDF 입력이 없습니다.')
    output.mkdir()
    documents, errors = [], []
    for i, item in enumerate(files, 1):
        pdf = root / item['file']
        dest = output / f'doc-{i:04d}' / 'screen'
        candidates = [p for p in pdf.parent.iterdir() if p.stem.casefold() == pdf.stem.casefold()
                      and p.suffix.lower() in {'.html', '.htm'}]
        entry = {**item, 'screen_bundle': str(dest / 'screen-bundle.json'),
                 'screening': str(dest / 'screening.json'), 'parts': []}
        try:
            require(len(candidates) <= 1, '같은 이름의 OCR HTML이 여러 개입니다.')
            screen(pdf, dest, candidates[0] if candidates else None, dpi)
        except Exception as exc:
            errors.append({'file': item['file'], 'error': str(exc)})
        documents.append(entry)
    manifest = {'schema': 1, 'input_root': str(root), 'documents': documents,
                'preparation_errors': errors}
    write_json(output / 'manifest.json', manifest)
    return {'manifest': str(output / 'manifest.json'), 'pdfs': len(files), 'errors': errors,
            'status': 'awaiting_image_screening'}


def native_html(pdf, target):
    """네이티브 텍스트·표를 판독용 HTML로 옮긴다. 내용 누락은 이미지 대조로 확인한다."""
    parts = ['<!doctype html><html lang="ko"><meta charset="utf-8">']
    with pdfplumber.open(pdf) as doc:
        for n, page in enumerate(doc.pages, 1):
            blocks, tables = [], page.find_tables()
            for table in tables:
                rows = table.extract()
                content = '<table>' + ''.join('<tr>' + ''.join(
                    '<td>' + html.escape(c or '').replace('\n', '<br>') + '</td>' for c in row
                ) + '</tr>' for row in rows) + '</table>'
                blocks.append((table.bbox[1], table.bbox[0], content))
            words = [w for w in page.extract_words() if not any(
                t.bbox[0] <= (w['x0'] + w['x1']) / 2 <= t.bbox[2] and
                t.bbox[1] <= (w['top'] + w['bottom']) / 2 <= t.bbox[3] for t in tables)]
            lines = []
            for word in sorted(words, key=lambda w: (w['top'], w['x0'])):
                if not lines or abs(lines[-1][0]['top'] - word['top']) > 3:
                    lines.append([])
                lines[-1].append(word)
            for line in lines:
                text = ' '.join(w['text'] for w in sorted(line, key=lambda w: w['x0']))
                blocks.append((line[0]['top'], line[0]['x0'], '<p>' + html.escape(text) + '</p>'))
            require(blocks, f'{n}쪽 텍스트가 없습니다. OCR HTML 또는 이미지 전사가 필요합니다.')
            parts.append(f'<section id="page-{n}"><div class="text-col">' +
                         ''.join(b[2] for b in sorted(blocks)) + '</div></section>')
    Path(target).write_text('\n'.join(parts) + '</html>', encoding='utf-8')


def needs_detail(bundle, screening):
    return bool(bundle['markup_hints'] or any(p['presence'] != 'absent' for p in screening['pages']))


def prepare_details(manifest_path):
    manifest = read_json(manifest_path)
    results = []
    for entry in manifest['documents']:
        try:
            bundle, screening = validate_screening(entry['screen_bundle'], entry['screening'])
            excluded = non_registry_pages(screening)
            if len(excluded) == bundle['pdf_page_count']:
                results.append({'file': entry['file'], 'route': 'excluded_non_registry', 'pages': excluded})
                continue
            if excluded and not entry['parts']:
                results.append({'file': entry['file'], 'route': 'needs_partition',
                                'error': '비등기 첨부가 섞여 있습니다. 문서 종류 판정에 따라 registry_inputs.py partition을 실행하세요.'})
                continue
            if not needs_detail(bundle, screening) and not entry.get('structural_review'):
                results.append({'file': entry['file'], 'route': 'text'})
                continue
            if not entry['parts']:
                dest = Path(entry['screen_bundle']).parent.parent / 'detail'
                source = bundle['ocr']
                if not source:
                    source = dest.parent / 'native.html'
                    native_html(bundle['pdf'], source)
                review.prepare(bundle['pdf'], source, dest, dpi=bundle['dpi'])
                entry['parts'] = [{'bundle': str(dest / 'bundle.json'), 'review': str(dest / 'review.json')}]
            results.append({'file': entry['file'], 'route': 'detail', 'parts': entry['parts']})
        except Exception as exc:
            results.append({'file': entry['file'], 'error': str(exc)})
    write_json(manifest_path, manifest)
    return results


def validate_job(manifest_path, input_root=None):
    """매번 원본 폴더를 재스캔해 PDF/페이지 누락·교체를 차단한다. 출력 생성 없음."""
    manifest_path = Path(manifest_path).resolve()
    manifest = read_json(manifest_path)
    require(manifest.get('schema') == 1, '이미지 검토 manifest 형식이 다릅니다.')
    root = Path(manifest['input_root']).resolve()
    require(input_root is None or Path(input_root).resolve() == root, '검토한 PDF 폴더와 분석 입력 폴더가 다릅니다.')
    entries = manifest['documents']
    require(entries and inventory(root) == [{'file': e['file'], 'sha256': e['sha256']} for e in entries],
            '대상 PDF가 누락·추가·변경되었습니다. 전체 입력을 다시 준비하세요.')
    dependencies = {str(manifest_path): sha256(manifest_path)}
    sources = []

    def bind(path):
        path = str(Path(path).resolve())
        dependencies[path] = sha256(path)

    for entry in entries:
        bundle, screening = validate_screening(entry['screen_bundle'], entry['screening'])
        pdf = root / entry['file']
        require(Path(bundle['pdf']).resolve() == pdf.resolve() and bundle['pdf_sha256'] == entry['sha256'],
                '사전 판독과 원본 PDF의 연결이 다릅니다.')
        for p in [pdf, entry['screen_bundle'], entry['screening'], bundle.get('ocr')]:
            if p:
                bind(p)
        for page in bundle['pages']:
            bind(Path(entry['screen_bundle']).parent / page['image'])
        non_registry = non_registry_pages(screening)
        if len(non_registry) == bundle['pdf_page_count']:
            require(not entry.get('parts'), '비등기 문서 전체 제외와 등기부 상세 입력이 충돌합니다.')
            continue
        require(not non_registry or entry.get('structural_review'),
                '비등기 첨부가 섞인 PDF는 문서 종류 판정에 따라 물건·첨부 분리가 필요합니다.')
        detailed = needs_detail(bundle, screening) or bool(entry.get('structural_review'))
        if not detailed:
            require(not entry.get('parts'), '상세 판독 기록이 있는데 취소선 없음으로 우회할 수 없습니다.')
            if bundle['ocr']:
                pages = review.extract_units(bundle['ocr'])
                require([p['page'] for p in pages] == list(range(1, bundle['pdf_page_count'] + 1)),
                        'OCR 페이지가 원본 전체 쪽수와 다릅니다.')
            sources.append({'file': entry['file'], 'pdf': str(pdf), 'route': 'text',
                            'path': bundle['ocr'] or str(pdf), 'pages': list(range(1, bundle['pdf_page_count'] + 1)),
                            'reviewer': screening['reviewer']})
            continue
        require(entry.get('parts'), f"{entry['file']}: 취소선/불확실 항목의 상세 이미지 판독이 필요합니다.")
        covered, strikes = [], set()
        for part in entry['parts']:
            detail, record, units, audit = review.validate(part['bundle'], part['review'])
            require(Path(detail['pdf']).resolve() == pdf.resolve() and detail['pdf_sha256'] == entry['sha256'],
                    '상세 판독과 사전 판독의 원본 PDF가 다릅니다.')
            mapping = {p['page']: p['source_page'] for p in detail['pages']}
            covered.extend(mapping.values())
            for a in audit:
                if a['decision']['strike_scope'] != 'none':
                    strikes.add(mapping[a['unit']['page']])
            for p in [part['bundle'], part['review'], detail['ocr']]:
                bind(p)
            for page in detail['pages']:
                bind(Path(part['bundle']).parent / page['image'])
            expected = record.get('analysis_expectations')
            require(isinstance(expected, dict) and isinstance(expected.get('mortgages'), list),
                    '상세 판독에 analysis_expectations.mortgages(현행 순위·금액 목록)가 필요합니다.')
            require('owner' in expected and 'location' in expected and 'other_encumbrances' in expected and 'seizures' in expected,
                    '상세 판독에서 현 소유자·소재지·기타부담·seizures(현행 압류)의 예상 결과를 확인하세요.')
            require(isinstance(expected['owner'], str) and isinstance(expected['location'], str)
                    and isinstance(expected['other_encumbrances'], list), '현행 예상값의 형식이 올바르지 않습니다.')
            require(all(isinstance(m, dict) and set(m) == {'rank', 'amount'}
                        and isinstance(m['rank'], str) and type(m['amount']) is int and m['amount'] >= 0
                         for m in expected['mortgages']), '근저당 예상값은 rank 문자열·amount 원화 정수 목록이어야 합니다.')
            require(isinstance(expected['seizures'], list) and all(
                isinstance(s, dict) and set(s) == {'rank', 'kind'} and isinstance(s['rank'], str)
                and s['rank'].isdigit() and s['kind'] in ('압류', '가압류') for s in expected['seizures']),
                'seizures는 rank 문자열·kind(압류/가압류) 목록이어야 합니다. 없으면 빈 목록을 기록하세요.')
            require(len({s['rank'] for s in expected['seizures']}) == len(expected['seizures']),
                    '압류 예상 순위가 중복됩니다.')
            sources.append({'file': entry['file'], 'pdf': str(pdf), 'route': 'detail', **part,
                            'pages': list(mapping.values()), 'registry_id': record['registry_id'],
                            'expected': expected, 'reviewer': record['reviewer'], 'as_of': record['as_of']})
        attachments = entry.get('attachments', [])
        if attachments:
            require(entry.get('structural_review'), '첨부 제외에는 구조 이미지 판독 사유가 필요합니다.')
            for page in attachments:
                require(page.get('kind') == 'attachment' and page.get('reason'), '첨부 제외 사유가 필요합니다.')
                review._evidence(page.get('evidence'), {page['page']})
        if entry.get('structure_plan'):
            require(sha256(entry['structure_plan']) == entry['structure_plan_sha256'], '구조 판독 계획이 변경되었습니다.')
            bind(entry['structure_plan'])
        excluded_pages = [p['page'] for p in attachments]
        require(sorted(excluded_pages) == non_registry, '첨부 제외 페이지가 이미지 문서 종류 판정과 다릅니다.')
        require(sorted(covered + excluded_pages) == list(range(1, bundle['pdf_page_count'] + 1)),
                '취소선이 있는 PDF는 전체 페이지 상세 판독이 필요합니다. 물건별 분할의 누락·중복도 확인하세요.')
        require({p['page'] for p in screening['pages'] if p['presence'] == 'present'} - set(excluded_pages) <= strikes,
                '취소선 존재로 확인한 페이지에 상세 취소 범위 기록이 없습니다.')
    return sources, dependencies


def document_classifications(manifest_path):
    classifications = []
    for entry in read_json(manifest_path)['documents']:
        record = read_json(entry['screening'])
        classifications.extend({'file': entry['file'], 'page': p['page'], 'reviewer': record['reviewer'],
                                **p['classification']} for p in record['pages'])
    return classifications


def prepare_analysis(manifest_path, input_root, output_prefix):
    require(manifest_path, '--image-review manifest.json이 필요합니다. 전체 PDF 이미지 판독부터 진행하세요.')
    sources, dependencies = validate_job(manifest_path, input_root)
    dest = review._new_dir(str(output_prefix) + '_image_inputs')
    dest.mkdir()
    classifications = document_classifications(manifest_path)
    classification_path = dest / 'document-classification.json'
    write_json(classification_path, classifications)
    for i, source in enumerate(sources, 1):
        if source['route'] == 'detail':
            target = dest / f'part-{i:04d}'
            review.export_current(source['bundle'], source['review'], target)
            source['path'] = str(target / 'current.html')
            source['artifacts'] = {str(p): sha256(p) for p in target.iterdir() if p.is_file()}
        source['input_sha256'] = sha256(source['path'])
    return sources, {'manifest': str(Path(manifest_path).resolve()), 'dependencies': dependencies,
                     'classification_report': {'path': str(classification_path.resolve()), 'sha256': sha256(classification_path)},
                     'document_classifications': classifications}


def check_result(source, prop, mortgages):
    """이미지 판독으로 기대한 현행 값이 실제 파싱에서도 일치해야 완료된다."""
    if source['route'] == 'detail':
        expected = source['expected']
        require(prop['고유번호'] == source['registry_id'], '판독 물건과 파싱 고유번호가 다릅니다.')
        actual = sorted([{'rank': str(m['순위번호']), 'amount': m['채권최고액']} for m in mortgages], key=lambda m: m['rank'])
        require(actual == sorted(expected['mortgages'], key=lambda m: m['rank']),
                f'이미지 판독의 현행 근저당 순위·금액과 파싱 결과 불일치: {actual}')
        for field, key in [('현재소유자', 'owner'), ('소재지', 'location'), ('기타부담_감지', 'other_encumbrances')]:
            require(prop.get(field) == expected[key], f'이미지 판독의 {field}와 파싱 결과가 다릅니다.')
        require('seizures' in expected, '상세 이미지 판독에 seizures(현행 압류 목록)가 필요합니다.')
        seizures = [{'rank': s['순위번호'], 'kind': s['종류']} for s in prop.get('현행압류목록', [])]
        require(sorted(seizures, key=lambda s: s['rank']) == sorted(expected['seizures'], key=lambda s: s['rank'])
                and prop.get('현행_가압류_건수') == len(seizures),
                '이미지 판독의 현행 압류 순위·종류·건수와 파싱 결과가 다릅니다.')
        prop['OCR검토필요'] = False
        prop['원본열람일'] = source['as_of'].replace('-', '.')
        prop['갑구_특이사항'] = prop.get('갑구_특이사항', '').replace(
            ' | OCR 결과 사용 — 원본의 순위·말소·금액·표 병합 대조 필요', '')
    prop['PDF파일'] = source['file']
    prop['이미지검토'] = {'상태': '상세판독반영' if source['route'] == 'detail' else '전체쪽취소선없음',
                       '판독자': source['reviewer'], '원본페이지': source['pages'], '분석입력': source['path']}


def proof_path(properties_path):
    # 입력 쌍마다 별도 증거. *.final.json도 원본 증거를 덮어쓰지 않는다.
    return Path(str(properties_path) + '.image-review.json')


def write_proof(properties_path, mortgages_path, context, sources, parent=None):
    from parse_registry_pdfs import __version__ as parser_version
    dependencies = dict(context['dependencies'])
    if context.get('classification_report'):
        report = context['classification_report']
        require(sha256(report['path']) == report['sha256'], '분석 중 문서 종류 판정 보고서가 변경되었습니다.')
        dependencies[report['path']] = report['sha256']
    for source in sources:
        require(sha256(source['path']) == source['input_sha256'], '분석 도중 입력이 변경되었습니다.')
        dependencies[str(Path(source['path']).resolve())] = source['input_sha256']
        for path, digest in source.get('artifacts', {}).items():
            require(sha256(path) == digest, '분석 도중 현행본 또는 삭제 근거가 변경되었습니다.')
            dependencies[str(Path(path).resolve())] = digest
    now = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M KST')
    proof = {'schema': 1, 'status': 'complete', 'parser_version': parser_version, 'created_at': now, **context,
             'dependencies': dependencies, 'sources': sources,
             'properties': str(Path(properties_path).resolve()), 'properties_sha256': sha256(properties_path),
             'mortgages': str(Path(mortgages_path).resolve()), 'mortgages_sha256': sha256(mortgages_path)}
    if parent:
        proof['parent'] = {'path': str(Path(parent).resolve()), 'sha256': sha256(parent)}
    write_json(proof_path(properties_path), proof)


def verify_proof(properties_path, mortgages_path):
    from parse_registry_pdfs import __version__ as parser_version
    path = proof_path(properties_path)
    require(path.is_file(), '전체 PDF 이미지 검토 완료 증거가 없습니다. 검토 전/일부 성공 JSON은 최종 조서를 만들 수 없습니다.')
    proof = read_json(path)
    require(proof.get('schema') == 1 and proof.get('status') == 'complete', '이미지 검토 완료 증거가 아닙니다.')
    require(proof.get('parser_version') == parser_version,
            '이전 파서 버전의 결과입니다. 현재 코드로 원본과 판독 기록부터 재실행하세요.')
    for key, value in [('properties', properties_path), ('mortgages', mortgages_path)]:
        require(Path(proof[key]).resolve() == Path(value).resolve() and sha256(value) == proof[key + '_sha256'],
                '이미지 검토 후 결과 JSON이 변경되거나 다른 입력과 섞였습니다.')
    require(proof.get('dependencies') and proof.get('sources'), '이미지 검토의 원본·판독 연결이 비어 있습니다.')
    for file, digest in proof['dependencies'].items():
        require(Path(file).is_file() and sha256(file) == digest, f'이미지 검토의 원본/판독/현행본이 변경되었습니다: {file}')
    _, current = validate_job(proof['manifest'])
    require(proof.get('document_classifications') == document_classifications(proof['manifest']),
            '결과의 문서 종류·제외 내역이 원본 이미지 판독 기록과 다릅니다.')
    require(all(proof['dependencies'].get(p) == digest for p, digest in current.items()), '이미지 검토 범위가 변경되었습니다.')
    if proof.get('parent'):
        parent = proof['parent']
        require(Path(parent['path']).is_file() and sha256(parent['path']) == parent['sha256'], '상위 이미지 검토 증거가 변경되었습니다.')
    return proof


def main(argv=None):
    ap = argparse.ArgumentParser(description='등기부 전체 PDF 이미지 판독 준비·검증 (이미지 판단은 AI/사람 수행)')
    commands = ap.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare', help='대상 폴더의 모든 PDF·모든 쪽 이미지 생성')
    p.add_argument('input_root'); p.add_argument('output'); p.add_argument('--dpi', type=int, default=200)
    p = commands.add_parser('details', help='사전 판독 완료 후 상세 판독 대장 준비')
    p.add_argument('manifest')
    p = commands.add_parser('prepare-part', help='복수 물건/전사 보완본을 물건별로 상세 판독 준비')
    p.add_argument('pdf'); p.add_argument('html'); p.add_argument('output')
    p.add_argument('--pages', nargs='+', type=int); p.add_argument('--dpi', type=int, default=200)
    p = commands.add_parser('check', help='전체 이미지 판독 완료 여부 검사')
    p.add_argument('manifest')
    args = ap.parse_args(argv)
    if getattr(args, 'output', None):
        try:
            cpa_storage.guard(args.output)
        except cpa_storage.StorageError as exc:
            ap.error(str(exc))
    try:
        if args.command == 'prepare':
            result = prepare_batch(args.input_root, args.output, args.dpi)
        elif args.command == 'details':
            result = prepare_details(args.manifest)
        elif args.command == 'prepare-part':
            result = review.prepare(args.pdf, args.html, args.output, args.pages, args.dpi)
        else:
            sources, _ = validate_job(args.manifest)
            result = {'status': 'ready_for_analysis', 'parts': len(sources)}
        print(__import__('json').dumps(result, ensure_ascii=False, indent=2))
        return 5 if (isinstance(result, dict) and result.get('errors') or
                     isinstance(result, list) and any('error' in r for r in result)) else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'이미지 검토 필요: {exc}')
        return 5


if __name__ == '__main__':
    sys.exit(main())
