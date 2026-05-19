"""Multi-turn REPL using OpenAI's Responses API.

Run this file when you want to compare Responses API behavior with the default
Chat Completions implementation in repl.py.
"""

from responses_agent import agent_turn


BANNER = """ReAct agent (OpenAI Responses API).
Type a question. Multi-turn: follow-ups use previous_response_id.
Commands: 'quit' or Ctrl-D to exit, '/clear' to clear hosted state."""


def main() -> None:
    print(BANNER)
    previous_response_id: str | None = None

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
            previous_response_id = None
            print("(hosted state cleared)")
            continue

        answer, previous_response_id = agent_turn(user, previous_response_id)
        print(f"\nassistant> {answer}")


if __name__ == "__main__":
    main()

