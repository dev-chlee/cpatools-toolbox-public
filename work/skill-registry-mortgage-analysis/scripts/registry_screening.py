"""AI의 페이지 이미지 사전 판독을 검증해 상세 판독 또는 텍스트 분석으로 분기한다.

이미지에서 취소선 존재 여부를 판단하는 주체는 AI/사람이다. 코드가 이미지 인식을
대신하거나 OCR 마커 부재를 취소선 없음으로 간주하지 않는다. 외부 API 호출 없음.
"""
from html.parser import HTMLParser
import html
from pathlib import Path
import re
import shutil
import tempfile
from registry_document_types import classify_text, validate_classification

from registry_review import (_bbox, _new_dir, _render, prepare, read_json,
                                 require, sha256, write_json)

SCREEN_SCHEMA = 1


def markup_hints(path):
    """원문에 이미 있는 서식 단서. 존재 여부의 이미지 판단과 별도로 보존한다."""
    if path is None:
        return []
    text = Path(path).read_text(encoding="utf-8-sig")
    hints = []

    class Marks(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag in {"s", "del", "strike"}:
                hints.append({"kind": "html_tag", "tag": tag, "line": self.getpos()[0]})
            if any(key == "style" and value and re.search(r"line-through", value, re.I)
                   for key, value in attrs):
                hints.append({"kind": "inline_style", "line": self.getpos()[0]})

    # Markdown도 인라인 HTML 취소선을 담을 수 있다. 확장자로 서식 단서를 버리지 않는다.
    Marks().feed(text)
    for kind, pattern in (("markdown", r"~~[^\r\n]+?~~"),
                          ("css", r"line-through"),
                          ("unicode", r"[\u0335\u0336\u0338]")):
        for match in re.finditer(pattern, text, re.I):
            hints.append({"kind": kind, "start": match.start(), "end": match.end(),
                          "line": text.count("\n", 0, match.start()) + 1})
    return hints


def screen(pdf, output, ocr=None, dpi=200):
    """PDF 전체 페이지의 사전 판독 묶음을 만든다. 모든 결과는 미검토로 시작한다."""
    import pdfplumber
    pdf = Path(pdf).resolve()
    ocr = Path(ocr).resolve() if ocr else None
    require(pdf.is_file(), "원본 PDF가 필요합니다.")
    require(type(dpi) is int and 150 <= dpi <= 600, "렌더 해상도는 150~600 DPI여야 합니다.")
    if ocr:
        require(ocr.is_file() and ocr.suffix.lower() in {".html", ".htm", ".md", ".txt"},
                "OCR 입력은 기존 HTML·MD·TXT 파일이어야 합니다.")
    hashes = {"pdf": sha256(pdf), "ocr": sha256(ocr) if ocr else None}
    with pdfplumber.open(pdf) as doc:
        count = len(doc.pages)
        page_texts = {i: p.extract_text() or '' for i, p in enumerate(doc.pages, 1)}
    ocr_hint_error = None
    if ocr and ocr.suffix.lower() in {'.html', '.htm'}:
        from registry_review import extract_units
        try:
            ocr_pages = extract_units(ocr)
        except ValueError as exc:
            ocr_pages, ocr_hint_error = [], str(exc)
        for p in ocr_pages:
            if p['page'] in page_texts:
                page_texts[p['page']] += '\n' + ' '.join(' '.join(u['cells']) for u in p['units'])
    require(count > 0, "PDF에 페이지가 없습니다.")
    output = _new_dir(output)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".registry-screen-") as tmp:
        tmp = Path(tmp)
        (tmp / "pages").mkdir()
        pages = []
        for number in range(1, count + 1):
            image = f"pages/page-{number:04d}.png"
            _render(pdf, number, tmp / image, dpi)
            pages.append({"page": number, "image": image, "image_sha256": sha256(tmp / image),
                          "document_hint": classify_text(page_texts[number])})
        require(hashes == {"pdf": sha256(pdf), "ocr": sha256(ocr) if ocr else None},
                "사전 판독 준비 중 원본이 변경되었습니다.")
        bundle = {"screen_schema": SCREEN_SCHEMA, "pdf": str(pdf), "pdf_sha256": hashes["pdf"],
                  "ocr": str(ocr) if ocr else None, "ocr_sha256": hashes["ocr"],
                  "pdf_page_count": count, "dpi": dpi, "markup_hints": markup_hints(ocr), "pages": pages,
                  "ocr_hint_error": ocr_hint_error}
        write_json(tmp / "screen-bundle.json", bundle)
        screening = {"screen_schema": SCREEN_SCHEMA, "bundle_sha256": sha256(tmp / "screen-bundle.json"),
                     "reviewer": "", "method": "image", "document_complete": False,
                     "pages": [{"page": p["page"], "image_sha256": p["image_sha256"],
                                "image_reviewed": False, "presence": "unreviewed", "note": "",
                                "evidence": [], "classification": {"kind": "unknown", "document_type": "",
                                "reason": "", "evidence": []}} for p in pages]}
        write_json(tmp / "screening.json", screening)
        parts = ['<!doctype html><html lang="ko"><meta charset="utf-8"><title>취소선 사전 판독</title>',
                 '<style>body{max-width:1100px;margin:24px auto;font-family:sans-serif}img{width:100%}pre{white-space:pre-wrap}</style>',
                 '<h1>문서 종류와 취소선 존재 여부 확인</h1>',
                 '<p>등기부 본체·계속·요약·별지는 등기부에 포함합니다. 계약서·설명서·대장은 별도 문서입니다. '
                 '텍스트 후보와 관계없이 이미지로 문서 종류와 근거를 기록하세요.</p>',
                 '<p>모든 페이지 이미지를 확인하고 screening.json을 작성하세요. 존재·없음·불확실을 구분하며, '
                 '가는 선과 검은 선, 일부 주소·금액, 표 테두리·도장도 확인합니다. 미검토는 없음이 아닙니다.</p>',
                 '<p>OCR 서식 단서:</p><pre>' + html.escape(str(bundle["markup_hints"])) + '</pre>']
        for p in pages:
            parts.append('<pre>문서 종류 후보: ' + html.escape(str(p['document_hint'])) + '</pre>')
            parts.append(f'<h2>원본 {p["page"]}쪽</h2><img src="{p["image"]}" alt="원본 {p["page"]}쪽">')
        (tmp / "screen.html").write_text("\n".join(parts) + "</html>", encoding="utf-8")
        tmp.rename(output)
    return {"output": str(output), "pages": count, "status": "awaiting_image_screening",
            "markup_hints": len(bundle["markup_hints"])}


