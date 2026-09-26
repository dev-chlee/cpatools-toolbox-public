"""변환 결과(MD·HTML)를 원응답(document_layout)과 대조하는 검증기.

파일에 쓰기 전에 만든 문자열과 페이지 배정 결과를 받아 순수 함수로 판정한다.
진입점은 :func:`verify_outputs` 하나다. 입력으로 주지 않은 형식(None)은 검사하지 않는다.

기대 텍스트 집합
    ``document_layout`` 트리의 모든 블록(최상위, 텍스트 자식, 표 셀 안, 목록 항목 안)을
    문서 순서로 돌며 자기 텍스트가 비어 있지 않은 블록을 센다. ``footer`` 블록과 그
    자손 전체는 빼고, 뺀 블록 수와 글자 수를 따로 기록한다. 비교와 글자 수는 공백
    (줄바꿈 포함)을 모두 뺀 문자열 기준이다.

실패 사유 (허용차 없음 — 하나라도 해당하면 검증 실패)
    1. 텍스트 없음: 기대 집합이 비어 있다.
    2. MD 누락: 기대 텍스트를 문서 순서대로, 앞 블록을 찾은 위치 다음부터 찾는다.
       같은 짧은 문구가 여러 번 나와도 개수까지 맞아야 한다. 표 셀의 ``\\|`` 는
       ``|`` 로 되돌려 비교한다(원문에 있던 ``\\|`` 도 같은 규칙으로 맞춘다).
       **되돌리기가 공백 제거보다 먼저다.** 출력기가 공백이 남아 있는 원문에
       이스케이프를 걸기 때문이고, 순서를 바꾸면 원문의 ``\\ |`` (백슬래시·공백·
       파이프)가 ``\\|`` 로 붙어 이스케이프로 잘못 읽힌다.
    3. HTML 누락: 페이지별 본문 칸(``text-col``)의 텍스트만 모아 태그를 걷고 엔티티를
       되돌린 뒤 존재 여부를 본다. 페이지 구분 표지와 빈 페이지 안내문은 제외한다.
    4. HTML 페이지 오배치: 페이지 배정 결과에서 기대 집합 블록이 자기 page_span 시작
       페이지가 아닌 곳에 렌더되면 실패다. 표·목록은 자기 자신만 시작 페이지를 본다
       (안쪽 블록은 다른 페이지가 시작이어도 오배치가 아니다). page_span 이 없는
       기대 집합 블록은 "페이지 확인 불가"로 세되 실패 사유로 삼지 않는다.
    5. 표 구조 불일치 / 6. 표 구조 확인 불가: 아래 "표 구조 검사".

표 구조 검사
    대조 대상은 ``document_layout`` 의 바깥 표(다른 표의 칸 안에 있지 않은 표)다. 행이
    없거나 칸이 하나도 없는 표는 뺀다(출력기가 표로 내보내지 않는다). 남은 바깥 표에
    문서 순서로 1부터 ``table_index`` 를 매기며, 형식이 달라도 같은 표는 같은 번호다.
    footer 아래 표는 출력기 동작을 그대로 따른다. MD 는 자기 텍스트가 있는(출력기와
    같이 ``text`` 가 빈 문자열이 아닌) footer 블록의 자손 표를 빼고, HTML 은 모두 넣는다.

    출력 쪽 표: MD 는 ``| --- |`` 구분선 바로 앞 줄(머리 행)부터 ``|`` 로 시작하는 줄이
    이어지는 덩어리 하나를 표 하나로 본다(구분선 줄은 행이 아니다). 칸은 ``\\|`` 가
    아닌 ``|`` 로 나눈다. HTML 은 본문 칸(``text-col``) 안의 ``<table>`` 을 그것이 있는
    페이지(``<section id="page-N">``)와 함께 모으며, 칸이 하나도 없는 ``<table>`` 은 뺀다.

    짝짓기: MD 는 문서 순서대로 n 번째끼리, HTML 은 페이지별로 그 페이지에 배정된 순서
    (``"full"`` 항목의 자손 안 바깥 표, ``"text_only"`` 항목은 표 없음)대로 n 번째끼리
    짝짓는다. 어느 배정 항목에도 들어가지 않은 바깥 표는 짝 없는 표로 센다.

    비교: 행 수(머리 행 + 본문 행), 열 수(행별 칸 수 최댓값, 모자란 칸은 빈 칸), 행·열
    위치마다 칸 텍스트. 칸 텍스트는 칸 안 모든 블록 텍스트를 문서 순서로 이어 붙여 공백을
    모두 뺀 값이다. MD 는 양쪽 모두 ``\\|`` 를 ``|`` 로 되돌려 비교하고(원문에 있던 ``\\|``
    도 같은 규칙), HTML 은 엔티티를 되돌린 값과 비교한다.

    결과(표 하나당 항목 하나, 목록은 줄이지 않는다):
    - 짝이 있는데 모양이나 칸이 다르면 ``table_mismatches`` 항목. ``cell_diffs`` 의
      ``row``·``col`` 은 1부터(머리 행이 먼저), 한쪽 격자 밖 위치의 head 는 None 이다.
    - 표 개수 불일치는 ``table_counts`` 의 expected/actual 로 드러나고, 짝 없는 표마다
      ``table_mismatches`` 항목이 하나씩 생긴다. 원응답에만 있는 표는 ``actual_shape`` 가
      None, 출력에만 있는 표는 ``table_index``·``expected_shape`` 가 None 이고 ``page`` 는
      HTML 이면 그 표가 나온 페이지, MD 면 None 이다. 개수가 다르면 짝 없는 표가 반드시
      생기므로 개수 불일치는 항상 ``table_mismatch`` 사유로 센다.
    - 병합 셀(row_span 또는 col_span 이 1 보다 큼, 0 은 1 로 본다)이나 중첩 표(칸 안에 표)가
      있는 표는 구조를 확인할 수 없어 ``table_unverifiable`` 로 센다. 둘 다 해당하면
      "병합 셀" 로 적는다. 이런 표도 개수와 짝짓기에는 넣되 행·열·칸은 비교하지 않는다.
      검사한 형식 중 하나라도 대조 대상에 넣은 표만, 표마다 한 번 적는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from google.cloud import documentai

from src.exporters.block_utils import (
    Block,
    BlockPath,
    block_page_range,
    collect_block_text,
    iter_blocks_with_paths,
    subtree_page_range,
)

TEXT_HEAD_CHARS = 40

_WHITESPACE = re.compile(r"\s+")
_ESCAPED_PIPE = re.compile(r"\\+\|")


def _squash(value: str) -> str:
    """공백(줄바꿈 포함)을 모두 뺀다."""
    return _WHITESPACE.sub("", value)


def _unescape_pipes(value: str) -> str:
    return _ESCAPED_PIPE.sub("|", value)


def _md_value(value: str) -> str:
    r"""MD 비교용 정규화. 이스케이프 해제가 공백 제거보다 먼저다.

    MD 출력기는 공백이 남아 있는 원문에 ``|`` → ``\|`` 를 건다. 공백을 먼저 빼면
    원문의 ``\ |`` (백슬래시·공백·파이프)가 ``\|`` 로 붙어 이스케이프로 잘못
    읽히므로, 출력기와 같은 순서로 되돌린다.
    """
    return _squash(_unescape_pipes(value))


def _html_value(value: str) -> str:
    return _squash(value)


def _own_text(block: Block) -> str:
    return block.text_block.text if block.text_block else ""


def _is_footer(block: Block) -> bool:
    return bool(block.text_block) and (block.text_block.type_ or "") == "footer"


def _block_type(block: Block) -> str:
    if block.table_block:
        return "table"
    if block.list_block:
        return "list"
    if block.text_block:
        return block.text_block.type_ or ""
    return ""


def _text_head(value: str) -> str:
    return " ".join(value.split())[:TEXT_HEAD_CHARS]


def _start_page(block: Block) -> int | None:
    own = block_page_range(block)
    return own[0] if own else None


@dataclass(frozen=True)
class BlockRef:
    """누락된 블록 한 개. ``page`` 는 page_span 시작 페이지(없으면 None)."""

    page: int | None
    block_type: str
    text_head: str

    def to_dict(self) -> dict:
        return {"page": self.page, "block_type": self.block_type, "text_head": self.text_head}


@dataclass(frozen=True)
class MisplacedBlock:
    """원래 페이지가 아닌 곳에 배정된 블록 한 개."""

    original_page: int
    assigned_page: int
    block_type: str
    text_head: str

    def to_dict(self) -> dict:
        return {
            "original_page": self.original_page,
            "assigned_page": self.assigned_page,
            "block_type": self.block_type,
            "text_head": self.text_head,
        }


@dataclass(frozen=True)
class CellDiff:
    """표 칸 하나의 차이. 위치는 1부터, head 는 공백 제거 후 앞 40자(격자 밖이면 None)."""

    row: int
    col: int
    expected_head: str | None
    actual_head: str | None

    def to_dict(self) -> dict:
        return {
            "row": self.row,
            "col": self.col,
            "expected_head": self.expected_head,
            "actual_head": self.actual_head,
        }


@dataclass(frozen=True)
class TableMismatch:
    """한 형식에서 표 하나의 구조 불일치(짝 없는 표 포함). 모양은 ``(행, 열)``."""

    format: str
    table_index: int | None
    page: int | None
    expected_shape: tuple[int, int] | None
    actual_shape: tuple[int, int] | None
    cell_diffs: tuple[CellDiff, ...] = ()

    def to_dict(self) -> dict:
        return {
            "format": self.format,
            "table_index": self.table_index,
            "page": self.page,
            "expected_shape": list(self.expected_shape) if self.expected_shape else None,
            "actual_shape": list(self.actual_shape) if self.actual_shape else None,
            "cell_diffs": [d.to_dict() for d in self.cell_diffs],
        }


@dataclass(frozen=True)
class UnverifiableTable:
    """구조를 확인할 수 없는 표 하나. ``reason`` 은 "병합 셀" 또는 "중첩 표"."""

    table_index: int
    page: int | None
    reason: str

    def to_dict(self) -> dict:
        return {"table_index": self.table_index, "page": self.page, "reason": self.reason}


@dataclass
class VerifyResult:
    """검증 결과. :attr:`success` 가 False 면 검증 실패다."""

    checked_formats: list[str]
    expected_count: int
    expected_chars: int
    text_none: bool
    md_missing: list[BlockRef] = field(default_factory=list)
    html_missing: list[BlockRef] = field(default_factory=list)
    html_misplaced: list[MisplacedBlock] = field(default_factory=list)
    footer_excluded_blocks: int = 0
    footer_excluded_chars: int = 0
    unknown_page_count: int = 0
    # 형식별 {"expected": n, "actual": n}. 검사한 형식만 담는다.
    table_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    table_mismatches: list[TableMismatch] = field(default_factory=list)
    table_unverifiable: list[UnverifiableTable] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not (
            self.text_none
            or self.md_missing
            or self.html_missing
            or self.html_misplaced
            or self.table_mismatches
            or self.table_unverifiable
        )

    @property
    def summary(self) -> str:
        formats = "·".join(f.upper() for f in self.checked_formats) or "없음"
        tables = "·".join(
            f"{fmt.upper()} {counts['expected']}개" for fmt, counts in self.table_counts.items()
        ) or "없음"
        context = (
            f"검사 형식 {formats}, 기대 텍스트 블록 {self.expected_count}개"
            f"(공백 제외 {self.expected_chars}자), "
            f"하단 문구 제외 {self.footer_excluded_blocks}개"
            f"({self.footer_excluded_chars}자), "
            f"페이지 확인 불가 {self.unknown_page_count}개, "
            f"대조한 표 {tables}"
        )
        if self.success:
            return f"검증 결과 누락·오배치·표 구조 불일치 없음 / {context}"
        reasons: list[str] = []
        if self.text_none:
            reasons.append("텍스트 없음")
        if self.md_missing:
            reasons.append(f"MD 누락 {len(self.md_missing)}개")
        if self.html_missing:
            reasons.append(f"HTML 누락 {len(self.html_missing)}개")
        if self.html_misplaced:
            reasons.append(f"HTML 페이지 오배치 {len(self.html_misplaced)}개")
        if self.table_mismatches:
            reasons.append(f"표 구조 불일치 {len(self.table_mismatches)}개")
        if self.table_unverifiable:
            reasons.append(f"표 구조 확인 불가 {len(self.table_unverifiable)}개")
        return f"검증 실패: {', '.join(reasons)} / {context}"

    def to_dict(self) -> dict:
        """누락 목록 파일(``<base>_verify_failed.json``)에 쓸 JSON 직렬화용 dict."""
        return {
            "success": self.success,
            "checked_formats": list(self.checked_formats),
            "summary": self.summary,
            "reasons": {
                "text_none": self.text_none,
                "md_missing": len(self.md_missing),
                "html_missing": len(self.html_missing),
                "html_misplaced": len(self.html_misplaced),
                "table_mismatch": len(self.table_mismatches),
                "table_unverifiable": len(self.table_unverifiable),
            },
            "expected_block_count": self.expected_count,
            "expected_char_count": self.expected_chars,
            "md_missing": [b.to_dict() for b in self.md_missing],
            "html_missing": [b.to_dict() for b in self.html_missing],
            "html_misplaced": [b.to_dict() for b in self.html_misplaced],
            "footer_excluded": {
                "block_count": self.footer_excluded_blocks,
                "char_count": self.footer_excluded_chars,
            },
            "unknown_page_count": self.unknown_page_count,
            "table_counts": {
                fmt: dict(counts) for fmt, counts in self.table_counts.items()
            },
            "table_mismatches": [m.to_dict() for m in self.table_mismatches],
            "table_unverifiable": [t.to_dict() for t in self.table_unverifiable],
        }


# ── 기대 텍스트 집합 ───────────────────────────────────────────


@dataclass
class _Expected:
    block: Block
    text: str  # 공백 제거본
    md_text: str  # MD 비교용(이스케이프 해제 뒤 공백 제거)
    ref: BlockRef


class _Layout:
    """원응답 블록을 문서 순서로 한 번 훑어 기대 집합과 소속 정보를 만든다.

    블록은 위치 경로(:func:`iter_blocks_with_paths`)로 식별한다. 페이지 배정 결과의
    항목도 같은 경로를 싣고 있어, 객체가 아니라 경로로 원응답 블록과 짝짓는다.
    """

    def __init__(self, document: documentai.Document):
        self.expected: list[_Expected] = []
        self.footer_blocks = 0
        self.footer_chars = 0
        self._blocks: dict[BlockPath, Block] = {}
        self._expected_paths: set[BlockPath] = set()

        layout = document.document_layout
        roots = list(layout.blocks) if layout else []
        for index, root in enumerate(roots):
            footer_path: BlockPath | None = None
            for path, block in iter_blocks_with_paths(root, (index,)):
                self._blocks[path] = block
                in_footer = footer_path is not None and _is_under(path, footer_path)
                if not in_footer and _is_footer(block):
                    footer_path, in_footer = path, True
                squashed = _squash(_own_text(block))
                if not squashed:
                    continue
                if in_footer:
                    self.footer_blocks += 1
                    self.footer_chars += len(squashed)
                    continue
                self._expected_paths.add(path)
                self.expected.append(
                    _Expected(
                        block=block,
                        text=squashed,
                        md_text=_md_value(_own_text(block)),
                        ref=BlockRef(
                            page=_start_page(block),
                            block_type=_block_type(block),
                            text_head=_text_head(_own_text(block)),
                        ),
                    )
                )

    def block_at(self, path: BlockPath) -> Block:
        """경로에 있는 원응답 블록. 원응답에 없는 경로는 프로그램 오류다."""
        try:
            return self._blocks[path]
        except KeyError:
            raise ValueError(
                f"페이지 배정 항목의 위치 경로 {path!r} 가 원응답에 없다"
            ) from None

    def is_expected(self, path: BlockPath) -> bool:
        return path in self._expected_paths


def _is_under(path: BlockPath, ancestor: BlockPath) -> bool:
    """``path`` 가 ``ancestor`` 자신이거나 그 자손의 경로인가."""
    return path[: len(ancestor)] == ancestor


# ── MD ─────────────────────────────────────────────────────────


def _check_markdown(expected: list[_Expected], markdown: str) -> list[BlockRef]:
    haystack = _md_value(markdown)
    missing: list[BlockRef] = []
    cursor = 0
    for item in expected:
        needle = item.md_text
        found = haystack.find(needle, cursor)
        if found < 0:
            missing.append(item.ref)
        else:
            cursor = found + len(needle)
    return missing


# ── HTML 본문 칸 ───────────────────────────────────────────────


class _TextColumnParser(HTMLParser):
    """``<div class="text-col">`` 안의 텍스트만 칸별로 모은다.

    빈 페이지 안내문(``<p class="empty-page">``)은 제외한다. 페이지 구분 표지는
    본문 칸 밖에 있으므로 자연히 빠진다. 엔티티는 파서가 되돌린다.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.columns: list[str] = []
        self._buffer: list[str] = []
        self._div_depth = 0  # 0 이면 본문 칸 밖
        self._skip_depth = 0

    @staticmethod
    def _classes(attrs) -> set[str]:
        for name, value in attrs:
            if name == "class" and value:
                return set(value.split())
        return set()

    def handle_starttag(self, tag, attrs):
        if self._div_depth == 0:
            if tag == "div" and "text-col" in self._classes(attrs):
                self._div_depth = 1
                self._buffer = []
            return
        if tag == "div":
            self._div_depth += 1
        if self._skip_depth:
            if tag == "p":
                self._skip_depth += 1
        elif tag == "p" and "empty-page" in self._classes(attrs):
            self._skip_depth = 1

    def handle_endtag(self, tag):
        if self._div_depth == 0:
            return
        if self._skip_depth and tag == "p":
            self._skip_depth -= 1
        if tag == "div":
            self._div_depth -= 1
            if self._div_depth == 0:
                self.columns.append("".join(self._buffer))
                self._buffer = []
                self._skip_depth = 0

    def handle_data(self, data):
        if self._div_depth and not self._skip_depth:
            self._buffer.append(data)


