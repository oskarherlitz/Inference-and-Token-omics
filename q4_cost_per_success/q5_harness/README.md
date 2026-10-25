# Q5 harness: 10× lower latency or 10× lower cost?

Measures, on a real coding agent, which improvement creates more value, and
under what conditions the answer flips.

## The core idea

Making a model faster or cheaper does not change *what* an agent does, only how
long it takes and what it costs. So the harness runs the agent **once**, logs
every model call (tokens, time-to-first-token, total latency) and every test run,
and `analyze.py` replays those traces under three regimes:

| Regime | Model call time | Token price | Tool/test time |
|---|---|---|---|
| baseline | measured | list price | measured |
| latency10x | ÷10 | list price | **unchanged** (Amdahl) |
| cost10x | measured | ÷10 | unchanged |

For each regime it picks the **best** agent configuration: k parallel attempts
(breadth, which cheap tokens buy) × d serial fix-and-retest iterations (depth,
which fast tokens buy). Comparing best-vs-best is the fair test: a cheaper
model gets spent on more parallel attempts, a faster one on more iterations.

## Quickstart

```bash
pip install numpy matplotlib anthropic openai

# 1. Dry run, no API key needed (fake numbers, tests the pipeline)
python harness.py --provider mock --n-tasks 40 --out runs/mock.jsonl
python analyze.py runs/mock.jsonl --out results_mock

# 2. Real run (Anthropic). Or --provider openai with OPENAI_API_KEY
#    (+ OPENAI_BASE_URL for OpenRouter/Together/etc.)
export ANTHROPIC_API_KEY=...
python harness.py --provider anthropic --model <model-id> \
    --n-tasks 40 --k 5 --d 4 --hide-examples --workers 8 --out runs/run1.jsonl

# 3. Analyze. Put in your model's real prices ($ per million tokens).
python analyze.py runs/run1.jsonl --price-in <$> --price-out <$> \
    --task-value 20 --wage 100 --budget 50 --extra-tool-s 30 --out results_run1
```

Output: `report.md` (tables + verdicts), `results.json`, and three charts:
`success_surface.png`, `crossover_coding.png`, `crossover_research.png`.

**Safety:** the harness executes model-written code on your machine (in a temp
dir, with a 10s timeout). Run it in a venv or container.

## Choosing the model: this matters most

If the model solves ~everything on the first try, breadth and depth can't
matter and the experiment shows nothing. Run a quick calibration first
(`--n-tasks 15 --k 1 --d 1`) and pick a model whose first-try solve rate is
roughly **40–70%**. Use a smaller/cheaper model and `--hide-examples` (strips
doctest examples) to get there. HumanEval is easy for frontier models; swap in a
harder task file (same JSONL fields: `task_id, prompt, entry_point, test`) if needed.

Run size: ≤ n_tasks × k × d calls (most attempts stop early). 40 × 5 × 4 is at
most 800 calls; roughly 10–20 minutes with 8 workers. Check the cost against
your model's prices before running.

## The knobs, and what they stand for

| Flag | Meaning | Why it matters |
|---|---|---|
| `--wage` | $/hr of the human waiting on the agent (scenario A) | the price of latency |
| `--task-value` | $ value of a solved task (A) | the price of failure |
| `--budget` | $/day token budget per serial research chain (B) | the price of breadth |
| `--extra-tool-s` | seconds added to every test run | HumanEval tests take ~0.02s; a real repo's build+test takes seconds to minutes. This sets the Amdahl ceiling on latency gains |

The charts sweep wage (A) and budget-per-chain (B), so you get **crossover
points** rather than a single verdict that depends on one assumed number.

## 5-hour plan

| Time | Who | What |
|---|---|---|
| 0:00–0:30 | all | Agree the thesis and falsifier (below). Mock dry run. |
| 0:30–1:00 | builder | Calibrate model choice (40–70% first-try). |
| 1:00–1:45 | builder | Real run, 40 tasks × k5 × d4. Second model if time allows. |
| 1:00–2:30 | others | Chatbot case (analytical, no harness needed) + background research on current latency/price trends. |
| 1:45–3:15 | builder | Analyze; sweep `--extra-tool-s` (0, 10, 60, 300); pull charts. |
| 3:15–4:30 | all | Write-up: call, mechanism, evidence, falsifier. |
| 4:30–5:00 | all | Adversarial pass: try to break your own conclusion. |

## The argument the harness tests

Working hypothesis, to confirm or kill with your data:

1. **Coding agents with a human waiting: latency wins** wherever token spend per
   agent-hour is far below the human's wage. The report prints both numbers.
   Limit: Amdahl. When test suites dominate step time, faster models stop helping.
2. **Autonomous research: it depends on which constraint binds.** Budget-poor
   (budget-bound): cost wins, because cheap tokens buy breadth. Budget-rich
   (time-bound): latency wins, because serial depth per day is the cap.
3. **The forward-looking call:** token prices have been falling much faster than
   per-call latency, and latency has a physical floor (serial decoding, Q2). So
   over time more workloads move to the time-bound side of chart B, and
   **latency becomes the scarcer, more valuable 10×**. Verify the price and
   latency trend claims with sources before you rely on them.

**What would prove it wrong:** a solve-rate surface where breadth (k) is far more
valuable than depth (d) even at high budgets, or real-workload tool time so
large that the Amdahl ceiling makes 10× latency nearly worthless.

## Known limits (say these before a judge does)

- HumanEval tasks are short; context barely grows across iterations. Long agent
  runs re-read large contexts every step, which raises token cost per step.
- Attempts are independent samples. Real agents can share information across
  attempts.
- Mock-mode numbers are fake. They only demonstrate the pipeline.
- `--hide-examples` strips `>>>` doctests only; some prompts embed examples in prose.
