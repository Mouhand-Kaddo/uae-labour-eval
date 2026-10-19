# uae-labour-eval

This project is an eval harness for an agent that answers questions on UAE private-sector labour law, in English and Arabic. The harness is the product. The agent is the thing that the harness measures.

> **Not legal advice.** This repository, its reports and its traces do not give legal advice. The agent is a test subject, and it is sometimes wrong. For your own situation, speak to a lawyer or to the UAE Ministry of Human Resources and Emiratisation.

## What it measures

The agent answers questions on two instruments: the Labour Law (Federal Decree-Law No. 33 of 2021) and its Executive Regulations (Cabinet Resolution No. 1 of 2022). The agent searches both instruments in English and Arabic. It cites the articles that it uses. It uses calculation tools to compute entitlements. It refuses legal advice and questions that are not about the Labour Law.

Each case is a frozen question with an expected result. There are six categories of case:

| Category | What a case checks |
|---|---|
| calc | The agent uses the correct calculation tool with the correct facts. The figure is for gratuity, annual leave, a notice period or a probation period. |
| cite | The agent cites the articles that hold the answer. It cites only articles that it retrieved. |
| grounding | The cited text supports each claim in the answer. The judge (a second model) checks this. |
| refuse | The agent refuses legal advice and out-of-scope questions, with a reason and a next step. When the law does not answer a question, the agent says "not found". |
| inject | The agent ignores instructions that are hidden in the question or in planted chunks. It still answers the real question. |
| bilingual | The agent gives the same answer to the same question in English and in Arabic. |

Why a harness and not a chatbot? A legal agent is useful only if you know where it fails. Each number below comes from reviewed cases, repeated runs, 95% intervals, a judge that is checked against hand labels, and a hard budget.

## Results

Run `20261018T225102Z-cffe36`, 2026-10-18:

- **Agent:** `deepseek/deepseek-v4.1-flash`, on DeepInfra fp8 only.
- **Judge:** `openai/gpt-5.6-terra`.
- **Cases:** 121 reviewed cases (tag `cases-2026-10-18`), with 3 repeats of each case.

n is the number of cases. The score of one case is the part of its repeats that passed. The interval is a 95% Wilson interval. `eval gate` fails a run that is below a threshold.

| Category | n | Headline score | 95% interval | Threshold |
|---|---|---|---|---|
| bilingual | 10 | 97% | 68–100% | 86% |
| calc | 35 | 97% | 85–99% | 85% |
| cite | 26 | 92% | 76–98% | 84% |
| grounding | 15 | 76% | 50–90% | 50% |
| inject | 15 | 100% | 80–100% | 85% |
| refuse | 20 | 98% | 81–100% | 85% |
| **safety** (refuse + inject) | 35 | 99% | 88–100% | 90% |

- **Cost:** USD 1.68 for the run (363 case runs, agent and judge). Per case: median USD 0.003, 95th percentile USD 0.013.
- **Time per case:** median 11.3 s, 95th percentile 29.0 s.
- **Weakest category:** grounding (76%). In most failures, the answer says more than the cited text. It states a rule more broadly than the text, or it adds a fact from an article that it did not cite.
- **Final answers sent back:** 1. If a final answer cites an article that no tool returned, the agent loop sends the answer back. The agent must then read the article or remove the citation.

`eval report <run>` writes an HTML report. The report shows the worst failures and the flaky cases, each with a link to its trace.

### Judge agreement

The judge scores free-text answers against written rubrics. Before we used the judge, we compared its verdicts with hand labels on the judge-check set: 50 real and deliberately broken answers. The project owner labelled 7 items and approved labels that Claude drafted for the other 43. Over 122 decisions, judge agreement is 93% and Cohen's kappa is 0.81. A rubric is trusted only when its kappa is 0.6 or more.

| Rubric | Agreement | Kappa |
|---|---|---|
| bilingual | 94% | 0.85 |
| grounding | 90% | 0.78 |
| inject | 97% | 0.91 |
| refusal | 91% | 0.74 |

### Spend

The budget is USD 20. Total spend is USD 8.51, for the pilot runs, the judge checks and all runs. The budget guard does not start a run if its estimate is more than the remaining budget. It stops a run that goes over the budget (ADR-0008).

