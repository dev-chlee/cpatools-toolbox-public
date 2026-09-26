"""이미지 대조에 따른 OCR 행 보완·물건별 분리. 원본 PDF/OCR은 변경하지 않는다."""
import argparse
import copy
import html
from pathlib import Path
import re

import cpa_storage
import registry_review as R


def write_pages(pages, target):
    blocks = ['<!doctype html><html lang="ko"><meta charset="utf-8">']
    for number, page in enumerate(pages, 1):
        blocks.append(f'<section id="page-{number}"><div class="text-col">')
        table = None
        for unit in page['units']:
            next_table = unit.get('table') if unit['kind'] == 'row' else None
            if table and table != next_table:
                blocks.append('</table>')
            if next_table and table != next_table:
                blocks.append('<table>')
            table = next_table
            cells = [html.escape(c).replace('\n', '<br>') for c in unit['cells']]
            blocks.append('<tr>' + ''.join('<td>' + c + '</td>' for c in cells) + '</tr>'
                          if unit['kind'] == 'row' else '<p>' + ' '.join(cells) + '</p>')
        if table:
            blocks.append('</table>')
        blocks.append('</div></section>')
    Path(target).write_text('\n'.join(blocks) + '</html>', encoding='utf-8')


def repair_ocr(ocr, corrections, output):
    """이미지에서 확인한 행 경계/글자만 보완. 취소 삭제는 후속 상세 판독에서 수행한다."""
    pages = R.extract_units(ocr)
    fixes = R.read_json(corrections)
    R.require(fixes.get('reviewer') and isinstance(fixes.get('corrections'), list), '판독자와 OCR 보완 목록이 필요합니다.')
    units = {u['id']: u for p in pages for u in p['units']}
    replacements = {}
    for fix in fixes['corrections']:
        key = fix.get('unit')
        R.require(key in units and key not in replacements, 'OCR 보완 대상 중복 또는 누락입니다.')
        before = units[key]
        R.require(fix.get('before') == before['cells'], '보완 전 OCR 내용이 다릅니다.')
        R.require(fix.get('reason'), '이미지 대조 사유가 필요합니다.')
        R._evidence(fix.get('evidence'), {before['page']})
        rows = fix.get('rows')
        R.require(isinstance(rows, list) and rows and all(isinstance(r, list) and r
                  and all(isinstance(c, str) for c in r) for r in rows), '보완할 행 목록이 필요합니다.')
        R.require(before['kind'] == 'row' or all(len(r) == 1 for r in rows), '문단 보완은 문단 단위로 기록하세요.')
        replacements[key] = [{**before, 'cells': row} for row in rows]
    for page in pages:
        page['units'] = [r for u in page['units'] for r in replacements.get(u['id'], [u])]
    output = R._new_dir(output); output.mkdir()
    write_pages(pages, output/'repaired.html')
    R.write_json(output/'repair-audit.json', {'source': str(Path(ocr).resolve()), 'source_sha256': R.sha256(ocr),
                 'corrections': str(Path(corrections).resolve()), 'corrections_sha256': R.sha256(corrections), **fixes})
    return str(output/'repaired.html')


def suggest_parts(ocr):
    """고유번호가 바뀌는 페이지를 분리 후보로 제안한다. 판독 완료 기록은 만들지 않는다."""
    groups, current = [], None
    for page in R.extract_units(ocr):
        text = ' '.join(' '.join(u['cells']) for u in page['units'])
        ids = set(re.findall(r'고\s*유\s*번\s*호\s*[:：]?\s*(\d{4}\s*-\s*\d{4}\s*-\s*\d{6})', text))
        R.require(len(ids) <= 1, '한 페이지에 여러 고유번호가 있습니다. 이미지 범위별 전사가 필요합니다.')
        uid = re.sub(r'\s+', '', next(iter(ids))) if ids else None
        if uid and (current is None or current['registry_id'] != uid):
            current = {'registry_id': uid, 'pages': []}; groups.append(current)
        R.require(current is not None, '첫 페이지의 고유번호가 없습니다. 이미지에서 문서 종류와 물건 경계를 확인하세요.')
        current['pages'].append(page['page'])
    return {'status': 'proposal_requires_image_review', 'parts': groups}


