"""Inner agent loop: one user turn -> OpenAI tool calls -> answer.

This is the heart of the agent. Every technique that makes ReAct work is here:

  1. SYSTEM_PROMPT tells the model when to use tools.
  2. chat() sends OpenAI function tool schemas with the conversation.
  3. The model may return one or more structured tool_calls.
  4. dispatch() runs each tool. Failures become tool outputs so the model can
     recover instead of crashing the loop.
  5. Tool outputs are appended as role="tool" messages with matching
     tool_call_id values.
  6. The turn ends when the model returns a normal assistant message with no
     tool_calls.
"""

from datetime import date

from llm import chat
from tools import dispatch, tool_output_error, tool_output_ok, tool_specs


SYSTEM_PROMPT = f"""You are a helpful ReAct-style agent.
Current date: {date.today().isoformat()}.

Use the provided tools when they can answer part of the user's question more
reliably than memory. After tool results are returned, continue until you can
answer the user directly. Do not invent tool results.

Tool outputs are JSON objects. Treat {{"ok": true, "result": ...}} as success.
Treat {{"ok": false, "error": ...}} as error feedback and recover when possible.
"""


def _assistant_message(message: dict) -> dict:
    """Keep only fields that are valid to send back in chat history."""
    result = {"role": "assistant", "content": message.get("content")}
    if message.get("tool_calls"):
        result["tool_calls"] = message["tool_calls"]
    if message.get("reasoning_content"):
        result["reasoning_content"] = message["reasoning_content"]
    return result


def agent_turn(messages: list[dict], max_steps: int = 8) -> str:
    """Run the inner tool-calling loop for one user turn.

    Mutates `messages` in place by appending:
      - assistant messages, possibly with tool_calls,
      - tool messages with tool outputs,
      - the final assistant message containing the user-facing answer.

    Returns the final answer string for the REPL to print.
    """
    for step in range(1, max_steps + 1):
        reply = chat(messages, tools=tool_specs())
        messages.append(_assistant_message(reply))

        tool_calls = reply.get("tool_calls") or []
        if not tool_calls:
            answer = reply.get("content") or ""
            print(f"  [step {step}] final")
            return answer.strip()

        print(f"  [step {step}] tool_calls: {len(tool_calls)}")
        for tool_call in tool_calls:
            name = tool_call["function"]["name"]
            arguments = tool_call["function"].get("arguments", "{}")
            print(f"  [step {step}] tool: {name}({arguments})")

            try:
                output = tool_output_ok(name, dispatch(name, arguments))
            except Exception as exc:
                output = tool_output_error(name, exc)

            preview = output[:120] + ("..." if len(output) > 120 else "")
            print(f"  [step {step}] result: {preview}")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": output,
                }
            )

    return "(stopped: max_steps reached without final answer)"
