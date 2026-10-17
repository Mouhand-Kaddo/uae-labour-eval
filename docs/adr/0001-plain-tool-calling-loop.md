# Plain tool-calling loop, no agent framework

The agent is a hand-written loop: send messages and tool schemas to the chat completions endpoint, run any tool calls, append the results, repeat until the model calls `final_answer` or hits the turn limit (6 model turns, capped `max_tokens`, low reasoning effort). We rejected LangChain-style frameworks because the harness must log every prompt, chunk ID, tool call, token count and cost per step, and a framework hides exactly those things behind its own abstractions. The loop is small enough that owning it costs less than learning and pinning a framework.

## Considered Options

- **LangChain / LlamaIndex / similar**: rejected; opaque prompts and retries make traces unreliable and replay hard.
- **Official `openrouter` Python SDK**: rejected for now; very young, releases almost daily, and pins `pydantic<2.13`.
- **`openai` SDK with a custom `base_url`**: rejected; OpenRouter-only fields (`provider`, `reasoning`, `session_id`) go through `extra_body`, and `usage.cost` arrives as an untyped extra. We need the raw `usage` object for the ledger anyway, so plain `httpx` is simpler.
