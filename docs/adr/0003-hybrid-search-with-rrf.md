# Hybrid search: BM25 plus embeddings, merged with reciprocal rank fusion

Search runs BM25 (`bm25s`) and bge-m3 embeddings over one index holding both languages, merges the two rankings with reciprocal rank fusion (k=60) and returns the top 8 chunks. One cross-lingual index means an Arabic question can find the English chunk of the right article and the other way round; citations are by instrument and article, so they are the same in either language. The corpus is a few hundred chunks, so vectors sit in a NumPy array and search is brute force; a vector database or reranker would add moving parts with nothing to gain at this size.

## Consequences

- Chunks are split by article; long articles are split into parts that each keep instrument, article and language.
- Arabic text is normalised the same way for documents and queries (strip diacritics and tatweel, unify alef forms, ى→ي, ة→ه) with a few hand-written rules. We rejected `camel-tools` (pulls pandas and kenlm) and `pyarabic` (unmaintained since 2022).
- Retrieval quality is measured, not assumed: if it turns out weak, reranking is the next step, and needs its own ADR.
