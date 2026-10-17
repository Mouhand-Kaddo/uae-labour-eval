"""`eval report`: a static, self-contained HTML page for one run, plus one page per trace."""

import json
from html import escape
from pathlib import Path
from string import Template
from typing import Any

from eval_harness.report_stats import Flaky, ReportNumbers, Score, report_numbers


class ReportError(Exception):
    pass


STYLE = """
:root {
  color-scheme: light dark;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #6b6a65;
  --grid: #e1e0d9; --axis: #c3c2b7; --series: #2a78d6; --border: rgba(11,11,11,0.10);
  --critical: #b42f2f;
}
@media (prefers-color-scheme: dark) {
  :root {
    --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #a3a29b;
    --grid: #2c2c2a; --axis: #383835; --series: #3987e5; --border: rgba(255,255,255,0.10);
    --critical: #e66767;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2rem 1.25rem 4rem; background: var(--page); color: var(--ink);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
}
main { max-width: 64rem; margin: 0 auto; }
h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
h2 { font-size: 1.125rem; margin: 2.5rem 0 .25rem; }
p, dd, .note { color: var(--ink-2); }
.note { font-size: .875rem; margin: .25rem 0 .75rem; }
a { color: var(--series); }
a:focus-visible { outline: 2px solid var(--series); outline-offset: 2px; }
dl.meta {
  display: grid; grid-template-columns: max-content 1fr; gap: .125rem 1rem; margin: .75rem 0;
}
dl.meta dt { color: var(--muted); }
dl.meta dd { margin: 0; overflow-wrap: anywhere; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); gap: .75rem; }
.tile {
  background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
  padding: .75rem 1rem;
}
.tile .label { color: var(--ink-2); font-size: .875rem; }
.tile .value {
  font-size: 1.5rem; white-space: nowrap; font-weight: 600; font-variant-numeric: tabular-nums;
}
.tile .sub { color: var(--muted); font-size: .8125rem; }
.table-wrap {
  overflow-x: auto; background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px;
}
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
caption { text-align: left; padding: .75rem 1rem .25rem; color: var(--ink-2); font-size: .875rem; }
th, td {
  padding: .4rem 1rem; text-align: left; border-top: 1px solid var(--grid); vertical-align: top;
}
thead th { color: var(--muted); font-weight: 500; font-size: .8125rem; border-top: none; }
td.num, th.num { text-align: right; }
tfoot td:not(.note) { font-weight: 600; }
.strip { display: block; }
.strip .track { stroke: var(--axis); stroke-width: 1; }
.strip .ci { stroke: var(--series); stroke-width: 2; stroke-linecap: round; }
.strip .point { fill: var(--series); stroke: var(--surface); stroke-width: 2; }
.fail { color: var(--critical); font-weight: 600; }
pre {
  margin: 0; padding: .75rem 1rem; white-space: pre-wrap; overflow-wrap: anywhere;
  font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--ink);
}
.step { margin: 1rem 0; }
.step h2 { margin: 0 0 .25rem; font-size: 1rem; }
code.details {
  white-space: pre-wrap; overflow-wrap: anywhere; font-size: .8125rem; color: var(--ink-2);
}
"""

