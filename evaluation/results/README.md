# Evaluation results

Each run folder holds `run.json` (system, split, model, prompt fingerprint, times) and
`results.jsonl` (one answer per case), exactly as the run command wrote them.
Dry runs with the fake model (`*-fake`) are never committed.

## Dev run 1 (2026-11-23)

| | |
|---|---|
| Runs | `20261123-182625-A-dev-openai-gpt-oss-120b`, `20261123-181444-B-dev-openai-gpt-oss-120b` |
| Model | `openai/gpt-oss-120b` on Groq, temperature 0, same for both systems |
| Code, prompts and settings | commit `dc9be8c` (prompt fingerprints in each `run.json` match that commit) |
| Cases | the 30 verified dev cases, labels as of `dc9be8c` |
| Rate-limit waits, errors | none |
| Scores | `dev-run-1-metrics.md` and `.json`, computed against the labels above, before any change |

Run on Maira's laptop; result files copied unchanged from her export.
