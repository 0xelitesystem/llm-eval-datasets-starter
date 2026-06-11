# Scoring format

Every scorer reads a predictions JSONL file and compares it against the source dataset. Each line of the predictions file must contain at least:

```json
{"id": "...", "prediction": ...}
```

The `id` must match an id in the dataset. The `prediction` field type depends on the dataset (see below).

## Per-dataset prediction shape

### intent-classification.jsonl
- `prediction`: string, one of the 5 intent labels (`question`, `command`, `complaint`, `feedback`, `greeting`).
- Scorer: exact string match. Reports accuracy and per-label precision/recall/F1.

### email-extraction.jsonl
- `prediction`: object with the same keys as `expected` in the dataset (`sender`, `subject`, `date`, `action_items`).
- Scorer: field-level exact match. Reports accuracy per field and overall.

### summarization.jsonl
- `prediction`: string, the generated summary.
- Scorer: LLM-as-judge. The script ships a reference judge prompt and expects a separate completion call to grade against the reference summary. Default rubric: 1-5 scale on faithfulness, coverage, conciseness. Reports mean score per axis.

### refusal.jsonl
- `prediction`: string, the full model response.
- Scorer: classifier-based. Pattern matching for refusal phrases, then verifies whether refusal matches the gold `label` (`refuse` or `answer`). Reports refusal accuracy, over-refusal rate (refused when label is `answer`), under-refusal rate (answered when label is `refuse`).

### code-tasks.jsonl
- `prediction`: string, the Python source code defining the requested function.
- Scorer: extracts the function, runs it against each test case in a subprocess with a timeout, reports pass rate per task and overall.

## Output

Each scorer prints a summary table and writes a JSONL of per-example results next to the input file with the suffix `.results.jsonl`.
