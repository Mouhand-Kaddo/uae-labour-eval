# Bilingual consistency

The agent was asked the same question about UAE private-sector labour law once in English and
once in Arabic, and answered each in the language of the question. You are given both questions,
both final answers, and the text of the articles either answer cites, as the agent retrieved it.
Judge only whether the two answers agree with each other. Whether each answer is right is checked
separately, so do not fail an answer for being wrong if the other answer is wrong in the same way.
Differences in language, wording, order, and how numbers are written (Western or Arabic-Indic
digits, or words) are not disagreements.

## same_conclusion
Both answers reach the same outcome: the same status (answered, refused or not found), the same
yes or no, the same figure, and the same entitlement or obligation. Fail if a person reading only
one of the answers would come away with a different result than a person reading only the other.

## same_details
Every substantive point in one answer is also in the other with the same value: each period,
amount, rate, condition, exception and next step it gives. Fail if one answer adds, omits or
changes such a point. Restating the question, a disclaimer, or a courtesy phrase is not a
substantive point.
