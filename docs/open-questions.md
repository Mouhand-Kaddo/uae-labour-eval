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

**Decision:** Treat the Arabic Art 29(9) sentence as law in both languages: leave pay for parts of the year is pro rata and on basic wage, and English answers state it (citing Art 29(9), noting the Arabic prevails). Research confidence: high (MOHRE's English translation, MOHRE guidance and u.ae all carry the sentence). Decided by the project owner on 2026-10-18 by adopting the recommendation in the research report `reports/UAE labour law open questions.md`.

## OQ-005: Annual-leave boundaries in Art 29(1)

- **Art 29(1)(a):** "Thirty days for each year of his extended service." "Extended service" (الممتدة) is not defined.
- **Art 29(1)(b):** "Two days for each month if his service period is more than six months and less than one year."

Questions:
1. Does a worker with exactly 6 months of service get anything under (b), given "more than six months"?
2. Under (b), are part months counted pro rata, rounded down, or ignored?
3. Does (a) mean 30 days per completed year only, with part years falling under (c) "parts of the last year"?

The annual-leave tool gives nothing for exactly 180 days of service, counts part months under (b) pro rata (service days × 2 ÷ 30), gives 30 days per completed 365-day year plus part years pro rata (days × 30 ÷ 365), and returns OQ-005 with every result that rests on one of these readings.

**Decision:** Keep the annual-leave tool's reading: nothing at exactly six months ("more than six months"); part months pro rata; 30 days per completed year, with part years at 30/365. Provisional (research confidence low–medium; no official worked example). Decided by the project owner on 2026-10-18 by adopting the recommendation in the research report `reports/UAE labour law open questions.md`.

## OQ-006: Temporary work and "less than a year" in ER Art 30(2); English and Arabic differ

- **ER Art 30(2) (EN):** "The end of service pay shall not be applicable in the event of operating under a temporary employment model or if its duration is less than a year."
- **ER Art 30(2) (AR):** "لا تنطبق مكافأة نهاية الخدمة في حال العمل بنمط التوظيف المؤقت إذا كانت مدته أقل من سنة" (end-of-service pay does not apply to work under the temporary pattern *if its duration is less than a year*).

The English reads as two separate exclusions (all temporary work, or any contract under a year). The Arabic reads as one: temporary work shorter than a year. The portal says the Arabic prevails, which would mean temporary work of a year or more earns gratuity, but the Arabic doesn't say how it is computed (Art 51 as for full-time, or otherwise).

Questions:
1. Does temporary work of one year or more earn gratuity?
2. If so, is it computed under Art 51 like full-time work?
3. Does "less than a year" also apply to part-time and job-sharing (only relevant under the English reading)?

The gratuity tool gives temporary work under one year no gratuity (ER Art 30(2), no OQ: both languages agree) and temporary work of one year or more the Art 51 gratuity × the hours ratio (full-time hours unless a ratio is given), returning OQ-006. Part-time and job sharing under one year get nothing, citing Art 51(2)–(3) and ER Art 30(1).

**Decision:** Arabic reading. (1) Temporary work of one year or more earns gratuity; only temporary work under one year is excluded. (2) It is computed as the Art 51 gratuity × (contracted annual hours ÷ full-time annual hours), which equals plain Art 51 on full-time hours. (3) Part-time and job-sharing work under one year earns nothing through Art 51(2)–(3), not ER Art 30(2). Research confidence: high for (1), low–medium for (2) (provisional), medium–high for (3). Decided by the project owner on 2026-10-18 by adopting the recommendation in the research report `reports/UAE labour law open questions.md`.

## OQ-007: English Art 60 contradicts itself

- **EN Art 60** gives a fine as "two million AED (1,000,000)". The Arabic says one million (مليون).

Not used by any calculation tool. Recorded so `cite` cases on penalties use the Arabic figure.

**Decision:** The Art 60(1) maximum fine is AED 1,000,000 (Arabic text, the English numeral, English Art 60(2)). Research confidence: high. Decided by the project owner on 2026-10-18 by adopting the recommendation in the research report `reports/UAE labour law open questions.md`.

## OQ-008: Which basic wage does ER Art 30(1) pro-rate for part-time and job-sharing workers?

- **ER Art 30(1) (EN):** "The annual number of working hours stipulated in the employment contract divided by the annual number of working hours under a full-time contract, multiplied by 100 equals the percentage multiplied by the value of the end of service pay under a full-time employment contract."
- **Art 51(5):** the gratuity is calculated "according to the last basic wage received by the foreign Worker".
- **ER Art 5(1)(b) (EN), job sharing:** tasks are shared between workers "and it shall reflect on the wage due to each of them in order to be proportionate. Workers shall be treated in accordance with the controls of parttime jobs."
- **ER Art 30(1) (AR):** "عدد ساعات العمل الواردة بعقد العمل في السنة مقسومًا على عدد ساعات العمل في عقد الدوام الكامل بالسنة مضروبًا في 100 يساوي النسبة مضروبة في قيمة مكافأة نهاية الخدمة لعقد العمل بالدوام الكامل." Like the English, it names no wage.

"The value of the end of service pay under a full-time employment contract" doesn't say whose wage that value is computed on. A part-time worker's own basic wage is usually already reduced for the hours worked, so applying the percentage to a gratuity computed on that wage would reduce it twice.

Options:
- **A.** full-time gratuity computed on the worker's own (part-time) last basic wage, then × the percentage
- **B.** full-time gratuity computed on the full-time equivalent basic wage for the same job, then × the percentage

The gratuity tool takes the worker's own basic wage and the hours ratio, computes the full-time value on the full-time-equivalent wage (own wage ÷ ratio), applies the percentage, and returns OQ-008 with every part-time or job-sharing result.

**Decision:** Option B: the full-time gratuity in ER Art 30(1) is computed on the full-time-equivalent basic wage, so the hours reduction applies once (equivalently, Art 51 on the worker's own proportionate wage). Provisional (research confidence low–medium; the text is silent). Decided by the project owner on 2026-10-18 by adopting the recommendation in the research report `reports/UAE labour law open questions.md`.

## OQ-009: Gratuity for flexible work

- **Art 52:** the Executive Regulations set the gratuity "for foreign workers in work patterns other than full-time".
- **ER Art 30** covers only "a part-time or employment sharing model" (30(1)) and temporary work (30(2)). ER Art 10(4)(d) lists a "Flexible employment contract" as a contract type.
- Remote work is not a gap: ER Art 5(1)(a) says it applies "whether the work was parttime or fulltime", so the full-time or part-time rule follows.

Is a flexible worker's gratuity computed like part-time under ER Art 30(1), like full-time under Art 51, or not at all? Given the contracted hours ratio, the gratuity tool computes it like part-time (OQ-008 wage basis, nothing under one year) and returns this question; without hours it answers with outcome `flexible_hours_not_stated`, no amount, and this question.

**Decision:** Flexible work is computed under ER Art 30(1) on the contracted annual hours, with the one-year threshold from Art 51; the result is undetermined only when the contract states no hours. Provisional (research confidence low–medium). Decided by the project owner on 2026-10-18 by adopting the recommendation in the research report `reports/UAE labour law open questions.md`.

## OQ-010: How ER Art 18 turns part-time hours into annual leave

- **Art 29(2) (EN):** "The part-time Worker is entitled to an annual leave according to the actual working hours spent by the Worker with the Employer ... in accordance with what is determined by the Executive Regulation".
- **ER Art 18 (EN):** the duration "shall be determined based upon the total working hours after converting it to working days, divided by the number of working days per annum, multiplied by the leaves determined by law, with a minimum limit of five working days per annum for annual leaves; and in calculating these due leaves, the part of a day shall be considered as a full day". Clause 4: the percentage is the yearly part-time hours ÷ full-time hours × 100.
- **ER Art 18 (AR):** "وتحدد مدتها على أساس مجموع ساعات العمل بعد تحويلها إلى أيام عمل، مقسومًا على عدد أيام العمل في السنة، مضروبًا في الإجازات المقررة قانونًا، وذلك بحد أدنى خمسة أيام عمل في السنة للإجازات السنوية، وفي حساب هذه الإجازات المستحقة يعد الجزء من اليوم يومًا كاملاً".

Questions:
1. For service that is not a whole year, is the five-day minimum pro-rated, applied in full, or not applied?
2. Is a part day rounded up on the total leave, or on each year's leave?
3. ER Art 18 counts "working days" while Art 29(1) counts "days": are part-time leave days working days and full-time leave days calendar days?

The annual-leave tool takes the full-time entitlement for the same service, multiplies it by the hours percentage (but not less than 5 ÷ 30, the five-day minimum as a share of a 30-day year), rounds the total up to a whole day, and returns OQ-010 with every part-time result.

**Decision:** Keep the tool's reading: full-time entitlement × hours ratio, the five-day floor pro-rated for part years, total rounded up. Provisional (research confidence low). Decided by the project owner on 2026-10-18 by adopting the recommendation in the research report `reports/UAE labour law open questions.md`.

## OQ-011: Annual leave for six months' service or less

- **Art 29(1)(b):** two days a month "if his service period is more than six months and less than one year."
- **Art 29(1)(c):** "A leave for parts of the last year he spent at work, in the event that his service ends before using his annual leave balance."
- **Art 29(9) (AR):** "كما يستحق أجرة الإجازة عن أجزاء السنة بنسبة ما قضاه منها في العمل" (he is also entitled to leave pay for parts of the year in proportion to the time worked); the English has no such words (OQ-004).

Read alone, (b) gives a worker with six months' service or less no leave. (c) and the Arabic 29(9) could give a pro-rata leave for any part of a year, including a first and only year. Does a worker whose service ends within six months earn any annual leave or leave pay?

The annual-leave tool gives no leave for fewer than 180 days of service and returns OQ-011 with that result (exactly 180 days is OQ-005).

**Decision:** Keep "no annual leave or leave pay for six months' service or less" as the default. Provisional and weakest of the decisions (research confidence low): Art 29(3) and the Arabic Art 29(9) arguably point the other way. Decided by the project owner on 2026-10-18 by adopting the recommendation in the research report `reports/UAE labour law open questions.md`.

## OQ-012: A contract notice period outside 30–90 days

- **Art 43(1):** the notice period agreed in the contract must be "not less than thirty (30) days, and not more than ninety (90) days."
- **Art 43(3):** pay in lieu of notice equals "the Worker's wage for the entire warning period or the remaining part of it."
- **Art 65(3):** "Every condition that violates the provisions of this Decree by law ... shall be considered null unless it is more beneficial to the Worker".

When a contract sets, say, 15 or 120 days, which notice period applies: the nearest limit (30 or 90), the contract's figure if it is more beneficial to the worker, or none? And which period does pay in lieu use? Given who terminates, the notice tool applies the decision below: it reports the period as below the minimum or above the maximum, gives the applicable period, prices pay in lieu on it, and returns OQ-012. Without who terminates, an out-of-range result has no applicable period or pay in lieu.

**Decision:** Worker-favourable split: a contract notice term that hurts the worker is replaced by the nearest limit (30 or 90 days); a term that helps the worker stands; pay in lieu uses the period that applies, at the last wage. Research confidence: medium for harmful terms, low for favourable terms (provisional). Decided by the project owner on 2026-10-18 by adopting the recommendation in the research report `reports/UAE labour law open questions.md`.

## OQ-013: How long is "six months" of probation?

- **Art 9(1):** the employer may appoint the worker under probation "for a period not exceeding six (6) months as of the date of commencing work".
- **Art 67:** "a calendar year shall be deemed as three hundred and sixty-five (365) days, and the month shall be deemed as thirty (30) days."

Options:
- **A.** six months = 180 days (Art 67's 30-day month), so a probation from 1 January to 30 June (181 days) is too long
- **B.** six calendar months from the start date (Gregorian calendar, Art 67), so 1 January to 30 June is within the limit

The probation tool uses A and returns OQ-013 only for probations of 181–184 days, where six calendar months could give the other answer; only cases in that window carry `depends_on: [OQ-013]`.

**Decision:** Option A: six months of probation is 180 days (Art 67's 30-day month). Only probations ending on days 181–184 differ from the calendar reading. Research confidence: medium. Decided by the project owner on 2026-10-18 by adopting the recommendation in the research report `reports/UAE labour law open questions.md`.

## OQ-014: Arabic and English Art 44(8) differ on "within one year"

- **EN:** "If the Worker is absent from work without a legitimate reason or an excuse acceptable to the Employer for more than twenty (20) non-consecutive days, or more than seven (7) consecutive days."
- **AR:** "تغيب العامل دون سبب مشروع أو عذر يقبله صاحب العمل لأكثر من (20) عشرين يومًا متقطعة خلال السنة الواحدة، أو أكثر من (7) سبعة أيام متتالية" (absence without a legitimate reason or an excuse the employer accepts for more than 20 non-consecutive days *within one year*, or more than 7 consecutive days).

The English gives no period over which the 20 non-consecutive days are counted; the Arabic counts them within one year.

**Decision:** The Arabic applies (the portal says the Arabic prevails): Art 44(8) allows dismissal without notice for more than 20 non-consecutive days of absence within one year, or more than 7 consecutive days. Decided by the project owner on 2026-10-18.

## OQ-015: How much annual leave may be carried forward?

- **Art 29(5) (AR):** "للعامل بموافقة صاحب العمل ووفق اللوائح التنظيمية المعمول بها في المنشأة، أن يرحل رصيد إجازته السنوية أو أيامًا منها إلى السنة التالية." The English: "The Worker may, upon the approval of the Employer and in accordance with the applicable organizational regulations in the Establishment, carry forward the balance of his annual leave, or days thereof, to the following year."
- **ER Art 19(1) (AR):** opens "مع مراعاة أحكام البندين رقمي (8) و(9) من المادة رقم (29) من المرسوم بقانون" and says "يجوز للعامل ترحيل ما لا يزيد على نصف الإجازة السنوية للسنة التي تليها". The English: "Subject to the provisions of clauses (8) and (9) of Article (29) of the Decree-Law: 1. The worker may carry forward, into the following year, what does not exceed half of the annual leave".

Art 29(5) lets the worker carry forward the balance, or days of it, with the employer's approval and names no limit. ER Art 19(1) caps the carry-forward at half the annual leave, does not mention the employer's approval, and is made subject to Art 29(8) and (9), not 29(5). May a worker carry forward more than half with the employer's approval?

Options:
- **A.** at most half the annual leave (ER Art 19(1)), and only with the employer's approval (Art 29(5))
- **B.** any part of the balance, including all of it, with the employer's approval (Art 29(5) read alone)

**Decision:** A. At most half the annual leave may be carried forward, with the employer's approval, because ER Art 19 is the implementing rule. Provisional (Art 29(5) read alone allows more). Decided by the project owner on 2026-10-18.

---

## Facts still to verify (agent work, not owner decisions)

Verified on 2026-10-18 by the research report `reports/UAE labour law open questions.md` (archived official copies; the live portal and MOHRE still refuse scripts):

- **Three amending decree-laws, no more.** The Ministry of Justice's consolidated Arabic compilation of the labour legislation, current to December 2025, marks every changed provision and attributes changes only to 14/2022, 20/2023 and 9/2024 ([MOJ 2025 compilation](https://www.moj.gov.ae/assets/966b93b0/تشريعات-تنظيم-علاقات-العمل-2025-النسخة-الالكترونية-639015001687388768.aspx)).
  - **14/2022:** changed Art 8(3) (removed the three-year cap on fixed-term contracts). Issued 15 Sep 2022, Official Gazette No. 736 of 28 Sep 2022, in force 29 Sep 2022. Article change primary (MOJ compilation note); dates secondary only (Eastlaws index title, Lexis).
  - **20/2023:** replaced Art 54 (disputes; one-year limitation). Signed **13 Sep 2023** (27 Safar 1445), not 15 Sep as Lexis gives; in force **1 Jan 2024** by its own Art 2 ([MOHRE AR copy](https://web.archive.org/web/20250909074946id_/https://mohre.gov.ae/assets/download/95f9a7d4/%D9%85%D8%B1%D8%B3%D9%88%D9%85%20%D8%A8%D9%82%D8%A7%D9%86%D9%88%D9%86%20%D8%A7%D8%AA%D8%AD%D8%A7%D8%AF%D9%8A%20%D8%B1%D9%82%D9%85%2020%20%D9%84%D8%B3%D9%86%D8%A9%202023%20%D8%A8%D8%AA%D8%B9%D8%AF%D9%8A%D9%84%20%D8%A8%D8%B9%D8%B6%20%D8%A3%D8%AD%D9%83%D8%A7%D9%85%20%D8%A7%D9%84%D9%85%D8%B1%D8%B3%D9%88%D9%85%20%D8%A8%D9%82%D8%A7%D9%86%D9%88%D9%86%20%D8%A7%D8%AA%D8%AD%D8%A7%D8%AF%D9%8A%20%D8%B1%D9%82%D9%85%2033%20%D9%84%D8%B3%D9%86%D8%A9%202021%20%D8%A8%D8%B4%D8%A3%D9%86%20%D8%AA%D9%86%D8%B8%D9%8A%D9%85%20%D8%B9%D9%84%D8%A7%D9%82%D8%A7%D8%AA%20%D8%A7%D9%84%D8%B9%D9%85%D9%84.pdf.aspx); [MOHRE EN copy](https://web.archive.org/web/20250903095312id_/https://www.mohre.gov.ae/assets/download/20670ee7/Federal%20Decree%20Law%20No.%2020%20of%202023%20Amending%20Certain%20Provisions%20of%20Federal%20Decree%20Law%20No.%2033%20of%202021%20Regarding%20the%20Regulation%20of%20Employment%20Relationships.pdf.aspx), third-party translation). Gazette number not found.
  - **9/2024:** replaced Arts 54 and 60, with a transitional Art 2 sending pending appeals to first-instance courts. Issued 29 Jul 2024, Official Gazette No. 780 (supplement) of **31 Jul 2024**, in force **30 days after publication**; sources name 29, 30 or 31 Aug 2024 and none 28 Aug, so state it as "30 days after publication on 31 July 2024". Article changes primary (MOJ); dates secondary.
  - Current Art 54(9) bars claims two years after the employment ends; 20/2023's one-year rule applied only from 1 Jan 2024 until 9/2024 took effect.
- **No amendment after 29 July 2024.** The portal's Labour Law page showed 3 amendments and a last update of 29 Jul 2024 in every capture through [2026-10-04](https://web.archive.org/web/20261004194241id_/https://uaelegislation.gov.ae/en/legislations/1541) (issued 20 Sep 2021, effective 02 Feb 2022, Official Gazette No. 712 (supplement) of 26 Sep 2021).
- **The Executive Regulations were never amended.** Their portal page shows a last update of 3 Feb 2022 and no amendments field ([ER portal page, 2026-10-04](https://web.archive.org/web/20261004194241id_/https://uaelegislation.gov.ae/en/legislations/1547)), and the MOJ compilation has no amendment notes on them.
- **Art 68(2) deadline extended once.** Art 68 itself is unamended. Ministerial Resolution No. 27 of 2023 extended the deadline for converting unlimited contracts once, to **31 Dec 2023** (MOHRE news headline, known from search snippets, and law-firm reports); no second extension found. Art 68(3) gratuity under the 1980 law stays outside the corpus, so the agent answers "not found" for it.
- **Fetchable official copies:** the MOJ 2025 compilation (Arabic, consolidated through 9/2024, includes the ER, live HTTP 200) at the URL above; MOHRE's PDFs of 20/2023 in both languages via Wayback; MOHRE's consolidated PDFs of January 2024 via Wayback (before 9/2024, so not for Arts 54 and 60). The MOJ compilation and both 20/2023 copies are in the corpus manifest as evidence, not indexed: `moj-labour-legislation-2025-ar`, `amending-decree-law-20-2023-ar` and `amending-decree-law-20-2023-en` (added 2026-10-18, #24).

Still unverified:

- The official-gazette record of 14/2022's dates, the gazette number of 20/2023, and the exact day 9/2024 took effect (its Art 4 was not reached).
- Ministerial Resolution 27/2023 itself, and what happens to unlimited contracts never converted (no official source).
- Any amendment after 4 Oct 2026, the last portal capture checked.
- A standalone official copy of 14/2022 or 9/2024 in either language. None found: on 2026-10-18 the portal returned HTTP 522 and the Wayback Machine had no capture. Their article changes rest on the MOJ compilation's notes, which give no dates for them.