def prepare_structure(manifest_path, file, plan_path, output):
    """전체 쪽 판독 후 물건별 HTML과 상세 대장 생성. 비등기 첨부도 근거와 함께 보존한다."""
    from registry_screening import validate_screening
    manifest = R.read_json(manifest_path)
    entry = next((e for e in manifest['documents'] if e['file'] == file), None)
    R.require(entry is not None, 'manifest에 없는 PDF입니다.')
    screen, screening = validate_screening(entry['screen_bundle'], entry['screening'])
    plan = R.read_json(plan_path)
    R.require(plan.get('reviewer') and plan.get('reason') and plan.get('parts'), '구조 판독자·사유·물건 목록이 필요합니다.')
    R.require(not entry.get('parts'), '기존 상세 대장을 덮어쓰지 않습니다. 새 manifest를 사용하세요.')
    excluded = plan.get('attachments', [])
    covered = [n for p in plan['parts'] for n in p['pages']] + [p['page'] for p in excluded]
    R.require(sorted(covered) == list(range(1, screen['pdf_page_count'] + 1)), '물건·첨부 페이지에 중복 또는 누락이 있습니다.')
    from registry_document_types import non_registry_pages
    R.require(sorted(p['page'] for p in excluded) == non_registry_pages(screening),
              '첨부 제외 페이지가 이미지 문서 종류 판정과 다릅니다.')
    for page in excluded:
        R.require(page.get('kind') == 'attachment' and page.get('reason'), '제외 페이지의 문서 종류와 사유가 필요합니다.')
        R._evidence(page.get('evidence'), {page['page']})
    output = R._new_dir(output); output.mkdir()
    parts = []
    for i, part in enumerate(plan['parts'], 1):
        source = part.get('ocr') or screen.get('ocr')
        R.require(source, '이미지 페이지는 판독 전사 HTML을 지정하세요.')
        pages = R.extract_units(source)
        if part.get('ocr_is_part'):
            R.require(len(pages) == len(part['pages']), '전사본과 원본 페이지 수가 다릅니다.')
        else:
            by_number = {p['page']: p for p in pages}
            R.require(all(n in by_number for n in part['pages']), 'OCR에 분리 대상 페이지가 없습니다.')
            pages = [copy.deepcopy(by_number[n]) for n in part['pages']]
        target = output/f'part-{i:04d}.html'
        write_pages(pages, target)
        dest = output/f'part-{i:04d}'
        R.prepare(screen['pdf'], target, dest, source_pages=part['pages'], dpi=screen['dpi'])
        parts.append({'bundle': str(dest/'bundle.json'), 'review': str(dest/'review.json')})
    entry.update(parts=parts, structural_review=plan['reason'], attachments=excluded,
                 structure_plan=str(Path(plan_path).resolve()), structure_plan_sha256=R.sha256(plan_path))
    R.write_json(manifest_path, manifest)
    return parts


def main():
    ap = argparse.ArgumentParser(description='이미지 판독에 따른 OCR 행 복원·물건/첨부 분리')
    sub = ap.add_subparsers(dest='command', required=True)
    p = sub.add_parser('repair'); p.add_argument('ocr'); p.add_argument('corrections'); p.add_argument('output')
    p = sub.add_parser('suggest'); p.add_argument('ocr')
    p = sub.add_parser('partition'); p.add_argument('manifest'); p.add_argument('file'); p.add_argument('plan'); p.add_argument('output')
    a = ap.parse_args()
    if getattr(a, 'output', None):
        try:
            cpa_storage.guard(a.output)
        except cpa_storage.StorageError as exc:
            ap.error(str(exc))
    result = repair_ocr(a.ocr, a.corrections, a.output) if a.command == 'repair' else (
        suggest_parts(a.ocr) if a.command == 'suggest' else prepare_structure(a.manifest, a.file, a.plan, a.output))
    print(__import__('json').dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
