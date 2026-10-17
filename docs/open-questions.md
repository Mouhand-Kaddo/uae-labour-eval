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

Until this is decided, the annual-leave tool gives nothing for exactly 180 days of service, counts part months under (b) pro rata (service days × 2 ÷ 30), gives 30 days per completed 365-day year plus part years pro rata (days × 30 ÷ 365), and returns OQ-005 with every result that rests on one of these readings.

**Decision:** _open_

## OQ-006: Temporary work and "less than a year" in ER Art 30(2); English and Arabic differ

- **ER Art 30(2) (EN):** "The end of service pay shall not be applicable in the event of operating under a temporary employment model or if its duration is less than a year."
- **ER Art 30(2) (AR):** "لا تنطبق مكافأة نهاية الخدمة في حال العمل بنمط التوظيف المؤقت إذا كانت مدته أقل من سنة" (end-of-service pay does not apply to work under the temporary pattern *if its duration is less than a year*).

The English reads as two separate exclusions (all temporary work, or any contract under a year). The Arabic reads as one: temporary work shorter than a year. The portal says the Arabic prevails, which would mean temporary work of a year or more earns gratuity, but the Arabic doesn't say how it is computed (Art 51 as for full-time, or otherwise).

Questions:
1. Does temporary work of one year or more earn gratuity?
2. If so, is it computed under Art 51 like full-time work?
3. Does "less than a year" also apply to part-time and job-sharing (only relevant under the English reading)?

Until this is decided, the gratuity tool returns no gratuity for temporary work, cites ER Art 30(2) and returns OQ-006; cases that depend on it carry `depends_on: [OQ-006]`.

**Decision:** _open_

## OQ-007: English Art 60 contradicts itself

- **EN Art 60** gives a fine as "two million AED (1,000,000)". The Arabic says one million (مليون).

Not used by any calculation tool. Recorded so `cite` cases on penalties use the Arabic figure.

**Decision:** _open_

## OQ-008: Which basic wage does ER Art 30(1) pro-rate for part-time and job-sharing workers?

- **ER Art 30(1) (EN):** "The annual number of working hours stipulated in the employment contract divided by the annual number of working hours under a full-time contract, multiplied by 100 equals the percentage multiplied by the value of the end of service pay under a full-time employment contract."
- **Art 51(5):** the gratuity is calculated "according to the last basic wage received by the foreign Worker".
- **ER Art 5(1)(b) (EN), job sharing:** tasks are shared between workers "and it shall reflect on the wage due to each of them in order to be proportionate. Workers shall be treated in accordance with the controls of parttime jobs."
- **ER Art 30(1) (AR):** "عدد ساعات العمل الواردة بعقد العمل في السنة مقسومًا على عدد ساعات العمل في عقد الدوام الكامل بالسنة مضروبًا في 100 يساوي النسبة مضروبة في قيمة مكافأة نهاية الخدمة لعقد العمل بالدوام الكامل." Like the English, it names no wage.

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

## OQ-010: How ER Art 18 turns part-time hours into annual leave

- **Art 29(2) (EN):** "The part-time Worker is entitled to an annual leave according to the actual working hours spent by the Worker with the Employer ... in accordance with what is determined by the Executive Regulation".
- **ER Art 18 (EN):** the duration "shall be determined based upon the total working hours after converting it to working days, divided by the number of working days per annum, multiplied by the leaves determined by law, with a minimum limit of five working days per annum for annual leaves; and in calculating these due leaves, the part of a day shall be considered as a full day". Clause 4: the percentage is the yearly part-time hours ÷ full-time hours × 100.
- **ER Art 18 (AR):** "وتحدد مدتها على أساس مجموع ساعات العمل بعد تحويلها إلى أيام عمل، مقسومًا على عدد أيام العمل في السنة، مضروبًا في الإجازات المقررة قانونًا، وذلك بحد أدنى خمسة أيام عمل في السنة للإجازات السنوية، وفي حساب هذه الإجازات المستحقة يعد الجزء من اليوم يومًا كاملاً".

Questions:
1. For service that is not a whole year, is the five-day minimum pro-rated, applied in full, or not applied?
2. Is a part day rounded up on the total leave, or on each year's leave?
3. ER Art 18 counts "working days" while Art 29(1) counts "days": are part-time leave days working days and full-time leave days calendar days?

Until this is decided, the annual-leave tool takes the full-time entitlement for the same service, multiplies it by the hours percentage (but not less than 5 ÷ 30, the five-day minimum as a share of a 30-day year), rounds the total up to a whole day, and returns OQ-010 with every part-time result.

