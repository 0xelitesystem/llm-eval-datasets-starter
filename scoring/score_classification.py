#!/usr/bin/env python3
"""
Score predictions for intent-classification.jsonl.

Usage:
    python3 score_classification.py datasets/intent-classification.jsonl predictions.jsonl
"""
import json
import sys
from collections import defaultdict


def load_jsonl(path):
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main(dataset_path, predictions_path):
    dataset = {row["id"]: row for row in load_jsonl(dataset_path)}
    preds = {row["id"]: row for row in load_jsonl(predictions_path)}

    missing = set(dataset) - set(preds)
    if missing:
        print(f"warning: {len(missing)} predictions missing", file=sys.stderr)

    total = 0
    correct = 0
    per_label = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    rows_out = []

    for example_id, row in dataset.items():
        if example_id not in preds:
            continue
        gold = row["expected"]
        pred = preds[example_id]["prediction"]
        is_correct = gold == pred
        total += 1
        correct += int(is_correct)
        if is_correct:
            per_label[gold]["tp"] += 1
        else:
            per_label[gold]["fn"] += 1
            per_label[pred]["fp"] += 1
        rows_out.append({"id": example_id, "gold": gold, "pred": pred, "correct": is_correct})

    accuracy = correct / total if total else 0.0
    print(f"accuracy: {accuracy:.3f} ({correct}/{total})")
    print()
    print(f"{'label':<20} {'precision':>10} {'recall':>8} {'f1':>6}")
    for label in sorted(per_label):
        c = per_label[label]
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        print(f"{label:<20} {prec:>10.3f} {rec:>8.3f} {f1:>6.3f}")

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
