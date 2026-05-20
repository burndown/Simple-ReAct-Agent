# 会话整理：Simple ReAct Agent

日期：2026-05-20

## 目标

这次会话的目标是把一个最小化的 Ollama ReAct demo，逐步改造成一个
OpenAI-compatible agent demo，并进一步从文本式 `Action: tool[arg]` 升级为
OpenAI function calling。

当前项目保留两条独立路径：

- `python -m repl`：默认路径，使用 Chat Completions + function calling。
- `python -m responses_repl`：独立实验路径，使用 OpenAI Responses API。

默认路径仍然是 Chat Completions，因为它兼容 OpenAI 以及很多
OpenAI-compatible provider，比如 DeepSeek 的 `/chat/completions`。

## 已完成的主要改动

- 把 Ollama `/api/chat` 替换为 OpenAI-compatible `/chat/completions`。
- 增加 `.env` 读取，支持 `KEY=value`、`export KEY=value`、fish shell 的
  `set -x KEY value`。
- 增加 `OPENAI_API_KEY`、`OPENAI_MODEL`、`OPENAI_BASE_URL` 配置。
- 增加 `PRINT_PROMPTS=1`，可以打印每次发给模型的 request payload，但不打印
  Authorization header。
- 从文本式 ReAct `Action: ...` 正则解析，升级为 OpenAI function calling。
- 为 `calculate` 和 `web_search` 增加 JSON Schema tool 定义。
- tool 执行结果改为通过 `role: "tool"` + `tool_call_id` 放回 `messages`。
- tool 输出内容统一包装成 JSON 字符串，成功为 `ok: true`，失败为 `ok: false`。
- 对 DeepSeek thinking 模式返回的 `reasoning_content` 做保留，避免下一轮请求
  报错。
- 新增独立 Responses API demo，不覆盖默认 Chat Completions 路径。

## 默认 Chat Completions 流程

默认 `repl.py` 使用 Chat Completions。这个 API 从服务端角度看是无状态的，
所以本地程序必须维护完整的 `messages` 历史，并在每次请求时把当前需要的上下文
发给模型。

基本流程：

```text
用户输入
  -> append role=user
  -> 发送 messages + tools 到 /chat/completions
  -> 模型返回 assistant tool_calls
  -> append assistant message，保留 tool_calls
  -> 本地 dispatch 执行 tool
  -> append role=tool，带上 tool_call_id 和执行结果
  -> 再次调用模型
  -> 如果没有 tool_calls，则 assistant content 是最终答案
```

tool 执行结果必须放回 `messages`：

```json
{
  "role": "tool",
  "tool_call_id": "call_...",
  "content": "{\"ok\": true, \"tool\": \"calculate\", \"result\": \"300\"}"
}
```

其中 `tool_call_id` 必须匹配上一条 assistant message 里的 tool call id。否则
很多 OpenAI-compatible API 会直接返回 400。

工具失败时也使用同样的 JSON envelope：

```json
{
  "role": "tool",
  "tool_call_id": "call_...",
  "content": "{\"ok\": false, \"tool\": \"calculate\", \"error\": {\"type\": \"ValueError\", \"message\": \"unsupported expression node: Call\"}}"
}
```

## Responses API 流程

独立的 `responses_repl.py` 使用 OpenAI `/v1/responses`。

Responses API 可以通过 `previous_response_id` 接续服务端保存的 response 链。
因此本地不需要像 Chat Completions 一样每次都重发完整 `messages`。

示例：

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

注意：每次都应该传**最新的** response id，而不是第一次的 response id。

tool 执行结果在 Responses API 中不是 `role: "tool"` message，而是 input item：

```json
{
  "type": "function_call_output",
  "call_id": "call_...",
  "output": "{\"ok\": true, \"tool\": \"calculate\", \"result\": \"300\"}"
}
```

## Chat Completions 如何组装 Prompt

Chat Completions 的一次请求大致长这样：

