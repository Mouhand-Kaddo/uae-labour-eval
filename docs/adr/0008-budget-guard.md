# Budget guard: refuse runs the remaining budget can't cover

The project has a hard USD 20 ceiling on all API spend. Every paid call appends its OpenRouter-reported `usage.cost` to `runs/ledger.jsonl`. Before a run, the runner estimates its cost as (average per-case cost for that model and category from the ledger, or live prices × assumed token counts when there is no history) × number of cases × 1.5, and refuses to start if that exceeds the remaining budget. Remaining budget is USD 20 minus the larger of the ledger total and the key's reported usage (`GET /api/v1/key`), so spend the local ledger never saw (CI, another machine, a lost ledger) still counts. A run that crosses the remaining budget mid-way aborts. A USD 20 limit set on the key in the OpenRouter dashboard is the last line of defence.

## Consequences

- The ledger is not committed; the key's usage is the cross-machine source of truth. Committed reports carry each run's spend and the cumulative total.
- The guard needs the key-usage endpoint to be reachable; if it isn't, the run refuses to start rather than trusting the ledger alone.
