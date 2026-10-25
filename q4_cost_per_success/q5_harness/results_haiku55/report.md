# Q5 harness results: claude-haiku-5-5 (anthropic)
40 tasks, up to k=5 attempts x d=4 iterations. Prices $0.1/$0.5 per M in/out tokens.

## Solve rate P(k, d)  [rows k = parallel attempts, cols d = iterations]
| k \ d | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| 1 | 1.00 | 1.00 | 1.00 | 1.00 |
| 2 | 1.00 | 1.00 | 1.00 | 1.00 |
| 3 | 1.00 | 1.00 | 1.00 | 1.00 |
| 4 | 1.00 | 1.00 | 1.00 | 1.00 |
| 5 | 1.00 | 1.00 | 1.00 | 1.00 |

## Where agent time goes
Model calls 6% of step time (of which time-to-first-token 67% of model time), tool/test execution 94%.
Token spend per hour of agent time: $0.02 (compare with the $100.0/hr of a waiting human).
Amdahl ceiling: 10x faster model -> at most 1.1x faster agent steps.

## A. Coding agent, human waiting (V=$20.0/task, wage=$100.0/hr)
- Baseline: best k=5, d=1 -> EV $19.125/task (P=1.00, wall 31.5s, $0.0009)
- 10× lower latency: best k=4, d=1 -> EV $19.161/task (P=1.00, wall 30.2s, $0.0007)
- 10× lower cost: best k=5, d=1 -> EV $19.125/task (P=1.00, wall 31.5s, $0.0001)
Gain from latency: $0.036/task; from cost: $0.001/task -> **LATENCY wins** (44.4x)

## B. Autonomous research (budget $50.0/day, 1 serial chain(s))
- Baseline: best k=5, d=1 -> 2745 solved/day (binding constraint: time)
- 10× lower latency: best k=5, d=1 -> 2864 solved/day (binding constraint: time)
- 10× lower cost: best k=5, d=1 -> 2745 solved/day (binding constraint: time)
**LATENCY wins** (2864 vs 2745 solved/day)

## Crossovers
A: latency starts beating cost at a human wage of ~$5/hr
B: latency starts beating cost once the budget exceeds ~$1 per serial chain per day