```json
{
  "model": "gpt-4o-mini",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful ReAct-style agent..."
    },
    {
      "role": "user",
      "content": "100 + 200"
    },
    {
      "role": "assistant",
      "content": null,
      "tool_calls": [
        {
          "id": "call_1",
          "type": "function",
          "function": {
            "name": "calculate",
            "arguments": "{\"expression\":\"100 + 200\"}"
          }
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_1",
      "content": "{\"ok\": true, \"tool\": \"calculate\", \"result\": \"300\"}"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "calculate",
        "description": "Evaluate a numeric expression...",
        "parameters": {}
      }
    }
  ],
  "tool_choice": "auto",
  "temperature": 0.0
}
```

这里的 prompt/context 由几部分组成：

- `system` message：全局行为约束和当前日期。
- `user` messages：用户每一轮输入。
- `assistant` messages：模型过往回答，或者模型请求过的 `tool_calls`。
- `tool` messages：本地工具执行结果，通过 `tool_call_id` 对应某次 tool call。
- `tools`：函数工具的 JSON Schema。

重要点：

- 工具定义不再写进 system prompt 文本里，而是通过 `tools` 字段传给模型。
- 第 4 轮对话时，通常要把第 1、2、3 轮相关 `messages` 一起发过去。
- Chat Completions 本身不记得上一轮请求，本地代码必须维护和裁剪历史。

## Responses API 如何组装 Prompt

Responses API 的请求结构不同。第一轮可能是：

```json
{
  "model": "gpt-4o-mini",
  "instructions": "You are a helpful ReAct-style agent...",
  "input": "100 + 200",
  "tools": [
    {
      "type": "function",
      "name": "calculate",
      "description": "Evaluate a numeric expression...",
      "parameters": {}
    }
  ],
  "temperature": 0.0
}
```

如果模型返回 function call，下一轮回传 tool 结果：

```json
{
  "model": "gpt-4o-mini",
  "instructions": "You are a helpful ReAct-style agent...",
  "previous_response_id": "resp_1",
  "input": [
    {
      "type": "function_call_output",
      "call_id": "call_1",
      "output": "{\"ok\": true, \"tool\": \"calculate\", \"result\": \"300\"}"
    }
  ],
  "tools": [
    {
      "type": "function",
      "name": "calculate",
      "description": "Evaluate a numeric expression...",
      "parameters": {}
    }
  ],
  "temperature": 0.0
}
```

下一轮用户继续追问：

```json
{
  "model": "gpt-4o-mini",
  "instructions": "You are a helpful ReAct-style agent...",
  "previous_response_id": "resp_2",
  "input": "divide that by 5",
  "tools": []
}
```

Responses API 的重点是：

- 本地只需要保存最新的 `previous_response_id`。
- 服务端通过 response 链恢复之前上下文。
- 本地不需要每次重发完整 `messages`。
- 但仍然要发送当前 `input`、`tools`，以及通常也要发送 `instructions`。

## Chat Completions 与 Responses API 对比

| 维度 | Chat Completions | Responses API |
|---|---|---|
| Endpoint | `/v1/chat/completions` | `/v1/responses` |
| 主要上下文字段 | `messages` | `input` + `previous_response_id` |
| 系统提示 | `role: "system"` message | `instructions` |
| 工具定义 | `tools[].function` | 顶层 function tool object |
| 模型请求工具 | assistant message 里的 `tool_calls` | output item：`type: "function_call"` |
| 工具结果回传 | `role: "tool"` message | `function_call_output` input item |
| 状态管理 | 本地维护并重发历史 | 服务端可根据最新 response id 接续 |
| 上下文占用 | 历史轮次占用模型 context | 历史轮次仍然占用模型 context |
| 兼容性 | OpenAI-compatible provider 普遍支持 | 偏 OpenAI 专有，provider 需明确支持 |

## 关键结论：Responses API 不等于无限上下文

`previous_response_id` 减少的是：

- 客户端重复发送长 `messages` 的网络 payload。
- 客户端维护完整对话历史的复杂度。
- agent 状态接续的本地代码负担。

它**不减少**：

- 模型推理时需要看到的历史上下文。
- 历史对话、tool calls、tool outputs 对 context window 的占用。
- 历史 input tokens 可能产生的计费影响。

所以，如果一个模型支持 10M context，那么 Chat Completions 和 Responses API 仍然都受
这个 10M context window 限制。Responses API 不会把 10M 变成无限记忆。

可以这样总结：

```text
Responses API 减少的是客户端历史管理和网络传输成本，
不是模型上下文占用，也不是历史 token 成本。
```

