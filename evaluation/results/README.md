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

## Challenge run 1 (2026-11-26)

| | |
|---|---|
| Runs | `20261126-132518-A-challenge-openai-gpt-oss-120b`, `20261126-171456-B-challenge-openai-gpt-oss-120b` |
| Model | `openai/gpt-oss-120b` on Groq, temperature 0, same for both systems |
| Code, prompts and settings | tag `challenge-baseline-2026-11-26` (`f37d427`); fingerprints A `1b32155b`, B `638c739d` (in each `run.json`) |
| Cases | the 40 challenge cases (39 scored; CH-023 disputed), development data (D-056) |
| Rate-limit waits, errors | A: CH-026 to CH-029 failed on a network outage and were retried in the same run (D-061; the old lines stay in `results.jsonl`). B: none |
| Scores | `challenge-run-1-metrics.md` and `.json`, computed against the labels, before the D-062 fixes |
| Analysis | `challenge-run-1-analysis.md`: every wrong decision and its cause, classified critical / important / minor |

Run on Maira's laptop; result files copied unchanged from her export. The earlier System B attempt
`20261123-192800-B-challenge` is not counted (5 cases hit the daily token limit) and stays on her laptop as a record.

