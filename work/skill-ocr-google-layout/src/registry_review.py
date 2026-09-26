"""이미지 판독 기록을 검증하여 등기부 OCR의 현행 정보만 별도로 내보낸다.

취소선을 자동 인식하거나 등기 효력을 추정하는 모듈이 아니다. prepare의 모든
페이지·행을 사람이거나 이미지를 볼 수 있는 AI가 판독해야 export가 가능하다.
원문, 판독 기록, 현행본을 분리하며 외부 API를 호출하지 않는다.
"""
from __future__ import annotations

import hashlib
import html
import base64
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone


SCHEMA = 1
KEPT = {"current", "context"}
STATES = KEPT | {"cancelled", "superseded", "history", "noise"}


class ReviewError(ValueError):
    """불완전한 판독으로 현행본이 생성되는 것을 막는다."""


def require(condition, message):
    if not condition:
        raise ReviewError(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"JSON 키 중복: {key}")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique)


class _Node:
    def __init__(self, tag, attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def text(self):
        parts = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag == "br":
                parts.append("\n")
            else:
                parts.append(child.text())
                if child.tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
                    parts.append("\n")
        return "".join(parts)


class _OCRReader(HTMLParser):
    """text-col 안의 글자를 빠짐없이 수집. HTML/스크립트는 실행하지 않는다."""
    ALLOWED = {"div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "table", "thead",
               "tbody", "tfoot", "tr", "td", "th", "span", "br", "ul", "ol", "li",
               "b", "i", "strong", "em", "small", "u", "s", "del", "strike", "a"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pages, self.stack, self.page_id = [], [], None
        self.in_section = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if not self.stack:
            if tag == "section" and re.fullmatch(r"page-[1-9]\d*", attrs.get("id", "")):
                require(not self.in_section, "중첩된 페이지 section은 지원하지 않습니다.")
                self.page_id = int(attrs["id"][5:])
                self.in_section = True
            if tag == "div" and "text-col" in attrs.get("class", "").split():
                require(self.in_section, "text-col의 page-N section이 필요합니다.")
                require(self.page_id not in [p[0] for p in self.pages], "페이지 번호가 중복됩니다.")
                self.stack = [_Node("div")]
            return
        require(tag in self.ALLOWED, f"지원하지 않는 OCR 텍스트 태그: {tag}")
        if tag in ("td", "th"):
            require(all(attrs.get(k, "1") == "1" for k in ("rowspan", "colspan")),
                    "병합 셀은 이미지 대조 후 원본 보존 사본에서 행·열을 분리하세요.")
        if tag == "table":
            require(not any(n.tag == "table" for n in self.stack), "중첩 표는 지원하지 않습니다.")
        node = _Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag != "br":
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag != "br":
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if not self.stack:
            if tag == "section":
                self.in_section, self.page_id = False, None
            return
        if tag == "br":
            return
        require(self.stack[-1].tag == tag, f"닫히지 않거나 순서가 잘못된 OCR 태그: {tag}")
        node = self.stack.pop()
        if not self.stack:
            self.pages.append((self.page_id, node))

    def handle_data(self, data):
        if self.stack:
            self.stack[-1].children.append(data)


def extract_units(ocr):
    reader = _OCRReader()
    reader.feed(Path(ocr).read_text(encoding="utf-8-sig"))
    reader.close()
    require(not reader.stack and not reader.in_section and reader.pages, "완전한 페이지별 OCR HTML이 필요합니다.")
    pages = []
    for number, root in reader.pages:
        units, table_number = [], 0

        def add(kind, cells, table=None, tags=None):
            units.append({"id": f"p{number}-u{len(units) + 1}", "page": number,
                          "kind": kind, "table": table, "tags": tags or ["p"], "cells": cells})

        def walk(node):
            nonlocal table_number
            if isinstance(node, str):
                if node.strip():
                    add("text", [node.strip()])
                return
            if node.tag == "table":
                table_number += 1
                table = f"p{number}-t{table_number}"

                def rows(n):
                    if isinstance(n, str):
                        require(not n.strip(), "표 밖으로 분리된 OCR 텍스트가 있습니다.")
                    elif n.tag == "tr":
                        cells = [c for c in n.children if isinstance(c, _Node)]
                        require(cells and all(c.tag in ("td", "th") for c in cells), "불완전한 표 행입니다.")
                        require(all(not c.strip() for c in n.children if isinstance(c, str)), "셀 밖의 OCR 텍스트가 있습니다.")
                        add("row", [c.text().strip() for c in cells], table, [c.tag for c in cells])
                    else:
                        require(n.tag in ("table", "thead", "tbody", "tfoot"), "지원하지 않는 표 구조입니다.")
                        for c in n.children:
                            rows(c)
                rows(node)
            elif node.tag in ("div", "ul", "ol"):
                for child in node.children:
                    walk(child)
            else:
                require(not any(isinstance(c, _Node) and c.tag == "table" for c in node.children),
                        "문단에 포함된 표는 분리해야 합니다.")
                if node.text().strip():
                    add("text", [node.text().strip()], tags=[node.tag if node.tag.startswith("h") else "p"])
        walk(root)
        require(units, f"OCR {number}쪽의 텍스트가 없습니다. 이미지를 전사한 후 다시 준비하세요.")
        pages.append({"page": number, "units": units})
    return pages


def _new_dir(path):
    path = Path(path).resolve()
    require(not path.exists(), f"출력 폴더가 이미 있습니다. 새 경로를 지정하세요: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _render(pdf, page, target, dpi):
    # Poppler 우선. 설치되지 않은 환경에서는 기존 스킬 의존성 PyMuPDF 사용.
    if shutil.which("pdftoppm"):
        subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-singlefile",
                        "-r", str(dpi), "-png", str(pdf), str(target.with_suffix(""))],
                       check=True, capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        import fitz
        with fitz.open(pdf) as doc:
            doc[page - 1].get_pixmap(dpi=dpi, alpha=False).save(target)


def prepare(pdf, ocr, output, source_pages=None, dpi=200):
    """읽기 전용 원본 + 새 검토 묶음. 모든 판독은 미검토 상태로 시작한다."""
    import fitz
    pdf, ocr = Path(pdf).resolve(), Path(ocr).resolve()
    require(pdf.is_file() and ocr.is_file(), "PDF와 OCR HTML 파일이 모두 필요합니다.")
    input_hashes = {"pdf": sha256(pdf), "ocr": sha256(ocr)}
    require(type(dpi) is int and 150 <= dpi <= 600, "렌더 해상도는 150~600 DPI여야 합니다.")
    pages = extract_units(ocr)
    with fitz.open(pdf) as doc:
        count = len(doc)
    mapping = source_pages if source_pages is not None else [p["page"] for p in pages]
    require(len(mapping) == len(pages) and len(set(mapping)) == len(mapping), "원본 페이지 매핑의 수 또는 중복을 확인하세요.")
    require(all(type(p) is int and 1 <= p <= count for p in mapping), "원본 PDF 범위 밖의 페이지입니다.")
    require(mapping == sorted(mapping), "원본 페이지 순서가 뒤바뀌었습니다.")
    output = _new_dir(output)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".registry-prepare-") as tmp:
        tmp = Path(tmp)
        (tmp / "pages").mkdir()
        for page, source_page in zip(pages, mapping):
            name = f"pages/page-{source_page:04d}.png"
            _render(pdf, source_page, tmp / name, dpi)
            page.update(source_page=source_page, image=name, image_sha256=sha256(tmp / name))
        require(input_hashes == {"pdf": sha256(pdf), "ocr": sha256(ocr)}, "이미지 준비 중 원본이 변경되었습니다. 다시 준비하세요.")
        bundle = {"schema": SCHEMA, "pdf": str(pdf), "pdf_sha256": input_hashes["pdf"],
                  "ocr": str(ocr), "ocr_sha256": input_hashes["ocr"], "pdf_page_count": count,
                  "dpi": dpi, "pages": pages}
        write_json(tmp / "bundle.json", bundle)
        review = {"schema": SCHEMA, "bundle_sha256": sha256(tmp / "bundle.json"),
                  "reviewer": "", "method": "image", "registry_id": "", "as_of": "",
                  "registry_page_count": len(pages), "entries": {},
                  "pages": [{"page": p["page"], "image_sha256": p["image_sha256"],
                             "image_reviewed": False, "text_complete": False, "printed_page": None,
                             "note": ""} for p in pages],
                  "decisions": [{"id": u["id"], "state": "unreviewed", "entry": "",
                                 "strike_scope": "unreviewed", "reason": "", "evidence": [],
                                 "edits": []} for p in pages for u in p["units"]]}
        write_json(tmp / "review.json", review)
        (tmp / "review.html").write_text(_review_html(bundle), encoding="utf-8")
        # 결과 폴더 전체를 한 번에 게시. 실패 시 부분 성공 폴더를 남기지 않는다.
        tmp.rename(output)
    return {"output": str(output), "pages": len(pages), "units": len(review["decisions"]), "status": "unreviewed"}


def _review_html(bundle):
    parts = [_html_start("등기부 원본 이미지 판독 대장"), "<h1>원본 이미지와 OCR 대조</h1>",
             "<p>아래 OCR은 말소 이력을 포함한 원문입니다. 각 이미지 전체와 취소선 범위를 확인하고 review.json을 작성하세요.</p>"]
    for page in bundle["pages"]:
        parts.append(f'<h2>OCR {page["page"]}쪽 / 원본 {page["source_page"]}쪽</h2><div class="review-grid"><div>')
        for u in page["units"]:
            parts.append(f'<p><b>{u["id"]}</b></p><pre>{html.escape(json.dumps(u["cells"], ensure_ascii=False))}</pre>')
        parts.append(f'</div><div><img src="{page["image"]}" alt="원본 {page["source_page"]}쪽"></div></div>')
    return "\n".join(parts) + "</body></html>"


def _bbox(box):
    require(isinstance(box, list) and len(box) == 4 and
            all(type(x) in (int, float) and math.isfinite(x) for x in box), "이미지 bbox는 유한한 숫자 4개여야 합니다.")
    require(0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1,
            "이미지 bbox는 좌상단 기준 0~1 좌표이며 폭·높이가 있어야 합니다.")


def _evidence(evidence, pages):
    require(isinstance(evidence, list) and evidence, "원본 이미지 위치와 판독 근거가 필요합니다.")
    for item in evidence:
        require(item.get("page") in pages, "판독하지 않은 페이지를 근거로 사용할 수 없습니다.")
        _bbox(item.get("bbox"))
        require(bool(str(item.get("note", "")).strip()), "이미지 근거의 설명이 필요합니다.")


def _index(items, key, expected, label):
    require(isinstance(items, list), f"{label} 목록이 필요합니다.")
    values = [item.get(key) for item in items]
    require(len(values) == len(set(values)) and set(values) == set(expected), f"{label} 누락·중복·알 수 없는 항목이 있습니다.")
    return dict(zip(values, items))


def _apply_edits(unit, decision, page_ids):
    cells = list(unit["cells"])
    edits = decision.get("edits", [])
    require(isinstance(edits, list), "edits는 목록이어야 합니다.")
    grouped = {}
    for edit in edits:
        ci, start, end = edit.get("cell"), edit.get("start"), edit.get("end")
        require(type(ci) is int and 0 <= ci < len(cells), "편집 셀 번호가 범위 밖입니다.")
        require(type(start) is int and type(end) is int and 0 <= start < end <= len(cells[ci]), "편집 문자 범위가 잘못되었습니다.")
        require(cells[ci][start:end] == edit.get("before"), "편집 전 텍스트가 원문 범위와 다릅니다.")
        require(edit.get("kind") in {"strike", "superseded", "ocr"}, "알 수 없는 편집 종류입니다.")
        require(isinstance(edit.get("after"), str), "편집 후 텍스트가 필요합니다.")
        if edit["kind"] != "ocr":
            require(edit["after"] == "", "취소·대체된 구간은 삭제만 가능합니다. 새 값은 원문 후속 등기에 남기세요.")
        _evidence(edit.get("evidence"), page_ids)
        require(any(e["page"] == unit["page"] for e in edit["evidence"]), "편집 대상 쪽의 이미지 근거가 필요합니다.")
        grouped.setdefault(ci, []).append(edit)
    for ci, cell_edits in grouped.items():
        ordered = sorted(cell_edits, key=lambda e: e["start"])
        require(all(a["end"] <= b["start"] for a, b in zip(ordered, ordered[1:])), "편집 범위가 서로 겹칩니다.")
        for edit in reversed(ordered):
            cells[ci] = cells[ci][:edit["start"]] + edit["after"] + cells[ci][edit["end"]:]
    return cells


def validate(bundle_path, review_path):
    bundle_path = Path(bundle_path).resolve()
    bundle, review = read_json(bundle_path), read_json(review_path)
    require(bundle.get("schema") == SCHEMA and review.get("schema") == SCHEMA, "지원하지 않는 검토 형식입니다.")
    require(review.get("bundle_sha256") == sha256(bundle_path), "검토 준비본이 변경되었습니다. 다시 판독하세요.")
    for key in ("pdf", "ocr"):
        require(Path(bundle[key]).is_file() and sha256(bundle[key]) == bundle[f"{key}_sha256"], "원본 PDF 또는 OCR이 변경되었습니다. 다시 준비하세요.")
    fresh = extract_units(bundle["ocr"])
    require(fresh == [{"page": p["page"], "units": p["units"]} for p in bundle["pages"]], "검토 대상 텍스트가 원본과 다릅니다.")
    page_ids = {p["page"] for p in bundle["pages"]}
    reviewed = _index(review.get("pages"), "page", page_ids, "페이지 판독")
    require(review.get("method") == "image" and bool(str(review.get("reviewer", "")).strip()), "이미지 판독자와 판독 방식이 필요합니다.")
    require(re.fullmatch(r"\d{4}-\d{4}-\d{6}", str(review.get("registry_id", ""))), "원본에서 확인한 등기 고유번호가 필요합니다.")
    source_text = "\n".join(" ".join(u["cells"]) for p in fresh for u in p["units"])
    source_ids = set(re.findall(r"고유번호\s*:?\s*(\d{4}-\d{4}-\d{6})", source_text))
    require(source_ids == {review["registry_id"]}, "OCR 고유번호가 판독 물건과 다르거나 여러 물건이 섞였습니다. 이미지 대조 후 물건별로 다시 준비하세요.")
    require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(review.get("as_of", ""))), "원본 기준일 형식은 YYYY-MM-DD입니다.")
    try:
        datetime.strptime(review.get("as_of", ""), "%Y-%m-%d")
    except (ValueError, TypeError):
        raise ReviewError("원본 발행·열람 기준일(YYYY-MM-DD)이 필요합니다.") from None
    count = review.get("registry_page_count")
    require(type(count) is int and count == len(page_ids), "등기부 본체의 인쇄된 전체 쪽수와 입력 쪽수가 다릅니다.")
    require([reviewed[p["page"]].get("printed_page") for p in bundle["pages"]] == list(range(1, count + 1)),
            "인쇄 페이지가 누락·중복되거나 순서가 다릅니다. 여러 물건은 나누어 판독하세요.")
    for p in bundle["pages"]:
        r = reviewed[p["page"]]
        image_path = (bundle_path.parent / p["image"]).resolve()
        require(image_path.is_relative_to(bundle_path.parent), "검토 이미지가 준비 폴더 밖에 있습니다.")
        require(image_path.is_file() and sha256(image_path) == p["image_sha256"] == r.get("image_sha256"), "원본 페이지 이미지가 변경되었습니다.")
        require(r.get("image_reviewed") is True and r.get("text_complete") is True and bool(str(r.get("note", "")).strip()),
                f'{p["page"]}쪽의 이미지 전체 판독·OCR 누락 확인이 끝나지 않았습니다.')
    units = [u for p in bundle["pages"] for u in p["units"]]
    decisions = _index(review.get("decisions"), "id", [u["id"] for u in units], "행·문단 판독")
    entries = review.get("entries")
    require(isinstance(entries, dict), "등기 항목별 상태가 필요합니다.")
    for entry in entries.values():
        require(entry.get("state") in {"current", "cancelled", "superseded", "history"}, "등기 항목의 상태가 미확정입니다.")
        _evidence(entry.get("evidence"), page_ids)
    result, audit, used_entries = [], [], set()
    for u in units:
        d = decisions[u["id"]]
        state, scope = d.get("state"), d.get("strike_scope")
        require(state in STATES and scope in {"none", "whole", "partial"}, f'{u["id"]}: 미판독·불확실 항목이 있습니다.')
        require(bool(str(d.get("reason", "")).strip()), f'{u["id"]}: 유지·제외 이유가 필요합니다.')
        _evidence(d.get("evidence"), page_ids)
        require(any(e["page"] == u["page"] for e in d["evidence"]), "해당 행이 있는 원본 쪽의 근거가 필요합니다.")
        entry = d.get("entry")
        if state not in {"context", "noise"}:
            require(entry in entries, f'{u["id"]}: 등기 항목 연결이 없습니다. 다음 쪽의 계속 행도 같은 항목에 연결하세요.')
        if entry:
            require(entry in entries, "알 수 없는 등기 항목입니다.")
            used_entries.add(entry)
            require(not (state in KEPT and entries[entry]["state"] != "current"), "말소·대체된 항목의 일부가 현행본에 남습니다.")
        require(not (scope == "whole" and state in KEPT), "전체 취소선이 있는 행을 현행본에 남길 수 없습니다.")
        strike_edits = [e for e in d.get("edits", []) if e.get("kind") == "strike"]
        require((scope == "partial") == bool(strike_edits), "부분 취소선에는 정확한 문자 삭제 범위가 필요합니다.")
        cells = _apply_edits(u, d, page_ids)
        if state in KEPT:
            require(state != "current" or any(c.strip() for c in cells), "현행 행의 내용이 전부 삭제되었습니다.")
            result.append({**u, "cells": cells, "state": state, "entry": entry})
        audit.append({"unit": u, "decision": d, "current_cells": cells if state in KEPT else None})
    require(used_entries == set(entries), "원문 행과 연결되지 않은 등기 항목이 있습니다.")
    for key, entry in entries.items():
        require(entry["state"] != "current" or any(u["entry"] == key and u["state"] == "current" for u in result),
                f"현행 항목 {key}의 내용이 전부 제외되었습니다.")
    require(any(u["state"] == "current" for u in result), "검증된 현행 정보가 없습니다.")
    return bundle, review, result, audit