## 重要但容易忽略的点

### 1. Responses API 的 instructions 不会自动继承

使用 `previous_response_id` 时，不要假设上一轮的 `instructions` 会自动继承到下一轮。
因此当前代码每次调用 `create_response()` 都传入 `instructions=INSTRUCTIONS`，这是有意为之。

如果不这样做，模型后续轮次可能缺少系统级约束。

### 2. Responses API 还有 Conversations API

`previous_response_id` 是链式接续：

```text
resp_1 -> resp_2 -> resp_3
```

OpenAI 还提供 Conversations API，可以创建长期 conversation object，用于跨 session、
跨设备、跨任务保存会话状态。

简单理解：

```text
previous_response_id:
适合短链路、单个连续任务。

conversation:
更像持久会话容器，适合长期会话和跨 session 状态。
```

### 3. Chat Completions 也有 store，但不是同一种状态管理

Chat Completions 可以通过 `store` 保存 completion，并后续 retrieve/list。

但这不等价于 Responses API 的 `previous_response_id` 状态接续。常规 Chat
Completions 多轮对话仍然需要本地维护 `messages`。

### 4. tool_choice 是重要控制点

当前代码使用：

```json
"tool_choice": "auto"
```

意思是模型自己决定是否调用工具。

生产环境里常见策略：

- `auto`：模型自行决定。
- `none`：禁止调用工具。
- `required`：必须调用至少一个工具。
- force specific tool：强制调用某个工具。
- allowed tools：当前步骤只允许某些工具。

例如代码 agent 可以限制某一步只允许读文件，不允许写文件。

### 5. Function calling 仍然需要服务端校验

工具参数是结构化的，但不代表一定安全或正确。

仍然需要在应用侧做：

- JSON parse。
- required 字段校验。
- enum/range 校验。
- path/url 权限校验。
- 参数长度限制。
- tool error 的结构化返回。

Function calling 解决的是“更可靠地表达工具调用意图”，不是替代业务校验。

### 5.1 Tool result 的结构化 JSON envelope

当前代码让工具函数继续返回业务字符串，由 agent runtime 统一包装：

成功：

```json
{
  "ok": true,
  "tool": "calculate",
  "result": "300"
}
```

失败：

```json
{
  "ok": false,
  "tool": "calculate",
  "error": {
    "type": "ValueError",
    "message": "unsupported expression node: Call"
  }
}
```

注意：Chat Completions 的 `role: "tool"` `content` 和 Responses API 的
`function_call_output.output` 仍然都是字符串，只是字符串内容是 JSON。这样模型和日志
系统都能明确区分成功结果与错误反馈。

### 6. Streaming 与 background mode

Responses API 更适合 agentic workflow 的原因之一，是它面向更复杂的输出 item、
长任务、异步执行和 background mode。

长任务，比如深度研究、复杂 coding、长 reasoning，不一定适合同步请求一直等待。
background mode 可以让任务后台运行，再轮询结果。

### 7. 数据保留与合规

如果使用服务端状态，例如：

- `previous_response_id`
- Conversations API
- stored responses
- background mode

就要考虑数据保留策略。

某些企业场景要求 Zero Data Retention，这会影响是否能使用服务端状态能力。

### 8. Debuggability：Chat 更透明，Responses 更省心

Chat Completions：

- 优点：完整上下文在本地，容易打印、审计、重放、裁剪。
- 缺点：payload 越来越大，本地状态管理更麻烦。

Responses API：

- 优点：本地只保存最新 response id，agent 状态接续更轻。
- 缺点：完整上下文不一定在本地一眼可见，最好自己保存 trace。

所以即使用 Responses API，也建议本地记录 run trace。

## DeepSeek 兼容性

DeepSeek 当前公开文档支持 OpenAI-compatible Chat Completions：

```text
https://api.deepseek.com/chat/completions
```

因此 DeepSeek 应使用默认路径：

```bash
python -m repl
```

DeepSeek 文档目前没有明确支持 OpenAI `/responses` endpoint，所以：

```text
DeepSeek -> Chat Completions path
OpenAI Responses-capable model -> responses_repl.py
```

另外，DeepSeek thinking 模式可能返回 `reasoning_content`。如果返回了这个字段，下一次
请求需要把它保留在 assistant message history 中，否则可能报错。

