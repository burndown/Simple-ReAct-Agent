"""Small wrapper around OpenAI's Responses API.

This is intentionally separate from llm.py, which uses Chat Completions.
Responses API has a different request/response shape and is not implemented by
every OpenAI-compatible provider.
"""

import json
import sys

import httpx

from llm import MODEL, OPENAI_API_KEY, OPENAI_BASE_URL, _env


PRINT_PROMPTS = (_env("PRINT_PROMPTS") or "").lower() in {"1", "true", "yes", "on"}


def _responses_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if base_url.endswith("/responses"):
        return base_url
    return f"{base_url}/responses"


def _print_payload(payload: dict) -> None:
    if not PRINT_PROMPTS:
        return
    print("\n=== responses payload ===", file=sys.stderr)
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
    print("=== end payload ===\n", file=sys.stderr)


def create_response(
    input_items: str | list[dict],
    instructions: str,
    tools: list[dict] | None = None,
    previous_response_id: str | None = None,
    temperature: float = 0.0,
) -> dict:
    """Create one Responses API response."""
    payload = {
        "model": MODEL,
        "instructions": instructions,
        "input": input_items,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id

    headers = {"Content-Type": "application/json"}
    if OPENAI_API_KEY:
        headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"

    _print_payload(payload)

    response = httpx.post(
        _responses_url(OPENAI_BASE_URL),
        headers=headers,
        json=payload,
        timeout=120,
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = response.text[:500]
        raise RuntimeError(
            f"responses request failed: {response.status_code} {response.reason_phrase} "
            f"for {_responses_url(OPENAI_BASE_URL)}: {detail}"
        ) from exc
    return response.json()

