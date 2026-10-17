# Sources are fetched from a manifest, not committed

The repo commits a corpus manifest (official URL, archived snapshot URL, retrieval date, language, instrument and expected SHA-256 for each source) and a `fetch` command that downloads the files and refuses any whose hash doesn't match. The source files themselves, and the embeddings derived from them, are not committed. Keeping legal texts out of the repo keeps the RAG generic (any manifest works) and keeps the MIT repo free of third-party documents. The official portal blocks scripted downloads, so each manifest entry also pins a Wayback Machine snapshot of the official URL, which the fetcher tries next.

## Consequences

- Reproducing a run requires network access to the portal or the Wayback Machine. CI caches the fetched files keyed by the manifest hash.
- Rebuilding embeddings costs well under USD 0.01 and is logged to the ledger like any other call.
- Committed reports quote short excerpts of the law inside traces; that is quotation inside results, not redistribution of the sources.
