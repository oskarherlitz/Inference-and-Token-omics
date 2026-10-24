"""Task loading. A task is a dict: {id, prompt, entry_point, test}.

`prompt` is a Python function signature + docstring, `test` defines
`check(candidate)`, exactly the HumanEval format. Custom tasks can be
supplied as a .jsonl file with the same fields.
"""
import gzip
import json
import random
import re
from pathlib import Path


def load_tasks(path, n=None, seed=0, hide_examples=False):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as f:
        tasks = [json.loads(line) for line in f if line.strip()]
    tasks = [
        {"id": t["task_id"] if "task_id" in t else t["id"],
         "prompt": t["prompt"], "entry_point": t["entry_point"], "test": t["test"]}
        for t in tasks
    ]
    if hide_examples:
        # Strip doctest examples from docstrings: makes tasks harder, so that
        # iteration (depth) and resampling (breadth) actually matter.
        for t in tasks:
            t["prompt"] = _strip_examples(t["prompt"])
    if n is not None and n < len(tasks):
        random.Random(seed).shuffle(tasks)
        tasks = tasks[:n]
    return tasks


def _strip_examples(prompt):
    out, skipping = [], False
    for line in prompt.splitlines():
        s = line.strip()
        if s.startswith(">>>"):
            skipping = True
            continue
        if skipping and s and not s.startswith(('"""', "'''")) and not re.match(r"^[A-Za-z]", s):
            continue  # expected-output line after a >>> line
        skipping = False
        out.append(line)
    return "\n".join(out) + "\n"
