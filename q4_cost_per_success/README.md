# Inference and Token-omics
BASES 6-Hour Challenge: Inference and Token-omics

Our thesis: **the unit of AI economics that matters is cost per successful task, not price per token.** Falling token prices do not tell you what a finished piece of work costs, because failed attempts, retries, and escalations are billed too. This repo measures that cost directly and builds a product around it.

| Folder | Question | What it does |
|---|---|---|
| [`cpst/`](cpst/) | Who sits on the intelligence-per-dollar frontier, and where? Who captures the margin? | Benchmarks models by **cost per successful task**, finds the cheapest routing policy that matches the best model's quality, and prices work **per success instead of per token**. Includes a live router, a metering SDK, and an interactive dashboard. |
| [`q5_harness/`](q5_harness/) | Q5: is 10× lower latency or 10× lower cost worth more? | Runs a coding agent once and replays its traces under counterfactual latency and price regimes. |

The two tools share building blocks: `cpst` reuses the HumanEval loader and sandboxed test runner from `q5_harness`.

## Run the demo in 30 seconds (no API key)

```bash
cd cpst && pip install -r requirements.txt
python run.py --n 60 --out runs/mock.jsonl && python report.py runs/mock.jsonl --out results/mock
open results/mock/dashboard.html
```

See [`cpst/README.md`](cpst/README.md) for the real run, the method, and known limits.
