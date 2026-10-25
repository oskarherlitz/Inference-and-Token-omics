"""Replay logged traces under routing policies and score cost per successful task.

A policy is a list of stages [(model, d), ...]. For each task instance:
  run stage 1's model for up to d verifier-driven iterations;
  if the verifier accepts, deliver that answer and stop;
  otherwise escalate to the next stage (fresh conversation, next model).
A single-model policy is just one stage.

Definitions (per task instance, then summed):
  cost       every dollar spent on the instance, across all stages
  delivered  some stage's answer passed the verifier
  correct    the delivered answer is actually right (ground truth)
  waste      dollars that did not buy the correct delivered answer:
             all failed iterations, all escalated stages, and the whole
             cost of any false accept or give-up

  CPST = total cost / number of correct deliveries
"""
import itertools
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


def load(path):
    meta, traces, tasks = {}, defaultdict(list), {}
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("meta"):
            meta = r
            continue
        if r.get("task_info"):
            tasks.setdefault(r["task"], {})["preview"] = r["preview"]
            continue
        info = tasks.setdefault(r["task"], {})
        info.update(family=r["family"], difficulty=r.get("difficulty", 1))
        if "error" in r:
            continue
        traces[(r["model"], r["task"], r["attempt"])].append(r)
    for steps in traces.values():
        steps.sort(key=lambda s: s["iter"])
    attempts = sorted({a for (_, _, a) in traces})
    return meta, dict(traces), tasks, attempts


def tokens(s):
    return s["fresh_in"] + s["cached_in"] + s["cache_write"] + s["out"]


def replay(traces, stages, task, attempt):
    cost = waste_extra = 0.0
    calls = tok = 0
    for depth, (model, d) in enumerate(stages):
        for s in traces.get((model, task, attempt), [])[:d]:
            cost += s["cost_usd"]; calls += 1; tok += tokens(s)
            if s["verified"]:
                good = s["cost_usd"] if s["correct"] else 0.0
                return dict(cost=cost, delivered=True, correct=bool(s["correct"]),
                            waste=cost - good, calls=calls, tokens=tok,
                            escalated=depth > 0, final_model=model)
    return dict(cost=cost, delivered=False, correct=False, waste=cost, calls=calls,
                tokens=tok, escalated=len(stages) > 1, final_model=None)


def name(stages):
    return " → ".join(f"{m}×{d}" for m, d in stages)


def summarize(outs):
    n = len(outs)
    c = np.array([o["cost"] for o in outs]); ok = np.array([o["correct"] for o in outs])
    dl = np.array([o["delivered"] for o in outs])
    total, n_ok, n_dl = c.sum(), int(ok.sum()), int(dl.sum())
    return dict(
        n=n, n_correct=n_ok, n_delivered=n_dl, n_false_accept=int((dl & ~ok).sum()),
        success_rate=n_ok / n if n else 0.0,
        false_accept_rate=((dl & ~ok).sum() / n_dl) if n_dl else 0.0,
        total_cost=float(total), cost_per_task=float(total / n) if n else 0.0,
        cpst=float(total / n_ok) if n_ok else float("inf"),
        cost_per_delivery=float(total / n_dl) if n_dl else float("inf"),
        waste_share=float(sum(o["waste"] for o in outs) / total) if total else 0.0,
        wasted_usd=float(sum(o["waste"] for o in outs)),
        calls_per_task=float(np.mean([o["calls"] for o in outs])) if n else 0.0,
        tokens_per_success=float(sum(o["tokens"] for o in outs) / n_ok) if n_ok else float("inf"),
        escalation_rate=float(np.mean([o["escalated"] for o in outs])) if n else 0.0)


def bootstrap(outs, B=2000, seed=0):
    """95% intervals for success rate and CPST, resampling task instances."""
    rng = np.random.default_rng(seed)
    c = np.array([o["cost"] for o in outs]); ok = np.array([o["correct"] for o in outs], float)
    idx = rng.integers(0, len(outs), size=(B, len(outs)))
    cs, oks = c[idx].sum(1), ok[idx].sum(1)
    cpst = np.where(oks > 0, cs / np.maximum(oks, 1), np.inf)
    sr = oks / len(outs)
    return dict(success_ci=[float(np.percentile(sr, 2.5)), float(np.percentile(sr, 97.5))],
                cpst_ci=[float(np.percentile(cpst, 2.5)), float(np.percentile(cpst, 97.5))])


def instances(tasks, attempts, family=None):
    return [(t, a) for t in sorted(tasks) for a in attempts
            if family in (None, "all") or tasks[t]["family"] == family]


def evaluate(traces, insts, stages, ci=True):
    outs = [replay(traces, stages, t, a) for t, a in insts]
    res = dict(name=name(stages), stages=[list(s) for s in stages], **summarize(outs))
    if ci:
        res.update(bootstrap(outs))
    return res, outs


def model_cost_order(traces, models):
    """Models sorted by observed average cost per call: cascades go cheap to expensive."""
    avg = {m: np.mean([s["cost_usd"] for (mm, _, _), st in traces.items() if mm == m for s in st]
                      or [np.inf]) for m in models}
    return sorted(models, key=lambda m: avg[m]), avg


def enumerate_policies(models, D):
    """Singles at every depth, plus every cheap-to-expensive cascade of 2 or 3 models.
    Intermediate stages try depths 1..D; the last stage always gets full depth D."""
    pols = [[(m, d)] for m in models for d in range(1, D + 1)]
    for r in (2, 3):
        for combo in itertools.combinations(models, r):  # preserves cheap-to-expensive order
            for ds in itertools.product(range(1, D + 1), repeat=r - 1):
                pols.append([(m, d) for m, d in zip(combo, list(ds) + [D])])
    return pols


def pareto(results):
    """Policies not beaten on both success rate (higher) and CPST (lower)."""
    front = []
    for r in results:
        if not any(o["success_rate"] >= r["success_rate"] and o["cpst"] <= r["cpst"]
                   and (o["success_rate"] > r["success_rate"] or o["cpst"] < r["cpst"])
                   for o in results):
            front.append(r["name"])
    return set(front)
