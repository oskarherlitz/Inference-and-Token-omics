# Cost per successful task: mock-small, mock-mid, mock-frontier

> **Mock data.** These numbers come from simulated models and only demonstrate the pipeline.

Up to d=3 verifier-driven iterations per model. Tasks per family: 60. Run started 2026-10-24 21:41:28.

## Scope: all (120 task instances)

**Today (baseline, `mock-frontier×3`):** 95.0% of tasks delivered correctly, CPST $0.0105 (95% CI $0.0099 to $0.0112). 10.5% of spend bought nothing.

**Router (`mock-mid×3`):** 94.2% success, CPST $0.0003 (95% CI $0.0003 to $0.0003), escalated on 0.0% of tasks.

**Spread:** a provider using the router can charge up to 97.1% gross margin per successful task and still cost the customer less than the baseline.

| Policy | Success | CPST | Waste | False accepts | $/task | Pareto |
|---|---|---|---|---|---|---|
| `mock-small×2 → mock-mid×3` | 85.8% | $0.0003 | 43.0% | 14.2% | $0.0003 | yes |
| `mock-mid×3` (router) | 94.2% | $0.0003 | 27.1% | 5.8% | $0.0003 | yes |
| `mock-mid×2` | 90.8% | $0.0003 | 27.5% | 5.2% | $0.0003 |  |
| `mock-small×3 → mock-mid×3` | 85.8% | $0.0003 | 45.0% | 14.2% | $0.0003 |  |
| `mock-small×1 → mock-mid×3` | 85.0% | $0.0003 | 39.3% | 15.0% | $0.0003 |  |
| `mock-small×2` | 75.0% | $0.0003 | 46.5% | 14.3% | $0.0002 |  |
| `mock-small×3` | 82.5% | $0.0003 | 45.9% | 13.9% | $0.0003 |  |
| `mock-mid×1` | 72.5% | $0.0003 | 28.7% | 5.4% | $0.0002 |  |
| `mock-small×1` | 47.5% | $0.0003 | 52.5% | 19.7% | $0.0002 |  |
| `mock-mid×2 → mock-frontier×3` | 95.0% | $0.0007 | 11.0% | 5.0% | $0.0007 | yes |
| `mock-small×3 → mock-frontier×3` | 85.8% | $0.0008 | 31.4% | 14.2% | $0.0006 |  |
| `mock-small×1 → mock-mid×1 → mock-frontier×3` | 85.0% | $0.0010 | 30.7% | 15.0% | $0.0008 |  |

**Per-success pricing for the router** (batches of 100 tasks):

| Target margin | Price per success | Customer saving vs baseline | P(batch loses money) | Effective price if billed on verifier passes |
|---|---|---|---|---|
| 10.0% | $0.0003 | 96.8% | 2.9% | $0.0004 |
| 20.0% | $0.0004 | 96.4% | 0.0% | $0.0004 |
| 30.0% | $0.0004 | 95.9% | 0.0% | $0.0005 |
| 40.0% | $0.0005 | 95.2% | 0.0% | $0.0005 |
| 50.0% | $0.0006 | 94.2% | 0.0% | $0.0006 |

## Scope: code (60 task instances)

**Today (baseline, `mock-frontier×3`):** 100.0% of tasks delivered correctly, CPST $0.0106 (95% CI $0.0097 to $0.0115). 11.3% of spend bought nothing.

**Router (`mock-small×2 → mock-mid×3`):** 100.0% success, CPST $0.0003 (95% CI $0.0002 to $0.0003), escalated on 13.3% of tasks.

**Spread:** a provider using the router can charge up to 97.5% gross margin per successful task and still cost the customer less than the baseline.

| Policy | Success | CPST | Waste | False accepts | $/task | Pareto |
|---|---|---|---|---|---|---|
| `mock-small×2 → mock-mid×3` (router) | 100.0% | $0.0003 | 35.0% | 0.0% | $0.0003 | yes |
| `mock-small×1 → mock-mid×3` | 100.0% | $0.0003 | 32.4% | 0.0% | $0.0003 |  |
| `mock-small×2` | 86.7% | $0.0003 | 39.3% | 0.0% | $0.0002 |  |
| `mock-small×3 → mock-mid×3` | 100.0% | $0.0003 | 37.5% | 0.0% | $0.0003 |  |
| `mock-small×3` | 95.0% | $0.0003 | 39.0% | 0.0% | $0.0003 |  |
| `mock-small×1` | 56.7% | $0.0003 | 43.6% | 0.0% | $0.0002 |  |
| `mock-mid×3` | 100.0% | $0.0003 | 27.7% | 0.0% | $0.0003 |  |
| `mock-mid×2` | 95.0% | $0.0003 | 28.9% | 0.0% | $0.0003 |  |
| `mock-mid×1` | 68.3% | $0.0003 | 33.1% | 0.0% | $0.0002 |  |
| `mock-small×3 → mock-frontier×3` | 100.0% | $0.0008 | 13.7% | 0.0% | $0.0008 |  |
| `mock-mid×2 → mock-frontier×3` | 100.0% | $0.0008 | 10.6% | 0.0% | $0.0008 |  |
| `mock-small×1 → mock-mid×1 → mock-frontier×3` | 100.0% | $0.0013 | 31.0% | 0.0% | $0.0013 |  |

