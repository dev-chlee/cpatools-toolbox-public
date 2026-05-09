"""dsd-to-xlsx CLI entry point.

사용:
  python -m dsd_to_xlsx input.dsd [output.xlsx]    # 단일 변환 + 자동 검증
  python -m dsd_to_xlsx --verify converted.xlsx    # 검증만
  python -m dsd_to_xlsx --batch <input_dir> <output_dir>  # 폴더 일괄
  python -m dsd_to_xlsx --version
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from dsd_to_xlsx import convert, verify, __version__


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="dsd2xlsx",
        description="DSD → xlsx 변환 + 자동 검증",
    )
    p.add_argument("--version", action="version", version=f"dsd-to-xlsx {__version__}")
    p.add_argument("--verify", metavar="XLSX", help="이미 변환된 xlsx 검증만 수행")
    p.add_argument("--batch", nargs=2, metavar=("INPUT_DIR", "OUTPUT_DIR"),
                   help="폴더 일괄 변환 + 검증")
    p.add_argument("input", nargs="?", help="DSD 파일 (단일 변환)")
    p.add_argument("output", nargs="?", help="출력 xlsx 경로 (생략 시 input.xlsx)")
    args = p.parse_args(argv)

    if args.verify:
        report = verify(Path(args.verify))
        print(report.format())
        return 0 if report.ok else 2

    if args.batch:
        return _batch(Path(args.batch[0]), Path(args.batch[1]))

    if not args.input:
        p.print_help(sys.stderr)
        return 1

    src = Path(args.input)
    dst = Path(args.output) if args.output else src.with_suffix(".xlsx")
    out = convert(src, dst)
    print(f"OK: {out}")
    print()
    report = verify(out)
    print(report.format())
    return 0 if report.ok else 2


def _batch(src_dir: Path, dst_dir: Path) -> int:
    dst_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(src_dir.glob("*.dsd"))
    if not files:
        print(f"DSD 없음: {src_dir}", file=sys.stderr)
        return 1

    ok = 0
    fail: list[tuple[str, str]] = []
    issues: list[str] = []
    t0 = time.time()
    for i, src in enumerate(files, 1):
        dst = dst_dir / (src.stem + ".xlsx")
        try:
            convert(src, dst)
            report = verify(dst)
            ok += 1
            if report.ok:
                print(f"[{i:3d}/{len(files)}] OK   {src.name}")
            else:
                issues.append(src.name)
                cnt = (len(report.missing_fs) + len(report.missing_meta)
                       + len(report.missing_note_numbers) + len(report.empty_sheets))
                print(f"[{i:3d}/{len(files)}] WARN {src.name} -- 검증 이슈 {cnt}건")
        except Exception as exc:
            fail.append((src.name, str(exc)))
            print(f"[{i:3d}/{len(files)}] FAIL {src.name} -- {exc}")

    print(f"\n완료: {ok}/{len(files)} (검증 이슈 {len(issues)}건)  ({time.time()-t0:.1f}s)")
    return 0 if not fail and not issues else 2


if __name__ == "__main__":
    sys.exit(main())
