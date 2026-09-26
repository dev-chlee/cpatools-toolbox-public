"""
Claude/Codex 대화에서 사용할 매출 TOD 자료·판정의 로컬 파일 변환기.

증빙 bundle을 검토 자료 JSONL로 저장하고, 현재 대화에서 작성한 판정을
tod_engine.py가 검증할 verdict JSON으로 변환한다. 문서 판단은 현재 대화가 한다.
"""

import argparse
import json
import os
import sys

import cpa_storage
from prompt_builder import build_judgment_prompt


def _utf8_console():
    """Windows 기본 콘솔에서도 한글 도움말과 진행 메시지를 UTF-8로 출력한다."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8')
            except (AttributeError, OSError):
                pass


def load_bundles(path):
    """Load bundles from a tod_engine --bundles-out JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get("bundles"), list):
        return data["bundles"]
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "sample" in data and "profile" in data:
        return [data]
    raise ValueError("bundles JSON은 배열, 단일 bundle 또는 {'bundles': [...]} 형식이어야 합니다.")


def build_prompt_job(bundle):
    """현재 Claude/Codex가 읽을 표본 한 건의 검토 자료를 구성한다."""
    sample = bundle.get("sample", {})
    folder = sample.get("folder", "")
    profile = (bundle.get("profile") or {}).get("id", "")
    return {
        "sample_folder": folder,
        "profile": profile,
        "prompt": build_judgment_prompt(bundle),
        "evidence_bundle": bundle,
    }


def build_prompt_jobs(bundles):
    """Build prompt jobs from evidence bundles."""
    return [build_prompt_job(bundle) for bundle in bundles]


def write_jsonl(items, path):
    """Write items as UTF-8 JSONL."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")


def read_jsonl(path):
    """Read UTF-8 JSONL, skipping blank lines."""
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no}: 올바르지 않은 JSONL 행: {e}") from e
    return items


def _strip_json_fence(text):
    stripped = str(text or "").strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def parse_verdict_payload(item):
    """
    Extract a verdict object from one response item.

    Accepted shapes:
      - verdict object itself: {"sample_folder": "...", "checks": {...}}
      - wrapper: {"sample_folder": "...", "verdict": {...}}
      - wrapper: {"sample_folder": "...", "response": "{...json...}"}
      - wrapper: {"sample_folder": "...", "content": "{...json...}"}
    """
    if not isinstance(item, dict):
        raise ValueError("판정 응답 항목은 JSON 객체여야 합니다.")

    if isinstance(item.get("verdict"), dict):
        verdict = dict(item["verdict"])
    elif "checks" in item:
        verdict = dict(item)
    else:
        raw = item.get("response", item.get("content"))
        if raw is None:
            raise ValueError("판정 응답 항목에는 verdict, checks, response 또는 content가 필요합니다.")
        raw = _strip_json_fence(raw)
        try:
            verdict = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Claude/Codex 판정 응답이 JSON이 아닙니다: {e}") from e
        if not isinstance(verdict, dict):
            raise ValueError("Claude/Codex 판정 응답 JSON은 객체여야 합니다.")

    if not verdict.get("sample_folder") and item.get("sample_folder"):
        verdict["sample_folder"] = item["sample_folder"]
    if not verdict.get("profile") and item.get("profile"):
        verdict["profile"] = item["profile"]
    return verdict


def collect_verdicts(response_items):
    """Convert response JSONL items to {'verdicts': [...]}."""
    verdicts = [parse_verdict_payload(item) for item in response_items]
    return {"verdicts": verdicts}


def main(argv=None):
    _utf8_console()
    ap = argparse.ArgumentParser(
        description="Claude/Codex 대화용 검토 자료와 판정을 로컬 JSONL/JSON으로 변환한다."
    )
    ap.add_argument("bundles_json", help="tod_engine.py --bundles-out 결과 JSON")
    ap.add_argument("--prompts-out", help="현재 대화에서 읽을 검토 자료 JSONL 출력")
    ap.add_argument("--responses", help="현재 대화에서 작성해 저장한 판정 JSONL 입력")
    ap.add_argument("--verdicts-out", help="tod_engine.py --verdicts 입력용 JSON 출력")
    args = ap.parse_args(argv)
    try:
        for out in (args.prompts_out, args.verdicts_out):
            if out:
                cpa_storage.guard(out)
    except cpa_storage.StorageError as exc:
        ap.error(str(exc))

    bundles = load_bundles(args.bundles_json)
    if args.prompts_out:
        jobs = build_prompt_jobs(bundles)
        write_jsonl(jobs, args.prompts_out)
        print(f"prompt jobs 저장: {args.prompts_out} ({len(jobs)}건)")

    if args.responses:
        if not args.verdicts_out:
            raise SystemExit("--responses 사용 시 --verdicts-out 이 필요합니다.")
        verdicts = collect_verdicts(read_jsonl(args.responses))
        os.makedirs(os.path.dirname(args.verdicts_out) or ".", exist_ok=True)
        with open(args.verdicts_out, "w", encoding="utf-8") as f:
            json.dump(verdicts, f, ensure_ascii=False, indent=2, default=str)
        print(f"verdicts 저장: {args.verdicts_out} ({len(verdicts['verdicts'])}건)")

    if not args.prompts_out and not args.responses:
        print(f"bundles 로드 완료: {len(bundles)}건")


if __name__ == "__main__":
    main()
