"""Run a minimal coding agent and log every step.

For each task we run K independent attempts. Each attempt is a serial
loop of up to D iterations: model writes code -> unit tests run -> on
failure the error goes back to the model. An attempt stops at its first
pass. We always run the maximum K and D; analyze.py derives every
smaller (k, d) configuration from prefixes of these traces.

Key design point: injecting latency or changing prices does not change
what the agent does, so we never re-run. We log the raw timings and
token counts once, and recompute wall-clock and cost under any
counterfactual regime afterwards.

Usage:
  python harness.py --provider anthropic --model <model-id> \
      --tasks data/HumanEval.jsonl.gz --n-tasks 40 --k 5 --d 4 \
      --hide-examples --out runs/run1.jsonl
  python harness.py --provider mock --n-tasks 20 --out runs/mock.jsonl
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from clients import make_client
from tasks import load_tasks

SYSTEM = ("You are a careful Python programmer. Reply with one complete, "
          "self-contained Python code block that implements the requested "
          "function, including any imports and helpers. No explanation.")

TEST_TIMEOUT_S = 10


def extract_code(text):
    blocks = re.findall(r"```(?:python|py)?\n(.*?)```", text, re.S)
    return max(blocks, key=len) if blocks else text


def run_tests(code, task, mock=False):
    """Returns (passed, feedback, tool_time_s)."""
    if mock:
        import random
        return "__SOLUTION__" in code, "AssertionError", random.uniform(0.2, 1.5)
    program = f"{code}\n\n{task['test']}\n\ncheck({task['entry_point']})\n"
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "prog.py"
        p.write_text(program)
        t0 = time.perf_counter()
        try:
            r = subprocess.run([sys.executable, "-I", str(p)], cwd=d,
                               capture_output=True, text=True, timeout=TEST_TIMEOUT_S)
            passed, err = r.returncode == 0, r.stderr
        except subprocess.TimeoutExpired:
            passed, err = False, f"Timed out after {TEST_TIMEOUT_S}s (possible infinite loop)."
        tool_time = time.perf_counter() - t0
    return passed, err[-1500:], tool_time


def run_attempt(client, task, attempt, max_d, mock, log, lock):
    messages = [{"role": "user", "content":
                 f"Implement this function:\n\n```python\n{task['prompt']}```"}]
    for it in range(max_d):
        try:
            r = client.complete(messages, system=SYSTEM)
        except Exception as e:  # rate limit, network: log and stop this attempt
            log_row = dict(task=task["id"], attempt=attempt, iter=it, error=repr(e))
            with lock:
                log.write(json.dumps(log_row) + "\n"); log.flush()
            return
        code = extract_code(r.text)
        passed, feedback, tool_s = run_tests(code, task, mock)
        row = dict(task=task["id"], attempt=attempt, iter=it, passed=passed,
                   input_tokens=r.input_tokens, output_tokens=r.output_tokens,
                   ttft_s=round(r.ttft_s, 4), model_s=round(r.total_s, 4),
                   tool_s=round(tool_s, 4))
        with lock:
            log.write(json.dumps(row) + "\n"); log.flush()
        if passed:
            return
        messages += [{"role": "assistant", "content": r.text},
                     {"role": "user", "content":
                      f"The tests failed with:\n\n```\n{feedback}\n```\n"
                      "Fix the function and reply with the full corrected code block."}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="mock", choices=["anthropic", "openai", "mock"])
    ap.add_argument("--model", default="mock")
    ap.add_argument("--tasks", default="data/HumanEval.jsonl.gz")
    ap.add_argument("--n-tasks", type=int, default=40)
    ap.add_argument("--k", type=int, default=5, help="max parallel attempts (breadth)")
    ap.add_argument("--d", type=int, default=4, help="max serial iterations (depth)")
    ap.add_argument("--hide-examples", action="store_true")
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="runs/run.jsonl")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    tasks = load_tasks(a.tasks, n=a.n_tasks, seed=a.seed, hide_examples=a.hide_examples)
    mock = a.provider == "mock"
    kw = {"seed": a.seed} if mock else {"temperature": a.temperature}
    client = make_client(a.provider, a.model, **kw)

    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    meta = dict(meta=True, provider=a.provider, model=a.model, k=a.k, d=a.d,
                n_tasks=len(tasks), hide_examples=a.hide_examples,
                started=time.strftime("%Y-%m-%d %H:%M:%S"))
    lock = threading.Lock()
    jobs = [(t, i) for t in tasks for i in range(a.k)]
    with out.open("w") as log:
        log.write(json.dumps(meta) + "\n")
        with ThreadPoolExecutor(a.workers) as ex:
            futs = [ex.submit(run_attempt, client, t, i, a.d, mock, log, lock) for t, i in jobs]
            for n, f in enumerate(as_completed(futs), 1):
                f.result()
                if n % 10 == 0 or n == len(futs):
                    print(f"  {n}/{len(futs)} attempts done", flush=True)
    print(f"Logged to {out}")


if __name__ == "__main__":
    main()