**Per-success pricing for the router** (batches of 100 tasks):

| Target margin | Price per success | Customer saving vs baseline | P(batch loses money) | Effective price if billed on verifier passes |
|---|---|---|---|---|
| 10.0% | $0.0003 | 97.2% | 2.4% | $0.0003 |
| 20.0% | $0.0003 | 96.9% | 0.0% | $0.0003 |
| 30.0% | $0.0004 | 96.4% | 0.0% | $0.0004 |
| 40.0% | $0.0004 | 95.8% | 0.0% | $0.0004 |
| 50.0% | $0.0005 | 95.0% | 0.0% | $0.0005 |

## Scope: extract (60 task instances)

**Today (baseline, `mock-frontier×3`):** 90.0% of tasks delivered correctly, CPST $0.0105 (95% CI $0.0095 to $0.0116). 9.7% of spend bought nothing.

**Router (`mock-mid×3`):** 88.3% success, CPST $0.0003 (95% CI $0.0003 to $0.0004), escalated on 0.0% of tasks.

**Spread:** a provider using the router can charge up to 97.2% gross margin per successful task and still cost the customer less than the baseline.

| Policy | Success | CPST | Waste | False accepts | $/task | Pareto |
|---|---|---|---|---|---|---|
| `mock-mid×2` | 86.7% | $0.0003 | 25.9% | 10.3% | $0.0003 | yes |
| `mock-mid×1` | 76.7% | $0.0003 | 24.4% | 9.8% | $0.0002 |  |
| `mock-mid×3` (router) | 88.3% | $0.0003 | 26.3% | 11.7% | $0.0003 | yes |
| `mock-small×3` | 70.0% | $0.0004 | 53.1% | 27.6% | $0.0002 |  |
| `mock-small×2 → mock-mid×3` | 71.7% | $0.0004 | 51.3% | 28.3% | $0.0003 |  |
| `mock-small×3 → mock-mid×3` | 71.7% | $0.0004 | 53.1% | 28.3% | $0.0003 |  |
| `mock-small×2` | 63.3% | $0.0004 | 54.1% | 28.3% | $0.0002 |  |
| `mock-small×1 → mock-mid×3` | 70.0% | $0.0004 | 46.7% | 30.0% | $0.0003 |  |
| `mock-small×1` | 38.3% | $0.0004 | 61.0% | 37.8% | $0.0002 |  |
| `mock-small×1 → mock-mid×1 → mock-frontier×3` | 70.0% | $0.0006 | 29.7% | 30.0% | $0.0004 |  |
| `mock-mid×2 → mock-frontier×3` | 90.0% | $0.0006 | 11.7% | 10.0% | $0.0006 | yes |
| `mock-small×3 → mock-frontier×3` | 71.7% | $0.0008 | 56.1% | 28.3% | $0.0005 |  |

**Per-success pricing for the router** (batches of 100 tasks):

| Target margin | Price per success | Customer saving vs baseline | P(batch loses money) | Effective price if billed on verifier passes |
|---|---|---|---|---|
| 10.0% | $0.0003 | 96.9% | 4.7% | $0.0004 |
| 20.0% | $0.0004 | 96.5% | 0.0% | $0.0004 |
| 30.0% | $0.0004 | 96.0% | 0.0% | $0.0005 |
| 40.0% | $0.0005 | 95.3% | 0.0% | $0.0006 |
| 50.0% | $0.0006 | 94.3% | 0.0% | $0.0007 |

## Where does the cheap model win? (extract family, by difficulty)

| Difficulty | Cheapest model alone: success / CPST | Baseline: success / CPST | Cheapest model's false-accept rate |
|---|---|---|---|
| 0 | 95.0% / $0.0003 | 100.0% / $0.0102 | 0.0% |
| 1 | 75.0% / $0.0003 | 85.0% / $0.0104 | 25.0% |
| 2 | 40.0% / $0.0006 | 85.0% / $0.0108 | 57.9% |

Difficulty 0 has no distractors, so the verifier catches nearly every mistake. At difficulty 2, plausible wrong numbers pass the verifier, which is where cheap models stop being cheap per success.

