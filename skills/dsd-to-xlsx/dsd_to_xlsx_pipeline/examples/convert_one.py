"""단일 파일 변환 + 자동 검증 예제."""

import sys
from pathlib import Path

# install 없이 단독 실행 가능하게 src/ 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from dsd_to_xlsx import convert, verify


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python convert_one.py <input.dsd> [output.xlsx]", file=sys.stderr)
        return 1

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) >= 3 else src.with_suffix(".xlsx")

    out = convert(src, dst)
    print(f"OK: {out}")

    report = verify(out)
    print()
    print(report.format())
    return 0 if report.ok else 2


if __name__ == "__main__":
    sys.exit(main())