def validate_screening(bundle_path, screening_path):
    bundle_path, screening_path = Path(bundle_path).resolve(), Path(screening_path).resolve()
    bundle, screening = read_json(bundle_path), read_json(screening_path)
    require(bundle.get("screen_schema") == SCREEN_SCHEMA and screening.get("screen_schema") == SCREEN_SCHEMA,
            "지원하지 않는 사전 판독 형식입니다.")
    require(screening.get("bundle_sha256") == sha256(bundle_path), "사전 판독 준비본이 변경되었습니다.")
    require(screening.get("method") == "image" and isinstance(screening.get("reviewer"), str)
            and screening["reviewer"].strip(), "실제 이미지 판독자와 판독 방식이 필요합니다.")
    require(screening.get("document_complete") is True, "문서 전체 페이지 확인이 끝나지 않았습니다.")
    pdf = Path(bundle["pdf"])
    ocr = Path(bundle["ocr"]) if bundle.get("ocr") else None
    require(pdf.is_file() and sha256(pdf) == bundle.get("pdf_sha256"), "원본 PDF가 변경되었습니다.")
    if ocr:
        require(ocr.is_file() and sha256(ocr) == bundle.get("ocr_sha256"), "원본 OCR이 변경되었습니다.")
    require(bundle.get("markup_hints") == markup_hints(ocr), "OCR 서식 단서가 원문과 다릅니다.")
    import pdfplumber
    with pdfplumber.open(pdf) as doc:
        count = len(doc.pages)
    pages, reviewed = bundle.get("pages"), screening.get("pages")
    require(type(bundle.get("pdf_page_count")) is int and bundle["pdf_page_count"] == count,
            "원본 전체 페이지 수가 다릅니다.")
    expected = list(range(1, count + 1))
    for values in (pages, reviewed):
        require(isinstance(values, list) and all(isinstance(p, dict) for p in values), "페이지 판독 목록이 필요합니다.")
        require(all(type(p.get("page")) is int for p in values)
                and [p["page"] for p in values] == expected, "사전 판독 페이지가 누락·중복되거나 순서가 다릅니다.")
    for p, r in zip(pages, reviewed):
        image = (bundle_path.parent / p["image"]).resolve()
        require(image.is_relative_to(bundle_path.parent) and image.is_file()
                and sha256(image) == p.get("image_sha256") == r.get("image_sha256"), "사전 판독 이미지가 변경되었습니다.")
        require(r.get("image_reviewed") is True and isinstance(r.get("note"), str) and r["note"].strip(),
                f'{p["page"]}쪽 이미지 확인 기록이 없습니다.')
        require(r.get("presence") in {"present", "absent", "uncertain"}, f'{p["page"]}쪽은 미검토 상태입니다.')
        validate_classification(r)
        evidence = r.get("evidence")
        require(isinstance(evidence, list), "이미지 위치 목록이 필요합니다.")
        if r["presence"] in {"present", "uncertain"}:
            require(evidence, f'{p["page"]}쪽의 취소선 또는 불확실한 부분 위치가 필요합니다.')
        for item in evidence:
            require(isinstance(item, dict), "이미지 위치 기록 형식이 잘못됐습니다.")
            _bbox(item.get("bbox"))
            require(isinstance(item.get("note"), str) and item["note"].strip(), "이미지 위치 설명이 필요합니다.")
    return bundle, screening
