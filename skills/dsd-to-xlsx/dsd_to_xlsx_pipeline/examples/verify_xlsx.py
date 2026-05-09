"""이미 변환된 xlsx의 검증만 단독 실행."""

import sys
from pathlib import Path

# install 없이 단독 실행 가능하게 src/ 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from dsd_to_xlsx import verify


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python verify_xlsx.py <converted.xlsx>", file=sys.stderr)
        return 1

    report = verify(Path(sys.argv[1]))
    print(report.format())
    return 0 if report.ok else 2


if __name__ == "__main__":
    sys.exit(main())
