"""Inner ReAct loop: one user turn -> Thought/Action/Observation cycles -> answer.

This is the heart of the agent. Every technique that makes ReAct work is here:

  1. SYSTEM_PROMPT tells the model the output format and tool list.
  2. chat() is called with stop=["Observation:"] so the model writes exactly
     one Action and then halts (server-side stop sequence).
  3. parse_action() pulls the first `Action: name[arg]` out of the reply
     (client-side stop, in case the model overshoots the server stop).
  4. dispatch() runs the tool. Failures become Observation: Error from ...
     messages so the model can react instead of crashing the loop.
  5. The Observation is appended as a user message, matching the original
     ReAct paper convention (works on models not trained for the tool role).
  6. `finish[answer]` is the sentinel action that ends the turn.
"""

import re

from llm import chat
from tools import dispatch, docs


SYSTEM_PROMPT = f"""You are a ReAct agent. Answer questions by interleaving short Thoughts and Actions.

Available actions:
{docs()}

OUTPUT FORMAT (every assistant message must follow this exactly):
Thought: <one short sentence of reasoning>
Action: <action_name>[<input>]

After writing one Action, STOP. The environment will reply with an Observation as a user message. Then continue with another Thought / Action. When you have the final answer, use finish[...].

If a tool can answer part of a question, use it first instead of answering from memory.

If an Observation starts with "Error from", treat it as feedback: analyze what went wrong and try a different Action. Do not finish[Error] on the first failure.
"""


# Matches the first `Action: name[arg]`. DOTALL lets [arg] span newlines.
ACTION_RE = re.compile(r"Action:\s*(\w+)\s*\[(.*?)\]", re.DOTALL)


def parse_action(text: str) -> tuple[str, str | None, str | None]:
    """Split an assistant reply into (thought, action_name, action_arg).

    Returns (text, None, None) when no Action is found — the caller treats
    that as the final answer (model decided to talk instead of act).
    """
    match = ACTION_RE.search(text)
    if not match:
        return text.strip(), None, None
    thought = text[: match.start()]
    thought = re.sub(r"^\s*Thought:\s*", "", thought, count=1).strip()
    return thought, match.group(1), match.group(2).strip()


def agent_turn(messages: list[dict], max_steps: int = 8) -> str:
    """Run the inner ReAct loop for one user turn.

    Mutates `messages` in place by appending:
      - assistant messages (Thought + Action),
      - user messages with content "Observation: ...",
      - the final assistant message containing the user-facing answer.

    Returns the final answer string for the REPL to print.
    """
    for step in range(1, max_steps + 1):
        reply = chat(messages, stop=["Observation:"])
        messages.append({"role": "assistant", "content": reply})

        thought, action, arg = parse_action(reply)
        print(f"  [step {step}] thought: {thought}")

        if action is None:
            print(f"  [step {step}] (no action - using reply as final)")
            return thought or reply.strip()

        print(f"  [step {step}] action:  {action}[{arg}]")

        if action == "finish":
            return arg

        try:
            observation = dispatch(action, arg)
        except Exception as exc:
            observation = f"Error from {action}: {exc}"

        preview = observation[:120] + ("..." if len(observation) > 120 else "")
        print(f"  [step {step}] observ:  {preview}")

        messages.append({"role": "user", "content": f"Observation: {observation}"})

    return "(stopped: max_steps reached without finish)"