**Decision:** _open_

## OQ-011: Annual leave for six months' service or less

- **Art 29(1)(b):** two days a month "if his service period is more than six months and less than one year."
- **Art 29(1)(c):** "A leave for parts of the last year he spent at work, in the event that his service ends before using his annual leave balance."
- **Art 29(9) (AR):** "كما يستحق أجرة الإجازة عن أجزاء السنة بنسبة ما قضاه منها في العمل" (he is also entitled to leave pay for parts of the year in proportion to the time worked); the English has no such words (OQ-004).

Read alone, (b) gives a worker with six months' service or less no leave. (c) and the Arabic 29(9) could give a pro-rata leave for any part of a year, including a first and only year. Does a worker whose service ends within six months earn any annual leave or leave pay?

Until this is decided, the annual-leave tool gives no leave for fewer than 180 days of service and returns OQ-011 with that result (exactly 180 days is OQ-005).

**Decision:** _open_

## OQ-012: A contract notice period outside 30–90 days

- **Art 43(1):** the notice period agreed in the contract must be "not less than thirty (30) days, and not more than ninety (90) days."
- **Art 43(3):** pay in lieu of notice equals "the Worker's wage for the entire warning period or the remaining part of it."
- **Art 65(3):** "Every condition that violates the provisions of this Decree by law ... shall be considered null unless it is more beneficial to the Worker".

When a contract sets, say, 15 or 120 days, which notice period applies: the nearest limit (30 or 90), the contract's figure if it is more beneficial to the worker, or none? And which period does pay in lieu use? The notice tool reports the period as below the minimum or above the maximum, returns OQ-012, and computes no pay in lieu until this is decided.

**Decision:** _open_

---

## Facts still to verify (agent work, not owner decisions)

- Effective dates of Decree-Laws 14/2022, 20/2023 and 9/2024: still not checked against the official gazette. Checked on 2026-10-17 (#5):
  - The portal (uaelegislation.gov.ae) answers scripts with 403 and a headless browser with a Cloudflare challenge; the MOHRE copy of the consolidated law refused connections. The Wayback Machine has no capture of any of the three decree-laws' portal pages or PDFs (legislation 1637 = 14/2022 has none; the portal IDs of 20/2023 and 9/2024 were not found), so they are not in the corpus manifest yet.
  - The portal's own page for the Labour Law ([Wayback 2026-10-04](https://web.archive.org/web/20261004194241id_/https://uaelegislation.gov.ae/en/legislations/1541)) gives: issued 20 Sep 2021, effective 02 Feb 2022, Official Gazette No 712 (ملحق) of 26 Sep 2021, "Legislation Amendments 3", "The last update on this law was listed on 29 Jul 2024". The amendment count was 2 on [2024-05-24](https://web.archive.org/web/20240524080227id_/https://uaelegislation.gov.ae/en/legislations/1541) and 3 by [2024-11-13](https://web.archive.org/web/20241113040436id_/https://uaelegislation.gov.ae/en/legislations/1541?keyword=).
  - Secondary sources only: 14/2022 dated 15 Sep 2022 ([Lexis Middle East](https://www.lexismiddleeast.com/law/UnitedArabEmirates/DecreeLaw_33_2021/en)); 20/2023 replaces Art 54 and takes effect 1 Jan 2024 ([BSA](https://bsalaw.com/insight/an-overview-of-federal-decree-law-no-20-of-2023-concerning-jurisdictional-rules-regarding-labour-disputes/)); 9/2024 issued 29 Jul 2024, replaces Arts 54 and 60, effective date reported differently (31 Aug 2024 by [Gulf News](https://gulfnews.com/living-in-uae/ask-us/3-major-changes-to-uae-labour-law--all-you-need-to-know-1.1724235733163) and [Fichte](https://fichtelegal.com/new-amendments-to-uae-federal-decree-law-no-33-2021-on-labour-relations/), 28 Aug 2024 by another firm). A government copy of 20/2023 was listed at u.ae but returned 404.
- Whether the Minister extended the Art 68(2) deadline for converting unlimited contracts. Art 68(3) lets employers calculate gratuity for those contracts under the 1980 law, which is outside the corpus, so the agent answers "not found" for it either way.
- Whether any amendment to the Labour Law or the Executive Regulations was issued after 29 July 2024 (none found on 2026-10-17). The portal's Labour Law page still listed 3 amendments and a last update of 29 Jul 2024 on 2026-10-04 (link above); the Executive Regulations' own amendment list was not checked.