def _check_html_text(expected: list[_Expected], html: str) -> list[BlockRef]:
    parser = _TextColumnParser()
    parser.feed(html)
    parser.close()
    # 칸 사이에 공백이 아닌 구분자를 넣어 페이지를 넘는 우연한 일치를 막는다.
    haystack = "\x00".join(_squash(column) for column in parser.columns)
    return [item.ref for item in expected if item.text not in haystack]


# ── HTML 페이지 배정 ───────────────────────────────────────────


def _container_start(block: Block) -> int | None:
    own = _start_page(block)
    if own is not None:
        return own
    subtree = subtree_page_range(block)
    return subtree[0] if subtree else None


def _container_head(block: Block) -> str:
    texts: list[str] = []
    collect_block_text(block, texts)
    return _text_head(" ".join(texts))


def _check_block_page(
    layout: _Layout, path: BlockPath, page: int, out: list[MisplacedBlock]
) -> None:
    if not layout.is_expected(path):
        return
    block = layout.block_at(path)
    start = _start_page(block)
    if start is None or start == page:
        return  # page_span 없음은 페이지 확인 불가로만 센다
    out.append(
        MisplacedBlock(
            original_page=start,
            assigned_page=page,
            block_type=_block_type(block),
            text_head=_text_head(_own_text(block)),
        )
    )


