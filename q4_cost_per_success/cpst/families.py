"""Task families for the CPST meter.

Every family separates two judgments, because billing per success depends
on the difference between them:

  check(output, task) -> (verified, feedback)
      What a production system can see without the answer key: unit tests,
      schema validation, internal consistency, grounding in the source.
      The agent stops when this passes, and its feedback drives retries.

  grade(output, task) -> correct
      Ground truth. Only a benchmark has this. In production it arrives
      later, if at all (customer acceptance, human review, a failed payment).

A step that is verified but not correct is a FALSE ACCEPT: the customer
receives a wrong answer that looked right. Whoever defines "success" for
billing has to price that risk.

Families:
  code     HumanEval functions. Reuses the teammate's loader and sandboxed
           test runner from q5_harness. Tests are both verifier and grader,
           so false accepts are zero here by construction (a stated limit).
  extract  Synthetic business invoices -> JSON fields. Ground truth is known
           exactly. The verifier checks the schema, that the total equals the
           subtotal plus tax, and that every value appears in the invoice. That
           catches made-up numbers but not "picked the wrong number from the
           invoice" (an old quote, last year's tax rate, the original due date).
"""
import gzip
import json
import random
import re
import sys
from datetime import date, timedelta
from pathlib import Path

Q5 = Path(__file__).resolve().parent.parent / "q5_harness"
sys.path.append(str(Q5))
from tasks import load_tasks          # noqa: E402  (teammate's HumanEval loader)
from harness import extract_code, run_tests  # noqa: E402  (teammate's sandboxed runner)


# ----------------------------------------------------------------- code ----

class CodeFamily:
    name = "code"
    system = ("You are a careful Python programmer. Reply with one complete, "
              "self-contained Python code block that implements the requested "
              "function, including any imports and helpers. No explanation.")

    def __init__(self, path=Q5 / "data/HumanEval.jsonl.gz", hide_examples=False):
        self.path, self.hide_examples = Path(path), hide_examples
        with gzip.open(self.path, "rt") as f:
            self._canon = {json.loads(l)["task_id"]: json.loads(l)["canonical_solution"]
                           for l in f if l.strip()}

    def load(self, n, seed=0):
        tasks = load_tasks(self.path, n=n, seed=seed, hide_examples=self.hide_examples)
        for t in tasks:
            t["family"], t["difficulty"] = self.name, 1
            t["canonical"] = self._canon.get(t["id"], "")
        return tasks

    def first_prompt(self, task):
        return f"Implement this function:\n\n```python\n{task['prompt']}```"

    def retry_prompt(self, feedback):
        return (f"The tests failed with:\n\n```\n{feedback}\n```\n"
                "Fix the function and reply with the full corrected code block.")

    def preview(self, task):
        """One line a person can read: the function and the first line of its docstring."""
        lines = [l.strip().strip('"').strip("'").strip() for l in task["prompt"].splitlines()]
        start = next((i for i, l in enumerate(task["prompt"].splitlines())
                      if '"""' in l or "'''" in l), None)
        doc = ""
        if start is not None:
            doc = next((l for l in lines[start:] if l and not l.startswith(">>>")), "")
        doc = doc.rstrip(".")[:110]
        return f"Write {task['entry_point']}(): {doc}" if doc else f"Write {task['entry_point']}()"

    def diff(self, output, task):
        return None  # tests say pass or fail; there are no fields to compare

    def check(self, output, task):
        passed, feedback, tool_s = run_tests(extract_code(output), task, mock=False)
        return passed, feedback, tool_s

    def grade(self, output, task, verified=None):
        # HumanEval's tests are the only ground truth available, so the grade
        # equals the check. Reuse the verified result instead of re-running.
        if verified is not None:
            return verified
        return run_tests(extract_code(output), task, mock=False)[0]

    def mock_output(self, task, ok, rng):
        body = task["canonical"] if ok else "    raise NotImplementedError\n"
        return f"```python\n{task['prompt']}{body}```"


# -------------------------------------------------------------- extract ----

V_ADJ = ["Brightline", "Northwind", "Summit", "Cedar", "Ironwood", "Meridian", "Bluestem",
         "Copperline", "Lakeshore", "Redfield", "Westbrook", "Harbor"]
V_NOUN = ["Office Supply", "Catering", "IT Services", "Printing", "Landscaping", "Cleaning",
          "Electrical", "Design Studio", "Plumbing", "Couriers"]
C_ADJ = ["Riverside", "Oakmont", "Pinecrest", "Hillview", "Maple", "Lakeview", "Fairway",
         "Elmwood", "Bayside", "Crestline"]
C_NOUN = ["Dental Group", "Public Library", "Bakery", "Law Offices", "Middle School",
          "Animal Hospital", "Fitness Club", "Coffee Roasters", "Family Clinic", "Hotel"]
