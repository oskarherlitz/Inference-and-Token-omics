"""Counterfactual analysis: is 10x lower latency or 10x lower cost worth more?

Reads a harness log and replays it under three regimes:
  baseline   : measured model latency, list prices
  latency10x : model call time / 10, prices unchanged   (tool time unchanged!)
  cost10x    : measured latency, token prices / 10

For every regime it searches over agent configurations (k parallel
attempts, d serial iterations) and reports the best achievable value,
because the honest comparison is "best use of a cheaper model" vs "best
use of a faster model", not the same config under both.

Two scenarios:
  A. Coding agent, human waiting. EV/task = V*P(solve) - $tokens - w*wall_hours.
  B. Autonomous research. Tasks form C independent serial chains (each
     step depends on the last), with a daily token budget B.
     Solved/day = P(solve) * min(C * 24h / E[wall], B / E[$]).

Usage:
  python analyze.py runs/run1.jsonl --price-in 3 --price-out 15 \
      --task-value 20 --wage 100 --budget 50 --chains 1 --out results/
Prices are $ per million tokens: set them to your model's actual list price.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

EXTRA_TOOL_S = 0.0  # set from --extra-tool-s
REGIMES = {"baseline": (1.0, 1.0), "latency10x": (0.1, 1.0), "cost10x": (1.0, 0.1)}
COLORS = {"baseline": "#8a8985", "latency10x": "#2a78d6", "cost10x": "#eb6834"}
LABELS = {"baseline": "Baseline", "latency10x": "10× lower latency", "cost10x": "10× lower cost"}


# ---------- loading ----------

def load(path):
    traces = defaultdict(lambda: defaultdict(list))  # task -> attempt -> steps
    meta = {}
    for line in Path(path).read_text().splitlines():
        r = json.loads(line)
        if r.get("meta"):
            meta = r
        elif "error" not in r:
            traces[r["task"]][r["attempt"]].append(r)
    for t in traces.values():
        for a in t.values():
            a.sort(key=lambda s: s["iter"])
    return traces, meta


# ---------- replay one configuration ----------

def replay_task(attempts, k, d, lat_mult, price_mult, p_in, p_out):
    """Returns (solved, wall_s, cost_usd) for one task under config (k, d).
    Attempts run in parallel; all are cancelled at the first success."""
    finishes, step_tables = [], []
    for a in sorted(attempts)[:k]:
        steps = attempts[a][:d]
        t, starts, ok_at = 0.0, [], None
        for s in steps:
            starts.append(t)
            t += s["model_s"] * lat_mult + s["tool_s"] + EXTRA_TOOL_S
            if s["passed"]:
                ok_at = t
                break
        finishes.append((ok_at, t))
        step_tables.append((starts, steps))
    successes = [f[0] for f in finishes if f[0] is not None]
    solved = bool(successes)
    wall = min(successes) if solved else max(f[1] for f in finishes)
    cost = 0.0
    for starts, steps in step_tables:
        for st, s in zip(starts, steps):
            if st < wall - 1e-9 or (not solved):
                cost += (s["input_tokens"] * p_in + s["output_tokens"] * p_out) / 1e6
            if s["passed"]:
                break
    return solved, wall, cost * price_mult


def evaluate(traces, k, d, regime, p_in, p_out):
    lat, pm = REGIMES[regime]
    rows = [replay_task(att, k, d, lat, pm, p_in, p_out) for att in traces.values()]
    s, w, c = map(np.array, zip(*rows))
    return dict(p=s.mean(), wall=w.mean(), cost=c.mean())


def grid(traces, regime, p_in, p_out):
    K = min(len(a) for a in traces.values())
    D = max(len(st) for a in traces.values() for st in a.values())
    return {(k, d): evaluate(traces, k, d, regime, p_in, p_out)
            for k in range(1, K + 1) for d in range(1, D + 1)}


# ---------- scenarios ----------

def ev_coding(m, V, wage):
    return V * m["p"] - m["cost"] - wage * m["wall"] / 3600


def throughput_research(m, budget, chains):
    time_lim = chains * 86400 / m["wall"]
    budget_lim = budget / m["cost"] if m["cost"] > 0 else np.inf
    return m["p"] * min(time_lim, budget_lim), ("time" if time_lim < budget_lim else "budget")


def best(g, score):
    cfg = max(g, key=lambda c: score(g[c]))
    return cfg, score(g[cfg])


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--price-in", type=float, default=3.0, help="$/M input tokens")
    ap.add_argument("--price-out", type=float, default=15.0, help="$/M output tokens")
    ap.add_argument("--task-value", type=float, default=20.0, help="$ value of a solved task (A)")
    ap.add_argument("--wage", type=float, default=100.0, help="$/hr of the waiting human (A)")
    ap.add_argument("--budget", type=float, default=50.0, help="$/day token budget (B)")
    ap.add_argument("--chains", type=int, default=1, help="independent serial chains (B)")
    ap.add_argument("--extra-tool-s", type=float, default=0.0,
                    help="seconds added to every test run, to mimic real builds/test suites "
                         "(HumanEval tests take ~0.02s; a real repo's suite can take minutes)")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    global EXTRA_TOOL_S
    EXTRA_TOOL_S = a.extra_tool_s

    traces, meta = load(a.log)
    G = {r: grid(traces, r, a.price_in, a.price_out) for r in REGIMES}
    base = G["baseline"]
    K = max(k for k, _ in base); D = max(d for _, d in base)
    report = []
    say = lambda s="": (print(s), report.append(s))

    say(f"# Q5 harness results: {meta.get('model', '?')} ({meta.get('provider', '?')})")
    say(f"{len(traces)} tasks, up to k={K} attempts x d={D} iterations. "
        f"Prices ${a.price_in}/${a.price_out} per M in/out tokens.\n")

    # Success surface
    say("## Solve rate P(k, d)  [rows k = parallel attempts, cols d = iterations]")
    say("| k \\ d | " + " | ".join(str(d) for d in range(1, D + 1)) + " |")
    say("|---|" + "---|" * D)
    for k in range(1, K + 1):
        say(f"| {k} | " + " | ".join(f"{base[(k, d)]['p']:.2f}" for d in range(1, D + 1)) + " |")

    # Amdahl: where does wall-clock go?
    steps = [s for t in traces.values() for at in t.values() for s in at]
    model_t = sum(s["model_s"] for s in steps)
    tool_t = sum(s["tool_s"] + EXTRA_TOOL_S for s in steps)
    ttft_t = sum(s["ttft_s"] for s in steps)
    total_t = model_t + tool_t
    share = model_t / total_t if total_t > 0 else 0.0
    say(f"\n## Where agent time goes")
    say(f"Model calls {share:.0%} of step time (of which time-to-first-token "
        f"{ttft_t / model_t:.0%} of model time), tool/test execution {1 - share:.0%}."
        if model_t > 0 else "No successful model calls recorded.")
    tok_cost = sum((x["input_tokens"] * a.price_in + x["output_tokens"] * a.price_out) / 1e6 for x in steps)
    say(f"Token spend per hour of agent time: ${tok_cost / (total_t / 3600):.2f} "
        f"(compare with the ${a.wage}/hr of a waiting human)."
        if total_t > 0 else f"Total token cost: ${tok_cost:.4f}")
    say(f"Amdahl ceiling: 10x faster model -> at most {1 / (1 - share + share / 10):.1f}x "
        f"faster agent steps.")

    # Scenario A
    say(f"\n## A. Coding agent, human waiting (V=${a.task_value}/task, wage=${a.wage}/hr)")
    resA = {}
    for r in REGIMES:
        cfg, v = best(G[r], lambda m: ev_coding(m, a.task_value, a.wage))
        m = G[r][cfg]; resA[r] = v
        say(f"- {LABELS[r]}: best k={cfg[0]}, d={cfg[1]} -> EV ${v:.3f}/task "
            f"(P={m['p']:.2f}, wall {m['wall']:.1f}s, ${m['cost']:.4f})")
    gl, gc = resA["latency10x"] - resA["baseline"], resA["cost10x"] - resA["baseline"]
    say(f"Gain from latency: ${gl:.3f}/task; from cost: ${gc:.3f}/task -> "
        f"**{'LATENCY' if gl > gc else 'COST'} wins** ({max(gl, gc) / max(min(gl, gc), 1e-9):.1f}x)")

    # Scenario B
    say(f"\n## B. Autonomous research (budget ${a.budget}/day, {a.chains} serial chain(s))")
    resB = {}
    for r in REGIMES:
        cfg, v = best(G[r], lambda m: throughput_research(m, a.budget, a.chains)[0])
        bind = throughput_research(G[r][cfg], a.budget, a.chains)[1]
        resB[r] = v
        say(f"- {LABELS[r]}: best k={cfg[0]}, d={cfg[1]} -> {v:.0f} solved/day "
            f"(binding constraint: {bind})")
    say(f"**{'LATENCY' if resB['latency10x'] > resB['cost10x'] else 'COST'} wins** "
        f"({resB['latency10x']:.0f} vs {resB['cost10x']:.0f} solved/day)")

    # Sweeps for crossover charts
    wages = [0, 5, 10, 25, 50, 100, 200, 400]
    sweepA = {r: [best(G[r], lambda m, w=w: ev_coding(m, a.task_value, w))[1] for w in wages]
              for r in REGIMES}
    # B scales linearly in chains when budget scales with them, so the one
    # number that matters is the daily budget per serial chain.
    chains = [round(x, 4) for x in np.logspace(-2, 3, 11)]  # $/chain/day
    sweepB = {r: [best(G[r], lambda m, b=b: throughput_research(m, b, 1)[0])[1] for b in chains]
              for r in REGIMES}
    xA = next((w for w, l, c in zip(wages, *(np.subtract(sweepA[x], sweepA["baseline"])
               for x in ("latency10x", "cost10x"))) if l > c), None)
    say(f"\n## Crossovers")
    say(f"A: latency starts beating cost at a human wage of ~${xA}/hr" if xA is not None
        else "A: cost beats latency at every wage tested")
    xB = next((b for b, l, cc in zip(chains, sweepB["latency10x"], sweepB["cost10x"]) if l > cc), None)
    say(f"B: latency starts beating cost once the budget exceeds ~${xB:,.0f} per serial chain per day"
        if xB is not None else "B: cost beats latency at every budget tested")

    json.dump(dict(meta=meta, A=resA, B=resB, wages=wages, sweepA=sweepA,
                   chains=chains, sweepB=sweepB,
                   surface={f"{k},{d}": v for (k, d), v in base.items()}),
              (out / "results.json").open("w"), indent=1, default=float)
    (out / "report.md").write_text("\n".join(report) + "\n")
    plot(out, base, K, D, wages, sweepA, chains, sweepB, a)
    print(f"\nWrote {out}/report.md, results.json, charts/*.png")


def plot(out, base, K, D, wages, sweepA, chains, sweepB, a):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#b5b4ae", "axes.labelcolor": "#52514e",
                         "xtick.color": "#52514e", "ytick.color": "#52514e",
                         "axes.grid": True, "grid.color": "#ebeae6", "grid.linewidth": 0.8})
    (out / "charts").mkdir(exist_ok=True)

    # 1. success surface heatmap (sequential single hue)
    M = np.array([[base[(k, d)]["p"] for d in range(1, D + 1)] for k in range(1, K + 1)])
    fig, ax = plt.subplots(figsize=(5, 4))
    im = ax.imshow(M, cmap="Blues", vmin=0, vmax=1, origin="lower", aspect="auto")
    ax.grid(False)
    for (i, j), v in np.ndenumerate(M):
        ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                color="white" if v > 0.6 else "#0b0b0b", fontsize=9)
    ax.set_xticks(range(D), range(1, D + 1)); ax.set_yticks(range(K), range(1, K + 1))
    ax.set_xlabel("d: serial iterations (depth, bought by latency)")
    ax.set_ylabel("k: parallel attempts (breadth, bought by cost)")
    ax.set_title("Solve rate by breadth and depth", loc="left", fontsize=11)
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout(); fig.savefig(out / "charts/success_surface.png", dpi=160); plt.close(fig)

    # 2. crossover charts
    for name, xs, sw, xlabel, ylabel, logx, title in [
        ("crossover_coding", wages, sweepA, "Human wage while waiting ($/hr)",
         "Gain over baseline ($ EV per task)", False, "A. Coding agent: value of each improvement"),
        ("crossover_research", chains, sweepB, "Token budget per serial research chain ($/day)",
         "Gain over baseline (solved tasks/day)", True, "B. Autonomous research: value of each improvement")]:
        fig, ax = plt.subplots(figsize=(6, 3.8))
        for r in ("latency10x", "cost10x"):
            gain = np.subtract(sw[r], sw["baseline"])
            ax.plot(xs, gain, color=COLORS[r], lw=2, marker="o", ms=5, label=LABELS[r])
            ax.annotate(LABELS[r], (xs[-1], gain[-1]), xytext=(6, 0), textcoords="offset points",
                        color="#52514e", va="center", fontsize=9)
        if logx:
            ax.set_xscale("log")
        ax.axhline(0, color="#b5b4ae", lw=1)
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
        ax.set_title(title, loc="left", fontsize=11)
        ax.legend(frameon=False, loc="upper left")
        fig.tight_layout(); fig.savefig(out / f"charts/{name}.png", dpi=160); plt.close(fig)


if __name__ == "__main__":
    main()
