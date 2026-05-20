"""Agent loop implemented with OpenAI's Responses API.

This module is a parallel implementation for comparison with react.py. It uses
Responses API output items instead of Chat Completions messages.
"""

from datetime import date

from responses_llm import create_response
from tools import dispatch, responses_tool_specs, tool_output_error, tool_output_ok


INSTRUCTIONS = f"""You are a helpful ReAct-style agent.
Current date: {date.today().isoformat()}.

Use the provided tools when they can answer part of the user's question more
reliably than memory. After tool results are returned, continue until you can
answer the user directly. Do not invent tool results.

Tool outputs are JSON objects. Treat {{"ok": true, "result": ...}} as success.
Treat {{"ok": false, "error": ...}} as error feedback and recover when possible.
"""


def _output_text(response: dict) -> str:
    if response.get("output_text"):
        return response["output_text"]

    parts = []
    for item in response.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    parts.append(content.get("text", ""))
    return "\n".join(part for part in parts if part).strip()


def _function_calls(response: dict) -> list[dict]:
    return [item for item in response.get("output", []) if item.get("type") == "function_call"]


def agent_turn(user_input: str, previous_response_id: str | None = None, max_steps: int = 8) -> tuple[str, str | None]:
    """Run one user turn with Responses API.

    Returns:
        (answer, latest_response_id). Pass latest_response_id into the next
        user turn to keep OpenAI-hosted conversation state.
    """
    next_input: str | list[dict] = user_input
    response_id = previous_response_id

    for step in range(1, max_steps + 1):
        response = create_response(
            next_input,
            instructions=INSTRUCTIONS,
            tools=responses_tool_specs(),
            previous_response_id=response_id,
        )
        response_id = response.get("id") or response_id

        calls = _function_calls(response)
        if not calls:
            print(f"  [step {step}] final")
            return _output_text(response), response_id

        print(f"  [step {step}] function_calls: {len(calls)}")
        tool_outputs = []
        for call in calls:
            name = call["name"]
            arguments = call.get("arguments", "{}")
            print(f"  [step {step}] tool: {name}({arguments})")

            try:
                output = tool_output_ok(name, dispatch(name, arguments))
            except Exception as exc:
                output = tool_output_error(name, exc)

            preview = output[:120] + ("..." if len(output) > 120 else "")
            print(f"  [step {step}] result: {preview}")

            tool_outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call["call_id"],
                    "output": output,
                }
            )

        next_input = tool_outputs

    return "(stopped: max_steps reached without final answer)", response_id