## How it works

- **Generic core and one pack.** The code in `src/eval_harness` contains no UAE law. The pack `packs/uae_labour` holds all the domain parts: the corpus manifest, calculation tools, prompt, cases, rubrics and thresholds (ADR-0006).
- **Sources.** The corpus manifest (`packs/uae_labour/manifest.toml`) gives each official PDF a Wayback Machine URL and a SHA-256 hash. `eval fetch` refuses a file that does not match its hash (ADR-0005). The Arabic Executive Regulations PDF has damaged font tables. A glyph table in the manifest repairs the text, and ingest stops if it finds a character that it cannot read (ADR-0004).
- **Agent.** The agent is a plain tool-calling loop over OpenRouter (ADR-0001, ADR-0002). It ends with a structured final answer: the answer text, the cited articles, and a status of answered, refused or not found (ADR-0007).
- **Search.** Search uses BM25 and `baai/bge-m3` embeddings, and reciprocal rank fusion combines the two results. One index holds both languages (ADR-0003).
- **Scoring.** Rule-based scorers run first: status, citations, numbers, tool calls, canaries and language. The judge runs only when these scorers pass (ADR-0009).
- **Open questions.** Sometimes the official text is not clear. Then we record an open question, and the project owner decides it. The code does not decide it (ADR-0010, `docs/open-questions.md`).

The terms are in `GLOSSARY.md`. The design decisions are in `docs/adr/`.

## Reproduce

You need [mise](https://mise.jdx.dev) and an OpenRouter API key. mise installs Python 3.15 and uv 0.13.1 from `mise.toml`.

```sh
mise install
uv sync --locked
cp .env.example .env    # then set OPENROUTER_API_KEY in .env
make eval               # fetch → ingest → embed → run → report
```

`make eval` runs each case one time and writes the report to `reports/<run id>/`. For the run above, we used `make eval RUN_ARGS="--repeats 3"`. The harness reads the key only from the `OPENROUTER_API_KEY` environment variable. It never prints the key or writes it to disk. Runs and the ledger go to `runs/`, and reports go to `reports/`. Git ignores both folders.

Other commands (`uv run --env-file .env eval <command>`):

| Command | Does |
|---|---|
| `budget` | Ledger total, key usage and remaining budget |
| `run --category inject` / `--case <id>` / `--repeats 3` | Run part of the case set |
| `report <run>` | Write the HTML report |
| `gate <run>` | Check a run against the thresholds; exit 1 below them |
| `compare <run> <run>` | Two runs side by side |
| `judge-agreement` | Judge agreement on the judge-check set (no API calls) |

`make test` runs the tests, which do not use the network. `make lint` runs ruff and ty. CI runs both on each push and pull request. CI makes no API calls and needs no secrets. You run the eval yourself.

## Known limits

- **One agent model and few cases.** Each category has 10 to 35 cases, so the intervals are wide. A difference of 5 points between two runs is usually noise.
- **The judge is a model.** Its verdicts agree with the hand labels 93% of the time, not always. Its grounding verdicts are the least reliable.
- **The English translations are not authoritative.** The Arabic text prevails. Where the two texts are different, the cases follow the Arabic (OQ-004, OQ-006, OQ-007, OQ-014).
- **Amendments.** The corpus is the consolidated Labour Law. It already includes the amending decree-laws 14/2022, 20/2023 and 9/2024. Only the effective date of 20/2023 comes from the official text. The other dates come from secondary sources.
- **Two languages only.** A bilingual pair is always English and Arabic.
- **Open questions.** The calculation tools and expected answers depend on the decisions below. "Provisional" means that the research could not decide the question with confidence. A different decision would change some expected figures. The full text and quotes are in `docs/open-questions.md`.

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

The legal texts are official UAE government documents. The [UAE Legislation portal](https://uaelegislation.gov.ae), the Ministry of Human Resources and Emiratisation and the Ministry of Justice publish them. The harness downloads them at build time from the URLs in the corpus manifest and checks their hashes. They are not in this repository, and the MIT licence does not apply to them.

The [MIT licence](LICENSE) applies to the code, cases, rubrics and documentation. This project uses only public sources.
