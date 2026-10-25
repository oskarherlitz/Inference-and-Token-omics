# CLAUDE.md: CPST (cost per successful task)

## What this project is for

BASES 6-hour challenge, sector **Inference and Token-omics**. Thesis: the unit of
AI economics that matters is **cost per successful task**, not price per token.
This folder measures it, finds the routing policy that minimizes it, and prices
work per success instead of per token. The Q5 latency-vs-cost harness lives in
`../q5_harness` and is a sibling experiment.

Timebox: prefer finishing a real run and an honest write-up over adding features.

## Working hypothesis (the data decides)

**Cheap models win wherever mistakes are cheap to catch.** A mistake the checker
catches triggers a retry or an escalation. A mistake that passes the checker
ships. So routing should beat the best model alone on code with tests and simple
invoices, and the advantage should shrink or vanish on invoices with distractors.

**Falsifiers:** cheap models matching the frontier's success at extract
difficulty 2, or false-accept rates that do not rise with difficulty.

## Core design decisions (don't undo these)

- **Checked versus correct.** Every call gets `verified` (what a production
  checker can see, no answer key) and `correct` (ground truth). The agent only
  ever sees the checker. Never feed ground truth into retry feedback.
- **Run once, replay many times.** `run.py` pays for each call once. Every
  policy (single model at depth 1..d, every cheap-to-expensive cascade) is
  scored by replaying logs in `policies.py`. New policy ideas belong there, not
  in new runs.
- **Same quality, lower cost.** The router is the cheapest policy within
  `--tolerance` (default 2 points) of the baseline's success rate. The baseline
  is the most expensive model alone with full retries. A "router" that only uses
  the baseline model is not routing and is reported as "routing does not help".
- **Provider cost first.** Prefer OpenRouter's reported `usage.cost`. List prices
  in `models.json` are a fallback only.
- **The dashboard is the product, with a Question 1 panel.** It speaks to the payer in plain words (what kind of work, a one-sentence recommendation, the cost of slipped mistakes, the ledger). The Q1 panel adds up the recommended choices across kinds of work and compares the open-weight share of tokens and spending with gateway data and the forecast in `market.json`. No "policy", "cascade", or "Pareto" on the page; "false accept" is "looked right, was wrong".
- **Benchmark numbers are not market shares.** The page must keep saying that the market split comes from gateway data, and the benchmark explains the mechanism.
- **Every model has `weights`** (`open` or `closed`) in `models.json`; the open/proprietary split depends on it.
- **One log schema** for the benchmark (`run.py`) and production
  (`meter.py`), so `report.py` reads both.

## Files

- `families.py`: task families with `check` (verifier) and `grade` (truth).
  `code` reuses `../q5_harness` loader and test runner. `extract` generates
  business invoices with distractors (difficulty 0, 1, 2).
- `providers.py`: metered OpenRouter, Anthropic, and mock clients. Usage parsing
  lives in `usage_from_openai` and `usage_from_anthropic`.
- `models.json`: registry of models, fallback prices, optional `effort`.
- `run.py`, `policies.py`, `billing.py`, `report.py`: run, replay, price, report.
- `meter.py`: production `Router` and `Meter` with `invoice()`.
- `dashboard_template.html`: `report.py` injects results and `market.json` at `/*__DATA__*/null`.
- `market.json`: gateway figures and the team forecast for Q1 (edit numbers here, not in HTML).

## Log schema (`runs/*.jsonl`)

First line: `{"meta": true, source, models, prices, families, n_per_family, d, k, mock, ...}`.
Each following line is one model call plus its check:
`task, family, difficulty, model, attempt, iter, verified, correct, fresh_in,
cached_in, cache_write, out, cost_usd, cost_source, model_s, tool_s, feedback`.
Rows with an `error` key are failed API calls and are skipped. Wrong answers on
`extract` carry `wrong: {field: [said, actual]}`. Lines with `task_info: true`
hold a readable `preview` of each task. Meter logs may
also contain `{"acceptance": true, task, correct}` rows. Keep this stable.

## Commands

```bash
python run.py --n 60 --out runs/mock.jsonl && python report.py runs/mock.jsonl --out results/mock
python run.py --models deepseek-v4-flash,deepseek-v4-pro,claude-haiku-5.5,claude-sonnet-5.5 \
    --n 30 --d 3 --max-usd 10 --out runs/real1.jsonl
python report.py runs/real1.jsonl --out results/real1
python examples/live_router.py --stages deepseek-v4-flash:2,claude-sonnet-5.5:2 --n 20
python -m pytest tests -q
```

## Gotchas

- **Mock numbers are fake.** Never quote them as findings.
- **Thinking models spend output tokens on reasoning.** If the frontier model
  fails with empty answers, raise `--max-tokens`.
- **Check OpenRouter slugs and prices** at openrouter.ai/models before a run.
- **Code tasks have zero false accepts by construction** (tests are both
  checker and grader). Extraction is where the checker/truth gap shows up.
- The harness **executes model-written code** (temp dir, 10s timeout). Use a venv.
- After a real run, copy `results/<run>/dashboard.html` to `../docs/index.html`
  so the GitHub Pages link shows real data.