def _check_container_page(
    layout: _Layout, path: BlockPath, page: int, out: list[MisplacedBlock]
) -> None:
    block = layout.block_at(path)
    interior = [p for p, _ in iter_blocks_with_paths(block, path)][1:]
    if not any(layout.is_expected(p) for p in interior):
        return  # 텍스트를 담지 않은 표·목록은 판정 대상이 아니다
    start = _container_start(block)
    if start is None or start == page:
        return
    out.append(
        MisplacedBlock(
            original_page=start,
            assigned_page=page,
            block_type=_block_type(block),
            text_head=_container_head(block),
        )
    )


def _check_full_subtree(
    layout: _Layout, root_path: BlockPath, page: int, out: list[MisplacedBlock]
) -> None:
    container: BlockPath | None = None
    for path, block in iter_blocks_with_paths(layout.block_at(root_path), root_path):
        if container is not None and _is_under(path, container):
            continue  # 표·목록 안쪽은 표·목록 자신만 본다
        if block.table_block or block.list_block:
            container = path
            _check_container_page(layout, path, page, out)
            continue
        _check_block_page(layout, path, page, out)


def _item_mode_and_path(item) -> tuple[str, BlockPath]:
    """배정 항목 ``PageItem(block, mode, path)`` 에서 모드와 위치 경로를 꺼낸다.

    경로가 없는 항목은 배정 결과를 만든 쪽의 프로그램 오류이므로 예외로 드러낸다.
    """
    path = item[2] if isinstance(item, tuple) and len(item) == 3 else None
    if not isinstance(path, tuple) or not path:
        raise ValueError(
            "페이지 배정 항목에 위치 경로가 없다. "
            "항목은 PageItem(block, mode, path) 모양이어야 한다"
        )
    return item[1], path


