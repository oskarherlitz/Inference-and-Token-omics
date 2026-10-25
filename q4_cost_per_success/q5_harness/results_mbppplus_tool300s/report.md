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
Model calls 1% of step time (of which time-to-first-token 85% of model time), tool/test execution 99%.
Token spend per hour of agent time: $0.00 (compare with the $100.0/hr of a waiting human).
Amdahl ceiling: 10x faster model -> at most 1.0x faster agent steps.

## A. Coding agent, human waiting (V=$20.0/task, wage=$100.0/hr)
- Baseline: best k=3, d=2 -> EV $8.417/task (P=0.93, wall 362.9s, $0.0007)
- 10× lower latency: best k=2, d=2 -> EV $8.477/task (P=0.93, wall 360.8s, $0.0005)
- 10× lower cost: best k=3, d=2 -> EV $8.418/task (P=0.93, wall 362.9s, $0.0001)
Gain from latency: $0.060/task; from cost: $0.001/task -> **LATENCY wins** (91.2x)

## B. Autonomous research (budget $50.0/day, 1 serial chain(s))
- Baseline: best k=3, d=1 -> 229 solved/day (binding constraint: time)
- 10× lower latency: best k=3, d=1 -> 230 solved/day (binding constraint: time)
- 10× lower cost: best k=3, d=1 -> 229 solved/day (binding constraint: time)
**LATENCY wins** (230 vs 229 solved/day)

## Crossovers
A: latency starts beating cost at a human wage of ~$5/hr
B: latency starts beating cost once the budget exceeds ~$0 per serial chain per day
