"""References to the legal text: rule refs (ADR-0010), article labels and article keys."""

import re
from dataclasses import dataclass

ARTICLE_NUMBER = re.compile(r"\d+")


def article_label(instrument: str, article: str) -> str:
    """How an article is written for people: "Labour Law Art 51"."""
    return f"{instrument} Art {article}"


def article_key(instrument: str, article: str) -> str:
    """An article's identity for matching citations: casefolded instrument and the article's
    first number, so "Labour Law" "51(2)" and "labour law" "51" match."""
    number = ARTICLE_NUMBER.search(str(article))
    return f"{instrument.strip().casefold()} {number.group() if number else str(article).strip()}"


@dataclass(frozen=True)
class Ref:
    instrument: str
    article: str
    clause: str | None = None

    def __str__(self) -> str:
        clause = f"({self.clause})" if self.clause else ""
        return article_label(self.instrument, self.article) + clause
