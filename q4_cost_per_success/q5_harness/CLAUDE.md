# CLAUDE.md: Q5 latency-vs-cost harness

## What this project is for

A team challenge on the future of a sector and what it means for the companies
of tomorrow. Sector: **Inference and Token-omics**. We answer one question:

> **Q5.** Suppose an inference provider could reduce latency by 10× or cost per
> token by 10×, but not both. Which improvement would create more economic
> value? How would the answer change for coding agents, chatbots, and
> automated research?

The deliverable is a **call**: a clear answer, the mechanism behind it, evidence,
and what would prove it wrong. This harness supplies the evidence. It is a
supporting experiment, not the deliverable. Timebox: about 5 hours total, so
prefer finishing a run and an analysis over adding features.

## Working thesis (unconfirmed; the data decides)

1. **Coding agents with a human waiting: latency wins** wherever token spend per
   agent-hour is far below the waiting human's wage. Limit: Amdahl's law. Test
   and build time doesn't shrink when the model gets faster.
2. **Autonomous research: it depends on the binding constraint.** If the token
   budget runs out first, cost wins, because cheap tokens buy parallel attempts
   (breadth). If wall-clock time runs out first, latency wins, because faster
   calls buy serial iterations (depth).
3. **Forward call:** if token prices keep falling faster than per-call latency,
   and latency has a physical floor (serial decoding), more workloads become
   time-bound, and latency becomes the scarcer, more valuable 10×. These trend
   claims have **not been sourced yet**. Don't state them as fact in any write-up
   without citations.
4. **Chatbots** are handled analytically, outside the harness. Latency matters
   only until responses feel instant.

**Falsifiers:** breadth (k) beats depth (d) even at high budgets, or real
tool/test time is so large that the Amdahl ceiling makes 10× latency nearly
worthless.

## Core design decisions (don't undo these)

- **Run once, replay many times.** Changing latency or price doesn't change what
  the agent does, so never re-run the agent to vary them. `harness.py` logs raw
  timings and tokens; `analyze.py` recomputes wall-clock and cost under each
  regime. New counterfactual knobs belong in `analyze.py`, not in new runs.
- **Best vs. best.** Each regime is scored at its own optimal (k, d). A cheaper
  model gets spent on more attempts, a faster one on more iterations. Comparing
  the same config under both regimes is the wrong test.
- **Latency10x scales model call time only.** Tool and test time stays unchanged.
  That is the Amdahl effect, and it's central to the argument.
- **Always log at max k and d.** Every smaller (k, d) is derived from prefixes of
  the traces. Attempts run in parallel and all are cancelled at the first
  success (cost counts only steps that started before that moment).

## Files

- `harness.py`: agent loop. k independent attempts per task, each up to d
  serial iterations of (model writes code → unit tests run → error fed back).
  Writes JSONL logs.
- `analyze.py`: replays logs under `baseline`, `latency10x`, `cost10x`. Scores
  scenario A (coding agent: EV = V·P − $tokens − wage·hours) and scenario B
  (research: solved/day = P·min(chains·24h/E[wall], budget/E[$])). Writes
  `report.md`, `results.json`, and `charts/` (success surface plus two crossover
  charts).
- `clients.py`: `anthropic`, `openai` (any OpenAI-compatible endpoint via
  `OPENAI_BASE_URL`), and `mock`. All stream, to measure time-to-first-token.
- `tasks.py`: loads HumanEval-format JSONL (`task_id, prompt, entry_point,
  test`). `--hide-examples` strips `>>>` doctests.
- `data/HumanEval.jsonl.gz`: 164 tasks from openai/human-eval.

## Log schema (`runs/*.jsonl`)

The first line is `{"meta": true, provider, model, k, d, n_tasks, ...}`. Each
following line is one model call plus its test run:
`task, attempt, iter, passed, input_tokens, output_tokens, ttft_s, model_s, tool_s`.
Rows with an `error` key are failed API calls; the analysis skips them. Keep this
schema stable, because `analyze.py` depends on it.

## Commands

```bash
pip install numpy matplotlib anthropic openai
python harness.py --provider mock --n-tasks 40 --out runs/mock.jsonl        # dry run, no key
python harness.py --provider anthropic --model <id> --n-tasks 15 --k 1 --d 1 --out runs/calib.jsonl
python harness.py --provider anthropic --model <id> --n-tasks 40 --k 5 --d 4 --hide-examples --out runs/run1.jsonl
python analyze.py runs/run1.jsonl --price-in <$/M> --price-out <$/M> --extra-tool-s 30 --out results_run1
```

## Gotchas

- **Calibrate the model first.** Pick one with a 40–70% first-try solve rate. If
  the model solves nearly everything on the first try, k and d can't matter and
  the run shows nothing. Frontier models on HumanEval are likely too strong; use
  a smaller model, `--hide-examples`, or a harder task file.
- **HumanEval tests take about 0.02s**, which unrealistically favors latency.
  Sweep `--extra-tool-s` (for example 0, 10, 60, 300) to mimic real build and
  test times.
- **Price defaults (3 / 15 $/M) are placeholders.** Always pass the actual model's
  list prices, and look them up rather than recalling them.
- **Mock-mode numbers are fake.** Use them only to check the pipeline. Never
  quote them as findings.
- The harness **executes model-written code** (temp dir, 10s timeout). Run it in a
  venv or container.
- In `analyze.py`, the sweep variable named `chains` (and the `chains` key in
  `results.json`) actually holds **budget per serial chain ($/day)**, not a chain
  count. Scenario B scales linearly in chains, so budget per chain is the only
  axis that matters.

## Known limits (state them in the write-up)

- HumanEval tasks are short, and context barely grows across iterations. Long
  agent runs re-read large contexts every step, which raises cost per step.
- Attempts are independent samples; real agents share information across
  attempts.
- `--hide-examples` misses examples written in prose instead of `>>>` doctests.
