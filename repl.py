"""Multi-turn REPL outer loop.

Holds the conversation history across user turns so follow-ups can refer back
to earlier context. Each user input triggers one `agent_turn`, which extends
the messages list with its full Thought/Action/Observation trace plus the
final answer.

Operational commands (handled here, not seen by the model):
  quit / exit  - leave
  /clear       - clear history (keep system prompt)
  /history     - dump the current messages list
"""

from react import SYSTEM_PROMPT, agent_turn


BANNER = """ReAct agent (OpenAI function calling).
Type a question. Multi-turn: each follow-up sees the full prior conversation.
Commands: 'quit' or Ctrl-D to exit, '/clear' to clear history, '/history' to dump messages."""


def main() -> None:
    print(BANNER)
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user = input("\nuser> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not user:
            continue
        if user.lower() in {"quit", "exit"}:
            return
        if user.lower() == "/clear":
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            print("(history cleared)")
            continue
        if user.lower() == "/history":
            for i, m in enumerate(messages):
                preview = str(m.get("content", "")).replace("\n", " ")[:100]
                print(f"  [{i}] {m['role']:9} {preview}")
            continue

        messages.append({"role": "user", "content": user})
        answer = agent_turn(messages)
        print(f"\nassistant> {answer}")


if __name__ == "__main__":
    main()
