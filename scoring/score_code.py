#!/usr/bin/env python3
"""
Score predictions for code-tasks.jsonl by executing the predicted function against tests.

Each prediction is expected to be a Python source string defining a function. The scorer
writes the code plus a test harness to a temp file and runs it in a subprocess with a
5-second timeout.

WARNING: this executes untrusted model output. Run in a sandbox or container. Do not run
on a machine with sensitive data.

Usage:
    python3 score_code.py datasets/code-tasks.jsonl predictions.jsonl
"""
import json
import os
import subprocess
import sys
import tempfile


HARNESS = '''
import json
import sys

{code}

def _run_tests(tests):
    results = []
    for i, t in enumerate(tests):
        inp = t["input"]
        expected = t["expected"]
        try:
            if isinstance(inp, list):
                actual = FUNC(*inp)
            else:
                actual = FUNC(inp)
            ok = actual == expected
            results.append({{"i": i, "ok": ok, "expected": expected, "actual": actual}})
        except Exception as e:
            results.append({{"i": i, "ok": False, "error": str(e)}})
    print(json.dumps(results))

tests = json.loads(sys.argv[1])
_run_tests(tests)
'''


def load_jsonl(path):
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def extract_func_name(code):
    """Find first 'def NAME(' in the code."""
    import re
    m = re.search(r"^\s*def\s+([a-zA-Z_]\w*)\s*\(", code, re.MULTILINE)
    return m.group(1) if m else None


def run_one(code, tests, timeout=5):
    func_name = extract_func_name(code)
    if not func_name:
        return {"error": "no function definition found", "passed": 0, "total": len(tests)}
    full = HARNESS.format(code=code).replace("FUNC", func_name)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(full)
        path = fh.name
    try:
        proc = subprocess.run(
            ["python3", path, json.dumps(tests)],
            capture_output=True, text=True, timeout=timeout,
        )
        if proc.returncode != 0:
            return {"error": proc.stderr.strip().splitlines()[-1] if proc.stderr else "non-zero exit", "passed": 0, "total": len(tests)}
        try:
            results = json.loads(proc.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            return {"error": "bad harness output", "passed": 0, "total": len(tests)}
        passed = sum(1 for r in results if r.get("ok"))
        return {"passed": passed, "total": len(tests), "results": results}
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "passed": 0, "total": len(tests)}
    finally:
        os.unlink(path)


def main(dataset_path, predictions_path):
    dataset = {row["id"]: row for row in load_jsonl(dataset_path)}
    preds = {row["id"]: row for row in load_jsonl(predictions_path)}

    total_tests = 0
    total_passed = 0
    fully_solved = 0
    examples_with_tests = 0
    rows_out = []

    for example_id, row in dataset.items():
        if example_id not in preds:
            continue
        tests = row.get("tests") or []
        if not tests:
            rows_out.append({"id": example_id, "skipped": True})
            continue
        examples_with_tests += 1
        result = run_one(preds[example_id]["prediction"], tests)
        passed = result["passed"]
        total = result["total"]
        total_passed += passed
        total_tests += total
        if passed == total:
            fully_solved += 1
        rows_out.append({"id": example_id, "passed": passed, "total": total, "error": result.get("error")})

    print(f"tasks fully solved: {fully_solved}/{examples_with_tests} = {fully_solved/examples_with_tests:.3f}")
    print(f"test pass rate:     {total_passed}/{total_tests} = {total_passed/total_tests:.3f}")

    out_path = predictions_path + ".results.jsonl"
    with open(out_path, "w") as fh:
        for r in rows_out:
            fh.write(json.dumps(r) + "\n")
    print(f"\nper-example results: {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
