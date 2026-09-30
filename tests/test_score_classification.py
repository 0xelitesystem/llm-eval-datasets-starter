"""Tests for scoring/score_classification.py.

Run from the repo root:
    python -m unittest discover -s tests
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scoring"))

import score_classification  # noqa: E402


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _score(dataset_rows, pred_rows):
    """Run main() on temp files. Returns (stdout text, parsed results rows)."""
    with tempfile.TemporaryDirectory() as d:
        dataset_path = os.path.join(d, "dataset.jsonl")
        preds_path = os.path.join(d, "preds.jsonl")
        _write_jsonl(dataset_path, dataset_rows)
        _write_jsonl(preds_path, pred_rows)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            score_classification.main(dataset_path, preds_path)
        with open(preds_path + ".results.jsonl", encoding="utf-8") as fh:
            results = [json.loads(line) for line in fh if line.strip()]
    return buf.getvalue(), results


class NormalOutputTest(unittest.TestCase):
    def test_summary_and_table_are_unchanged(self):
        out, results = _score(
            [
                {"id": "a", "expected": "billing"},
                {"id": "b", "expected": "billing"},
                {"id": "c", "expected": "greeting"},
            ],
            [
                {"id": "a", "prediction": "billing"},
                {"id": "b", "prediction": "greeting"},
                {"id": "c", "prediction": "greeting"},
            ],
        )
        head = out.split("\nper-example results:")[0]
        self.assertEqual(
            head,
            "accuracy: 0.667 (2/3)\n"
            "\n"
            "label                 precision   recall     f1\n"
            "billing                   1.000    0.500  0.667\n"
            "greeting                  0.500    1.000  0.667\n",
        )
        self.assertEqual([r["correct"] for r in results], [True, False, True])


class TerminalEscapeInjectionTest(unittest.TestCase):
    """A prediction label must not reach the terminal as raw control characters."""

    PAYLOAD = (
        "\x1b]0;OWNED\x07"            # OSC: set window title
        "\x1b]52;c;SGVsbG8=\x07"      # OSC 52: clipboard write
        "\x1b7\x1b[3A\r"              # save cursor, move up, carriage return
        "accuracy: 1.000 (100/100)\x1b[K\x1b8\r"
        "\x9b31m"                     # C1 CSI
        "\x7f\x00"                    # DEL, NUL
        "\u202eevil\u2066\u200f\u061c"  # bidi controls
        "account_help"
    )

    def test_control_characters_are_escaped_in_printed_table(self):
        out, results = _score(
            [{"id": "intent-001", "expected": "billing"}],
            [{"id": "intent-001", "prediction": self.PAYLOAD}],
        )
        for ch in ["\x1b", "\x07", "\r", "\x9b", "\x7f", "\x00",
                   "\u202e", "\u2066", "\u200f", "\u061c"]:
            self.assertNotIn(ch, out, "raw control character %r printed" % ch)
        # The label is still visible, in escaped form.
        self.assertIn("\\x1b]0;OWNED\\x07", out)
        self.assertIn("\\u202eevil", out)
        # The real score is what the terminal shows.
        self.assertTrue(out.startswith("accuracy: 0.000 (0/1)\n"))
        # The machine-readable results keep the exact prediction.
        self.assertEqual(results[0]["pred"], self.PAYLOAD)

    def test_gold_labels_from_a_custom_dataset_are_escaped_too(self):
        out, _ = _score(
            [{"id": "x", "expected": "ok\x1b[2J"}],
            [{"id": "x", "prediction": "ok\x1b[2J"}],
        )
        self.assertNotIn("\x1b", out)
        self.assertIn("ok\\x1b[2J", out)


if __name__ == "__main__":
    unittest.main()
