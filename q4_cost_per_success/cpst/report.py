"""Turn a run log into the CPST report, charts and dashboard.

  python report.py runs/mock.jsonl --out results/mock
  python report.py runs/real1.jsonl --out results/real1 --tolerance 0.02

Baseline   = the most expensive model alone, with full retries: what a careful
             customer does today when they just "use the best model".
Router     = the cheapest-CPST policy whose success rate is within --tolerance
             of the baseline's. Same quality, lower cost per success.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

import billing
import policies as P

HERE = Path(__file__).parent


def clean(x):
    """JSON-safe: inf/nan -> None, numpy -> python."""
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not math.isfinite(float(x)) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def analyze_scope(traces, insts, models, D, tol):
    pols = P.enumerate_policies(models, D)
    results, outs = [], {}
    for st in pols:
        r, o = P.evaluate(traces, insts, st, ci=False)
        results.append(r); outs[r["name"]] = o
    front = P.pareto(results)
    for r in results:
        r["pareto"] = r["name"] in front
    by = {r["name"]: r for r in results}
    base = by[P.name([(models[-1], D)])]
    cheap = by[P.name([(models[0], D)])]
    eligible = [r for r in results if r["success_rate"] >= base["success_rate"] - tol]
    rec = min(eligible, key=lambda r: (r["cpst"], -r["success_rate"], len(r["stages"])))
    if all(m == models[-1] for m, _ in rec["stages"]):
        rec = base  # fewer tries of the same model is not routing
    for r in {id(x): x for x in (base, cheap, rec)}.values():
        r.update(P.bootstrap(outs[r["name"]]))
    spread = billing.max_undercut_margin(rec["cpst"], base["cpst"])
    table = billing.margin_table(outs[rec["name"]], rec["cpst"], base["cpst"])
    singles = {m: by[P.name([(m, D)])] for m in models}
    pack = lambda o: [[round(x["cost"], 8), int(x["delivered"]), int(x["correct"])] for x in o]
    # Many cascades behave exactly like a simpler policy (the later stage is never reached).
    # Keep the simplest policy for each distinct outcome so tables stay readable.
    shown, seen = [], set()
    keep = {base["name"], cheap["name"], rec["name"]}
    for r in sorted(results, key=lambda r: (r["cpst"], len(r["stages"]))):
        key = (round(r["success_rate"], 9), round(r["cpst"], 12) if math.isfinite(r["cpst"]) else None)
        if key in seen and r["name"] not in keep:
            continue
        seen.add(key); shown.append(r)
    return dict(policies=shown, n_policies_evaluated=len(results), baseline=base["name"],
                routing_helps=bool(spread is not None and spread > 0.01 and rec is not base),
                router=rec["name"], cheapest=cheap["name"], spread=spread, margins=table,
                singles={m: s["name"] for m, s in singles.items()},
                outcomes={base["name"]: pack(outs[base["name"]]), rec["name"]: pack(outs[rec["name"]])})


SEGMENTS = [  # kinds of work a user would recognize: (key, label, family, difficulties or None)
    ("code", "Writing code", "code", None),
    ("doc_clean", "Simple invoices", "extract", {0}),
    ("doc_messy", "Tricky invoices", "extract", {1, 2}),
    ("prod", "Your tasks", "prod", None),
]


def replay_steps(traces, stages, task, attempt):
    """The calls a policy would make on one task, in order, with the outcome."""
    steps = []
    for model, d in stages:
        for s in traces.get((model, task, attempt), [])[:d]:
            steps.append(dict(m=model, v=bool(s["verified"]), c=bool(s["correct"]),
                              cost=s["cost_usd"],
                              tok=[s["fresh_in"], s["cached_in"], s["cache_write"], s["out"]],
                              why=(s.get("feedback") or "").strip().splitlines()[-1][:160]
                                  if s.get("feedback") else "",
                              wrong=s.get("wrong")))
            if s["verified"]:
                return steps, ("correct" if s["correct"] else "wrong")
    return steps, "gave_up"


def user_view(traces, tasks, attempts, models, D, tol, labels):
    """Everything the user-facing dashboard needs, in plain terms."""
    out = []
    for key, label, fam, diffs in SEGMENTS:
        insts = [(t, a) for t, a in P.instances(tasks, attempts)
                 if tasks[t].get("family") == fam and (diffs is None or tasks[t].get("difficulty") in diffs)]
        if not insts:
            continue
        sc = analyze_scope(traces, insts, models, D, tol)
        by = {p["name"]: p for p in sc["policies"]}
        options = [dict(id=m, kind="single", stages=[[m, D]], title=labels.get(m, m),
                        how=f"Uses only {labels.get(m, m)}, retrying up to {D} times when the check fails")
                   for m in models]
        rstages = by[sc["router"]]["stages"]
        if sc["routing_helps"]:
            names = [labels.get(m, m) for m, _ in rstages]
            how = (f"Sends every task to {names[0]}, which matched the most capable model’s accuracy here"
                   if len(names) == 1 else
                   f"Starts with {names[0]}, " + ", then ".join(f"switches to {n}" for n in names[1:])
                   + " only if the automatic check fails")
            options.append(dict(id="smart", kind="smart", stages=rstages, title="Smart routing", how=how))
        for o in options:
            led = []
            for t, a in insts:
                steps, outcome = replay_steps(traces, o["stages"], t, a)
                led.append(dict(task=t, preview=tasks[t].get("preview", t), steps=steps, outcome=outcome,
                                cost=sum(s["cost"] for s in steps)))
            n = len(led)
            cnt = lambda k: sum(1 for x in led if x["outcome"] == k)
            total = sum(x["cost"] for x in led)
            o.update(n=n, correct=cnt("correct"), wrong=cnt("wrong"), gave_up=cnt("gave_up"),
                     total_cost=total, tries=sum(len(x["steps"]) for x in led) / n,
                     cpst=total / cnt("correct") if cnt("correct") else None, ledger=led)
        out.append(dict(key=key, label=label, n=len(insts), options=options,
                        routing_helps=sc["routing_helps"], best_alone=models[-1], cheapest=models[0]))
    return out


def money(x, digits=4):
    return "n/a" if x is None or not math.isfinite(x) else f"${x:,.{digits}f}"


def pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def write_report(res, meta, out):
    L = []
    say = L.append
    say(f"# Cost per successful task: {', '.join(meta.get('models', []))}")
    if meta.get("mock"):
        say("\n> **Mock data.** These numbers come from simulated models and only demonstrate the pipeline.\n")
    say(f"Up to d={meta.get('d')} verifier-driven iterations per model. Tasks per family: "
        f"{meta.get('n_per_family')}. Run started {meta.get('started')}.\n")
    for scope, s in res["scopes"].items():
        by = {r["name"]: r for r in s["policies"]}
        b, r = by[s["baseline"]], by[s["router"]]
        say(f"## Scope: {scope} ({b['n']} task instances)\n")
        say(f"**Today (baseline, `{b['name']}`):** {pct(b['success_rate'])} of tasks delivered correctly, "
            f"CPST {money(b['cpst'])} (95% CI {money(b['cpst_ci'][0])} to {money(b['cpst_ci'][1])}). "
            f"{pct(b['waste_share'])} of spend bought nothing.")
        say(f"\n**Router (`{r['name']}`):** {pct(r['success_rate'])} success, CPST {money(r['cpst'])} "
            f"(95% CI {money(r['cpst_ci'][0])} to {money(r['cpst_ci'][1])}), escalated on "
            f"{pct(r['escalation_rate'])} of tasks.")
        if not s["routing_helps"]:
            say("\n**No cheaper policy matched the baseline** within the tolerance on this scope. "
                "Routing does not help here: the checker lets too many plausible wrong answers "
                "through for cheap models to be trusted.")
        elif s["spread"] is not None:
            say(f"\n**Spread:** a provider using the router can charge up to {pct(s['spread'])} gross "
                f"margin per successful task and still cost the customer less than the baseline.")
        say("\n| Policy | Success | CPST | Waste | False accepts | $/task | Pareto |")
        say("|---|---|---|---|---|---|---|")
        for p in s["policies"][:12]:
            mark = " (baseline)" if p["name"] == s["baseline"] else " (router)" if p["name"] == s["router"] else ""
            say(f"| `{p['name']}`{mark} | {pct(p['success_rate'])} | {money(p['cpst'])} | "
                f"{pct(p['waste_share'])} | {pct(p['false_accept_rate'])} | {money(p['cost_per_task'])} | "
                f"{'yes' if p['pareto'] else ''} |")
        say("\n**Per-success pricing for the router** (batches of 100 tasks):\n")
        say("| Target margin | Price per success | Customer saving vs baseline | P(batch loses money) | "
            "Effective price if billed on verifier passes |")
        say("|---|---|---|---|---|")
        for m in s["margins"]:
            say(f"| {pct(m['margin'])} | {money(m['price'])} | {pct(m['customer_saving'])} | "
                f"{pct(m['prob_loss'])} | {money(m['price_if_billed_on_verified'])} |")
        say("")
    if res.get("by_difficulty"):
        say("## Where does the cheap model win? (extract family, by difficulty)\n")
        say("| Difficulty | Cheapest model alone: success / CPST | Baseline: success / CPST | "
            "Cheapest model's false-accept rate |")
        say("|---|---|---|---|")
        for d, row in res["by_difficulty"].items():
            c, b = row["cheapest"], row["baseline"]
            say(f"| {d} | {pct(c['success_rate'])} / {money(c['cpst'])} | {pct(b['success_rate'])} / "
                f"{money(b['cpst'])} | {pct(c['false_accept_rate'])} |")
        say("\nDifficulty 0 has no distractors, so the verifier catches nearly every mistake. "
            "At difficulty 2, plausible wrong numbers pass the verifier, which is where cheap "
            "models stop being cheap per success.\n")
    (out / "report.md").write_text("\n".join(L) + "\n")


def plot(res, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#9aa5b1", "axes.labelcolor": "#33414e",
                         "xtick.color": "#33414e", "ytick.color": "#33414e"})
    (out / "charts").mkdir(exist_ok=True)
    for scope, s in res["scopes"].items():
        ps = [p for p in s["policies"] if p["cpst"] is not None and math.isfinite(p["cpst"])]
        fig, ax = plt.subplots(figsize=(6.4, 4))
        ax.scatter([p["cpst"] for p in ps], [p["success_rate"] for p in ps], s=18, color="#b8c2cc",
                   label="all policies", zorder=2)
        fr = sorted((p for p in ps if p["pareto"]), key=lambda p: p["cpst"])
        ax.plot([p["cpst"] for p in fr], [p["success_rate"] for p in fr], color="#33414e", lw=1.2,
                zorder=3, label="best tradeoffs")
        for key, color, lab in (("baseline", "#b3261e", "baseline: best model alone"),
                                ("router", "#1d6b52", "router (same quality, lowest CPST)")):
            p = next(x for x in ps if x["name"] == s[key])
            ax.scatter([p["cpst"]], [p["success_rate"]], s=70, color=color, zorder=4, label=lab)
        ax.set_xscale("log")
        ax.set_xlabel("Cost per successful task (USD, log scale)")
        ax.set_ylabel("Share of tasks delivered correctly")
        ax.set_title(f"Routing policies, {scope}", loc="left", fontsize=11)
        ax.legend(frameon=False, fontsize=8, loc="lower right")
        fig.tight_layout(); fig.savefig(out / f"charts/pareto_{scope}.png", dpi=160); plt.close(fig)


def observed_report(path, out):
    """Production logs from meter.py: what actually happened, per family and overall."""
    from meter import Meter
    outs = list(Meter(path).outcomes().values())
    L = ["# Cost per successful task, as run (production meter log)\n",
         "| Scope | Tasks | Correct | CPST | Spend that bought nothing | Wrong but passed checker | Escalated |",
         "|---|---|---|---|---|---|---|"]
    res = {}
    for fam in ["all"] + sorted({o["family"] for o in outs}):
        sub = [o for o in outs if fam == "all" or o["family"] == fam]
        r = P.summarize(sub); res[fam] = r
        L.append(f"| {fam} | {r['n']} | {pct(r['success_rate'])} | {money(r['cpst'], 6)} | {pct(r['waste_share'])} | "
                 f"{pct(r['false_accept_rate'])} | {pct(r['escalation_rate'])} |")
    (out / "report.md").write_text("\n".join(L) + "\n")
    (out / "results.json").write_text(json.dumps(clean(res), indent=1))
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--out", default="results/run")
    ap.add_argument("--tolerance", type=float, default=0.02,
                    help="router may trail the baseline's success rate by at most this much")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    first = json.loads(Path(a.log).read_text().splitlines()[0])
    if first.get("source") == "meter":
        return observed_report(a.log, out)

    meta, traces, tasks, attempts = P.load(a.log)
    present = sorted({m for (m, _, _) in traces})
    models, avg = P.model_cost_order(traces, meta.get("models") or present)
    models = [m for m in models if m in present]
    D = meta.get("d") or max(len(v) for v in traces.values())
    fams = sorted({t["family"] for t in tasks.values()})
    scopes = ["all"] + fams if len(fams) > 1 else fams

    res = dict(meta=meta, models=models, avg_cost_per_call=avg, scopes={})
    for sc in scopes:
        res["scopes"][sc] = analyze_scope(traces, P.instances(tasks, attempts, sc), models, D, a.tolerance)

    if "extract" in fams:
        res["by_difficulty"] = {}
        for d in sorted({t["difficulty"] for t in tasks.values() if t["family"] == "extract"}):
            insts = [(t, at) for t, at in P.instances(tasks, attempts, "extract")
                     if tasks[t]["difficulty"] == d]
            res["by_difficulty"][d] = {
                "cheapest": P.evaluate(traces, insts, [(models[0], D)], ci=False)[0],
                "baseline": P.evaluate(traces, insts, [(models[-1], D)], ci=False)[0]}

    res["user"] = user_view(traces, tasks, attempts, models, D, a.tolerance, meta.get("labels") or {})
    write_report(res, meta, out)
    data = clean(res)
    (out / "results.json").write_text(json.dumps(data, indent=1))
    plot(res, out)
    from providers import load_registry
    reg = load_registry()  # older logs may lack labels or weights; fill them from the registry
    meta.setdefault("labels", {}); meta.setdefault("weights", {})
    for m in models:
        meta["labels"].setdefault(m, reg.get(m, {}).get("label", m))
        meta["weights"].setdefault(m, reg.get(m, {}).get("weights", "closed"))
    market_file = HERE / "market.json"
    market = json.loads(market_file.read_text()) if market_file.exists() else None
    page = clean(dict(meta=meta, models=models, user=res["user"], market=market))  # only what the page needs
    html = (HERE / "dashboard_template.html").read_text().replace("/*__DATA__*/null", json.dumps(page))
    (out / "dashboard.html").write_text(html)
    print((out / "report.md").read_text())
    print(f"Wrote {out}/report.md, results.json, dashboard.html, charts/")


if __name__ == "__main__":
    main()
