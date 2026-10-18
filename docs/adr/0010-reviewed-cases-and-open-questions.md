# Only reviewed cases count, and the owner decides every ambiguity

Every drafted case starts `reviewed: false`, and the runner reports unreviewed cases separately from headline scores, so a mistake in drafting can't inflate or deflate the published numbers. Expected values for calc cases are worked out by hand from the article text, with the arithmetic in a `rationale` field; they are never produced by running the calculation tools, which would only prove the tools agree with themselves. Where the sources are ambiguous, the ambiguity is written up in `docs/open-questions.md` and the project owner decides it. Calculation rules that depend on a decision cite both the article and the open question, and cases that depend on an unresolved question cannot be marked reviewed.

## Consequences

- When the English and Arabic texts differ, the open question records both; the Arabic prevails per the official portal, but the difference is still recorded.
- References live in data, not code comments: each rule carries a `Ref(instrument, article, clause)`, tool results return the refs they used, and tests are named and parameterised by article.