def _html_start(title):
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>'
            'body{font-family:"Malgun Gothic",sans-serif;margin:28px;color:#172631;line-height:1.6}'
            'table{border-collapse:collapse;width:100%;margin:16px 0}td,th{border:1px solid #b5c2cc;'
            'padding:9px;vertical-align:top;white-space:pre-wrap}h1{font-size:25px}'
            'h2{border-top:2px solid #286078;padding-top:14px}pre{white-space:pre-wrap;overflow-wrap:anywhere}'
            '.review-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}.review-grid img{width:100%;position:sticky;top:0}'
            '</style></head><body>')


def _current_html(bundle, review, units):
    parts = [_html_start("등기부 현행 정보"), "<h1>이미지 검토를 거친 현행 정보</h1>",
             f'<p>고유번호 {review["registry_id"]} · 원본 기준일 {review["as_of"]}</p>',
             '<p>원본에서 확인한 현행 내용의 별도 추출본입니다. 원본 증명서를 대체하지 않습니다. '
             '삭제 내역과 이미지 위치는 별도 audit.json에 보관합니다.</p>']
    for page in bundle["pages"]:
        selected = [u for u in units if u["page"] == page["page"]]
        parts.append(f'<section id="page-{page["page"]}"><h2>원본 {page["source_page"]}쪽</h2><div class="text-col">')
        if not selected:
            parts.append('<p>이 쪽에서 현행 정보로 남길 내용 없음.</p>')
        opened = None
        for u in selected:
            if opened and opened != u["table"]:
                parts.append("</table>")
                opened = None
            if u["kind"] == "row":
                if not opened:
                    parts.append("<table>")
                    opened = u["table"]
                parts.append(f'<tr data-source-unit="{u["id"]}">' + "".join(
                    f'<{tag}>{html.escape(cell).replace(chr(10), "<br>")}</{tag}>'
                    for tag, cell in zip(u["tags"], u["cells"])) + "</tr>")
            else:
                tag = u["tags"][0]
                parts.append(f'<{tag} data-source-unit="{u["id"]}">{html.escape(u["cells"][0]).replace(chr(10), "<br>")}</{tag}>')
        if opened:
            parts.append("</table>")
        parts.append("</div></section>")
    return "\n".join(parts) + "</body></html>"


