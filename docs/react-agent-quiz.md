# ReAct Agent 理解测试问答

这份文档整理了一组围绕本项目的 ReAct agent、Chat Completions function
calling、Responses API、tool result 和现代 agent 架构的复习题。

## 1. Tool call 执行后，runtime 应该放回什么？

题目：

模型返回 Chat Completions tool call：

```json
{
  "id": "call_123",
  "type": "function",
  "function": {
    "name": "calculate",
    "arguments": "{\"expression\":\"100 + 200\"}"
  }
}
```

本地 runtime 执行后得到 `300`。下一步应该放回什么？为什么必须带
`tool_call_id`？

答案：

Chat Completions 应该放回 `role: "tool"` message：

```json
{
  "role": "tool",
  "tool_call_id": "call_123",
  "content": "{\"ok\": true, \"tool\": \"calculate\", \"result\": \"300\"}"
}
```

Responses API 则回传：

```json
{
  "type": "function_call_output",
  "call_id": "call_123",
  "output": "{\"ok\": true, \"tool\": \"calculate\", \"result\": \"300\"}"
}
```

必须带 `tool_call_id` / `call_id`，因为一次模型响应里可能有多个 tool calls。
没有 ID，模型无法知道哪个结果属于哪次调用。

## 2. Responses API 为什么不用每次发送完整历史，但历史仍然占 context？

答案：

`previous_response_id` 让服务端能接上之前的 response 链，所以客户端不用每次发送
完整 `messages`。这减少的是客户端请求体大小和本地状态管理复杂度。

但模型生成当前回答时，仍然需要参考之前的 user、assistant、tool call、tool
output 等历史内容。这些内容仍然属于模型有效上下文，仍然受 context window 限制，
也可能计入输入 token 成本。

一句话：

```text
客户端传输层少发了，模型推理层仍然要用。
```

## 3. 为什么结构化 tool result 比纯文本更适合 agent？

答案：

纯文本错误：

```text
Error from calculate: unsupported expression node
```

需要模型或程序自己猜这是不是错误。

结构化结果：

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

优势：

- 模型可以直接根据 `ok: true/false` 判断成功或失败。
- 程序、测试、日志和 UI 都可以稳定解析 JSON。
- 错误类型和错误原因更清楚，有助于模型恢复，比如把 `sqrt(16)` 改写成
  `16 ** 0.5`。
- 多工具场景下更容易追踪每个工具的成功或失败。

## 4. ReAct agent 为什么必须有 `max_steps`？

答案：

ReAct loop 的下一步由模型决定。如果模型一直调用工具、不返回最终答案，runtime
就会一直循环。

可能发生：

- 一直调用 `web_search`。
- 工具报错后反复重试。
- 搜索结果不满意，不断换 query。
- 模型忘记给 final answer。
- 被 tool output 带偏。

所以 runtime 必须设置保护栏：

```python
for step in range(1, max_steps + 1):
```

超过限制后返回：

```text
(stopped: max_steps reached without final answer)
```

`max_steps` 是 agent runtime 的安全机制，不是模型能力的一部分。

## 5. ReAct 和 RAG 的区别是什么？

答案：

RAG 是一种知识增强方法：

```text
retrieve documents -> augment prompt -> generate answer
```

ReAct 是一种 agent 执行模式：

```text
reason -> act/tool call -> observe tool result -> continue
```

关系：

RAG 可以作为 ReAct agent 的一个工具，例如：

```text
retrieve_documents(query)
```

也就是说，RAG 解决“如何把外部知识给模型”，ReAct 解决“模型如何多步决策并调用工具”。

## 6. 为什么现代 agent 通常不是纯 ReAct？

答案：

纯 ReAct 只是内部执行循环。真实生产 agent 通常会在它外面叠加其他机制：

- planning：先拆任务、排步骤。
- human-in-the-loop：高风险操作需要人工确认。
- multi-agent orchestration：研究、编码、测试、审查交给不同 agent。
- memory：长期记忆、用户偏好、项目知识。
- RAG/retrieval：从文档、代码、数据库检索上下文。
- guardrails：权限、schema 校验、敏感操作拦截。
- reflection/evaluation：执行后自检、重试、评估结果。
- tracing/observability：记录每一步 tool call、输入输出、错误。
- sandbox：隔离文件系统、网络、命令执行权限。

一句话：

```text
Pure ReAct is the inner loop. Production agents add planning, memory,
retrieval, guardrails, human approval, tracing, and sometimes multi-agent
orchestration around that loop.
```

## 7. Chat Completions 和 Responses API 的 tool result 回传格式分别是什么？

答案：

Chat Completions：

```json
{
  "role": "tool",
  "tool_call_id": "call_123",
  "content": "{\"ok\": true, \"tool\": \"calculate\", \"result\": \"300\"}"
}
```

关键字段：

- `role: "tool"`
- `tool_call_id`
- `content`

Responses API：

```json
{
  "type": "function_call_output",
  "call_id": "call_123",
  "output": "{\"ok\": true, \"tool\": \"calculate\", \"result\": \"300\"}"
}
```

关键字段：

- `type: "function_call_output"`
- `call_id`
- `output`

记忆方式：

```text
Chat Completions: role=tool + tool_call_id + content
Responses API: function_call_output + call_id + output
```

