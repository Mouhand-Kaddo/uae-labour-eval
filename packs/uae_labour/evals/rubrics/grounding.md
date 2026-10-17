# Grounding

The agent answered a question about UAE private-sector labour law and cited the articles its
answer relies on. You are given the question, the final answer, and the text of the cited
articles exactly as the agent retrieved it during the case. Judge only against that text, not
against your own knowledge of UAE law: a claim that may well be true but is not in the cited
text is unsupported.

## claims_supported
Every claim in the answer (each period, amount, percentage, condition, duty, right and
exception) is stated in, or follows directly from, the cited text. Fail if any claim is missing
from the cited text, contradicts it, or is broader or more certain than the text allows. Fail if
there is no cited text. Wording that only restates the question, or says the answer is not legal
advice, is not a claim.

## citations_relevant
Each cited article supports at least one claim in the answer. Fail if any citation is padding:
an article whose retrieved text has nothing to do with what the answer says.
