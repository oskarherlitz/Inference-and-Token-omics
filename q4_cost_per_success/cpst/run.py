"""Run every model on every task once, logging every step.

Each (model, task, attempt) is a small agent loop of up to D iterations:
model answers -> verifier checks -> on rejection the feedback goes back to
the model. The loop stops at the first verified answer, exactly like a
production agent that trusts its checker. Every step also gets a ground-truth
grade, which the agent never sees.

Routing policies (cascades, retry limits) are evaluated afterwards by
replaying these traces in policies.py, so one run supports every policy
comparison without paying for the same call twice. Same design as the
teammate's q5_harness: run once, replay many times.

Usage:
  python run.py --models mock-small,mock-mid,mock-frontier --n 40 --out runs/mock.jsonl
  python run.py --models deepseek-v4-flash,claude-haiku-5.5,claude-sonnet-5.5 \
      --families code,extract --n 30 --d 3 --max-usd 5 --out runs/real1.jsonl
"""
import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from families import FAMILIES
from providers import load_registry, make_client


class Budget:
    """Hard stop on spend, so a bad loop cannot drain the API key."""

    def __init__(self, cap):
        self.cap, self.spent, self.lock = cap, 0.0, threading.Lock()

    def ok(self):
        return self.cap is None or self.spent < self.cap

    def add(self, x):
        with self.lock:
            self.spent += x


def run_attempt(name, client, fam, task, attempt, max_d, log, lock, budget, mock):
    messages = [{"role": "user", "content": fam.first_prompt(task)}]
    for it in range(max_d):
        if not budget.ok():
            return
        base = dict(task=task["id"], family=fam.name, difficulty=task["difficulty"],
                    model=name, attempt=attempt, iter=it)
        try:
            ctx = dict(task=task, family=fam, attempt=attempt) if mock else \
                dict(session_id=f"{name}|{task['id']}|{attempt}")
            r = client.complete(messages, system=fam.system, **ctx)
        except Exception as e:  # rate limit, network: log and end this attempt
            with lock:
                log.write(json.dumps({**base, "error": repr(e)[:300]}) + "\n"); log.flush()
            return
        verified, feedback, tool_s = fam.check(r.text, task)
        correct = fam.grade(r.text, task, verified=verified if fam.name == "code" else None)
        wrong = None if correct else fam.diff(r.text, task)
        budget.add(r.cost_usd)
        row = {**base, "verified": bool(verified), "correct": bool(correct),
               "fresh_in": r.fresh_in, "cached_in": r.cached_in, "cache_write": r.cache_write,
               "out": r.out, "cost_usd": round(r.cost_usd, 8), "cost_source": r.cost_source,
               "model_s": round(r.model_s, 3), "tool_s": round(tool_s, 3),
               "feedback": (feedback or "")[:240]}
        if wrong:
            row["wrong"] = {k: [str(g)[:40], str(w)[:40]] for k, (g, w) in wrong.items()}
        with lock:
            log.write(json.dumps(row) + "\n"); log.flush()
        if verified:
            return
        messages += [{"role": "assistant", "content": r.text},
                     {"role": "user", "content": fam.retry_prompt(feedback)}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="mock-small,mock-mid,mock-frontier",
                    help="comma-separated names from models.json")
    ap.add_argument("--families", default="code,extract")
    ap.add_argument("--n", type=int, default=40, help="tasks per family")
    ap.add_argument("--d", type=int, default=3, help="max verifier-driven iterations per attempt")
    ap.add_argument("--k", type=int, default=1, help="independent attempts per (model, task)")
    ap.add_argument("--hide-examples", action="store_true", help="harder HumanEval prompts")
    ap.add_argument("--max-usd", type=float, default=None, help="stop all calls once spend hits this")
    ap.add_argument("--max-tokens", type=int, default=4096,
                    help="leave room for reasoning tokens on thinking models")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="runs/run.jsonl")
    a = ap.parse_args()

    reg = load_registry()
    names = [m.strip() for m in a.models.split(",") if m.strip()]
    fams = []
    for f in a.families.split(","):
        fams.append(FAMILIES[f](hide_examples=a.hide_examples) if f == "code" else FAMILIES[f]())
    tasks = {f.name: f.load(a.n, seed=a.seed) for f in fams}
    clients = {}
    for n in names:
        mock = reg[n]["provider"] == "mock"
        clients[n] = (make_client(n, reg, seed=a.seed) if mock
                      else make_client(n, reg, max_tokens=a.max_tokens), mock)

    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    prices = {n: reg[n]["price"] for n in names}
    labels = {n: reg[n].get("label", n) for n in names}
    weights = {n: reg[n].get("weights", "closed") for n in names}
    meta = dict(meta=True, source="benchmark", models=names, prices=prices, labels=labels, weights=weights,
                families=[f.name for f in fams], n_per_family=a.n, d=a.d, k=a.k,
                mock=all(m for _, m in clients.values()), max_usd=a.max_usd,
                started=time.strftime("%Y-%m-%d %H:%M:%S"))
    lock, budget = threading.Lock(), Budget(a.max_usd)
    jobs = [(n, f, t, i) for n in names for f in fams for t in tasks[f.name] for i in range(a.k)]
    print(f"{len(jobs)} attempts ({len(names)} models x {sum(len(v) for v in tasks.values())} tasks"
          f" x k={a.k}), up to d={a.d} calls each")
    with out.open("w") as log:
        log.write(json.dumps(meta) + "\n")
        for f in fams:  # a readable line per task, so reports can show what was asked
            for t in tasks[f.name]:
                log.write(json.dumps(dict(task_info=True, task=t["id"], family=f.name,
                                          difficulty=t["difficulty"], preview=f.preview(t))) + "\n")
        with ThreadPoolExecutor(a.workers) as ex:
            futs = [ex.submit(run_attempt, n, clients[n][0], f, t, i, a.d, log, lock, budget,
                              clients[n][1]) for n, f, t, i in jobs]
            for done, fu in enumerate(as_completed(futs), 1):
                try:
                    fu.result()
                except Exception as e:  # same pattern as q5_harness: one bad task never kills the run
                    print(f"  WARNING: worker raised {e!r}", flush=True)
                if done % 25 == 0 or done == len(futs):
                    print(f"  {done}/{len(futs)} attempts, ${budget.spent:.4f} spent", flush=True)
    if not budget.ok():
        print(f"Stopped early: hit the --max-usd cap of ${a.max_usd}.")
    print(f"Logged to {out}")


if __name__ == "__main__":
    main()
