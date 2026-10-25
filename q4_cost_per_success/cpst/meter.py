"""The product side: run a routing policy live, meter every call, bill per success.

The benchmark (run.py + report.py) finds the policy with the lowest cost per
successful task. This module runs that policy in production:

  Router   executes a cascade: cheap model first, verifier after every call,
           escalate on rejection. Same loop the benchmark replays.
  Meter    logs every call in the same JSONL schema as run.py, so report.py
           and the dashboard read production logs too, and issues invoices.

    from meter import Meter, Router
    meter  = Meter("runs/prod.jsonl")
    router = Router([("deepseek-v4-flash", 2), ("claude-sonnet-5.5", 2)], family, meter)
    answer = router.solve(task)            # None if every stage was rejected
    meter.accept(task["id"], correct=True)   # optional: customer acceptance arrives later
    print(meter.invoice(price_per_success=0.004))

You can also meter calls your own code makes:

    with meter.task("ticket-123", family="support") as t:
        resp = client.chat.completions.create(...)
        t.record_openai(resp, model="deepseek-v4-flash", verified=my_check(resp))
"""
import json
import threading
import time
from collections import defaultdict
from pathlib import Path

from providers import load_registry, make_client, usage_from_anthropic, usage_from_openai


class TaskMeter:
    def __init__(self, meter, task_id, family, difficulty, attempt):
        self.m, self.id, self.family, self.difficulty, self.attempt = meter, task_id, family, difficulty, attempt
        self.steps = []

    def record(self, model, fresh_in=0, cached_in=0, cache_write=0, out=0, cost_usd=0.0,
               cost_source="list", verified=False, correct=None, model_s=0.0, feedback=""):
        self.steps.append(dict(task=self.id, family=self.family, difficulty=self.difficulty,
                               model=model, attempt=self.attempt, iter=len(self.steps),
                               verified=bool(verified), correct=correct, fresh_in=fresh_in,
                               cached_in=cached_in, cache_write=cache_write, out=out,
                               cost_usd=round(cost_usd, 8), cost_source=cost_source,
                               model_s=round(model_s, 3), tool_s=0.0, feedback=feedback[:240]))

    def record_openai(self, resp, model, verified=False, price=None):
        f, c, w, o, cost, src = usage_from_openai(resp, price or self.m.price(model))
        self.record(model, f, c, w, o, cost, src, verified)

    def record_anthropic(self, resp, model, verified=False, price=None):
        f, c, w, o, cost, src = usage_from_anthropic(resp, price or self.m.price(model))
        self.record(model, f, c, w, o, cost, src, verified)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.m._write(self.steps)
        return False


