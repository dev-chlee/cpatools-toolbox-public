"""PDF 또는 페이지·표 구조가 있는 기존 OCR HTML을 읽기 전용으로 제공한다.

HTML은 Google Layout OCR의 text-col 블록만 읽는다. 스크립트·링크·이미지는
실행하거나 가져오지 않으며, 판독 불가능한 병합 행은 추측하지 않고 거절한다.
"""
from html.parser import HTMLParser
from pathlib import Path
import re
import pdfplumber


class OCRPage:
    def __init__(self, text, tables, number):
        self.text, self.tables, self.page_number = text, tables, number

    def extract_text(self):
        return self.text

    def extract_tables(self):
        return self.tables


class _Reader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pages, self.depth, self.number = [], 0, 0
        self.text, self.tables, self.table, self.row, self.cell = [], [], None, None, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'section' and attrs.get('id', '').startswith('page-'):
            self.number = attrs['id'][5:]
        if tag == 'div':
            if self.depth:
                self.depth += 1
            elif 'text-col' in attrs.get('class', '').split():
                self.depth = 1
                self.text, self.tables = [], []
        if not self.depth:
            return
        if tag in ('script', 'style'):
            raise ValueError('OCR 텍스트 영역의 script/style은 지원하지 않습니다.')
        if tag == 'table':
            if self.table is not None:
                raise ValueError('OCR 중첩 표는 원본 대조 후 단일 표로 정리하세요.')
            self.table = []
        elif tag == 'tr':
            self.row = []
        elif tag in ('td', 'th'):
            if any(attrs.get(k, '1') != '1' for k in ('rowspan', 'colspan')):
                raise ValueError('OCR 병합 셀은 원본 대조 후 행·열을 분리하세요.')
            self.cell = []
        elif tag == 'br':
            self.text.append('\n')
            if self.cell is not None:
                self.cell.append('\n')

    def handle_data(self, data):
        if self.depth:
            self.text.append(data)
            if self.cell is not None:
                self.cell.append(data)

    def handle_endtag(self, tag):
        if not self.depth:
            return
        if tag in ('td', 'th'):
            if self.cell is not None and self.row is not None:
                self.row.append(''.join(self.cell).strip())
            self.cell = None
            self.text.append(' ')
        elif tag == 'tr':
            if self.table is not None and self.row:
                self.table.append(self.row)
            self.row = None
            self.text.append('\n')
        elif tag == 'table':
            if self.table:
                self.tables.append(self.table)
            self.table = None
            self.text.append('\n')
        elif tag in ('p', 'h1', 'h2', 'h3'):
            self.text.append('\n')
        elif tag == 'div':
            self.depth -= 1
            if not self.depth:
                self.pages.append(OCRPage(''.join(self.text).strip(), self.tables, self.number))


class OCRDocument:
    def __init__(self, path):
        reader = _Reader()
        reader.feed(Path(path).read_text(encoding='utf-8-sig'))
        reader.close()
        if reader.depth or not reader.pages:
            raise ValueError('페이지별 text-col 영역이 있는 완전한 OCR HTML이 필요합니다.')
        self.pages = reader.pages
        for page in self.pages:
            if not page.text:
                raise ValueError(f'OCR {page.page_number}쪽의 텍스트가 비어 있습니다.')
            for table in page.tables:
                if not any('등기목적' in re.sub(r'\s+', '', ' '.join(row)) for row in table):
                    continue
                for row in table:
                    if row and re.match(r'^\d+\s+\d+(?:\s|$)', row[0].strip()):
                        raise ValueError(f'OCR {page.page_number}쪽 순위번호 {row[0]!r}: 여러 등기가 한 행으로 합쳐졌습니다. 원본 대조 후 분리하세요.')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def open_document(path):
    if Path(path).suffix.lower() in ('.html', '.htm'):
        return OCRDocument(path)
    return pdfplumber.open(path)