def _audit_html(bundle_path, bundle, review, audit):
    labels = {"current": "현행 유지", "context": "문맥 유지", "cancelled": "말소 제외",
              "superseded": "후속 대체로 제외", "history": "이력 제외", "noise": "안내·여백 제외"}
    parts = [_html_start("등기부 이미지 판독·삭제 근거"), "<h1>이미지 판독·삭제 근거</h1>",
             '<p>이 파일은 과거 이력을 포함한 검토 자료입니다. 현행 정보는 current.html을 사용하세요. '
             '빨간 상자는 판독자가 기록한 취소선 범위이며 자동 선 인식 결과가 아닙니다.</p>',
             f'<p>고유번호 {review["registry_id"]} · 원본 기준일 {review["as_of"]}</p>']
    for page in bundle["pages"]:
        selected = [a for a in audit if a["unit"]["page"] == page["page"]]
        rectangles = {}
        for a in selected:
            d, uid = a["decision"], a["unit"]["id"]
            evidence = d["evidence"] if d["strike_scope"] == "whole" else [
                e for edit in d["edits"] if edit["kind"] == "strike" for e in edit["evidence"]]
            for e in evidence:
                if e["page"] == page["page"]:
                    rectangles.setdefault(tuple(e["bbox"]), []).append(uid)
        overlay = []
        for (x0, y0, x1, y1), ids in rectangles.items():
            overlay.append(f'<rect x="{x0 * 1000}" y="{y0 * 1000}" width="{(x1-x0) * 1000}" '
                           f'height="{(y1-y0) * 1000}" fill="#ce293f" fill-opacity=".08" stroke="#ce293f" stroke-width="1.5">'
                           f'<title>{", ".join(ids)}</title></rect>')
        img = Path(bundle_path).resolve().parent / page["image"]
        encoded = base64.b64encode(img.read_bytes()).decode("ascii")
        parts.append(f'<h2>원본 {page["source_page"]}쪽</h2><div class="review-grid"><div>')
        for a in selected:
            d, u = a["decision"], a["unit"]
            parts.append(f'<details><summary>{u["id"]} · {labels[d["state"]]} · {html.escape(d["reason"])}</summary>')
            parts.append('<p>원문</p><pre>' + html.escape(" | ".join(u["cells"])) + '</pre><p>현행본</p><pre>' +
                         html.escape(" | ".join(a["current_cells"]) if a["current_cells"] is not None else "제외") + '</pre>')
            for edit in d["edits"]:
                parts.append(f'<p>셀 {edit["cell"]}, 문자 {edit["start"]}:{edit["end"]} ({edit["kind"]})</p>'
                             f'<pre>{html.escape(edit["before"])} → {html.escape(edit["after"] or "삭제")}</pre>')
            parts.append('</details>')
        parts.append('</div><div><div style="position:sticky;top:0">'
                     f'<img style="display:block;position:static" src="data:image/png;base64,{encoded}" alt="원본 {page["source_page"]}쪽">'
                     '<svg viewBox="0 0 1000 1000" preserveAspectRatio="none" '
                     'style="position:absolute;left:0;top:0;width:100%;height:100%">' +
                     ''.join(overlay) + '</svg></div></div></div>')
    return "\n".join(parts) + "</body></html>"


