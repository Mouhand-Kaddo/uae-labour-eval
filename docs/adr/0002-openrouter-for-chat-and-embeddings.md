# OpenRouter for chat and embeddings, models chosen in config

All paid calls (agent, judge, embeddings) go through OpenRouter, so one key, one bill and one cost field (`usage.cost`, present on every response) cover the whole budget. Model IDs live in `config.toml`; prices and capabilities are read at run start from `GET /api/v1/models` rather than hard-coded, because prices change and some models now have time- or size-based price overrides. The judge must come from a different model family than the agent so it is not grading its own family's answers.

## Consequences

- Embeddings default to `baai/bge-m3` via `POST /api/v1/embeddings`, which keeps torch and multi-GB model downloads out of the project.
- The default agent model is locked only after a small pilot on a few cheap tool-calling candidates, including Arabic cases.
- Tool-calling and structured-output support vary by OpenRouter provider endpoint, so requests that rely on them set `provider.require_parameters: true`.
