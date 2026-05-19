"""Single-shot wrapper around an OpenAI-compatible chat endpoint.

This is the entire LLM interface: one pure function that takes a messages
list and returns the assistant's next message. No state, no side effects
beyond the HTTP call. The caller owns the messages list and decides what to do
with returned text or tool calls.
"""

import os
import sys
import json
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
PRINT_PROMPTS = (_env("PRINT_PROMPTS") or "").lower() in {"1", "true", "yes", "on"}


def _chat_completions_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def _print_payload(payload: dict) -> None:
    if not PRINT_PROMPTS:
        return
    print("\n=== chat.completions payload ===", file=sys.stderr)
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
    print("=== end payload ===\n", file=sys.stderr)


def chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    temperature: float = 0.0,
) -> dict:
    """One round-trip to an OpenAI-compatible /chat/completions endpoint.

    Args:
        messages: chat history, including system/user/assistant/tool messages.
        tools: optional OpenAI function tool schemas.
        temperature: 0.0 = deterministic. Bump for variety.

    Returns:
        The assistant message, which may contain content and/or tool_calls.
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    headers = {"Content-Type": "application/json"}
    if OPENAI_API_KEY:
        headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"

    _print_payload(payload)

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
    return response.json()["choices"][0]["message"]
