"""Run a routing policy live on held-out invoices and print the bill.

The invoices use a different seed from the benchmark, so this is an
out-of-sample check of the policy report.py picked.

  cd cpst
  python examples/live_router.py --stages mock-small:2,mock-frontier:2 --n 60
  python examples/live_router.py --stages deepseek-v4-flash:2,claude-sonnet-5.5:2 --n 20 --margin 0.3
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from families import ExtractFamily  # noqa: E402
from meter import Meter, Router     # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", default="mock-small:2,mock-frontier:2",
                    help="model:max_tries,... cheap to expensive")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=1, help="differs from the benchmark's seed 0")
    ap.add_argument("--margin", type=float, default=0.3)
    ap.add_argument("--out", default="runs/live.jsonl")
    a = ap.parse_args()

    stages = [(s.split(":")[0], int(s.split(":")[1])) for s in a.stages.split(",")]
    Path(a.out).unlink(missing_ok=True)
    fam, meter = ExtractFamily(), Meter(a.out)
    router = Router(stages, fam, meter)
    for task in fam.load(a.n, seed=a.seed):
        router.solve(task)
    print(f"Policy: {' -> '.join(f'{m} x{d}' for m, d in stages)}\n")
    print(meter.invoice(margin=a.margin))
    print(f"\nLog: {a.out}  (python report.py {a.out} --out results/live)")


if __name__ == "__main__":
    main()