def _check_page_assignment(
    layout: _Layout, page_assignment: dict[int, list]
) -> list[MisplacedBlock]:
    misplaced: list[MisplacedBlock] = []
    for page in sorted(page_assignment):
        for item in page_assignment[page]:
            mode, path = _item_mode_and_path(item)
            if mode == "text_only":
                layout.block_at(path)  # 원응답에 없는 경로는 예외
                _check_block_page(layout, path, page, misplaced)
            else:
                _check_full_subtree(layout, path, page, misplaced)
    return misplaced


# ── 표 구조 ────────────────────────────────────────────────────

_MERGED = "병합 셀"
_NESTED = "중첩 표"

Grid = list[list[str]]


@dataclass(frozen=True)
class _SourceTable:
    """원응답의 바깥 표 하나. ``grid`` 는 칸 텍스트 원문(행별 칸 수 그대로)."""

    index: int
    path: BlockPath
    page: int | None
    under_text_footer: bool  # MD 출력기가 건너뛰는 footer 의 자손인가
    grid: Grid
    unverifiable: str | None

    @property
    def shape(self) -> tuple[int, int]:
        return len(self.grid), max(len(row) for row in self.grid)


@dataclass(frozen=True)
class _OutputTable:
    """출력 문자열에서 읽은 표 하나. ``page`` 는 HTML 페이지(MD 는 None)."""

    page: int | None
    grid: Grid

    @property
    def shape(self) -> tuple[int, int]:
        return len(self.grid), max((len(row) for row in self.grid), default=0)


