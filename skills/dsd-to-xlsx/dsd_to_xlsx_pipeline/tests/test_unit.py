"""
dsd-to-xlsx 단위 테스트
========================
import sanity + 핵심 함수 시그니처 점검. 실제 .dsd 변환은 examples/test_self.py가
담당하므로 여기서는 모듈 구조만 검증한다.

실행: python tests/test_unit.py
"""
import sys, os, json
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, 'reconfigure'):
        try:
            _s.reconfigure(encoding='utf-8')
        except (AttributeError, OSError):
            pass

PKG_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG_ROOT / 'src'))

results = []


def run_test(name, fn, description=""):
    try:
        ok = bool(fn())
        results.append({
            'name': name, 'description': description, 'passed': ok, 'error': None,
        })
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    except Exception as e:
        results.append({
            'name': name, 'description': description, 'passed': False, 'error': str(e),
        })
        print(f"  [FAIL] {name} — {e}")


# ============================================================
# 1. 모듈 import sanity
# ============================================================
print("=" * 60)
print("1. dsd_to_xlsx 모듈 import")
print("=" * 60)

def import_top():
    import dsd_to_xlsx as m
    return all(hasattr(m, n) for n in (
        'convert', 'parse', 'render_xlsx', 'verify', '__version__'
    ))

run_test('top_level_api', import_top,
         "convert / parse / render_xlsx / verify / __version__ 노출")


def import_subpackages():
    import dsd_to_xlsx.core, dsd_to_xlsx.parsers, dsd_to_xlsx.extractors, dsd_to_xlsx.renderers, dsd_to_xlsx.verify  # noqa
    return True

run_test('subpackages_import', import_subpackages,
         "core / parsers / extractors / renderers / verify subpackage import")


# ============================================================
# 2. 버전 형식
# ============================================================
print()
print("=" * 60)
print("2. 버전 형식")
print("=" * 60)


def version_is_string():
    from dsd_to_xlsx import __version__
    return isinstance(__version__, str) and len(__version__.split('.')) >= 2

run_test('version_format', version_is_string, "x.y[.z] 형식")


# ============================================================
# 3. VerifyReport 자료구조
# ============================================================
print()
print("=" * 60)
print("3. VerifyReport sanity")
print("=" * 60)


def verify_report_attrs():
    from dsd_to_xlsx.verify import VerifyReport
    # 더미 path로 인스턴스 생성 후 속성 존재 확인
    r = VerifyReport(xlsx_path='/tmp/dummy.xlsx')
    return all(hasattr(r, a) for a in (
        'ok', 'missing_fs', 'missing_meta', 'missing_note_numbers',
    ))

run_test('verify_report_shape', verify_report_attrs,
         "ok / missing_fs / missing_meta / missing_note_numbers")


# ============================================================
# 4. CLI entry
# ============================================================
print()
print("=" * 60)
print("4. CLI entry")
print("=" * 60)


def main_callable():
    from dsd_to_xlsx.__main__ import main  # noqa: F401
    return callable(main)

run_test('main_callable', main_callable, "python -m dsd_to_xlsx 진입점 존재")


# ============================================================
# 결과
# ============================================================
print()
print("=" * 60)
total = len(results)
passed = sum(1 for r in results if r['passed'])
failed = total - passed
print(f"UNIT TEST 결과: {passed}/{total} PASS ({failed} FAIL)")
print("=" * 60)

out = Path(__file__).parent / 'test_results_unit.json'
with open(out, 'w', encoding='utf-8') as f:
    json.dump({'total': total, 'passed': passed, 'failed': failed, 'tests': results},
              f, ensure_ascii=False, indent=2)
print(f"\n결과 파일: {out}")
sys.exit(0 if failed == 0 else 1)
