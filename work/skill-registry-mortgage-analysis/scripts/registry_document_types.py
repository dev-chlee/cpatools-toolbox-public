"""문서 종류 후보와 이미지 판정 검증. 단서 부재는 비등기 판정이 아니다."""
import re
from registry_review import require, _evidence


def classify_text(text):
    """페이지 텍스트로 후보만 제안한다. 인용·혼합·이미지 쪽은 이미지 확인이 필요하다."""
    t = re.sub(r'\s+', '', text or '')
    registry = [name for name, pattern in (
        ('등기부 제목', r'등기사항(?:전부|일부)증명서|등기부등본'),
        ('등기 구역', r'【(?:표제부|갑구|을구)】'),
        ('등기 요약', r'주요등기사항요약'),
        ('등기 별지', r'공동담보목록|공동전세목록'),
        ('고유번호와 등기 표', r'고유번호.*(?:순위번호|등기목적|권리자및기타사항)'),
    ) if re.search(pattern, t)]
    other = [name for name, pattern in (
        ('임대차계약서', r'(?:부동산|주택|아파트|상가)?(?:전세|월세|임대차)계약서'),
        ('중개대상물 확인·설명서', r'중개대상물확인.{0,3}설명서'),
        ('공제·보험증서', r'공제증서|공제가입증서|보험증권'),
        ('건축물대장', r'건축물대장'),
        ('토지·임야대장', r'토지대장|임야대장'),
    ) if re.search(pattern, t)]
    kind = 'registry' if registry and not other else 'non_registry' if other and not registry else 'unknown'
    return {'kind': kind, 'registry_signals': registry, 'other_signals': other,
            'requires_image_confirmation': True}


def validate_classification(page):
    c = page.get('classification')
    require(isinstance(c, dict) and c.get('kind') in ('registry', 'non_registry', 'unknown'),
            f"{page['page']}쪽 문서 종류 이미지 판정이 필요합니다.")
    require(c['kind'] != 'unknown', f"{page['page']}쪽 문서 종류 판단 불가: 이미지를 확대해 본체·계속·요약·별지·첨부를 확인하세요.")
    require(isinstance(c.get('document_type'), str) and c['document_type'].strip()
            and isinstance(c.get('reason'), str) and c['reason'].strip(), '문서 종류와 판정 사유가 필요합니다.')
    _evidence(c.get('evidence'), {page['page']})
    return c


def non_registry_pages(screening):
    return [p['page'] for p in screening['pages'] if p['classification']['kind'] == 'non_registry']