def _cell_text(cell) -> str:
    texts: list[str] = []
    for block in cell.blocks:
        collect_block_text(block, texts)
    return " ".join(texts)


def _span_of(value: int) -> int:
    return value or 1


def _unverifiable_reason(block: Block, path: BlockPath) -> str | None:
    rows = list(block.table_block.header_rows) + list(block.table_block.body_rows)
    if any(
        _span_of(cell.row_span) > 1 or _span_of(cell.col_span) > 1
        for row in rows
        for cell in row.cells
    ):
        return _MERGED
    inner = list(iter_blocks_with_paths(block, path))[1:]
    if any(node.table_block for _, node in inner):
        return _NESTED
    return None


def _collect_source_tables(document: documentai.Document) -> list[_SourceTable]:
    """바깥 표를 문서 순서로 모은다. 행이나 칸이 하나도 없는 표는 뺀다."""
    tables: list[_SourceTable] = []
    layout = document.document_layout
    roots = list(layout.blocks) if layout else []
    for index, root in enumerate(roots):
        table_path: BlockPath | None = None
        footer_path: BlockPath | None = None
        for path, block in iter_blocks_with_paths(root, (index,)):
            if table_path is not None and _is_under(path, table_path):
                continue  # 표 칸 안: 바깥 표가 아니다
            table_path = None
            if footer_path is not None and not _is_under(path, footer_path):
                footer_path = None
            if (
                footer_path is None
                and _is_footer(block)
                and block.text_block.text  # MD 출력기와 같은 판정(공백만 있어도 건너뜀)
            ):
                footer_path = path
            if not block.table_block:
                continue
            table_path = path
            rows = list(block.table_block.header_rows) + list(block.table_block.body_rows)
            if not rows or not any(row.cells for row in rows):
                continue
            tables.append(
                _SourceTable(
                    index=len(tables) + 1,
                    path=path,
                    page=_start_page(block),
                    under_text_footer=footer_path is not None,
                    grid=[[_cell_text(cell) for cell in row.cells] for row in rows],
                    unverifiable=_unverifiable_reason(block, path),
                )
            )
    return tables


