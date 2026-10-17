# Open questions

Ambiguities found in the sources. The project owner decides each one; the code and the agent never do. Calculation rules that depend on a decision cite the article and the question ID, and cases that depend on an open question cannot be marked reviewed (ADR-0010).

Quotes are from the consolidated texts on uaelegislation.gov.ae (Labour Law: legislation 1541; Executive Regulations: legislation 1547), read on 2026-10-17 from Wayback Machine copies of the official URLs. The portal states that the Arabic text prevails over the English. They will be re-quoted from the hashed sources once fetched.

**Blocks calc:** OQ-001, OQ-002 and OQ-003 are decided (#4); the calculation tools follow those decisions.

---

## OQ-001: How is a day's basic wage derived? (blocks calc)

- **Art 51(2):** gratuity is "calculated according to the basic wage, as follows: a. The wage of twenty-one (21) days for each year of the first five years of service. b. The wage of thirty (30) days for each year in excess of that."
- **Art 67:** "a calendar year shall be deemed as three hundred and sixty-five (365) days, and the month shall be deemed as thirty (30) days."

The law never says how to turn a monthly basic wage into "the wage of one day".

Options:
- **A.** monthly basic wage ÷ 30 (reads Art 67's 30-day month as the divisor)
- **B.** monthly basic wage × 12 ÷ 365 (reads Art 67's 365-day year as the divisor)

Also affects leave cash-out (OQ-003) and pay in lieu of notice.

**Decision:** B. A day's basic wage is monthly basic wage × 12 ÷ 365. Decided by the project owner on 2026-10-17 (#4).

## OQ-002: Is the gratuity cap two years of basic wage or of wage? (blocks calc)

- **Art 51(6) (EN):** "the total end-of-service gratuity for the foreign Worker does not exceed two years' wage."
- **Art 51(6) (AR):** "ألا تزيد مكافأة نهاية الخدمة للعامل الأجنبي في مجموعها عن أجر سنتين"
- **Art 1** defines **Wage** (الأجر) as the basic wage *plus* allowances and benefits in kind, separately from **Basic Wage** (الأجر الأساسي). The gratuity itself is computed on the basic wage (Art 51(2), 51(5)).

Read literally, the cap uses the defined term "Wage", which includes allowances, while everything else in Art 51 uses the basic wage.

Options:
- **A.** cap = 24 × monthly basic wage
- **B.** cap = 24 × monthly wage (basic plus allowances)
- **C.** cap = 730 days × the daily rate from OQ-001 (A or B base)

**Decision:** two years of basic wage. Decided by the project owner on 2026-10-17 (#4). With the OQ-001 daily rate, options A and C on a basic-wage base give the same figure: 730 × (monthly × 12 ÷ 365) = 24 × monthly basic wage.

## OQ-003: Which wage pays for untaken annual leave? (blocks calc)

- **ER Art 19(1):** carried-forward leave may be paid in cash "in accordance with the wage he earns at the time the leave is due."
- **ER Art 19(2):** on termination, the worker receives "a cash equivalent of the balance of his annual leaves due by law in accordance with his basic salary."
- **Art 29(9) (AR)** ends: "وتحسب وفق الأجر الأساسي" (calculated according to the basic wage). The English Art 29(9) has no such words (see OQ-004).

Termination cash-out looks like basic wage from both ER 19(2) and the Arabic Art 29(9). Cash-out during employment (ER 19(1)) says "wage".

Options:
- **A.** termination: basic wage; during employment: wage (follow each clause as written)
- **B.** basic wage in both situations

**Decision:** B. Basic wage in both situations. Decided by the project owner on 2026-10-17 (#4).

## OQ-004: Arabic and English Art 29(9) differ

- **EN:** "The Worker is entitled to receive wages for the days of the entitled rest days if he leaves the work before using it, regardless of their duration, in relation to the period for which he has not obtained his leave."
- **AR adds:** "كما يستحق أجرة الإجازة عن أجزاء السنة بنسبة ما قضاه منها في العمل، وتحسب وفق الأجر الأساسي" (he is also entitled to leave pay for parts of the year in proportion to the time worked, calculated on the basic wage).

The Arabic prevails per the portal. Question: should the agent quote the Arabic rule when answering in English, and should English `cite` cases expect the pro-rata rule?

**Decision:** _open_

## OQ-005: Annual-leave boundaries in Art 29(1)

- **Art 29(1)(a):** "Thirty days for each year of his extended service." "Extended service" (الممتدة) is not defined.
- **Art 29(1)(b):** "Two days for each month if his service period is more than six months and less than one year."

Questions:
1. Does a worker with exactly 6 months of service get anything under (b), given "more than six months"?
2. Under (b), are part months counted pro rata, rounded down, or ignored?
3. Does (a) mean 30 days per completed year only, with part years falling under (c) "parts of the last year"?

**Decision:** _open_

## OQ-006: Scope of "less than a year" in ER Art 30(2)

- **ER Art 30(2):** "The end of service pay shall not be applicable in the event of operating under a temporary employment model or if its duration is less than a year."

Does "if its duration is less than a year" apply only to temporary work, or to part-time and job-sharing too? (Art 51(2) already requires one year of continuous service for full-time workers.)

**Decision:** _open_

## OQ-007: English Art 60 contradicts itself

- **EN Art 60** gives a fine as "two million AED (1,000,000)". The Arabic says one million (مليون).

Not used by any calculation tool. Recorded so `cite` cases on penalties use the Arabic figure.

**Decision:** _open_

## OQ-008: Which basic wage does ER Art 30(1) pro-rate for part-time and job-sharing workers?

- **ER Art 30(1) (EN):** "The annual number of working hours stipulated in the employment contract divided by the annual number of working hours under a full-time contract, multiplied by 100 equals the percentage multiplied by the value of the end of service pay under a full-time employment contract."
- **Art 51(5):** the gratuity is calculated "according to the last basic wage received by the foreign Worker".
- **ER Art 5(1)(b) (EN), job sharing:** tasks are shared between workers "and it shall reflect on the wage due to each of them in order to be proportionate. Workers shall be treated in accordance with the controls of parttime jobs."
- The Arabic ER Art 30 is not quoted yet: its text layer still has unmapped glyphs (ADR-0004).

"The value of the end of service pay under a full-time employment contract" doesn't say whose wage that value is computed on. A part-time worker's own basic wage is usually already reduced for the hours worked, so applying the percentage to a gratuity computed on that wage would reduce it twice.

Options:
- **A.** full-time gratuity computed on the worker's own (part-time) last basic wage, then × the percentage
- **B.** full-time gratuity computed on the full-time equivalent basic wage for the same job, then × the percentage

Until this is decided, the gratuity tool applies the percentage to a full-time gratuity computed on the basic wage it is given (A when given the worker's own wage), and returns OQ-008 with every part-time or job-sharing result.

**Decision:** _open_

## OQ-009: Gratuity for flexible work

- **Art 52:** the Executive Regulations set the gratuity "for foreign workers in work patterns other than full-time".
- **ER Art 30** covers only "a part-time or employment sharing model" (30(1)) and temporary work (30(2)). ER Art 10(4)(d) lists a "Flexible employment contract" as a contract type.
- Remote work is not a gap: ER Art 5(1)(a) says it applies "whether the work was parttime or fulltime", so the full-time or part-time rule follows.

Is a flexible worker's gratuity computed like part-time under ER Art 30(1), like full-time under Art 51, or not at all? The gratuity tool rejects the flexible work pattern until this is decided.

**Decision:** _open_

---

## Facts still to verify (agent work, not owner decisions)

- Effective dates of Decree-Laws 14/2022, 20/2023 and 9/2024: so far only from law firms and news; to be checked against the official gazette.
- Whether the Minister extended the Art 68(2) deadline for converting unlimited contracts. Art 68(3) lets employers calculate gratuity for those contracts under the 1980 law, which is outside the corpus, so the agent answers "not found" for it either way.
- Whether any amendment to the Labour Law or the Executive Regulations was issued after 29 July 2024 (none found on 2026-10-17).
