"""Tests for scoring/score_code.py.

These run small Python snippets through the scorer, the same way it runs
model predictions. Run from the repo root:
    python -m unittest discover -s tests
"""
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scoring"))

import score_code  # noqa: E402

REVERSE_TESTS = [
    {"input": "hello", "expected": "olleh"},
    {"input": "", "expected": ""},
    {"input": "a", "expected": "a"},
    {"input": "AB CD", "expected": "DC BA"},
]

GRANDCHILD_SECONDS = 20


def _alive(pid):
    """True while process `pid` is still running."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            k32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)
    try:
        with open("/proc/%d/stat" % pid) as fh:
            if fh.read().rsplit(")", 1)[1].split()[0] == "Z":
                return False
    except (OSError, IndexError):
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_dead(pid, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return not _alive(pid)


def _spawn_grandchild_code(pid_file, detach, then):
    """Prediction source that starts a long-running grandchild process, waits
    until it has written its pid, then runs `then` at module level."""
    grandchild = (
        "import os, time; "
        "open({tmp!r}, 'w').write(str(os.getpid()) + chr(10) + os.getcwd()); "
        "os.replace({tmp!r}, {dst!r}); "
        "time.sleep({secs})"
    ).format(tmp=pid_file + ".tmp", dst=pid_file, secs=GRANDCHILD_SECONDS)
    stdio = ", stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL" if detach else ""
    return (
        "import os, subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', {gc!r}]{stdio})\n"
        "_t = time.monotonic()\n"
        "while not os.path.exists({pf!r}) and time.monotonic() - _t < 10:\n"
        "    time.sleep(0.05)\n"
        "{then}\n"
        "def reverse_string(s):\n"
        "    return s[::-1]\n"
    ).format(gc=grandchild, stdio=stdio, pf=pid_file, then=then)


class NormalScoringTest(unittest.TestCase):
    def test_correct_solution_passes(self):
        r = score_code.run_one("def reverse_string(s):\n    return s[::-1]\n", REVERSE_TESTS)
        self.assertIsNone(r.get("error"))
        self.assertEqual((r["passed"], r["total"]), (4, 4))

    def test_wrong_solution_fails(self):
        r = score_code.run_one("def reverse_string(s):\n    return s\n", REVERSE_TESTS)
        self.assertIsNone(r.get("error"))
        self.assertEqual((r["passed"], r["total"]), (2, 4))

    def test_crashing_solution_reports_last_stderr_line(self):
        r = score_code.run_one("raise ValueError('boom')\ndef reverse_string(s):\n    return s\n", REVERSE_TESTS)
        self.assertEqual(r["error"], "ValueError: boom")
        self.assertEqual((r["passed"], r["total"]), (0, 4))

    def test_missing_function(self):
        r = score_code.run_one("x = 1\n", REVERSE_TESTS)
        self.assertEqual(r["error"], "no function definition found")

    def test_hanging_solution_times_out(self):
        r = score_code.run_one("import time\ntime.sleep(30)\ndef reverse_string(s):\n    return s\n",
                               REVERSE_TESTS, timeout=2)
        self.assertEqual(r["error"], "timeout")


class IsolationTest(unittest.TestCase):
    """Prediction code must not see the caller's secrets or working folder."""

    def test_api_keys_in_environment_are_not_inherited(self):
        code = (
            "import os\n"
            "_AT_IMPORT = os.environ.get('ANTHROPIC_API_KEY', 'none')\n"
            "def probe(x):\n"
            "    return [_AT_IMPORT, os.environ.get('OPENAI_API_KEY', 'none')]\n"
        )
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-CANARY",
                                          "OPENAI_API_KEY": "sk-CANARY"}):
            r = score_code.run_one(code, [{"input": "x", "expected": ["none", "none"]}])
        self.assertIsNone(r.get("error"), r)
        self.assertEqual(r["passed"], 1, r)

    def test_code_does_not_run_in_callers_working_folder(self):
        code = (
            "import os\n"
            "open('LEAKED.txt', 'w').write('x')\n"
            "_CWD = os.getcwd()\n"
            "def probe(x):\n"
            "    return _CWD\n"
        )
        old = os.getcwd()
        with tempfile.TemporaryDirectory() as caller_dir:
            os.chdir(caller_dir)
            try:
                r = score_code.run_one(code, [{"input": 0, "expected": None}])
            finally:
                os.chdir(old)
            self.assertIsNone(r.get("error"), r)
            self.assertFalse(os.path.exists(os.path.join(caller_dir, "LEAKED.txt")))
            child_cwd = r["results"][0]["actual"]
            self.assertNotEqual(os.path.normcase(os.path.realpath(child_cwd)),
                                os.path.normcase(os.path.realpath(caller_dir)))
        # The scratch folder is removed after scoring.
        self.assertFalse(os.path.exists(child_cwd))


class ProcessTreeTest(unittest.TestCase):
    """Processes started by prediction code must not outlive scoring."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pid_file = os.path.join(self.tmp.name, "grandchild.pid")

    def tearDown(self):
        # Clean up after a failing run so no stray process is left behind.
        try:
            pid = self._grandchild_pid()
            if _alive(pid):
                os.kill(pid, 9 if os.name != "nt" else 1)
        except (OSError, ValueError):
            pass
        self.tmp.cleanup()

    def _grandchild_pid(self):
        with open(self.pid_file) as fh:
            return int(fh.read().splitlines()[0])

    def _grandchild_cwd(self):
        with open(self.pid_file) as fh:
            return fh.read().splitlines()[1]

    def test_timeout_kills_grandchildren_and_returns_promptly(self):
        # The grandchild keeps the output pipes open; the child hangs.
        code = _spawn_grandchild_code(self.pid_file, detach=False, then="time.sleep(40)")
        start = time.monotonic()
        r = score_code.run_one(code, REVERSE_TESTS, timeout=3)
        elapsed = time.monotonic() - start
        self.assertEqual(r["error"], "timeout")
        self.assertLess(elapsed, 12, "scorer waited %.1fs for processes the prediction started" % elapsed)
        self.assertTrue(_wait_dead(self._grandchild_pid()), "grandchild survived the timeout")
        self.assertFalse(os.path.exists(self._grandchild_cwd()), "scratch folder left behind")

    def test_detached_grandchild_does_not_outlive_scoring(self):
        # The child finishes normally but leaves a background process running.
        code = _spawn_grandchild_code(self.pid_file, detach=True, then="")
        r = score_code.run_one(code, REVERSE_TESTS, timeout=5)
        self.assertIsNone(r.get("error"), r)
        self.assertEqual(r["passed"], 4)
        self.assertTrue(_wait_dead(self._grandchild_pid()), "grandchild still running after scoring")
        self.assertFalse(os.path.exists(self._grandchild_cwd()), "scratch folder left behind")


if __name__ == "__main__":
    unittest.main()