class Meter:
    def __init__(self, path, registry=None):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.registry = registry or load_registry()
        self.lock = threading.Lock()
        if not self.path.exists():
            self.path.write_text(json.dumps(dict(meta=True, source="meter",
                                                 started=time.strftime("%Y-%m-%d %H:%M:%S"))) + "\n")

    def price(self, model):
        return self.registry.get(model, {}).get("price")

    def task(self, task_id, family="prod", difficulty=1, attempt=0):
        return TaskMeter(self, task_id, family, difficulty, attempt)

    def _write(self, steps):
        with self.lock, self.path.open("a") as f:
            for s in steps:
                if s["correct"] is None:
                    s["correct"] = s["verified"]  # until the customer says otherwise
                f.write(json.dumps(s) + "\n")

    def accept(self, task_id, correct):
        """Record ground truth after the fact (customer accepted or rejected the answer)."""
        with self.lock, self.path.open("a") as f:
            f.write(json.dumps(dict(acceptance=True, task=task_id, correct=bool(correct))) + "\n")

    def outcomes(self):
        """One outcome per task: total cost, delivered, correct (acceptance overrides)."""
        steps, accepted = defaultdict(list), {}
        for line in self.path.read_text().splitlines():
            r = json.loads(line)
            if r.get("meta"):
                continue
            if r.get("acceptance"):
                accepted[r["task"]] = r["correct"]
            elif "error" not in r:
                steps[r["task"]].append(r)
        outs = {}
        for t, st in steps.items():
            st.sort(key=lambda s: s["iter"])
            v = next((s for s in st if s["verified"]), None)
            correct = accepted.get(t, bool(v and v["correct"]))
            good = v["cost_usd"] if (v and correct) else 0.0
            cost = sum(s["cost_usd"] for s in st)
            models = [s["model"] for s in st]
            outs[t] = dict(cost=cost, delivered=v is not None, correct=bool(v) and correct,
                           waste=cost - good, calls=len(st), models=models,
                           tokens=sum(s["fresh_in"] + s["cached_in"] + s["cache_write"] + s["out"] for s in st),
                           escalated=len(set(models)) > 1, family=st[0]["family"])
        return outs

    def invoice(self, price_per_success=None, margin=0.3, bill_on="correct"):
        """The same work billed two ways. If no price is given, price at a target margin."""
        o = list(self.outcomes().values())
        n, cost = len(o), sum(x["cost"] for x in o)
        n_ok, n_dl = sum(x["correct"] for x in o), sum(x["delivered"] for x in o)
        waste = sum(x["waste"] for x in o)
        cpst = cost / n_ok if n_ok else float("inf")
        price = price_per_success if price_per_success is not None else cpst / (1 - margin)
        billable = n_ok if bill_on == "correct" else n_dl
        lines = [f"Tasks run                          {n:>10}",
                 f"Delivered correctly                {n_ok:>10}",
                 f"Wrong but passed the checker       {n_dl - n_ok:>10}",
                 f"Gave up                            {n - n_dl:>10}",
                 "",
                 "Billed by token",
                 f"  Token charges                    ${cost:>12.6f}",
                 f"  Of which bought nothing          ${waste:>12.6f}  ({(waste / cost if cost else 0):.0%})",
                 f"  Cost per correct task            ${cpst:>12.6f}",
                 "",
                 f"Billed by success (per {'accepted answer' if bill_on == 'correct' else 'checker pass'})",
                 f"  Price per success                ${price:>12.6f}",
                 f"  Customer pays                    ${price * billable:>12.6f}",
                 f"  Provider cost                    ${cost:>12.6f}",
                 f"  Provider margin                  {((price * billable - cost) / (price * billable) if billable else 0):>12.1%}"]
        return "\n".join(lines)


class Router:
    """Execute a cascade policy live: [(model_name, max_tries), ...], cheap to expensive."""

    def __init__(self, stages, family, meter, registry=None, grade=True, **client_kw):
        """grade=True when tasks carry an answer key (benchmarks, held-out tests).
        In production set grade=False and report acceptance later with meter.accept()."""
        reg = registry or meter.registry
        self.stages, self.family, self.meter, self.grade = stages, family, meter, grade
        self.clients = {}
        for m, _ in stages:
            mock = reg[m]["provider"] == "mock"
            self.clients[m] = (make_client(m, reg, **({} if mock else client_kw)), mock)

    def solve(self, task, attempt=0):
        with self.meter.task(task["id"], self.family.name, task.get("difficulty", 1), attempt) as t:
            for model, tries in self.stages:
                client, mock = self.clients[model]
                messages = [{"role": "user", "content": self.family.first_prompt(task)}]
                for _ in range(tries):
                    ctx = (dict(task=task, family=self.family, attempt=attempt) if mock
                           else dict(session_id=f"{model}|{task['id']}|{attempt}"))
                    r = client.complete(messages, system=self.family.system, **ctx)
                    ok, feedback, _ = self.family.check(r.text, task)
                    truth = self.family.grade(r.text, task, verified=ok) if self.grade else None
                    t.record(model, r.fresh_in, r.cached_in, r.cache_write, r.out, r.cost_usd,
                             r.cost_source, ok, truth, r.model_s, feedback or "")
                    if ok:
                        return r.text
                    messages += [{"role": "assistant", "content": r.text},
                                 {"role": "user", "content": self.family.retry_prompt(feedback)}]
        return None