PAGE = Template(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>$style</style>
</head>
<body>
<main>
$body
</main>
</body>
</html>
"""
)

STRIP_WIDTH = 160
RESULT_FIELDS = frozenset(
    {"case_id", "repeat", "category", "reviewed", "status", "passed", "cost_usd", "latency_s"}
)


def write_report(run_dir: Path) -> Path:
    """Write `<run_dir>/report/index.html` and one page per trace; return the index path."""
    summary = _read_summary(run_dir)
    results = summary.get("cases")
    if not isinstance(results, list):
        raise ReportError(f"{run_dir / 'summary.json'} has no case results")
    for result in results:
        missing = RESULT_FIELDS - set(result) if isinstance(result, dict) else RESULT_FIELDS
        if missing:
            raise ReportError(
                f"{run_dir / 'summary.json'}: a case result is missing {sorted(missing)}"
            )
    numbers = report_numbers(results)
    out = run_dir / "report"
    (out / "traces").mkdir(parents=True, exist_ok=True)

    trace_links: dict[tuple[str, int], str] = {}
    verdicts: dict[tuple[str, int], Any] = {}
    for result in results:
        key = (result["case_id"], result["repeat"])
        steps = _read_trace(run_dir / "traces" / f"{key[0]}.{key[1]}.jsonl")
        if steps is None:
            continue
        name = f"{key[0]}.{key[1]}.html"
        (out / "traces" / name).write_text(_trace_page(summary, result, steps), encoding="utf-8")
        trace_links[key] = f"traces/{name}"
        verdicts[key] = next((s.get("details") for s in steps if s.get("type") == "verdict"), None)

    index = out / "index.html"
    index.write_text(_index_page(summary, numbers, trace_links, verdicts), encoding="utf-8")
    return index


def _read_summary(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "summary.json"
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"cannot read {path}: {exc}") from exc
    if not isinstance(summary, dict):
        raise ReportError(f"{path} is not a JSON object")
    return summary


def _read_trace(path: Path) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    try:
        steps = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except json.JSONDecodeError as exc:
        raise ReportError(f"cannot read {path}: {exc}") from exc
    if not all(isinstance(step, dict) for step in steps):
        raise ReportError(f"{path} has a step that is not a JSON object")
    return steps


def _index_page(
    summary: dict[str, Any],
    numbers: ReportNumbers,
    trace_links: dict[tuple[str, int], str],
    verdicts: dict[tuple[str, int], Any],
) -> str:
    run_id = str(summary.get("run_id", ""))
    body = "\n".join(
        [
            f"<h1>Eval report: {_text(run_id)}</h1>",
            _meta(summary),
            _headline_section(numbers),
            _safety_section(numbers.safety),
            _cost_section(summary, numbers),
            _failures_section(numbers.failures, trace_links, verdicts),
            _flaky_section(numbers.flaky),
            _unreviewed_section(numbers.unreviewed),
            _judge_section(summary.get("judge_agreement")),
            _all_results_section(summary["cases"], trace_links),
        ]
    )
    return PAGE.substitute(title=_text(f"Eval report {run_id}"), style=STYLE, body=body)


def _meta(summary: dict[str, Any]) -> str:
    selection = summary.get("selection") or {}
    rows = [
        ("Model", summary.get("model")),
        ("Status", summary.get("status")),
        ("Started", summary.get("started_at")),
        ("Repeats", selection.get("repeats")),
        ("Case set hash", summary.get("case_set_hash")),
        ("Git commit", summary.get("git_commit")),
    ]
    items = "".join(f"<dt>{label}</dt><dd>{_text(value)}</dd>" for label, value in rows)
    return f'<dl class="meta">{items}</dl>'


def _headline_section(numbers: ReportNumbers) -> str:
    rows = "".join(_score_row(score) for score in numbers.headline)
    average = numbers.headline_average
    return f"""<section id="scores">
<h2>Headline scores</h2>
<p class="note">Pass rate on reviewed cases per category, with n and a Wilson 95% interval.
With repeats, every repeat counts towards n.</p>
<div class="table-wrap"><table>
<caption>Reviewed cases by category</caption>
{_score_head()}
<tbody>{rows or _empty_row("No reviewed cases in this run.")}</tbody>
<tfoot><tr><td>Average</td><td class="num">{_pct(average)}</td><td class="note" colspan="3">
unweighted mean of the category pass rates</td></tr></tfoot>
</table></div>
</section>"""


def _safety_section(safety: Score) -> str:
    return f"""<section id="safety">
<h2>Safety pass rate</h2>
<p class="note">Reviewed refuse and inject cases pooled and shown on their own,
so the headline average cannot hide a safety failure.</p>
<div class="tiles"><div class="tile">
<div class="label">Safety pass rate</div>
<div class="value">{_pct(safety.rate)}</div>
<div class="sub">{safety.passed} of {safety.n} passed · 95% CI {_interval(safety)}</div>
{_strip(safety)}
</div></div>
</section>"""


def _cost_section(summary: dict[str, Any], numbers: ReportNumbers) -> str:
    tiles = [
        ("Latency p50", _seconds(numbers.latency_p50), "per case"),
        ("Latency p95", _seconds(numbers.latency_p95), "per case"),
        ("Cost p50", _usd(numbers.cost_p50), "per case"),
        ("Cost p95", _usd(numbers.cost_p95), "per case"),
        ("Run spend", _usd(summary.get("run_spend_usd")), "this run"),
        ("Cumulative spend", _usd(summary.get("cumulative_usd")), "all runs so far"),
    ]
    html = "".join(
        f'<div class="tile"><div class="label">{label}</div>'
        f'<div class="value">{value}</div><div class="sub">{sub}</div></div>'
        for label, value, sub in tiles
    )
    return f"""<section id="cost">
<h2>Latency and cost</h2>
<p class="note">Percentiles over every case result in the run, reviewed or not.</p>
<div class="tiles">{html}</div>
</section>"""


def _failures_section(
    failures: list[dict[str, Any]],
    trace_links: dict[tuple[str, int], str],
    verdicts: dict[tuple[str, int], Any],
) -> str:
    rows = "".join(
        f"<tr><td>{_case_link(r, trace_links)}</td><td>{_text(r['category'])}</td>"
        f"<td>{'yes' if r['reviewed'] else 'no'}</td><td>{_text(r['status'])}</td>"
        f'<td><code class="details">{_details(verdicts.get((r["case_id"], r["repeat"])))}'
        "</code></td></tr>"
        for r in failures
    )
    return f"""<section id="failures">
<h2>Worst failures</h2>
<p class="note">Safety failures first, then wrong calc answers, then the rest;
reviewed before unreviewed. Each links to its trace.</p>
<div class="table-wrap"><table>
<thead><tr><th>Case</th><th>Category</th><th>Reviewed</th><th>Status</th><th>Scorer details</th>
</tr></thead>
<tbody>{rows or _empty_row("No failures.", 5)}</tbody>
</table></div>
</section>"""


def _flaky_section(flaky: list[Flaky]) -> str:
    rows = "".join(
        f"<tr><td>{_text(f.case_id)}</td><td>{_text(f.category)}</td>"
        f"<td>{f.passed} of {f.runs}</td></tr>"
        for f in flaky
    )
    return f"""<section id="flaky">
<h2>Flaky cases</h2>
<p class="note">Cases that both passed and failed across repeats (needs <code>--repeats</code>).</p>
<div class="table-wrap"><table>
<thead><tr><th>Case</th><th>Category</th><th>Passed</th></tr></thead>
<tbody>{rows or _empty_row("No case flipped between pass and fail.", 3)}</tbody>
</table></div>
</section>"""


def _unreviewed_section(unreviewed: list[Score]) -> str:
    rows = "".join(_score_row(score) for score in unreviewed)
    return f"""<section id="unreviewed">
<h2>Unreviewed cases</h2>
<p class="note">Expected results not yet checked by the project owner;
not in the headline scores or the safety pass rate.</p>
<div class="table-wrap"><table>
<caption>Unreviewed cases by category</caption>
{_score_head()}
<tbody>{rows or _empty_row("No unreviewed cases in this run.")}</tbody>
</table></div>
</section>"""


def _judge_section(agreement: Any) -> str:
    if isinstance(agreement, dict):
        content = (
            f"<p>{_pct(agreement.get('agreement'))} agreement with the project owner's labels, "
            f"Cohen's kappa {_text(_fixed(agreement.get('kappa'), 2))}, "
            f"n = {_text(agreement.get('n'))}.</p>"
        )
    else:
        content = "<p>Not measured yet: no judge agreement is recorded for this run.</p>"
    return f'<section id="judge">\n<h2>Judge agreement</h2>\n{content}\n</section>'


def _all_results_section(
    results: list[dict[str, Any]], trace_links: dict[tuple[str, int], str]
) -> str:
    rows = "".join(
        f"<tr><td>{_case_link(r, trace_links)}</td><td>{_text(r['category'])}</td>"
        f"<td>{'yes' if r['reviewed'] else 'no'}</td><td>{_text(r['status'])}</td>"
        f"<td>{_verdict(r['passed'])}</td><td class='num'>{_seconds(r['latency_s'])}</td>"
        f"<td class='num'>{_usd(r['cost_usd'])}</td></tr>"
        for r in results
    )
    return f"""<section id="results">
<h2>All case results</h2>
<div class="table-wrap"><table>
<thead><tr><th>Case</th><th>Category</th><th>Reviewed</th><th>Status</th><th>Verdict</th>
<th class="num">Latency</th><th class="num">Cost</th></tr></thead>
<tbody>{rows or _empty_row("No case results.", 7)}</tbody>
</table></div>
</section>"""


def _trace_page(summary: dict[str, Any], result: dict[str, Any], steps: list[dict]) -> str:
    title = f"{result['case_id']} (repeat {result['repeat']})"
    sections = "".join(
        f'<section class="step"><h2>{n}. {_text(step.get("type"))}</h2><div class="table-wrap">'
        f'<pre dir="auto">{_text(json.dumps(step, indent=2, ensure_ascii=False))}</pre>'
        "</div></section>"
        for n, step in enumerate(steps, 1)
    )
    body = f"""<p><a href="../index.html">Back to the report</a></p>
<h1>Trace: {_text(title)}</h1>
<dl class="meta">
<dt>Run</dt><dd>{_text(summary.get("run_id"))}</dd>
<dt>Category</dt><dd>{_text(result["category"])}</dd>
<dt>Reviewed</dt><dd>{"yes" if result["reviewed"] else "no"}</dd>
<dt>Status</dt><dd>{_text(result["status"])}</dd>
<dt>Verdict</dt><dd>{_verdict(result["passed"])}</dd>
</dl>
{sections}"""
    return PAGE.substitute(title=_text(f"Trace {title}"), style=STYLE, body=body)


def _score_head() -> str:
    return (
        '<thead><tr><th scope="col">Category</th><th scope="col" class="num">Pass rate</th>'
        '<th scope="col" class="num">n</th><th scope="col">95% CI</th>'
        '<th scope="col"><span class="note">0–100%</span></th></tr></thead>'
    )


def _score_row(score: Score) -> str:
    return (
        f'<tr><th scope="row">{_text(score.label)}</th><td class="num">{_pct(score.rate)}</td>'
        f'<td class="num">{score.n}</td><td>{_interval(score)}</td><td>{_strip(score)}</td></tr>'
    )


def _strip(score: Score) -> str:
    if score.rate is None or score.interval is None:
        return ""
    low, high = (STRIP_WIDTH * v for v in score.interval)
    x = STRIP_WIDTH * score.rate
    label = f"{score.label}: {_pct(score.rate)}, 95% CI {_interval(score)}, n = {score.n}"
    return (
        f'<svg class="strip" width="{STRIP_WIDTH + 12}" height="16" viewBox="-6 0 '
        f'{STRIP_WIDTH + 12} 16" role="img" aria-label="{_text(label)}">'
        f"<title>{_text(label)}</title>"
        f'<line class="track" x1="0" x2="{STRIP_WIDTH}" y1="8" y2="8"/>'
        f'<line class="ci" x1="{low:.1f}" x2="{high:.1f}" y1="8" y2="8"/>'
        f'<circle class="point" cx="{x:.1f}" cy="8" r="5"/></svg>'
    )


def _case_link(result: dict[str, Any], trace_links: dict[tuple[str, int], str]) -> str:
    label = _text(f"{result['case_id']} #{result['repeat']}")
    href = trace_links.get((result["case_id"], result["repeat"]))
    return f'<a href="{_text(href)}">{label}</a>' if href else f"{label} (no trace)"


def _empty_row(message: str, columns: int = 5) -> str:
    return f'<tr><td colspan="{columns}">{message}</td></tr>'


def _verdict(passed: bool) -> str:
    return "pass" if passed else '<span class="fail">fail</span>'


def _details(details: Any) -> str:
    if not details:
        return ""
    return _text(json.dumps(details, ensure_ascii=False))


def _interval(score: Score) -> str:
    if score.interval is None:
        return "–"
    low, high = score.interval
    return f"{low * 100:.0f}%–{high * 100:.0f}%"


def _pct(value: Any) -> str:
    return f"{value:.0%}" if isinstance(value, int | float) else "–"


def _seconds(value: Any) -> str:
    return f"{value:.2f} s" if isinstance(value, int | float) else "–"


def _usd(value: Any) -> str:
    return f"USD {value:.6f}" if isinstance(value, int | float) else "–"


def _fixed(value: Any, places: int) -> str:
    return f"{value:.{places}f}" if isinstance(value, int | float) else "–"


def _text(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)
