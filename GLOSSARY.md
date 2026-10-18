# UAE Labour Eval

An eval harness that measures a bilingual (English/Arabic) assistant for UAE private-sector labour law. The harness is the product; the agent is the thing it measures.

Legal terms use the wording of the official text. Where the official English translation uses an awkward word, the canonical term here is the plain one and the official word is noted. The Arabic text prevails over the English (stated on the official legislation portal).

## Legal instruments

**Labour Law** / المرسوم بقانون اتحادي رقم (33) لسنة 2021 بشأن تنظيم علاقات العمل:
Federal Decree-Law No. 33 of 2021 Regulating Labour Relations, in its consolidated (amended) form.
_Avoid_: Labour Code, the 1980 law, "the new law"

**Executive Regulations** / اللائحة التنفيذية:
Cabinet Resolution No. 1 of 2022, which details how the Labour Law is applied.
_Avoid_: bylaws, implementing rules, ER (in prose)

**Instrument**:
One legal text the corpus cites as a unit, such as the Labour Law or the Executive Regulations.
_Avoid_: document, law (when either instrument is meant)

**Article** / المادة:
A numbered provision of an instrument, the unit every citation points to.
_Avoid_: section (for legal text), clause (for the whole article)

**Clause** / البند:
A numbered paragraph inside an article, such as Art 51(2).
_Avoid_: sub-article, paragraph

**Amending decree-law**:
A later decree-law that changes articles of the Labour Law; its changes are already folded into the consolidated text.
_Avoid_: update, revision

## Parties and work

**Worker** / العامل:
A natural person authorised by the Ministry to work for a licensed establishment under an employer's direction.
_Avoid_: employee, staff

**Foreign worker** / العامل الأجنبي:
A worker who is not a UAE national; the only worker the gratuity rules of the Labour Law pay out to.
_Avoid_: expat, non-national

**National worker** / العامل المواطن:
A UAE national worker, whose end-of-service entitlement comes from pensions legislation instead.
_Avoid_: Emirati employee

**Employer** / صاحب العمل:
A natural or legal person employing one or more workers for a wage.
_Avoid_: company, sponsor

**Establishment** / المنشأة:
A licensed business unit in which workers are employed.
_Avoid_: company, entity

**Work pattern** / نمط العمل:
The kind of working arrangement in a contract: full-time, part-time, temporary or flexible (plus remote and job-sharing in the Executive Regulations).
_Avoid_: contract type, work model

**Full-time** / الدوام الكامل:
Working for one employer for the full daily working hours throughout business days.

**Part-time** / الدوام الجزئي:
Working for one or more employers for a specified number of hours or days.

**Temporary work** / العمل المؤقت:
Work whose nature requires a set period, or which ends when a specific job is completed.

**Fixed-term contract** / عقد العمل لمدة محددة:
The only contract form under the Labour Law since Decree-Law 14/2022: a contract for a definite, renewable period.
_Avoid_: limited contract

**Unlimited contract** / عقد العمل غير محدد المدة:
A contract with no end date, concluded under the 1980 law, which employers had to convert to a fixed-term contract (Art 68).
_Avoid_: open-ended contract, indefinite contract

**Continuous service** / الخدمة المستمرة:
Uninterrupted service with the same employer or its legal successor from the start date.
_Avoid_: tenure, length of employment

## Pay and entitlements

**Basic wage** / الأجر الأساسي:
The wage stated in the employment contract, excluding all allowances and benefits in kind.
_Avoid_: base salary, basic salary

**Wage** / الأجر:
The basic wage plus cash allowances and benefits in kind due under the contract or the law.
_Avoid_: total wage, gross salary, package, total salary

**Gratuity** / مكافأة نهاية الخدمة:
The end-of-service payment owed to a foreign worker with at least one year of continuous service.
_Avoid_: severance, end-of-service benefit, EOSB, bonus

**Annual leave** / الإجازة السنوية:
Paid leave a worker earns for each period of service.
_Avoid_: vacation, holiday

**Leave cash-out** / بدل نقدي عن الإجازة:
Cash paid instead of untaken annual leave.
_Avoid_: leave encashment, leave salary

**Notice period** / مدة الإنذار:
The period, set in the contract, that a party must give before terminating it; 30 to 90 days outside probation. The official English calls it "Warning Period".
_Avoid_: warning period, notice

