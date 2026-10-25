"""Convert MBPP+ (EvalPlus) to HumanEval format for the Q5 harness.

Runs each task's canonical solution to generate expected outputs for all
base + plus inputs, then builds a def check(candidate): with those assertions.

Run: python convert_mbppplus.py --out data/mbppplus.jsonl
"""
import argparse
import gzip
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


TIMEOUT_S = 10


def run_canonical(canonical_solution, entry_point, inputs, atol):
    """Execute canonical solution against all inputs; return list of
    (input_args, expected_output_repr, ok) tuples. Skips inputs that
    raise exceptions or produce un-repr-able values."""
    results = []
    with tempfile.TemporaryDirectory() as d:
        prog = Path(d) / "canon.py"
        lines = [canonical_solution, "", "import json, sys"]
        lines.append("_inputs = json.loads(sys.stdin.read())")
        lines.append("_out = []")
        lines.append("for _args in _inputs:")
        lines.append(f"    try:")
        lines.append(f"        _r = {entry_point}(*_args)")
        lines.append(f"        _out.append(repr(_r))")
        lines.append(f"    except Exception as _e:")
        lines.append(f"        _out.append(None)")
        lines.append("print(json.dumps(_out))")
        prog.write_text("\n".join(lines))
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(prog)],
                input=json.dumps(inputs),
                capture_output=True, text=True, timeout=TIMEOUT_S, cwd=d,
            )
            if proc.returncode != 0:
                return []
            outputs = json.loads(proc.stdout)
        except Exception:
            return []
    for args, out_repr in zip(inputs, outputs):
        if out_repr is not None:
            results.append((args, out_repr))
    return results


def build_check(entry_point, pairs, atol):
    """Build def check(candidate): with one assertion per (input, expected) pair."""
    lines = ["def check(candidate):"]
    for args, expected_repr in pairs:
        args_str = ", ".join(repr(a) for a in args)
        if atol and atol > 0:
            lines.append(
                f"    assert abs(candidate({args_str}) - {expected_repr}) <= {atol}, "
                f"repr(candidate({args_str}))"
            )
        else:
            lines.append(f"    assert candidate({args_str}) == {expected_repr}, repr(candidate({args_str}))")
    return "\n".join(lines) + "\n"


def build_prompt(entry_point, canonical_solution, description):
    """Extract function signature from canonical solution + add docstring."""
    sig_lines = []
    in_sig = False
    for line in canonical_solution.splitlines():
        if not in_sig and re.match(r"\s*def ", line):
            in_sig = True
        if in_sig:
            sig_lines.append(line.rstrip())
            if line.rstrip().endswith(":"):
                break
    sig = "\n".join(sig_lines).strip() if sig_lines else f"def {entry_point}(*args):"
    # Strip outer triple-quotes if present, then strip assert examples
    desc = description.strip().strip('"""').strip("'''").strip()
    doc_lines = [l for l in desc.splitlines()
                 if not l.strip().startswith("assert")]
    doc = " ".join(doc_lines).strip()
    return f'{sig}\n    """{doc}\n    """\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/MbppPlus.jsonl.gz")
    ap.add_argument("--out", default="data/mbppplus.jsonl")
    ap.add_argument("--base-only", action="store_true",
                    help="Use only base_input (skips plus_input; faster but easier)")
    a = ap.parse_args()

    with gzip.open(a.src) as f:
        raw = [json.loads(l) for l in f]

    written, skipped = 0, 0
    with open(a.out, "w") as out_f:
        for t in raw:
            entry_point = t["entry_point"]
            canonical = t["canonical_solution"]
            plus = t["plus_input"] if isinstance(t["plus_input"], list) else []
            inputs = t["base_input"] if a.base_only else t["base_input"] + plus
            atol = t.get("atol", 0) or 0

            pairs = run_canonical(canonical, entry_point, inputs, atol)
            if len(pairs) < 3:
                skipped += 1
                continue

            prompt = build_prompt(entry_point, canonical, t["prompt"])
            test = build_check(entry_point, pairs, atol)
            import ast
            try:
                ast.parse(test)
            except SyntaxError:
                skipped += 1
                continue
            out_f.write(json.dumps({
                "task_id": t["task_id"],
                "prompt": prompt,
                "entry_point": entry_point,
                "test": test,
            }) + "\n")
            written += 1

    print(f"Wrote {written} tasks to {a.out} (skipped {skipped})")


if __name__ == "__main__":
    main()
