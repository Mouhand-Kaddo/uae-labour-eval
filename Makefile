.PHONY: eval test lint

ENV_FILE ?= .env
RUNS_DIR ?= runs
REPORTS_DIR ?= reports
RUN_ARGS ?=
UV_RUN = uv run $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE))

eval:
	$(UV_RUN) eval fetch
	$(UV_RUN) eval ingest
	$(UV_RUN) eval embed
	$(UV_RUN) eval run $(RUN_ARGS)
	run_dir=$$(ls -d $(RUNS_DIR)/*/ | sort | tail -n 1) && \
	$(UV_RUN) eval report "$$run_dir" --out "$(REPORTS_DIR)/$$(basename "$$run_dir")"

test:
	uv run pytest

lint:
	uv run ruff check
	uv run ruff format --check
	uv run ty check
