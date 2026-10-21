"""Shared Claude client.

Model: claude-opus-5-5 by default (override with CAREERPILOT_MODEL).
Refusals: server-side `fallbacks: "default"` re-runs a declined request on
Anthropic's recommended fallback model inside the same call.
"""
import os

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def model():
    return os.environ.get("CAREERPILOT_MODEL") or os.environ.get("JHB_MODEL") or "claude-opus-5-5"


def available():
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.environ.get("ANTHROPIC_PROFILE"))


_client = None


def client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    return _client


def create(messages, system=None, tools=None, max_tokens=16000, effort="medium"):
    kwargs = dict(model=model(), max_tokens=max_tokens, messages=messages,
                  betas=[FALLBACK_BETA], fallbacks="default",
                  thinking={"type": "adaptive"}, output_config={"effort": effort})
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = tools
    return client().beta.messages.create(**kwargs)


def text_of(response):
    if response.stop_reason == "refusal":
        cat = getattr(response.stop_details, "category", None) if response.stop_details else None
        return f"(Claude declined this request{f' — category: {cat}' if cat else ''}.)"
    return "".join(b.text for b in response.content if b.type == "text").strip()


def ask(prompt, system=None, max_tokens=16000, effort="medium"):
    return text_of(create([{"role": "user", "content": prompt}], system=system, max_tokens=max_tokens, effort=effort))