def export_current(bundle_path, review_path, output):
    """검증을 마친 뒤에만 현행 파일을 쓰며 원본을 덮어쓰지 않는다."""
    bundle, review, units, audit = validate(bundle_path, review_path)
    output = _new_dir(output)
    meta = {"schema": SCHEMA, "status": "image_reviewed_current", "registry_id": review["registry_id"],
            "scope": "current_only", "history_removed": True,
            "as_of": review["as_of"], "reviewer": review["reviewer"],
            "reviewed_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="minutes"),
            "pdf_sha256": bundle["pdf_sha256"], "ocr_sha256": bundle["ocr_sha256"],
            "review_sha256": sha256(review_path), "bundle_sha256": sha256(bundle_path),
            "pages": len(bundle["pages"]), "input_units": len(audit), "retained_units": len(units),
            "excluded_units": len(audit) - len(units),
            "edited_units": sum(bool(a["decision"]["edits"]) for a in audit)}
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".registry-export-") as tmp:
        tmp = Path(tmp)
        write_json(tmp / "current.json", {**meta, "units": units})
        write_json(tmp / "audit.json", {**meta, "source_pdf": bundle["pdf"], "source_ocr": bundle["ocr"],
                                      "review": review, "audit": audit})
        (tmp / "current.html").write_text(_current_html(bundle, review, units), encoding="utf-8")
        (tmp / "audit.html").write_text(_audit_html(bundle_path, bundle, review, audit), encoding="utf-8")
        (tmp / "current.txt").write_text("\n".join(" | ".join(u["cells"]) for u in units) + "\n", encoding="utf-8")
        tmp.rename(output)
    return {**meta, "output": str(output)}
