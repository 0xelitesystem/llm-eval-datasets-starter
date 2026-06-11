#!/usr/bin/env python3
"""
Score predictions for email-extraction.jsonl.

Usage:
    python3 score_extraction.py datasets/email-extraction.jsonl predictions.jsonl
"""
import json
import sys
from collections import defaultdict


def load_jsonl(path):
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def normalize(v):
    if isinstance(v, list):
        return [str(x).strip().lower() for x in v]
    if v is None:
        return None
    return str(v).strip().lower()


def main(dataset_path, predictions_path):
    dataset = {row["id"]: row for row in load_jsonl(dataset_path)}
    preds = {row["id"]: row for row in load_jsonl(predictions_path)}

    total_examples = 0
    fully_correct = 0
    field_counts = defaultdict(lambda: {"correct": 0, "total": 0})
    rows_out = []

    for example_id, row in dataset.items():
        if example_id not in preds:
            continue
        gold = row["expected"]
        pred = preds[example_id]["prediction"]
        total_examples += 1
        field_results = {}
        all_match = True
        for field in gold:
            g = normalize(gold.get(field))
            p = normalize(pred.get(field)) if isinstance(pred, dict) else None
            match = g == p
            field_results[field] = match
            field_counts[field]["total"] += 1
            field_counts[field]["correct"] += int(match)
            if not match:
                all_match = False
        if all_match:
            fully_correct += 1
        rows_out.append({"id": example_id, "fields": field_results, "all_match": all_match})

    print(f"fully correct: {fully_correct}/{total_examples} = {fully_correct/total_examples:.3f}")
    print()
    print(f"{'field':<20} {'accuracy':>10}")
    for field in sorted(field_counts):
        c = field_counts[field]
        acc = c["correct"] / c["total"] if c["total"] else 0.0
        print(f"{field:<20} {acc:>10.3f} ({c['correct']}/{c['total']})")

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
