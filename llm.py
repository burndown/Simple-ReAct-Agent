"""Single-shot wrapper around an OpenAI-compatible chat endpoint.

This is the entire LLM interface: one pure function that takes a messages
list and returns the assistant's next text. No state, no side effects beyond
the HTTP call. The caller owns the messages list and decides what to do with
the returned text.
"""

import os
from pathlib import Path

import httpx


def _load_dotenv(path: str = ".env") -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        return {}

    values = {}
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("set -x "):
            parts = line.split(maxsplit=3)
            if len(parts) == 4:
                values[parts[2]] = parts[3].strip("\"'")
            continue

        if line.startswith("export "):
            line = line.removeprefix("export ").strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


DOTENV = _load_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name) or DOTENV.get(name) or default


OPENAI_BASE_URL = _env("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = _env("OPENAI_API_KEY")
MODEL = _env("OPENAI_MODEL") or _env("MODEL", "gpt-4o-mini")


def _chat_completions_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def chat(
    messages: list[dict],
    stop: list[str] | None = None,
    temperature: float = 0.0,
) -> str:
    """One round-trip to an OpenAI-compatible /chat/completions endpoint.

    Args:
        messages: list of {"role": "system"|"user"|"assistant", "content": str}.
        stop: server-side stop sequences. Generation halts before emitting any.
        temperature: 0.0 = deterministic. Bump for variety.

    Returns:
        The assistant's text content for this call.
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if stop:
        payload["stop"] = stop

    headers = {"Content-Type": "application/json"}
    if OPENAI_API_KEY:
        headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"

    response = httpx.post(
        _chat_completions_url(OPENAI_BASE_URL),
        headers=headers,
        json=payload,
        timeout=120,
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = response.text[:500]
        raise RuntimeError(
            f"chat request failed: {response.status_code} {response.reason_phrase} "
            f"for {_chat_completions_url(OPENAI_BASE_URL)}: {detail}"
        ) from exc
    return response.json()["choices"][0]["message"]["content"]
