# llm-eval-datasets-starter

Small, public-domain evaluation datasets for LLM applications. Plus the scoring scripts and format spec so you can actually use them.

Most public LLM eval datasets are either:
1. Too academic to map to product use cases (MMLU does not tell you if your customer support bot works)
2. Too large to run on every change (5000+ examples, takes hours, costs money)
3. Already memorized by current models

This repo provides small, focused, in-domain eval sets that are useful for everyday product development.

## Contents

| Task | Dataset | Size | File |
|---|---|---|---|
| Classification | Customer intent (5 classes) | 100 examples | [datasets/intent-classification.jsonl](datasets/intent-classification.jsonl) |
| Extraction | Structured data from emails | 50 examples | [datasets/email-extraction.jsonl](datasets/email-extraction.jsonl) |
| Summarization | Article summarization (3 sentences) | 30 examples | [datasets/summarization.jsonl](datasets/summarization.jsonl) |
| Refusal | Safety refusal correctness | 40 examples | [datasets/refusal.jsonl](datasets/refusal.jsonl) |
| Code | Short Python tasks | 50 examples | [datasets/code-tasks.jsonl](datasets/code-tasks.jsonl) |

All examples are hand-written or derived from public-domain sources. No leakage from common training sets (verified by checking model recall before inclusion).

## Format

All datasets use JSONL with this schema:

```json
{
  "id": "intent-001",
  "input": "...",
  "expected": "...",
  "metadata": {
    "difficulty": "easy" | "medium" | "hard",
    "category": "..."
  }
}
```

The `expected` field structure depends on the task. See [scoring/FORMAT.md](scoring/FORMAT.md) for details per task.

## Scoring

Scoring scripts in [scoring/](scoring/). Each is a single Python file with no external dependencies (except `anthropic` for the LLM-judge tasks).

**Warning: `score_code.py` runs every prediction as Python code on your machine.** Each one runs in its own process with a timeout, a throwaway working folder and an environment cut down to `PATH` and `SYSTEMROOT`, so API keys in your shell are not handed to it, and any processes it starts are killed afterwards. That is not a sandbox: the code still runs as your user and can read your files and reach the network. If you did not produce the predictions yourself, run this scorer in a container or VM.

Run a scoring script:

```bash
python scoring/score_classification.py \
  --dataset datasets/intent-classification.jsonl \
  --predictions my-predictions.jsonl \
  --output scores.json
```

Predictions file format matches `expected` schema, one prediction per line, with matching `id` field.

## How to use this

1. Run your system on the input column of a dataset
2. Save predictions in the matching format
3. Run the scoring script
4. Compare to baseline scores (see baseline-scores.md per dataset folder)

For most tasks, expect 4 to 8 hours total: set up scoring once, then runs take 5 to 20 minutes per eval depending on your system speed.

## What this is not

- Not a benchmark. There is no public leaderboard for these scores. They are for your team's internal regression tracking.
- Not exhaustive. Real product eval needs datasets that reflect your actual user inputs. These are a starter; build domain-specific sets on top.
- Not adversarial. These are honest test cases. Adversarial eval (jailbreaks, prompt injection) is a separate concern, covered in [prompt-injection-test-suite](https://github.com/0xelitesystem/prompt-injection-test-suite).

## Why these dataset sizes are small

50 to 100 examples per dataset is a deliberate choice:

- Small enough to run frequently (every prompt change, not weekly)
- Small enough that you can hand-inspect every example
- Large enough to detect meaningful regressions (a 5% drop in 100 examples is significant)
- Cheap enough that running a full eval costs cents, not dollars

If you need higher statistical confidence, bootstrap from these or add more domain-specific examples.

## Adding your own

The format spec in [scoring/FORMAT.md](scoring/FORMAT.md) covers what each task's `expected` should look like. Build new datasets in the same format and the scoring scripts will work with them.

For tasks not covered here (translation, math reasoning, multi-turn conversation), see CONTRIBUTING.md for the requirements.

## More

Part of a catalog of single-file browser tools and plain-language references, all MIT licensed and dependency-free: [0xelitesystem.github.io](https://0xelitesystem.github.io/). Built by [elitesystem.ai](https://elitesystem.ai).

## License

MIT. All dataset content is public-domain or original-to-this-repo. No copyrighted text included.

## Related

- [rag-evaluation-rubrics](https://github.com/0xelitesystem/rag-evaluation-rubrics) - evaluation methodology for RAG specifically
- [prompt-model-side-by-side](https://github.com/0xelitesystem/prompt-model-side-by-side) - tool to run prompts across multiple models
- [agent-failure-modes](https://github.com/0xelitesystem/agent-failure-modes) - failure patterns to test for
- [prompt-cost-calculator](https://github.com/0xelitesystem/prompt-cost-calculator) - cost per eval run estimation
- [ai-generated-code-review-rubrics](https://github.com/0xelitesystem/ai-generated-code-review-rubrics) - scoring approach for code-generation outputs
- [prompt-injection-test-suite](https://github.com/0xelitesystem/prompt-injection-test-suite) - the adversarial-eval companion
