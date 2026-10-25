"""Per-token vs per-success billing.

Today the customer pays for every token, including failed attempts, so the
customer carries the failure risk. Under per-success billing the provider
charges a fixed price per successful task and eats the cost of failures.

Three questions this module answers from replayed outcomes:

1. Price. To earn gross margin m, the provider charges P = CPST / (1 - m).
2. Spread. A router with a lower CPST than the customer's current setup can
   undercut it and still profit. The largest margin that still saves the
   customer money is  1 - CPST_router / CPST_baseline.
3. Risk. Margins are uncertain batch to batch. Bootstrapped batches give the
   probability that a batch of N tasks loses money at price P.

There is also a definitional trap: billing on *verified* deliveries means
the customer pays for false accepts (answers that passed the checker but
were wrong). Billing on *correct* deliveries needs an acceptance signal the
provider does not control. The gap between the two is reported explicitly.
"""
import numpy as np


def price_for_margin(cpst, margin):
    return cpst / (1 - margin)


def max_undercut_margin(cpst_router, cpst_baseline):
    if not np.isfinite(cpst_router) or not np.isfinite(cpst_baseline) or cpst_baseline <= 0:
        return None
    return 1 - cpst_router / cpst_baseline


def simulate_pnl(outs, price, batch=100, B=4000, bill_on="correct", seed=0):
    rng = np.random.default_rng(seed)
    c = np.array([o["cost"] for o in outs])
    paid = np.array([o["correct"] if bill_on == "correct" else o["delivered"] for o in outs], float)
    idx = rng.integers(0, len(outs), size=(B, batch))
    rev, cost = price * paid[idx].sum(1), c[idx].sum(1)
    margin = np.where(rev > 0, (rev - cost) / np.maximum(rev, 1e-12), -np.inf)
    return dict(prob_loss=float((rev < cost).mean()),
                margin_mean=float(np.mean(margin[np.isfinite(margin)])) if np.isfinite(margin).any() else None,
                margin_p5=float(np.percentile(margin, 5)))


def customer_price_per_correct(outs, price, bill_on="correct"):
    n_ok = sum(o["correct"] for o in outs)
    n_paid = sum(o["correct"] if bill_on == "correct" else o["delivered"] for o in outs)
    return price * n_paid / n_ok if n_ok else float("inf")


def margin_table(outs, cpst_router, cpst_baseline, margins=(0.1, 0.2, 0.3, 0.4, 0.5), batch=100):
    rows = []
    for m in margins:
        p = price_for_margin(cpst_router, m)
        risk = simulate_pnl(outs, p, batch=batch)
        rows.append(dict(margin=m, price=p,
                         customer_saving=(1 - p / cpst_baseline) if np.isfinite(cpst_baseline) else None,
                         prob_loss=risk["prob_loss"], margin_p5=risk["margin_p5"],
                         price_if_billed_on_verified=customer_price_per_correct(outs, p, "verified")))
    return rows
