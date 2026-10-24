# Q5 harness results: claude-haiku-5-5 (anthropic)
40 tasks, up to k=5 attempts x d=4 iterations. Prices $0.1/$0.5 per M in/out tokens.

## Solve rate P(k, d)  [rows k = parallel attempts, cols d = iterations]
| k \ d | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| 1 | 0.80 | 0.88 | 0.93 | 0.93 |
| 2 | 0.80 | 0.93 | 0.93 | 0.93 |
| 3 | 0.80 | 0.93 | 0.93 | 0.95 |
| 4 | 0.80 | 0.93 | 0.93 | 0.95 |
| 5 | 0.80 | 0.93 | 0.93 | 0.95 |

## Where agent time goes
Model calls 77% of step time (of which time-to-first-token 85% of model time), tool/test execution 23%.
Token spend per hour of agent time: $0.28 (compare with the $100.0/hr of a waiting human).
Amdahl ceiling: 10x faster model -> at most 3.3x faster agent steps.

## A. Coding agent, human waiting (V=$20.0/task, wage=$100.0/hr)
- Baseline: best k=3, d=4 -> EV $18.882/task (P=0.95, wall 4.2s, $0.0010)
- 10× lower latency: best k=3, d=4 -> EV $18.960/task (P=0.95, wall 1.4s, $0.0010)
- 10× lower cost: best k=3, d=4 -> EV $18.883/task (P=0.95, wall 4.2s, $0.0001)
Gain from latency: $0.078/task; from cost: $0.001/task -> **LATENCY wins** (85.5x)

## B. Autonomous research (budget $50.0/day, 1 serial chain(s))
- Baseline: best k=3, d=1 -> 33670 solved/day (binding constraint: time)
- 10× lower latency: best k=1, d=1 -> 139773 solved/day (binding constraint: time)
- 10× lower cost: best k=3, d=1 -> 33670 solved/day (binding constraint: time)
**LATENCY wins** (139773 vs 33670 solved/day)

## Crossovers
A: latency starts beating cost at a human wage of ~$5/hr
B: latency starts beating cost once the budget exceeds ~$10 per serial chain per day
