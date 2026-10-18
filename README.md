<img src="assets/icon.svg" width="64" height="64" alt="">

# uae-labour-eval

An eval harness for a bilingual (English and Arabic) assistant on UAE private-sector labour law. The harness is the product: it shows how well the assistant works, with numbers you can check, trace by trace. The assistant is the thing it measures.

> **Not legal advice.** Nothing in this repository, its reports or its traces is legal advice. The assistant is a test subject and is often wrong; see the results below. For your own situation, ask a lawyer or the UAE Ministry of Human Resources and Emiratisation.

## What it measures

The agent answers questions on Federal Decree-Law No. 33 of 2021 (the Labour Law) and Cabinet Resolution No. 1 of 2022 (its Executive Regulations). It searches both instruments in both languages, cites the articles it used, computes entitlements with calculation tools, and refuses legal advice and questions outside the law. Each **case** is a frozen question with an expected result. Six categories:

| Category | What a case checks |
|---|---|
| calc | Gratuity, annual leave, notice and probation figures, computed by the calculation tool with the right inputs |
| cite | The answer cites the articles that hold the answer, and only articles it actually retrieved |
| grounding | Every claim in a free-text answer is supported by the cited text (judged by a second model) |
| refuse | Legal advice and out-of-scope questions are refused with a reason and a next step; questions the law does not answer get "not found" |
| inject | Prompt injection in the question or in planted fake articles is ignored, and the real question still gets answered |
| bilingual | The same question in English and Arabic gets the same answer |

Why a harness and not a chatbot: a legal assistant is only useful if you know where it fails. Every number below comes from reviewed cases, repeated runs, intervals, a judge whose agreement with hand labels is measured, and a hard budget.

## Results

Run [`20261018T131431Z-09b9ca`](reports/20261018T131431Z-09b9ca/index.html) on 2026-10-18: agent `deepseek/deepseek-v4.1-flash` (pinned to DeepInfra fp8), judge `openai/gpt-5.6-terra`, 121 reviewed cases (tag `cases-v1`), 3 repeats each. n counts distinct cases; a case scores the share of its repeats that passed. Intervals are 95% Wilson intervals.

| Category | n | Pass rate | 95% interval | Threshold |
|---|---|---|---|---|
| bilingual | 10 | 97% | 68–100% | 86% |
| calc | 35 | 95% | 83–99% | 85% |
| cite | 26 | 95% | 79–99% | 84% |
| grounding | 15 | 60% | 36–80% | 50% |
| inject | 15 | 96% | 73–99% | 85% |
| refuse | 20 | 95% | 76–99% | 85% |
| **safety** (refuse + inject) | 35 | 95% | 83–99% | 90% |

- **Cost:** USD 1.61 for the run (363 case runs, agent and judge). Per case: p50 USD 0.003, p95 USD 0.012.
- **Latency per case:** p50 13.1 s, p95 36.0 s.
- **Weak spot:** grounding. In 15 of its 18 failed runs, the answer added a claim the cited text does not make, such as "a month is 30 days" (Art 67) while citing only Art 9. The [report](reports/20261018T131431Z-09b9ca/index.html) lists the worst failures and the flaky cases, each linked to its trace.
- **Thresholds** (`packs/uae_labour/evals/thresholds.toml`) are this run's rate minus 10 points, rounded down, with a 0.90 floor for safety. `eval gate` fails a run below them.

### Judge agreement

The judge scores free-text answers against written rubrics. Before trusting it, 50 real and deliberately broken answers were hand-labelled without seeing its verdicts (the judge-check set). The owner labelled 7 items and approved labels drafted by Claude for the other 43. Agreement over 122 decisions is 91%, Cohen's kappa 0.76. A rubric counts as trusted at kappa 0.6 or above.

| Rubric | Agreement | Kappa |
|---|---|---|
| bilingual | 94% | 0.85 |
| grounding | 85% | 0.63 |
| inject | 97% | 0.91 |
| refusal | 91% | 0.74 |

### Spend

The hard budget for v1 is USD 20. Total spend so far is USD 2.46, including the pilots, the judge checks and the final run. The budget guard refuses to start a run whose estimate would cross the ceiling, and stops a run that crosses it (ADR-0008).

## How it works

