# Contributing

This repo holds small, public-domain eval datasets. Contributions welcome under these rules.

## Data sources

Only data you can release under MIT or public domain. Do not submit data scraped from copyrighted sources, gated APIs, or sites with restrictive terms.

Good sources: prompts you wrote yourself, examples from public-domain books (Project Gutenberg), public government documents, Wikipedia (CC BY-SA, attribute), open datasets explicitly licensed for redistribution.

## Format

Datasets are JSONL, one example per line. Required fields depend on the dataset type. See `scoring/FORMAT.md`.

Every example needs a stable `id`. Use a short prefix matching the dataset (`ic-`, `ee-`, `sum-`, `ref-`, `code-`) followed by a zero-padded number.

## Adding examples

1. Edit the JSONL file. Add new lines at the end with the next sequential id.
2. Validate the file parses as JSONL:
   ```bash
   python3 -c "import json; [json.loads(l) for l in open('datasets/yourfile.jsonl')]"
   ```
3. If you changed any expected outputs, mention it in the PR description.

## Adding a new dataset

1. Pick a name in kebab-case, e.g. `code-review.jsonl`.
2. Document the prediction shape in `scoring/FORMAT.md`.
3. Add a corresponding `scoring/score_<name>.py` following the existing scorers' interface.
4. Update README.md to list it.

## Tests

The scorer tests use only the standard library. Run them from the repo root:

```bash
python3 -m unittest discover -s tests
```

## What not to include

No personal data, no real names paired with sensitive attributes, no copyrighted text excerpts longer than fair use, no API keys or tokens, no examples that reveal information about specific living people beyond what is publicly documented.
