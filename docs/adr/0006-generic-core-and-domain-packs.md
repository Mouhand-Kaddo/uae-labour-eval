# Generic core, UAE specifics in one pack

Fetch, ingest, chunking, search (`search_sources`, `get_section`), the agent loop, the runner, scorers, budget guard and report know nothing about UAE labour law. Everything domain-specific (corpus manifest, section-heading patterns, calculation tools, system prompt, cases, rubrics) lives in `packs/uae_labour/`, selected by a path in `config.toml`. This is a folder and a config path, not a plugin system: there is one pack, and a second pack is the moment to find out what the interface really needs.