FIELDS = ["vendor", "customer", "invoice_number", "invoice_date", "due_date",
          "subtotal", "tax_rate_pct", "total_due"]
SCHEMA_HINT = ("{\"vendor\": str, \"customer\": str, \"invoice_number\": str, "
               "\"invoice_date\": \"YYYY-MM-DD\", \"due_date\": \"YYYY-MM-DD\" (current due date, "
               "after any extension), \"subtotal\": number (USD, after discounts, before tax), "
               "\"tax_rate_pct\": number (the rate on this invoice), \"total_due\": number "
               "(USD, subtotal plus tax)}")


def _money(x):
    return f"${x:,.2f}"


def _prose_date(d):
    return d.strftime("%B %-d, %Y")


def make_invoice(i, difficulty, seed=0):
    """One synthetic business invoice with known answers and optional distractors.
    difficulty 0 = clean, 1 = two distractors, 2 = four distractors + noise.
    Every distractor is a real number or date in the document, so a check that
    asks 'does this value appear in the source?' cannot catch it."""
    rng = random.Random(f"invoice|{seed}|{i}|{difficulty}")
    vendor = f"{rng.choice(V_ADJ)} {rng.choice(V_NOUN)}"
    customer = f"{rng.choice(C_ADJ)} {rng.choice(C_NOUN)}"
    number = f"INV-{rng.randrange(10000, 99999)}"
    issued = date(2026, 1, 5) + timedelta(days=rng.randrange(0, 280))
    due = issued + timedelta(days=rng.choice([15, 30, 45, 60]))
    subtotal = rng.randrange(50_000, 25_000_000) / 100
    rate = rng.randrange(16, 42) * 0.25
    total = round(subtotal * (1 + rate / 100), 2)
    truth = dict(vendor=vendor, customer=customer, invoice_number=number,
                 invoice_date=issued.isoformat(), due_date=due.isoformat(),
                 subtotal=subtotal, tax_rate_pct=rate, total_due=total)

    first = f"Invoice {number} from {vendor} to {customer}, dated {_prose_date(issued)}."
    s, distractors = [], {}
    pool = ["quote", "old_rate", "extension", "prior_invoice"]
    rng.shuffle(pool)
    chosen = set(pool[: {0: 0, 1: 2, 2: 4}[difficulty]])

    if "quote" in chosen:
        quote = round(subtotal + rng.randrange(2, 30) * 25, 2)
        s.append(f"The original quote was {_money(quote)}; after a loyalty discount the "
                 f"subtotal comes to {_money(subtotal)}.")
        distractors["subtotal"] = quote
    else:
        s.append(f"The subtotal is {_money(subtotal)}.")

    if "old_rate" in chosen:
        old = round(max(0.25, rate - rng.randrange(1, 8) * 0.25), 2)
        s.append(f"Last year’s orders were taxed at {old:.2f}%; this invoice applies sales tax "
                 f"of {rate:.2f}%.")
        distractors["tax_rate_pct"] = old
    else:
        s.append(f"Sales tax is charged at {rate:.2f}%.")

    s.append(f"The total amount due is {_money(total)}.")

    if "extension" in chosen:
        term = (due - issued).days  # the original due date must still fall after the invoice date
        orig = due - timedelta(days=rng.choice([d for d in (10, 15, 30) if d < term]))
        s.append(f"Payment was originally due {_prose_date(orig)}, but the vendor agreed to "
                 f"extend the due date to {_prose_date(due)}.")
        distractors["due_date"] = orig.isoformat()
    else:
        s.append(f"Payment is due by {_prose_date(due)}.")

    if "prior_invoice" in chosen:
        prev = f"INV-{rng.randrange(10000, 99999)}"
        s.append(f"Invoice {prev} from an earlier order remains unpaid and is not part of this bill.")
        distractors["invoice_number"] = prev

    if difficulty == 2:
        s.append(f"The customer’s credit limit with {vendor} is {_money(rng.randrange(20, 400) * 1000)}.")
        s.append(f"A late fee of {rng.choice([1.5, 2.0, 2.5])}% per month applies after the due date.")
    if difficulty >= 1:
        rng.shuffle(s)
    return dict(id=f"extract/d{difficulty}/{i:03d}", family="extract", difficulty=difficulty,
                doc=" ".join([first] + s), truth=truth, distractors=distractors)


