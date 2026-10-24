# Q5 harness results: mock (mock)
40 tasks, up to k=5 attempts x d=4 iterations. Prices $3.0/$15.0 per M in/out tokens.

## Solve rate P(k, d)  [rows k = parallel attempts, cols d = iterations]
| k \ d | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| 1 | 0.50 | 0.78 | 0.93 | 1.00 |
| 2 | 0.75 | 0.95 | 1.00 | 1.00 |
| 3 | 0.82 | 1.00 | 1.00 | 1.00 |
| 4 | 0.88 | 1.00 | 1.00 | 1.00 |
| 5 | 0.93 | 1.00 | 1.00 | 1.00 |

## Where agent time goes
Model calls 82% of step time (of which time-to-first-token 20% of model time), tool/test execution 18%.
Token spend per hour of agent time: $3.15 (compare with the $100.0/hr of a waiting human).
Amdahl ceiling: 10x faster model -> at most 3.8x faster agent steps.

## A. Coding agent, human waiting (V=$20.0/task, wage=$100.0/hr)
- Baseline: best k=5, d=2 -> EV $19.858/task (P=1.00, wall 4.2s, $0.0251)
- 10× lower latency: best k=4, d=2 -> EV $19.948/task (P=1.00, wall 1.1s, $0.0206)
- 10× lower cost: best k=5, d=2 -> EV $19.881/task (P=1.00, wall 4.2s, $0.0025)
Gain from latency: $0.090/task; from cost: $0.023/task -> **LATENCY wins** (4.0x)

## B. Autonomous research (budget $50.0/day, 1 serial chain(s))
- Baseline: best k=1, d=4 -> 6416 solved/day (binding constraint: budget)
- 10× lower latency: best k=1, d=4 -> 6416 solved/day (binding constraint: budget)
- 10× lower cost: best k=5, d=2 -> 19933 solved/day (binding constraint: budget)
**COST wins** (6416 vs 19933 solved/day)

## Crossovers
A: latency starts beating cost at a human wage of ~$10/hr
B: latency starts beating cost once the budget exceeds ~$316 per serial chain per day
