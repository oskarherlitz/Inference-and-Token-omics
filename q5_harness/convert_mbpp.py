"""Convert MBPP sanitized dataset to HumanEval format for the Q5 harness.

Output fields: task_id, prompt, entry_point, test
Run: python convert_mbpp.py --out data/mbpp_sanitized.jsonl
"""
import argparse
import json
import re
import sys


def extract_entry_point(code):
    m = re.search(r"^def ([A-Za-z_][A-Za-z0-9_]*)\s*\(", code, re.MULTILINE)
    if not m:
        return None
    return m.group(1)


def extract_signature(code):
    """Return just the first 'def ...:' line (handles multi-line signatures)."""
    lines = code.splitlines()
    sig_lines = []
    in_sig = False
    for line in lines:
        if not in_sig and re.match(r"\s*def ", line):
            in_sig = True
        if in_sig:
            sig_lines.append(line)
            if line.rstrip().endswith(":"):
                break
    return "\n".join(sig_lines) if sig_lines else ""


def build_prompt(entry_point, sig, description):
    """Build a HumanEval-style prompt: signature + docstring."""
    indent = "    "
    # Normalise indentation to 0 for the def line
    sig = sig.strip()
    doc = description.strip()
    return f"{sig}\n{indent}\"\"\"{doc}\n{indent}\"\"\"\n"


def build_test(entry_point, test_imports, test_list):
    """Wrap test_list assertions in def check(candidate):, replacing the
    function name with `candidate`."""
    lines = []
    for imp in test_imports:
        lines.append(imp)
    lines.append("def check(candidate):")
    for assertion in test_list:
        # Replace every occurrence of entry_point( with candidate(
        fixed = re.sub(
            r"\b" + re.escape(entry_point) + r"\s*\(",
            "candidate(",
            assertion,
        )
        lines.append(f"    {fixed}")
    return "\n".join(lines) + "\n"


def convert(split="test"):
    from datasets import load_dataset
    ds = load_dataset("google-research-datasets/mbpp", "sanitized")
    tasks = []
    skipped = 0
    for item in ds[split]:
        entry_point = extract_entry_point(item["code"])
        if not entry_point:
            skipped += 1
            continue
        sig = extract_signature(item["code"])
        if not sig:
            skipped += 1
            continue
        prompt = build_prompt(entry_point, sig, item["prompt"])
        test = build_test(entry_point, item["test_imports"], item["test_list"])
        tasks.append({
            "task_id": f"MBPP/{item['task_id']}",
            "prompt": prompt,
            "entry_point": entry_point,
            "test": test,
        })
    return tasks, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test", choices=["train", "test", "validation"])
    ap.add_argument("--out", default="data/mbpp_sanitized.jsonl")
    a = ap.parse_args()

    tasks, skipped = convert(a.split)
    with open(a.out, "w") as f:
        for t in tasks:
            f.write(json.dumps(t) + "\n")
    print(f"Wrote {len(tasks)} tasks to {a.out} (skipped {skipped} with no def)")

    # Smoke test: verify check(candidate) is parseable and entry_point is present
    ok = all("def check(candidate):" in t["test"] and t["entry_point"] in t["prompt"] for t in tasks)
    print("Smoke test:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
