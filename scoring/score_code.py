#!/usr/bin/env python3
"""
Score predictions for code-tasks.jsonl by executing the predicted function against tests.

Each prediction is expected to be a Python source string defining a function. The scorer
writes the code plus a test harness to a fresh temp folder and runs it in a subprocess with
a 5-second timeout. The subprocess starts in that folder, in Python isolated mode (-I), with
only PATH and SYSTEMROOT in its environment, so API keys in your environment are not passed
on. Every process it starts is killed when scoring of that example ends.

WARNING: this executes untrusted model output. That is not a sandbox: the code still runs as
your user, with your files and your network. Run in a sandbox or container. Do not run on a
machine with sensitive data.

Usage:
    python3 score_code.py datasets/code-tasks.jsonl predictions.jsonl
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class _JobBasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _JobExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JobBasicLimits),
            ("IoInfo", ctypes.c_uint64 * 6),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    _k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    _k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _k32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _k32.CloseHandle.argtypes = (wintypes.HANDLE,)


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


def _child_env():
    """Only what Python needs to start. API keys and other secrets stay behind."""
    return {k: os.environ[k] for k in ("PATH", "SYSTEMROOT") if k in os.environ}


def _windows_job(proc):
    """Put the child in a Job object so every process it starts can be killed with it."""
    job = _k32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = _JobExtendedLimits()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if (_k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))  # 9 = extended limits
            and _k32.AssignProcessToJobObject(job, int(proc._handle))):
        return job
    _k32.CloseHandle(job)
    return None


def _kill_tree(proc, job):
    """Kill the child and every process it started."""
    if job:
        _k32.TerminateJobObject(job, 1)
    elif os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
    elif proc.poll() is None:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if proc.poll() is None:
        proc.kill()


def _remove_dir(path):
    """Delete the scratch folder. A process killed a moment ago can still hold it briefly."""
    for _ in range(40):
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            return
        time.sleep(0.05)


def run_one(code, tests, timeout=5):
    func_name = extract_func_name(code)
    if not func_name:
        return {"error": "no function definition found", "passed": 0, "total": len(tests)}
    full = HARNESS.format(code=code).replace("FUNC", func_name)
    workdir = tempfile.mkdtemp(prefix="score_code_")
    with tempfile.NamedTemporaryFile("w", suffix=".py", dir=workdir, delete=False) as fh:
        fh.write(full)
        path = fh.name
    proc = job = None
    try:
        proc = subprocess.Popen(
            [sys.executable, "-I", path, json.dumps(tests)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=workdir, env=_child_env(), start_new_session=(os.name == "posix"),
        )
        job = _windows_job(proc) if os.name == "nt" else None
        stdout, stderr = proc.communicate(timeout=timeout)
        if proc.returncode != 0:
            return {"error": stderr.strip().splitlines()[-1] if stderr else "non-zero exit", "passed": 0, "total": len(tests)}
        try:
            results = json.loads(stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            return {"error": "bad harness output", "passed": 0, "total": len(tests)}
        passed = sum(1 for r in results if r.get("ok"))
        return {"passed": passed, "total": len(tests), "results": results}
    except subprocess.TimeoutExpired:
        _kill_tree(proc, job)
        try:
            proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass
        return {"error": "timeout", "passed": 0, "total": len(tests)}
    finally:
        if proc is not None:
            _kill_tree(proc, job)
            proc.wait()
        if job:
            _k32.CloseHandle(job)
        _remove_dir(workdir)


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
