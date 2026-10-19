# Raising the grounding score, 2026-10-18 (v2)

**Result: grounding went from 60% to 76% on the full run, and no category fell outside noise.** The final run is `20261018T225102Z-cffe36`, on the same 121 cases as v1 (case set hash `3dd76011…`), 3 repeats each. It passed 341 of 363 case runs against 330 in v1 and passes every threshold. The work cost USD 6.05 in API spend: 6 grounding or calc measurements, 2 full runs, a stopped full run, and 3 re-judgings of the judge-check set.

**Caveat.** The prompt rule that gave most of the gain (H3) was written after reading the grounding failures of these same 15 cases. There is no held-out grounding set, so 76% probably overstates how the agent does on new questions.

## Method

One change at a time, each measured on the 15 grounding cases with 3 repeats (45 case runs, about USD 0.45 and 15 minutes). A rerun of the v1 code with no change scored 30/45 against v1's 27/45, so a gap under about 7 points is noise. A change was kept only if it moved the score past that, or removed a failure class it targeted, and the tests stayed green. The prompt change was then checked on the full case set, because it reaches every category.

## Why grounding failed in v1

The 18 failed grounding runs in v1 fell into three groups:

- **The judge failed answers for naming the law** (2 to 5 runs per measurement). "Federal Decree-Law No. 33 of 2021" is not in the text of the article, so the judge called it unsupported. The system prompt supplies the name.
- **The agent cited an article it never read** (3 runs, all `grounding-en-004`). It cited Art 12 from memory.
- **The agent said more than the cited text** (about 10 runs). Two patterns:
  - true facts from articles it did not cite, such as "basic wage means without allowances" (Art 1) or "a month is 30 days";
  - conditions and exceptions dropped, such as the piece-rate rule for notice pay, the Ministry deciding claims up to AED 50,000 itself, or assuming the user is a foreign worker.

## Changes

| | Change | Measured effect | Kept |
|---|---|---|---|
| H1 | Grounding rubric: naming the instrument a cited article belongs to is not a claim | Name-only failures 2–5 → 1; headline 60% (noise) | Yes, as a scoring fix |
| H2 | The agent loop sends back a final answer that cites an article no tool returned, so the agent reads it or drops it | Unread-citation failures 3 → 0; headline 66% (noise) | Yes |
| H3 | Prompt: say only what the cited text says, keep its conditions and exceptions, read and cite the article a fact comes from or leave it out, and say when the user's facts don't show a condition is met | 82% against 60–67% before; unsupported-claim failures 14 → 7; answers got longer, not shorter | Yes |
| H4 | Prompt: call the calculation tool whenever it covers the question, and let a decided interpretation in its result stand | Calc 90% → 97%; grounding 78% (unchanged) | Yes |

H4 fixed a side effect of H3. On the first full run, calc fell from 95% to 90%: the agent answered probation and notice questions from the article text and skipped the tool (4 runs), and once overrode the decided OQ-006 with its own reading of ER Art 30(2).

## The judge

H1 changed the rubric, so the 20 grounding items of the judge-check set were re-judged, three times. Grounding agreement was 80–82%, kappa 0.54–0.58, against 85% and 0.63 in v1. The drop is not from H1. Three of the 20 items flip from one judging to the next, none over the law's name. v1's 0.63 caught those items on a good day.

Four items disagree with their labels every time: jc-007, jc-010, jc-021 and jc-040. In each, the answer says something the cited text doesn't (for example "basic wage, without allowances", from Art 1, uncited), and the judge fails it as the rubric says to. The labels, drafted by Claude, pass them. One item, jc-026, is a judge error: it treats a partial Art 44 list as complete. On 2026-10-19 the owner relabelled the four as fail. Grounding agreement is now 90%, kappa 0.78 (the claims check alone 80%, 0.59).

## Review

The code changes (H2 and the reporting) went through three rounds of independent review by four reviewers: Claude Opus 5.5, Sonnet 5.5, Haiku 4.5 and GPT-6 Luna. Round 1 found that in a bilingual pair the guard counted articles read by the other half (all four reviewers), that Arabic-Indic article numbers never matched, and that sent-back answers were invisible to the report. All were fixed with tests. Rounds 2 and 3 found only small issues, which were fixed or dismissed.

## Not tried

- A held-out grounding set, written after this work, to measure H3 without the tuning bias.
- `calc-gratuity-ar-001` still fails 3/3, as in v1: the agent answers "not found" for a national worker.
