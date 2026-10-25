"""Model clients. Each returns a CallResult with measured timings and token counts.

Timings are measured with streaming so latency can be split into
time-to-first-token (prefill + queueing + network) and decode time.
"""
import os
import random
import time
from dataclasses import dataclass


@dataclass
class CallResult:
    text: str
    input_tokens: int
    output_tokens: int
    ttft_s: float        # time to first token
    total_s: float       # full model call wall-clock


class AnthropicClient:
    def __init__(self, model, max_tokens=2048, temperature=1.0):
        import anthropic  # pip install anthropic ; needs ANTHROPIC_API_KEY
        self.client = anthropic.Anthropic()
        self.model, self.max_tokens, self.temperature = model, max_tokens, temperature

    def complete(self, messages, system=None):
        t0 = time.perf_counter()
        ttft = None
        chunks = []
        kwargs = dict(model=self.model, max_tokens=self.max_tokens,
                      messages=messages)
        if system:
            kwargs["system"] = system
        with self.client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                if ttft is None:
                    ttft = time.perf_counter() - t0
                chunks.append(text)
            final = stream.get_final_message()
        total = time.perf_counter() - t0
        return CallResult("".join(chunks), final.usage.input_tokens,
                          final.usage.output_tokens, ttft or total, total)


class OpenAICompatClient:
    """Works with OpenAI, OpenRouter, Together, Fireworks, vLLM, etc.
    Set OPENAI_API_KEY and optionally OPENAI_BASE_URL."""

    def __init__(self, model, max_tokens=2048, temperature=1.0):
        import openai  # pip install openai
        self.client = openai.OpenAI(base_url=os.environ.get("OPENAI_BASE_URL"))
        self.model, self.max_tokens, self.temperature = model, max_tokens, temperature

    def complete(self, messages, system=None):
        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        t0 = time.perf_counter()
        ttft, chunks, usage = None, [], None
        # stream_options is OpenAI-native; some compatible endpoints reject it.
        # Try with usage first, fall back silently if the endpoint refuses.
        for kwargs in (
            {"stream_options": {"include_usage": True}},
            {},
        ):
            try:
                stream = self.client.chat.completions.create(
                    model=self.model, messages=msgs, max_tokens=self.max_tokens,
                    temperature=self.temperature, stream=True, **kwargs)
                for ev in stream:
                    if ev.choices and ev.choices[0].delta.content:
                        if ttft is None:
                            ttft = time.perf_counter() - t0
                        chunks.append(ev.choices[0].delta.content)
                    if getattr(ev, "usage", None):
                        usage = ev.usage
                break  # success
            except Exception:
                if not kwargs:
                    raise  # both attempts failed; propagate
                t0 = time.perf_counter()
                ttft, chunks, usage = None, [], None
        total = time.perf_counter() - t0
        text = "".join(chunks)
        in_tok = usage.prompt_tokens if usage else sum(len(m["content"]) // 4 for m in msgs)
        out_tok = usage.completion_tokens if usage else len(text) // 4
        return CallResult(text, in_tok, out_tok, ttft or total, total)


class MockClient:
    """Offline stand-in for dry runs. Returns the canonical-ish answer with
    some probability, otherwise a broken one; simulates realistic timings
    without sleeping. Lets you test the whole pipeline with no API key."""

    def __init__(self, model="mock", p_correct=0.45, seed=None, **_):
        self.p = p_correct
        self.rng = random.Random(seed)

    def complete(self, messages, system=None):
        prompt = messages[0]["content"]
        turn = len(messages) // 2  # later turns (with feedback) do a bit better
        ok = self.rng.random() < min(0.95, self.p + 0.15 * turn)
        sig = next((l for l in prompt.splitlines() if l.startswith("def ")), "def f():")
        body = "    return __SOLUTION__" if ok else "    raise NotImplementedError"
        out_tok = self.rng.randint(80, 400)
        in_tok = sum(len(m["content"]) for m in messages) // 4
        ttft = self.rng.uniform(0.3, 1.2)
        decode = out_tok / self.rng.uniform(50, 120)
        return CallResult(f"```python\n{sig}\n{body}\n```", in_tok, out_tok,
                          ttft, ttft + decode)


def make_client(provider, model, **kw):
    return {"anthropic": AnthropicClient, "openai": OpenAICompatClient,
            "mock": MockClient}[provider](model=model, **kw)
