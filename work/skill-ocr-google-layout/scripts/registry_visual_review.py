#!/usr/bin/env python3
"""등기부 취소선 사전 판독·조건별 분기·상세 판독·현행본 생성 (외부 API 호출 없음)."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

SKILL = "skill-ocr-google-layout"
# 명령별 기본 출력: (보관소 칸, 폴더). 판독 중간물은 work, 현행본은 output.
DEFAULT_OUTPUT = {"screen": ("work", "registry-screen"), "route": ("work", "registry-route"),
                  "prepare": ("work", "registry-review"), "export": ("output", "registry-current")}

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import cpa_storage
from src.registry_review import ReviewError, export_current, prepare, validate
from src.registry_screening import screen, route


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    initial = commands.add_parser("screen", help="전체 페이지의 취소선 존재 여부 확인 준비")
    initial.add_argument("--pdf", required=True, help="원본 전체 PDF")
    initial.add_argument("--ocr", help="기존 OCR HTML·MD·TXT (생략 가능)")
    initial.add_argument("--dpi", type=int, default=200, help="이미지 DPI (150~600, 기본 200)")
    initial.add_argument("--output", help="새 사전 판독 폴더 (기본: 보관소 work/registry-screen)")
    routing = commands.add_parser("route", help="존재·불확실은 상세 이미지 판독, 확인된 부재는 텍스트 분석")
    routing.add_argument("--bundle", required=True, help="screen의 screen-bundle.json")
    routing.add_argument("--screening", required=True, help="이미지 존재 여부를 확인한 screening.json")
    routing.add_argument("--output", help="새 분기 결과 폴더 (기본: 보관소 work/registry-route)")
    prep = commands.add_parser("prepare", help="원본 이미지와 미검토 판독 대장 생성")
    prep.add_argument("--pdf", required=True, help="원본 PDF")
    prep.add_argument("--ocr", required=True, help="페이지별 text-col이 있는 OCR HTML")
    prep.add_argument("--source-pages", help="OCR 쪽 순서에 대응하는 원본 물리 쪽수, 예: 4,5,6")
    prep.add_argument("--dpi", type=int, default=200, help="이미지 DPI (150~600, 기본 200)")
    prep.add_argument("--output", help="새 검토 폴더 (기본: 보관소 work/registry-review)")
    for name, description in (("validate", "이미지 판독 완결성 검증"), ("export", "검증 후 현행본 별도 생성")):
        command = commands.add_parser(name, help=description)
        command.add_argument("--bundle", required=True, help="prepare가 만든 bundle.json")
        command.add_argument("--review", required=True, help="이미지 판독을 마친 review.json")
        if name == "export":
            command.add_argument("--output", help="새 결과 폴더 (기본: 보관소 output/registry-current)")
    args = parser.parse_args()
    if args.command in DEFAULT_OUTPUT:
        try:
            if args.output:
                args.output = str(cpa_storage.guard(args.output))
            else:
                slot_name, folder = DEFAULT_OUTPUT[args.command]
                args.output = str(cpa_storage.slot(SKILL, slot_name) / folder)
        except cpa_storage.StorageError as exc:
            parser.error(str(exc))
    try:
        if args.command == "screen":
            result = screen(args.pdf, args.output, args.ocr, args.dpi)
        elif args.command == "route":
            result = route(args.bundle, args.screening, args.output)
        elif args.command == "prepare":
            mapping = [int(x.strip()) for x in args.source_pages.split(",")] if args.source_pages else None
            result = prepare(args.pdf, args.ocr, args.output, mapping, args.dpi)
        elif args.command == "export":
            result = export_current(args.bundle, args.review, args.output)
        else:
            bundle, _, units, audit = validate(args.bundle, args.review)
            result = {"status": "PASS", "pages": len(bundle["pages"]), "retained_units": len(units), "input_units": len(audit)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ReviewError, OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"현행본 처리 실패: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