**Pay in lieu of notice** / بدل الإنذار:
The wage for all or the rest of the notice period, owed by the party that does not honour it.
_Avoid_: notice pay, notice compensation

**Probation period** / فترة التجربة:
A period of up to six months from the start of work in which the employer evaluates the worker and either party can end the contract on short notice.
_Avoid_: trial period

## Corpus and retrieval

**Corpus**:
The set of instruments the agent may search and cite, in every language they are published in.
_Avoid_: knowledge base, documents, dataset

**Source**:
One saved file of one instrument in one language, with its official URL, retrieval date and hash.
_Avoid_: document, PDF (when the file format doesn't matter)

**Corpus manifest**:
The list of sources a corpus is built from, with the hash each fetched file must match.
_Avoid_: source list, config

**Chunk**:
A piece of one article in one language, the unit search returns.
_Avoid_: passage, snippet, document

**Pack**:
Everything specific to one legal domain: its corpus manifest, calculation tools, prompt, cases and rubrics.
_Avoid_: plugin, domain module

## Agent

**Agent**:
The tool-calling assistant being measured.
_Avoid_: bot, assistant (in eval output), model (when the whole loop is meant)

**Calculation tool**:
A deterministic function that computes a statutory entitlement from stated facts, citing the articles it applies.
_Avoid_: calculator, helper

**Final answer**:
The agent's structured reply: answer text, cited articles, and a status of answered, refused or not found.
_Avoid_: response, output

**Refusal**:
A final answer that declines because the question asks for legal advice or is out of scope.
_Avoid_: rejection, decline

**Not found**:
A final answer saying the corpus does not answer the question; distinct from a refusal.
_Avoid_: unknown, no answer

**Legal advice**:
Guidance on what a specific person should do, or how their case would turn out; computing an entitlement from stated facts is not legal advice.
_Avoid_: legal opinion, consultation

## Evaluation

**Case**:
One frozen test input with its expected result and scoring method.
_Avoid_: test, example, sample, item

**Category**:
The kind of behaviour a case measures: calc, cite, grounding, refuse, inject or bilingual.
_Avoid_: type, suite

**Bilingual pair**:
A bilingual case: the same question in English and Arabic (its two halves), run separately and scored as one case that passes only if each half is right and the two agree.
_Avoid_: translation case, parallel case

**Reviewed case**:
A case whose expected result the project owner has checked; only reviewed cases count towards headline scores.
_Avoid_: verified case, gold case

**Planted chunk**:
A fake chunk carrying hidden instructions, added to search results for one inject case only.
_Avoid_: poisoned document, injection payload

**Open question**:
A recorded ambiguity in the sources that the project owner decides, never the agent or the code.
_Avoid_: assumption, TBD

**Scorer**:
A rule that decides whether one case passed.
_Avoid_: grader, metric, checker

**Judge**:
The model that scores free-text answers against a rubric.
_Avoid_: grader, evaluator, LLM-as-judge

**Rubric**:
The written criteria the judge applies to one category.
_Avoid_: prompt, guidelines

**Judge agreement**:
How often the judge's verdicts match the project owner's hand labels, with Cohen's kappa.
_Avoid_: judge accuracy, calibration

**Judge-check set**:
About 50 answers, real ones from a run plus deliberately broken ones, that the project owner labels without seeing the judge's verdicts; judge agreement is measured on it.
_Avoid_: gold set, calibration set

**Run**:
One execution of a set of cases against one agent model, with a fixed case-set hash.
_Avoid_: eval, job, experiment

**Trace**:
The step-by-step record of one case within a run, complete enough to replay it.
_Avoid_: log, transcript

**Headline score**:
A category's pass rate over reviewed cases, reported with n and a 95% interval.
_Avoid_: accuracy (unqualified), score

**Safety pass rate**:
The pass rate over reviewed refuse and inject cases together.
_Avoid_: safety score, guardrail rate

**Threshold**:
The minimum headline score or safety pass rate `eval gate` accepts for a run.
_Avoid_: target, baseline

**Ledger**:
The record of the cost of every paid API call, used to enforce the budget.
_Avoid_: spend log, billing log

**Budget**:
The USD 20 ceiling on all API spend for v1.
_Avoid_: quota, limit (unqualified)
