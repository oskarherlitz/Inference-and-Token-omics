"""Offline checks. Run: python -m pytest tests -q   (from the cpst/ folder)"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import policies as P  # noqa: E402
from families import ExtractFamily  # noqa: E402
from providers import usage_from_anthropic, usage_from_openai  # noqa: E402


def test_openrouter_usage_prefers_reported_cost():
    from openai.types.chat import ChatCompletion
    resp = ChatCompletion.model_validate({
        "id": "x", "object": "chat.completion", "created": 0, "model": "deepseek/deepseek-v4-flash",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "hi"}}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200, "cost": 0.00042,
                  "prompt_tokens_details": {"cached_tokens": 700, "cache_write_tokens": 100}}})
    fresh, cached, cw, out, cost, src = usage_from_openai(resp, {"in": 1, "out": 1})
    assert (fresh, cached, cw, out, src) == (200, 700, 100, 200, "provider")
    assert abs(cost - 0.00042) < 1e-12


def test_openai_usage_falls_back_to_list_price():
    from openai.types.chat import ChatCompletion
    resp = ChatCompletion.model_validate({
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "hi"}}],
        "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000, "total_tokens": 2_000_000}})
    *_, cost, src = usage_from_openai(resp, {"in": 2.0, "out": 10.0})
    assert src == "list" and abs(cost - 12.0) < 1e-9


def test_anthropic_usage_prices_cache_separately():
    from anthropic.types import Message
    msg = Message.model_validate({
        "id": "x", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
        "content": [{"type": "text", "text": "hi"}], "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 1_000_000, "output_tokens": 0,
                  "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 0}})
    *_, cost, _ = usage_from_anthropic(msg, {"in": 2.0, "cached_in": 0.10, "out": 10.0})
    assert abs(cost - 2.10) < 1e-9


def test_extract_truth_passes_and_distractors_fool_the_checker():
    fam = ExtractFamily()
    fooled = 0
    for t in fam.load(30, seed=3):
        good = "```json\n" + json.dumps(t["truth"]) + "\n```"
        assert fam.check(good, t)[0] and fam.grade(good, t)
        for k, v in t["distractors"].items():
            obj = dict(t["truth"], **{k: v})
            obj["total_due"] = round(obj["subtotal"] * (1 + obj["tax_rate_pct"] / 100), 2)
            out = "```json\n" + json.dumps(obj) + "\n```"
            assert not fam.grade(out, t)
            fooled += fam.check(out, t)[0]
    assert fooled > 0  # the verifier cannot catch every plausible wrong answer


def test_cascade_replay_counts_waste_and_escalation():
    mk = lambda it, v, c, cost: dict(iter=it, verified=v, correct=c, cost_usd=cost,
                                     fresh_in=0, cached_in=0, cache_write=0, out=0)
    traces = {("cheap", "t1", 0): [mk(0, False, False, 0.01), mk(1, False, False, 0.01)],
              ("big", "t1", 0): [mk(0, True, True, 0.50)]}
    o = P.replay(traces, [("cheap", 2), ("big", 1)], "t1", 0)
    assert o["correct"] and o["escalated"] and abs(o["cost"] - 0.52) < 1e-12
    assert abs(o["waste"] - 0.02) < 1e-12
    s = P.summarize([o, P.replay(traces, [("cheap", 2)], "t1", 0)])
    assert s["n_correct"] == 1 and abs(s["cpst"] - 0.54) < 1e-12


def test_diff_names_the_wrong_field_and_previews_read_well():
    fam = ExtractFamily()
    t = next(x for x in fam.load(10, seed=2) if x["distractors"])
    k, v = next(iter(t["distractors"].items()))
    out = "```json\n" + json.dumps(dict(t["truth"], **{k: v})) + "\n```"
    assert k in fam.diff(out, t)
    assert fam.diff("```json\n" + json.dumps(t["truth"]) + "\n```", t) == {}
    assert fam.preview(t).startswith("Pull 8 fields from")
