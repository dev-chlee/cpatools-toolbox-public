"""폴더 내 모든 .dsd → .xlsx 일괄 변환 + 자동 검증 예제."""

import sys
import time
from pathlib import Path

# install 없이 단독 실행 가능하게 src/ 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from dsd_to_xlsx import convert, verify


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: python convert_batch.py <input_dir> <output_dir>", file=sys.stderr)
        return 1

    src_dir = Path(sys.argv[1])
    dst_dir = Path(sys.argv[2])
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
            if report.ok:
                ok += 1
                print(f"[{i:3d}/{len(files)}] OK   {src.name}")
            else:
                ok += 1
                issues.append(src.name)
                print(f"[{i:3d}/{len(files)}] WARN {src.name} -- 검증 이슈 ({len(report.missing_fs)}+{len(report.missing_meta)}+{len(report.missing_note_numbers)}+{len(report.empty_sheets)}건)")
        except Exception as exc:
            fail.append((src.name, str(exc)))
            print(f"[{i:3d}/{len(files)}] FAIL {src.name} -- {exc}")

    print(f"\n완료: {ok}/{len(files)} (검증 이슈 {len(issues)}건)  ({time.time()-t0:.1f}s)")
    if issues:
        print("검증 이슈 파일:")
        for name in issues:
            print(f"  - {name}  (`python examples/verify_xlsx.py <output_dir>/{Path(name).stem}.xlsx` 로 상세 확인)")
    return 0 if not fail else 2


if __name__ == "__main__":
    sys.exit(main())
