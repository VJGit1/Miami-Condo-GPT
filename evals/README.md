# Evals

## Smoke split (`cases/smoke.jsonl`)

15 cases covering lookup, aggregation, joins, fuzzy names, viz artifacts, and adversarial refusals.

## Commands

```bash
# Gateway refusal checks only (no LLM / DB)
python -m evals.runner --split smoke --offline-only

# Full agent eval (Postgres + OPENAI_API_KEY)
python -m evals.runner --split smoke --min-pass-rate 0.7
```

Reports land in `results/` (gitignored). Live runs also append latency rows to `results/metrics.jsonl` via `observability.py`.
