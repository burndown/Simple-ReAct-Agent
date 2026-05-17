"""Single-shot wrapper around Ollama's chat endpoint.

This is the entire LLM interface: one pure function that takes a messages
list and returns the assistant's next text. No state, no side effects beyond
the HTTP call. The caller owns the messages list and decides what to do with
the returned text.
"""

import httpx

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.2:3b"


def chat(
    messages: list[dict],
    stop: list[str] | None = None,
    temperature: float = 0.0,
) -> str:
    """One round-trip to Ollama's /api/chat.

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
        "stream": False,
        "options": {"temperature": temperature},
    }
    if stop:
        payload["options"]["stop"] = stop

    response = httpx.post(OLLAMA_URL, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()["message"]["content"]
