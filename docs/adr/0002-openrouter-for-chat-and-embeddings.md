# OpenRouter for chat and embeddings, models chosen in config

All paid calls (agent, judge, embeddings) go through OpenRouter, so one key, one bill and one cost field (`usage.cost`, present on every response) cover the whole budget. Model IDs live in `config.toml`; prices and capabilities are read at run start from `GET /api/v1/models` rather than hard-coded, because prices change and some models now have time- or size-based price overrides. The judge must come from a different model family than the agent so it is not grading its own family's answers.

## Consequences

- Embeddings default to `baai/bge-m3` via `POST /api/v1/embeddings`, which keeps torch and multi-GB model downloads out of the project.
- The default agent model is locked only after a small pilot on a few cheap tool-calling candidates, including Arabic cases.
- Tool-calling and structured-output support vary by OpenRouter provider endpoint, so requests that rely on them set `provider.require_parameters: true`.

## Decision: default agent model (2026-10-18)

- **Owner's choice:** the agent is `deepseek/deepseek-v4.1-flash`. The judge stays `openai/gpt-5.6-terra`, which is from another family. Pilot evidence: `docs/pilot-2026-10-17.md`.
- **Pinned to one endpoint:** `[provider_routing."deepseek/deepseek-v4.1-flash"]` has `order = ["deepinfra/fp8"]` and `allow_fallbacks = false`. The model has 34 provider endpoints, with different quantizations (fp4 to unknown) and prices. Pinning keeps the weights, the fp8 quantization and the price the same on every run. The trace and the ledger record which provider served each call.
- **Why not the dated snapshot:** the owner first chose `deepseek/deepseek-v4.1-flash-1017`, pinned to DeepSeek's own endpoint. The account's paid-training guardrail (account settings) removes that endpoint, so every call returned HTTP 404 and no money was spent. The plain model is pinned to DeepInfra instead.
- **Peak pricing:** DeepSeek's own endpoint costs 2× on weekdays from 01:00 to 04:00 and 06:00 to 10:00 UTC (`pricing.overrides`). DeepInfra fp8 charges a flat USD 0.14/0.42 per million tokens. The budget guard prices every model at its highest override that a call can meet, because the 1.5× margin does not cover a 2× peak. Time-based overrides always count, since a run may fall in their window. Size-based ones, such as terra above 272k prompt tokens, count only if the assumed prompt size per call (`assumed_prompt_tokens_per_case`) reaches them; otherwise they would double the judge estimate for cases that can never reach them. It also prices a strictly pinned model at the most expensive matching endpoint, because `GET /models` gives a model's cheapest endpoint price (USD 0.0648/0.144 here).
