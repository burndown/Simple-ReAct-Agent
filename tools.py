"""Tool functions the agent can call through OpenAI function calling.

Each tool is a plain Python function with string arguments and a string result.
A single `TOOLS` dict is the source of truth for both the OpenAI tool schema
and the dispatcher.
"""

import ast
import json
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


# --- dispatch table: name -> metadata ---------------------------------------

TOOLS: dict[str, dict] = {
    "calculate": {
        "fn": calculate,
        "description": "Evaluate a numeric expression using whitelisted arithmetic operators.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "A numeric expression, for example: 2**10 + 1889.",
                },
            },
            "required": ["expression"],
            "additionalProperties": False,
        },
    },
    "web_search": {
        "fn": web_search,
        "description": "Return top web snippets for a search query via DuckDuckGo.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The web search query.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


def tool_specs() -> list[dict]:
    """OpenAI Chat Completions tool schemas."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": meta["description"],
                "parameters": meta["parameters"],
            },
        }
        for name, meta in TOOLS.items()
    ]


def responses_tool_specs() -> list[dict]:
    """OpenAI Responses API tool schemas."""
    return [
        {
            "type": "function",
            "name": name,
            "description": meta["description"],
            "parameters": meta["parameters"],
        }
        for name, meta in TOOLS.items()
    ]


def dispatch(name: str, arguments: str | dict) -> str:
    """Run a tool by name using JSON arguments from an OpenAI tool call."""
    if name not in TOOLS:
        known = sorted(TOOLS)
        raise ValueError(f"unknown action {name!r}; known: {known}")

    if isinstance(arguments, str):
        arguments = json.loads(arguments or "{}")
    if not isinstance(arguments, dict):
        raise ValueError(f"tool arguments must be an object, got {type(arguments).__name__}")

    fn = TOOLS[name]["fn"]
    return fn(**arguments)