_MD_SEPARATOR = re.compile(r"^\| ---(?: \| ---)* \|$")
_MD_CELL_BOUNDARY = re.compile(r"(?<!\\)\|")


def _markdown_cells(line: str) -> list[str]:
    parts = _MD_CELL_BOUNDARY.split(line)
    return parts[1:-1] if len(parts) > 1 else parts


def _parse_markdown_tables(markdown: str) -> list[_OutputTable]:
    # splitlines() 는 칸 안에 남을 수 있는 \r·  등에서도 끊으므로 \n 으로만 나눈다.
    lines = markdown.split("\n")
    tables: list[_OutputTable] = []
    i = 1
    while i < len(lines):
        if _MD_SEPARATOR.match(lines[i]) and lines[i - 1].startswith("|"):
            grid = [_markdown_cells(lines[i - 1])]
            j = i + 1
            while j < len(lines) and lines[j].startswith("|"):
                grid.append(_markdown_cells(lines[j]))
                j += 1
            tables.append(_OutputTable(page=None, grid=grid))
            i = j + 1
        else:
            i += 1
    return tables


_PAGE_ID = re.compile(r"^page-(\d+)$")


class _HtmlTableParser(HTMLParser):
    """본문 칸(``text-col``) 안의 ``<table>`` 을 페이지 번호와 함께 모은다.

    칸이 하나도 없는 ``<table>`` 은 버린다. 엔티티는 파서가 되돌린다.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[_OutputTable] = []
        self._page: int | None = None
        self._div_depth = 0  # 0 이면 본문 칸 밖
        self._table_depth = 0
        self._grid: Grid = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "section" and "page" in (attributes.get("class") or "").split():
            match = _PAGE_ID.match(attributes.get("id") or "")
            self._page = int(match.group(1)) if match else None
            return
        if self._div_depth == 0:
            if tag == "div" and "text-col" in (attributes.get("class") or "").split():
                self._div_depth = 1
            return
        if tag == "div":
            self._div_depth += 1
        elif tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._grid = []
        elif self._table_depth == 1 and tag == "tr":
            self._grid.append([])
        elif self._table_depth == 1 and tag in ("td", "th"):
            if not self._grid:
                self._grid.append([])
            self._cell = []

    def handle_endtag(self, tag):
        if self._div_depth == 0:
            return
        if tag == "div":
            self._div_depth -= 1
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0:
                self._close_cell()
                if any(self._grid):
                    self.tables.append(_OutputTable(page=self._page, grid=self._grid))
                self._grid = []
        elif self._table_depth == 1 and tag in ("td", "th"):
            self._close_cell()

    def _close_cell(self):
        if self._cell is not None:
            self._grid[-1].append("".join(self._cell))
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _parse_html_tables(html: str) -> list[_OutputTable]:
    parser = _HtmlTableParser()
    parser.feed(html)
    parser.close()
    return parser.tables


def _cell_diffs(expected: Grid, actual: Grid, normalize) -> list[CellDiff]:
    """두 격자를 겹친 범위 전체에서 칸별로 비교한다.

    원응답 쪽 모자란 칸은 출력기처럼 빈 칸으로 채운다. 한쪽 격자 밖 위치는 None 이다.
    """
    expected_cols = max(len(row) for row in expected)
    rows = max(len(expected), len(actual))
    cols = max(expected_cols, max((len(row) for row in actual), default=0))
    diffs: list[CellDiff] = []
    for r in range(rows):
        for c in range(cols):
            want = None
            if r < len(expected) and c < expected_cols:
                row = expected[r]
                want = normalize(row[c]) if c < len(row) else ""
            got = None
            if r < len(actual) and c < len(actual[r]):
                got = normalize(actual[r][c])
            if want != got:
                diffs.append(
                    CellDiff(
                        row=r + 1,
                        col=c + 1,
                        expected_head=None if want is None else want[:TEXT_HEAD_CHARS],
                        actual_head=None if got is None else got[:TEXT_HEAD_CHARS],
                    )
                )
    return diffs


def _compare_pair(
    fmt: str, source: _SourceTable, output: _OutputTable, normalize
) -> TableMismatch | None:
    if source.unverifiable:
        return None  # 개수와 순서에만 넣는다
    diffs = _cell_diffs(source.grid, output.grid, normalize)
    if source.shape == output.shape and not diffs:
        return None
    return TableMismatch(
        format=fmt,
        table_index=source.index,
        page=source.page,
        expected_shape=source.shape,
        actual_shape=output.shape,
        cell_diffs=tuple(diffs),
    )


def _pair_in_order(
    fmt: str,
    sources: list[_SourceTable],
    outputs: list[_OutputTable],
    normalize,
) -> list[TableMismatch]:
    """n 번째끼리 짝짓고, 짝 없는 표는 따로 적는다."""
    found: list[TableMismatch] = []
    for source, output in zip(sources, outputs):
        mismatch = _compare_pair(fmt, source, output, normalize)
        if mismatch:
            found.append(mismatch)
    for source in sources[len(outputs):]:
        found.append(
            TableMismatch(fmt, source.index, source.page, source.shape, None)
        )
    for output in outputs[len(sources):]:
        found.append(TableMismatch(fmt, None, output.page, None, output.shape))
    return found


def _html_sources_by_page(
    layout: _Layout,
    tables: list[_SourceTable],
    page_assignment: dict[int, list],
) -> tuple[dict[int, list[_SourceTable]], list[_SourceTable]]:
    """배정 결과로 페이지별 기대 표 목록과, 어느 항목에도 들지 않은 표를 만든다."""
    by_path = {table.path: table for table in tables}
    by_page: dict[int, list[_SourceTable]] = {}
    placed: set[BlockPath] = set()
    for page in sorted(page_assignment):
        for item in page_assignment[page]:
            mode, path = _item_mode_and_path(item)
            block = layout.block_at(path)
            if mode == "text_only":
                continue  # 자기 텍스트만 렌더된다
            for sub_path, _ in iter_blocks_with_paths(block, path):
                table = by_path.get(sub_path)
                if table is not None:
                    by_page.setdefault(page, []).append(table)
                    placed.add(sub_path)
    unplaced = [table for table in tables if table.path not in placed]
    return by_page, unplaced


def _check_html_tables(
    layout: _Layout,
    tables: list[_SourceTable],
    html: str,
    page_assignment: dict[int, list],
) -> tuple[list[TableMismatch], dict[str, int]]:
    outputs = _parse_html_tables(html)
    by_page, unplaced = _html_sources_by_page(layout, tables, page_assignment)
    out_by_page: dict[int | None, list[_OutputTable]] = {}
    for output in outputs:
        out_by_page.setdefault(output.page, []).append(output)

    found: list[TableMismatch] = []
    pages = sorted(set(by_page) | set(out_by_page), key=lambda p: (p is None, p or 0))
    for page in pages:
        found.extend(
            _pair_in_order(
                "html", by_page.get(page, []), out_by_page.get(page, []), _html_value
            )
        )
    found.extend(_pair_in_order("html", unplaced, [], _html_value))
    expected = sum(len(items) for items in by_page.values()) + len(unplaced)
    return found, {"expected": expected, "actual": len(outputs)}


# ── 진입점 ─────────────────────────────────────────────────────


def verify_outputs(
    document: documentai.Document,
    *,
    markdown: str | None = None,
    html: str | None = None,
    page_assignment: dict[int, list] | None = None,
) -> VerifyResult:
    """만든 MD·HTML 을 원응답과 대조한다.

    Args:
        document: 원응답 Document.
        markdown: 만든 MD 문자열. None 이면 MD 는 검사하지 않는다.
        html: 만든 HTML 문자열. None 이면 HTML 은 검사하지 않는다.
        page_assignment: ``HTMLExporter._group_blocks_by_page()`` 모양의 배정 결과
            ``{page: [PageItem(block, "full" | "text_only", path), ...]}``.
            html 을 줄 때 필수. 원응답 블록과는 ``path`` 로만 짝짓는다.

    Raises:
        ValueError: html 을 주고 page_assignment 를 주지 않았을 때, 배정 항목에
            위치 경로가 없거나 그 경로가 원응답에 없을 때.
    """
    if html is not None and page_assignment is None:
        raise ValueError("HTML 을 검사하려면 page_assignment 가 필요하다")

    layout = _Layout(document)
    expected = layout.expected
    checked: list[str] = []
    result = VerifyResult(
        checked_formats=checked,
        expected_count=len(expected),
        expected_chars=sum(len(item.text) for item in expected),
        text_none=not expected,
        footer_excluded_blocks=layout.footer_blocks,
        footer_excluded_chars=layout.footer_chars,
        unknown_page_count=sum(1 for item in expected if item.ref.page is None),
    )

    tables = _collect_source_tables(document)
    compared: dict[int, _SourceTable] = {}

    if markdown is not None:
        checked.append("md")
        result.md_missing = _check_markdown(expected, markdown)
        md_sources = [t for t in tables if not t.under_text_footer]
        md_outputs = _parse_markdown_tables(markdown)
        result.table_mismatches.extend(
            _pair_in_order("md", md_sources, md_outputs, _md_value)
        )
        result.table_counts["md"] = {
            "expected": len(md_sources),
            "actual": len(md_outputs),
        }
        compared.update((t.index, t) for t in md_sources)

    if html is not None:
        checked.append("html")
        result.html_missing = _check_html_text(expected, html)
        result.html_misplaced = _check_page_assignment(layout, page_assignment)
        html_mismatches, html_counts = _check_html_tables(
            layout, tables, html, page_assignment
        )
        result.table_mismatches.extend(html_mismatches)
        result.table_counts["html"] = html_counts
        compared.update((t.index, t) for t in tables)

    result.table_unverifiable = [
        UnverifiableTable(table_index=t.index, page=t.page, reason=t.unverifiable)
        for _, t in sorted(compared.items())
        if t.unverifiable
    ]
    return result