## Responses API 实测记录

`responses_repl.py` 已经用 `doubao-seed-2-0-lite-260428` 在一个
Responses-compatible endpoint 上手动跑通。

实测覆盖了这些行为：

- 第一轮普通问答没有 `previous_response_id`，直接返回最终回答。
- 第二轮 `100 + 200` 带上上一轮最新 response id，模型返回 function call：
  `calculate({"expression": "100 + 200"})`。
- 本地执行 `calculate` 得到 `300`，再通过 `function_call_output` 回传：

  ```json
  {
    "type": "function_call_output",
    "call_id": "call_...",
    "output": "300"
  }
  ```

- 模型基于 tool output 返回最终答案。
- 后续搜索 “latest agentic RAG survey in 6 months” 时，模型调用 `web_search`，
  并基于搜索结果回答。
- 再追问 “give the summary in chinese” 时，只发送新 input 和最新
  `previous_response_id`，模型仍然能复用上一轮论文上下文，用中文总结。
- 多 tool call 场景也已跑通。提示：
  `Calculate 100 + 200 and 30 * 4. Use the calculate tool for both calculations before answering.`
  模型在同一个 response 中返回 2 个 function calls：

  ```text
  calculate({"expression": "100 + 200"}) -> 300
  calculate({"expression": "30 * 4"}) -> 120
  ```

  本地 loop 逐个执行两个 tool call，并把两个 `function_call_output` 一起作为下一轮
  input 回传，随后模型返回最终答案。

这说明该 provider/model 的 Responses-compatible 行为至少支持：

- `/responses` 风格请求。
- `previous_response_id` 上下文接续。
- function call output item。
- 多轮上下文延续。
- 同一 response 中的多个 function calls。

## ReAct 基础概念

ReAct = Reasoning + Acting。

原始 ReAct 常见格式：

```text
Thought: 我需要计算这个数字
Action: calculate[100 + 200]
Observation: 300
Final Answer: 300
```

现在使用 function calling 后，`Action` 不再是文本，而是结构化 tool call：

```json
{
  "name": "calculate",
  "arguments": "{\"expression\":\"100 + 200\"}"
}
```

ReAct 是 agent loop 模式，function calling 是工具调用接口。二者关系是：

```text
ReAct 决定何时调用工具、根据结果如何继续。
Function calling 提供可靠的结构化工具调用格式。
```

## 现代 Agent 通常不是纯 ReAct

真实产品里的 agent 通常是复合结构：

- ReAct execution loop
- planning
- structured tool calling
- retrieval / RAG
- memory
- validation
- tracing
- permission checks
- prompt-injection defense
- multi-agent orchestration

Codex、Claude Code 这类 coding agent 都不是单纯 ReAct，而是把 ReAct 作为内部执行循环，
外面叠加计划、权限、上下文压缩、工具路由、测试验证和错误恢复。

## Debug

打印发给模型的 payload：

```bash
PRINT_PROMPTS=1 python -m repl
```

fish：

```fish
set -x PRINT_PROMPTS 1
python -m repl
```

关闭：

```fish
set -e PRINT_PROMPTS
```

## 当前文件结构

- `llm.py`：Chat Completions HTTP wrapper。
- `react.py`：默认 Chat Completions tool-call loop。
- `repl.py`：默认多轮 REPL。
- `tools.py`：本地工具、Chat Completions tool schema、Responses tool schema、dispatcher。
- `responses_llm.py`：Responses API HTTP wrapper。
- `responses_agent.py`：Responses API tool-call loop。
- `responses_repl.py`：Responses API REPL。
- `docs/chat_history_chat_tool_function_call.md`：Chat Completions tool calling 的完整
  payload 日志示例。

## 下一步计划

- 继续用 Responses-compatible 模型验证更多边界场景，例如多 tool call、tool error、
  长上下文和 streaming。
- 增加 focused tests：tool schema、dispatch、tool-call loop、tool error、多 tool call、
  final answer。
- 增加 run trace，记录每一步 tool name、arguments、output preview、final answer。
- 增加更实用的工具：`fetch_url`、`arxiv_search`、`current_time`、`read_file`、
  `write_note`。
- 给 web/search 输出增加 prompt-injection hardening。
