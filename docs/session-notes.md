# Session Notes: Simple ReAct Agent

Date: 2026-05-19

## Goal

Convert a minimal Ollama-based ReAct demo into an OpenAI-compatible agent demo,
then evolve it from text-based `Action: tool[arg]` parsing to structured OpenAI
function calling.

## Current State

The project now has two independent agent paths:

- `python -m repl` uses Chat Completions with structured function calling.
- `python -m responses_repl` is a separate OpenAI Responses API comparison
  path.

The default path remains Chat Completions because it is compatible with OpenAI
and many OpenAI-compatible providers, including DeepSeek's chat endpoint.

## Main Changes

- Replaced Ollama `/api/chat` calls with OpenAI-compatible
  `/chat/completions`.
- Added `.env` loading with support for `KEY=value`, `export KEY=value`, and
  fish-style `set -x KEY value`.
- Added `OPENAI_MODEL`, `OPENAI_BASE_URL`, and `OPENAI_API_KEY` configuration.
- Added `PRINT_PROMPTS=1` to print each outgoing request payload without
  printing authorization headers.
- Replaced text-based ReAct action parsing with OpenAI function calling.
- Added structured tool schemas for `calculate` and `web_search`.
- Added `role: tool` result messages with matching `tool_call_id`.
- Preserved DeepSeek `reasoning_content` in assistant history when present.
- Added a separate Responses API implementation without replacing the default
  Chat Completions implementation.

## Default Chat Completions Flow

The default runtime uses local `messages` history.

```text
user input
  -> append role=user
  -> send messages + tools to /chat/completions
  -> model returns assistant tool_calls
  -> append assistant message with tool_calls
  -> execute local tool
  -> append role=tool with tool_call_id and output
  -> call model again
  -> no tool_calls means final answer
```

Tool results must be placed back into `messages`:

```json
{
  "role": "tool",
  "tool_call_id": "call_...",
  "content": "300"
}
```

The `tool_call_id` must match the previous assistant tool call ID.

## Responses API Flow

The optional Responses API path uses `/v1/responses`.

Instead of resending all local `messages`, it can continue state with
`previous_response_id`:

```text
input: "100 + 200"
previous_response_id: null
=> resp_1

input: function_call_output
previous_response_id: resp_1
=> resp_2

input: "divide that by 5"
previous_response_id: resp_2
=> resp_3
```

Each turn should use the latest response ID, not the first response ID.

Tool output is returned as a Responses input item:

```json
{
  "type": "function_call_output",
  "call_id": "call_...",
  "output": "300"
}
```

## DeepSeek Compatibility

DeepSeek supports an OpenAI-compatible Chat Completions endpoint:

```text
https://api.deepseek.com/chat/completions
```

Use the default path for DeepSeek:

```bash
python -m repl
```

DeepSeek's public docs currently describe Chat Completions and function calling
there, not OpenAI's `/responses` endpoint. The Responses API path should be
used with OpenAI unless the provider explicitly supports `/responses`.

DeepSeek may return `reasoning_content` in thinking mode. If present, the next
request must preserve it in the assistant message history.

## Prompt Construction

In the Chat Completions path, the request payload contains:

- `messages`: system prompt, user messages, assistant messages, tool result
  messages, and final answers.
- `tools`: JSON schemas for available functions.
- `tool_choice: "auto"`: lets the model decide whether to call a tool.
- `temperature`: defaults to `0.0`.

The system prompt is intentionally small:

```text
You are a helpful ReAct-style agent.
Current date: YYYY-MM-DD.

Use the provided tools when they can answer part of the user's question more
reliably than memory. After tool results are returned, continue until you can
answer the user directly. Do not invent tool results.
```

Tool definitions are not embedded as text in the system prompt anymore. They
are sent through the API's `tools` field.

## Important Concepts

### ReAct

ReAct means reasoning plus acting. The model decides when to call tools, the
runtime executes those tools, and tool results are sent back so the model can
continue.

With function calling, the old text format:

```text
Action: calculate[100 + 200]
```

becomes structured:

```json
{
  "name": "calculate",
  "arguments": "{\"expression\":\"100 + 200\"}"
}
```

### Function Calling vs ReAct

ReAct is the agent loop pattern. Function calling is the structured interface
used to request tool execution reliably.

### Modern Agents

Production agents are rarely pure ReAct. They usually combine:

- ReAct execution loops
- planning
- structured tool calling
- retrieval
- memory
- validation
- tracing
- permission checks
- prompt-injection defenses

## Debugging

Print outgoing Chat Completions or Responses payloads:

```bash
PRINT_PROMPTS=1 python -m repl
```

fish:

```fish
set -x PRINT_PROMPTS 1
python -m repl
```

Disable:

```fish
set -e PRINT_PROMPTS
```

## Current Files

- `llm.py`: Chat Completions HTTP wrapper.
- `react.py`: default Chat Completions tool-call loop.
- `repl.py`: default multi-turn REPL.
- `tools.py`: local tools, Chat Completions tool schemas, Responses tool
  schemas, and dispatcher.
- `responses_llm.py`: Responses API HTTP wrapper.
- `responses_agent.py`: Responses API tool-call loop.
- `responses_repl.py`: Responses API REPL.

## Planned Features

- Add focused tests for tool schemas, dispatch, tool-call loops, tool errors,
  multiple tool calls, and final-answer handling.
- Return structured JSON tool results instead of plain strings.
- Add run traces for every tool call and final answer.
- Add practical tools such as `fetch_url`, `arxiv_search`, `current_time`,
  `read_file`, and `write_note`.
- Expand the Responses API path with streaming and trace comparison.
- Add prompt-injection hardening for web/search outputs.