- **Generic core, domain pack.** `src/eval_harness` knows nothing about UAE law. Everything domain-specific (sources, calculation tools, prompt, cases, rubrics, thresholds) lives in `packs/uae_labour` (ADR-0006).
- **Sources.** `packs/uae_labour/manifest.toml` pins each official PDF to a Wayback Machine copy and a SHA-256; `eval fetch` refuses any file that does not match (ADR-0005). The Arabic Executive Regulations PDF has broken font tables; a glyph table in the manifest repairs it, and ingest fails on any unreadable character (ADR-0004).
- **Agent.** A plain tool-calling loop over OpenRouter, ending in a structured final answer with citations and a status of answered, refused or not found (ADR-0001, 0002, 0007).
- **Search.** BM25 and `baai/bge-m3` embeddings, fused with reciprocal rank fusion over one index of both languages (ADR-0003).
- **Scoring.** Rule-based scorers first (status, citations, numbers, tool calls, canaries, language); the judge runs only when they pass (ADR-0009).
- **Open questions.** Where the official text is ambiguous, the ambiguity is written down and decided by the project owner, not by the code (ADR-0010, `docs/open-questions.md`).

Vocabulary is in `GLOSSARY.md`; decisions are in `docs/adr/`.

## Reproduce

You need [mise](https://mise.jdx.dev) (it installs Python 3.15 and uv 0.13.1 from `mise.toml`) and an OpenRouter API key.

```sh
mise install
uv sync --locked
cp .env.example .env    # then set OPENROUTER_API_KEY in .env
make eval               # fetch → ingest → embed → run → report
```

`make eval` runs every case once and writes the report to `reports/<run id>/`. The published run used `make eval RUN_ARGS="--repeats 3"`. The key is read only from the `OPENROUTER_API_KEY` environment variable; it is never printed or written to disk by the harness. Runs and the cost ledger go to the git-ignored `runs/`.

Other commands (`uv run --env-file .env eval <command>`):

| Command | Does |
|---|---|
| `budget` | Ledger total, key usage and remaining budget |
| `run --category inject` / `--case <id>` / `--repeats 3` | Run part of the case set |
| `report <run>` | Write the HTML report |
| `gate <run>` | Check a run against the thresholds; exit 1 below them |
| `compare <run> <run>` | Two runs side by side |
| `judge-agreement` | Judge agreement on the judge-check set (no API calls) |

`make test` runs the test suite (no network) and `make lint` runs ruff and ty. CI runs both on every push. On pushes to `main` and on manual dispatch it also runs a fixed 20-case subset and gates it against the `[ci]` thresholds, only when the `OPENROUTER_API_KEY` repository secret is set.

## Known limits

- **One model, small n.** Each category has 10–35 cases, so the intervals are wide; a 5-point difference between two runs is usually noise.
- **The judge is a model.** It agrees with the hand labels 91% of the time, not always. Its grounding verdicts are the least reliable (kappa 0.63).
- **English translations are not authoritative.** The Arabic text prevails. Where the two differ, the case set follows the Arabic (OQ-004, OQ-006, OQ-007, OQ-014).
- **Amendments.** The corpus is the consolidated Labour Law, which already folds in Decree-Laws 14/2022, 20/2023 and 9/2024. Their effective dates are from the official text for 20/2023 only; the others are from secondary sources.
- **Only two languages.** The bilingual pairing assumes English and Arabic.
- **Open questions.** The calculation tools and expected answers depend on these decisions. "Provisional" means the research could not settle it with confidence; a different reading would change some expected figures. Full text and quotes: `docs/open-questions.md`.

| OQ | Question | Decision |
|---|---|---|
| 001 | Daily basic wage | Monthly basic wage × 12 ÷ 365 |
| 002 | Gratuity cap | 24 × monthly basic wage |
| 003 | Wage for untaken leave | Basic wage |
| 004 | Arabic Art 29(9), missing in English | Applies in both languages: leave for part years, pro rata, on basic wage |
| 005 | Annual-leave boundaries | Nothing at exactly six months; part months pro rata (provisional) |
| 006 | Temporary work under ER Art 30(2) | One year or more earns gratuity; under a year earns none |
| 007 | Art 60 maximum fine | AED 1,000,000 |
| 008 | Part-time gratuity base | Full-time-equivalent wage, hours reduction applied once (provisional) |
| 009 | Flexible work gratuity | ER Art 30(1) on contracted hours (provisional) |
| 010 | Part-time annual leave | Full-time entitlement × hours ratio (provisional) |
| 011 | Leave for six months' service or less | None (provisional, weakest) |
| 012 | Contract notice outside 30–90 days | Harmful terms move to the nearest limit; favourable terms stand |
| 013 | Six months of probation | 180 days |
| 014 | Art 44(8) absence | Arabic: more than 20 days within one year, or more than 7 in a row |
| 015 | Carrying leave forward | At most half, with the employer's approval (provisional) |

## Legal texts and licence

The legal texts are official UAE government documents, published on the [UAE Legislation portal](https://uaelegislation.gov.ae), the Ministry of Human Resources and Emiratisation and the Ministry of Justice. They are fetched at build time from the URLs in the manifest and checked against their hashes; they are not committed to this repository and are **not covered by the MIT licence**.

The code, cases, rubrics and documentation are under the [MIT licence](LICENSE). This project uses public sources only.
