#!/usr/bin/env python3
"""
Score predictions for summarization.jsonl using LLM-as-judge.

This script does NOT make API calls. It prints judge prompts to stdout, one per example,
which you can pipe to your provider of choice. Or import `build_judge_prompt` and call
your own client.

Usage:
    # print prompts
    python3 score_summarization.py datasets/summarization.jsonl predictions.jsonl --prompts

    # if you already have judge responses in judgments.jsonl:
    python3 score_summarization.py datasets/summarization.jsonl predictions.jsonl --score judgments.jsonl
"""
import argparse
import json
import re
import sys


JUDGE_PROMPT = """You are scoring a summary against a reference. Rate the candidate on three axes from 1 to 5:

faithfulness: does the candidate contain only claims supported by the source? 5 means every claim is supported. 1 means major fabrication.
coverage: does the candidate include the key points from the reference summary? 5 means all key points. 1 means most key points missing.
conciseness: is the candidate appropriately brief without losing information? 5 means tight and complete. 1 means rambling or padded.

Source:
{source}

Reference summary:
{reference}

Candidate summary:
{candidate}

Reply with ONLY a single line of JSON: {{"faithfulness": N, "coverage": N, "conciseness": N}}.
"""


def load_jsonl(path):
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def build_judge_prompt(source, reference, candidate):
    return JUDGE_PROMPT.format(source=source, reference=reference, candidate=candidate)


def print_prompts(dataset_path, predictions_path):
    dataset = {row["id"]: row for row in load_jsonl(dataset_path)}
    preds = {row["id"]: row for row in load_jsonl(predictions_path)}
    for example_id, row in dataset.items():
        if example_id not in preds:
            continue
        prompt = build_judge_prompt(
            source=row["input"],
            reference=row["expected"],
            candidate=preds[example_id]["prediction"],
        )
        print(json.dumps({"id": example_id, "prompt": prompt}))


def parse_judgment(text):
    match = re.search(r'\{[^{}]*\}', text)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
        return {k: int(obj[k]) for k in ("faithfulness", "coverage", "conciseness")}
    except (ValueError, KeyError):
        return None


def score(judgments_path):
    judgments = load_jsonl(judgments_path)
    axes = {"faithfulness": [], "coverage": [], "conciseness": []}
    rows_out = []
    for row in judgments:
        parsed = parse_judgment(row.get("response", ""))
        if parsed is None:
            rows_out.append({"id": row["id"], "parsed": False})
            continue
        for axis in axes:
            axes[axis].append(parsed[axis])
        rows_out.append({"id": row["id"], "parsed": True, **parsed})

    print(f"{'axis':<16} {'mean':>6} {'n':>4}")
    for axis, scores in axes.items():
        mean = sum(scores) / len(scores) if scores else 0
        print(f"{axis:<16} {mean:>6.2f} {len(scores):>4}")
    return rows_out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("predictions")
    parser.add_argument("--prompts", action="store_true", help="print judge prompts to stdout")
    parser.add_argument("--score", metavar="JUDGMENTS_FILE", help="score from completed judgments")
    args = parser.parse_args()

    if args.prompts:
        print_prompts(args.dataset, args.predictions)
    elif args.score:
        score(args.score)
    else:
        parser.error("pass --prompts or --score")


if __name__ == "__main__":
    main()