def _parse_json(text):
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S) or re.search(r"(\{.*\})", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _values_in(doc):
    """Every dollar amount, percentage, date and invoice number stated in the document."""
    from datetime import datetime
    dollars = {round(float(a.replace(",", "")), 2) for a in re.findall(r"\$([\d,]+\.\d{2})", doc)}
    pcts = {round(float(p), 2) for p in re.findall(r"([\d.]+)%", doc)}
    dates = set()
    for m in re.finditer(r"([A-Z][a-z]+ \d{1,2}, \d{4})", doc):
        try:
            dates.add(datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat())
        except ValueError:
            pass
    numbers = set(re.findall(r"INV-\d{5}", doc))
    return dollars, pcts, dates, numbers


TOL = {"subtotal": 0.005, "total_due": 0.02, "tax_rate_pct": 1e-6}


def _same(k, got, want):
    try:
        if isinstance(want, (int, float)):
            return abs(float(got) - float(want)) <= TOL.get(k, 1e-9)
        return str(got).strip().lower() == str(want).strip().lower()
    except (TypeError, ValueError):
        return False


class ExtractFamily:
    name = "extract"
    system = ("You extract structured fields from business invoices. "
              "Reply with one JSON object only, inside a ```json code block.")

    def __init__(self, difficulties=(0, 1, 2)):
        self.difficulties = difficulties

    def load(self, n, seed=0):
        return [make_invoice(i, self.difficulties[i % len(self.difficulties)], seed)
                for i in range(n)]

    def first_prompt(self, task):
        return f"Invoice:\n\"\"\"\n{task['doc']}\n\"\"\"\n\nReturn JSON with this schema:\n{SCHEMA_HINT}"

    def retry_prompt(self, feedback):
        return (f"A validator rejected your JSON:\n{feedback}\n"
                "Re-read the invoice and reply with the full corrected JSON object.")

    def preview(self, task):
        t, n = task["truth"], len(task["distractors"])
        extra = "no distractors" if n == 0 else f"{n} distractors"
        return f"Pull 8 fields from {t['vendor']}’s invoice to {t['customer']}, {extra}"

    def diff(self, output, task):
        """Which fields were wrong, as {field: [model said, correct value]}."""
        obj = _parse_json(output)
        if obj is None:
            return {"answer": ["unreadable", "valid JSON"]}
        return {k: [obj.get(k), task["truth"][k]] for k in FIELDS
                if not _same(k, obj.get(k), task["truth"][k])}

    def check(self, output, task):
        """Production-style verifier: no answer key."""
        obj = _parse_json(output)
        if obj is None:
            return False, "Output is not a parseable JSON object.", 0.0
        issues = [f"missing field '{k}'" for k in FIELDS if k not in obj]
        if issues:
            return False, "; ".join(issues), 0.0
        try:
            sub, rate, total = float(obj["subtotal"]), float(obj["tax_rate_pct"]), float(obj["total_due"])
            date.fromisoformat(str(obj["invoice_date"])); date.fromisoformat(str(obj["due_date"]))
        except (TypeError, ValueError):
            return False, "amounts must be numbers and dates must be YYYY-MM-DD", 0.0
        if abs(sub * (1 + rate / 100) - total) > 0.02:
            issues.append("total_due does not equal subtotal plus tax")
        dollars, pcts, dates, numbers = _values_in(task["doc"])
        if round(sub, 2) not in dollars:
            issues.append("subtotal does not appear in the invoice")
        if round(rate, 2) not in pcts:
            issues.append("tax_rate_pct does not appear in the invoice")
        for k in ("invoice_date", "due_date"):
            if str(obj[k]) not in dates:
                issues.append(f"{k} does not match any date in the invoice")
        if str(obj["invoice_number"]).strip().upper() not in numbers:
            issues.append("invoice_number does not appear in the invoice")
        for k in ("vendor", "customer"):
            if str(obj[k]).strip().lower() not in task["doc"].lower():
                issues.append(f"{k} name does not appear in the invoice")
        return (not issues), "; ".join(issues), 0.0

    def grade(self, output, task, verified=None):
        obj = _parse_json(output)
        return obj is not None and all(_same(k, obj.get(k), task["truth"][k]) for k in FIELDS)

    def mock_output(self, task, ok, rng):
        """Failure modes for the offline mock, from most to least dangerous."""
        obj = dict(task["truth"])
        recompute = lambda o: round(o["subtotal"] * (1 + o["tax_rate_pct"] / 100), 2)
        if not ok:
            modes = ["inconsistent", "hallucinated", "bad_json"]
            if task["distractors"]:
                # the realistic, checker-proof failure: more tempting with more distractors
                modes = ["distractor"] * (1 + 2 * task["difficulty"]) + modes
            mode = rng.choice(modes)
            if mode == "bad_json":
                return "Here are the fields: vendor is " + obj["vendor"]
            if mode == "distractor":
                k = rng.choice(sorted(task["distractors"]))
                obj[k] = task["distractors"][k]
                obj["total_due"] = recompute(obj)
            elif mode == "inconsistent":
                obj["total_due"] = round(obj["total_due"] + rng.choice([-50, 25, 100]), 2)
            else:
                obj["subtotal"] = round(obj["subtotal"] + 125, 2)
                obj["total_due"] = recompute(obj)
        return "```json\n" + json.dumps(obj, indent=1) + "\n```"


FAMILIES = {"code": CodeFamily, "extract": ExtractFamily}
