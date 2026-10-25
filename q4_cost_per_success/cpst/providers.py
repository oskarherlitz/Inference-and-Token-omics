"""Metered model clients.

The teammate's q5_harness clients measure latency. CPST needs dollars, so
these clients record what a bill is actually made of:

  fresh_in     input tokens billed at the full rate
  cached_in    input tokens read from the prompt cache (often 10x cheaper)
  cache_write  input tokens written to the cache (often pricier than fresh)
  out          output tokens
  cost_usd     the provider's own reported cost when available (OpenRouter
               returns usage.cost on every response), otherwise list prices

Models are declared in models.json so prices live in one place.
"""
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path

REGISTRY = Path(__file__).with_name("models.json")


@dataclass
class Metered:
    text: str
    fresh_in: int
    cached_in: int
    cache_write: int
    out: int
    cost_usd: float
    cost_source: str  # "provider" or "list"
    model_s: float


def list_cost(price, fresh_in, cached_in, cache_write, out):
    """Dollar cost from $/M-token list prices."""
    return (fresh_in * price["in"] + cached_in * price.get("cached_in", price["in"])
            + cache_write * price.get("cache_write", price["in"]) + out * price["out"]) / 1e6


def usage_from_anthropic(resp, price):
    """(fresh_in, cached_in, cache_write, out, cost_usd, cost_source) from an Anthropic response."""
    u = resp.usage
    fresh, cr = u.input_tokens, getattr(u, "cache_read_input_tokens", 0) or 0
    cw, out = getattr(u, "cache_creation_input_tokens", 0) or 0, u.output_tokens
    return fresh, cr, cw, out, list_cost(price, fresh, cr, cw, out), "list"


def usage_from_openai(resp, price):
    """Same tuple from an OpenAI-compatible response. Prefers OpenRouter's usage.cost."""
    u = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
    details = u.get("prompt_tokens_details") or {}
    cached, cw = details.get("cached_tokens") or 0, details.get("cache_write_tokens") or 0
    prompt, out = u.get("prompt_tokens") or 0, u.get("completion_tokens") or 0
    fresh = max(prompt - cached - cw, 0)
    if u.get("cost") is not None:
        return fresh, cached, cw, out, float(u["cost"]), "provider"
    return fresh, cached, cw, out, list_cost(price, fresh, cached, cw, out) if price else 0.0, "list"


def load_registry(path=REGISTRY):
    return {k: v for k, v in json.loads(Path(path).read_text()).items() if not k.startswith("_")}


class AnthropicMetered:
    """Direct Anthropic API. Needs ANTHROPIC_API_KEY. With cache=True the system
    prompt and the task prompt are marked cacheable, so retries re-read them
    from cache (only if they exceed the model's minimum cacheable length)."""

    def __init__(self, model_id, price, max_tokens=2048, temperature=1.0, cache=True, **_):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model_id, self.price, self.cache = model_id, price, cache
        self.max_tokens, self.temperature = max_tokens, temperature

    def complete(self, messages, system=None, **_):
        msgs = [dict(m) for m in messages]
        sys_arg = system
        if self.cache:
            if system:
                sys_arg = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
            msgs[0] = {"role": "user", "content": [{"type": "text", "text": msgs[0]["content"],
                                                    "cache_control": {"type": "ephemeral"}}]}
        kw = dict(model=self.model_id, max_tokens=self.max_tokens,
                  temperature=self.temperature, messages=msgs)
        if sys_arg:
            kw["system"] = sys_arg
        t0 = time.perf_counter()
        r = self.client.messages.create(**kw)
        dt = time.perf_counter() - t0
        text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        return Metered(text, *usage_from_anthropic(r, self.price), dt)


class OpenAICompatMetered:
    """OpenRouter (default) or any OpenAI-compatible endpoint.
    OpenRouter: set OPENROUTER_API_KEY. Others: OPENAI_API_KEY + OPENAI_BASE_URL."""

    def __init__(self, model_id, price, provider="openrouter", max_tokens=2048,
                 temperature=1.0, effort=None, **_):
        import openai
        if provider == "openrouter":
            self.client = openai.OpenAI(base_url="https://openrouter.ai/api/v1",
                                        api_key=os.environ.get("OPENROUTER_API_KEY"))
        else:
            self.client = openai.OpenAI(base_url=os.environ.get("OPENAI_BASE_URL"))
        self.provider, self.model_id, self.price, self.effort = provider, model_id, price, effort
        self.max_tokens, self.temperature = max_tokens, temperature

    def complete(self, messages, system=None, session_id=None, **_):
        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        extra = {}
        if self.provider == "openrouter":
            if session_id:
                extra["session_id"] = session_id  # sticky routing keeps the prompt cache warm
            if self.effort:
                extra["reasoning"] = {"effort": self.effort}  # thinking depth is a cost lever
        extra = extra or None
        t0 = time.perf_counter()
        r = self.client.chat.completions.create(
            model=self.model_id, messages=msgs, max_tokens=self.max_tokens,
            temperature=self.temperature, extra_body=extra)
        dt = time.perf_counter() - t0
        return Metered(r.choices[0].message.content or "", *usage_from_openai(r, self.price), dt)


class MockMetered:
    """Offline stand-in. Skill falls with task difficulty and rises with
    verifier feedback; outputs come from the family so the real verifier and
    grader run on them. Deterministic per (model, task, attempt, turn).
    Numbers are invented: they demonstrate the pipeline, not the market."""

    def __init__(self, model_id, price, skill=0.8, out_tokens=300, seed=0, **_):
        self.model_id, self.price, self.skill = model_id, price, skill
        self.out_tokens, self.seed = out_tokens, seed

    def complete(self, messages, system=None, task=None, family=None, attempt=0, **_):
        turn = len(messages) // 2
        rng = random.Random(f"{self.seed}|{self.model_id}|{task['id']}|{attempt}|{turn}")
        p = self.skill ** (1 + 0.8 * task.get("difficulty", 1))
        p = p + (1 - p) * 0.25 * turn      # feedback from the verifier helps, a little
        text = family.mock_output(task, rng.random() < p, rng)
        prompt_tok = (len(system or "") + sum(len(str(m["content"])) for m in messages)) // 4
        first_tok = (len(system or "") + len(str(messages[0]["content"]))) // 4
        cached = first_tok if turn > 0 else 0        # retries re-read the stable prefix
        cw = first_tok if turn == 0 else 0
        out = max(20, int(rng.gauss(self.out_tokens, self.out_tokens * 0.2)))
        fresh = prompt_tok - cached - cw
        return Metered(text, fresh, cached, cw, out,
                       list_cost(self.price, fresh, cached, cw, out), "list",
                       0.4 + out / rng.uniform(60, 140))


def make_client(name, registry=None, **kw):
    reg = registry or load_registry()
    if name not in reg:
        raise SystemExit(f"Unknown model '{name}'. Add it to {REGISTRY.name}; known: {sorted(reg)}")
    spec = dict(reg[name])
    provider = spec.pop("provider")
    cls = {"anthropic": AnthropicMetered, "openrouter": OpenAICompatMetered,
           "openai": OpenAICompatMetered, "mock": MockMetered}[provider]
    if cls is OpenAICompatMetered:
        spec["provider"] = provider
    return cls(**spec, **kw)
