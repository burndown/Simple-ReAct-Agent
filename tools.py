"""Tool functions the ReAct agent can call.

Each tool is a plain Python function that takes a string arg and returns a
string result. A single `TOOLS` dict is the source of truth for the dispatcher
and the system prompt — adding a tool is one entry.

`finish` is intentionally not a tool: it's a sentinel handled in react.agent_turn.
"""

import ast
import operator

from ddgs import DDGS


# --- calculate: safe arithmetic via AST walk --------------------------------
# We use an AST walk instead of eval() because the LLM produces the expression
# from arbitrary text — eval() would be a remote code execution vector.

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"unsupported expression node: {type(node).__name__}")


def calculate(expression: str) -> str:
    """Evaluate a numeric expression. Whitelisted operators only."""
    tree = ast.parse(expression.strip(), mode="eval")
    return str(_eval_node(tree.body))


# --- web_search: DuckDuckGo snippets, no key required -----------------------
# Returns top-N snippets (title + body) for a query. Body is the search
# snippet, not the full page — token-cheap by design. We cap per-result body
# length so a verbose snippet can't blow up the context window.

_WEB_MAX_RESULTS = 2
_WEB_BODY_CAP = 200


def web_search(query: str) -> str:
    """Return top web snippets for a query via DuckDuckGo."""
    try:
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=_WEB_MAX_RESULTS))
    except Exception as exc:
        return f"search failed: {exc}"
    if not hits:
        return f"no results for '{query}'."
    lines = []
    for hit in hits:
        body = hit.get("body", "")[:_WEB_BODY_CAP].rsplit(" ", 1)[0] + "..."
        lines.append(f"- {hit.get('title', '')}: {body}")
    return "\n".join(lines)


# --- dispatch table: name -> (callable, doc) --------------------------------

TOOLS: dict[str, tuple] = {
    "calculate":  (calculate,  "calculate[expression]  - evaluate a math expression. Example: calculate[2**10 + 1889]"),
    "web_search": (web_search, "web_search[query]      - top web snippets via DuckDuckGo. Example: web_search[Eiffel Tower height]"),
}


def docs() -> str:
    """Tool list rendered for the system prompt."""
    lines = [f"- {doc}" for _, doc in TOOLS.values()]
    lines.append("- finish[answer]            - return the final answer and stop. Example: finish[42]")
    return "\n".join(lines)


def dispatch(name: str, arg: str) -> str:
    """Run a tool by name. Raises ValueError on unknown; tool exceptions propagate."""
    if name not in TOOLS:
        known = sorted(TOOLS) + ["finish"]
        raise ValueError(f"unknown action {name!r}; known: {known}")
    fn, _doc = TOOLS[name]
    return fn(arg)
