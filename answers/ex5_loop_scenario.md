# Ex5 — Edinburgh research loop scenario

## Your answer

For Ex5 I implemented four tools (`venue_search`, `get_weather`,
`calculate_cost`, `generate_flyer`) in `starter/edinburgh_research/tools.py`
and used the existing reference `verify_dataflow` in `integrity.py`. The
three read-only tools are `parallel_safe=True`; `generate_flyer` is
`parallel_safe=False` because it writes `workspace/flyer.html`.

The pattern I followed for every tool: build an `args` dict at the top,
do the work, then call `record_tool_call(name, args, output)` before
returning a `ToolResult`. Even the error paths log a record — without
that, the integrity check has no ground truth to compare against and
silently passes everything. I also routed `_load_fixture` through a
`ToolError("SA_TOOL_DEPENDENCY_MISSING")` so a missing JSON fixture
fails the run with a structured error rather than `FileNotFoundError`.

The flyer uses `<span data-testid="venue_name">…</span>` style tagging
on every fact (venue, address, date, time, party, weather condition,
temperature, total, deposit). `extract_testid_facts` in the reference
integrity helper consumes these as structured pairs and avoids regex
false positives on stray numbers in HTML attributes.

Real-mode confirmation: `make ex5-real` (Nebius, planner
`Qwen3-Next-80B-A3B-Thinking`, executor `Qwen3-32B`) ran in session
`sess_4c80ad1f6903`. The model spiralled on `venue_search` — six calls,
then a `handoff_to_structured` — and never reached `generate_flyer`.
This is the documented Qwen failure mode in `docs/real-mode-failures.md`
and is independent of my tool implementations, which all behave
deterministically offline (`make ex5` writes a 1311-byte flyer and the
integrity check verifies 4 facts).

## Citations

- `starter/edinburgh_research/tools.py` — four tools + `_load_fixture`
- `~/Library/Application Support/sovereign-agent/examples/ex5-edinburgh-research/sess_4c80ad1f6903/logs/trace.jsonl` — real-mode spiral
- `starter/edinburgh_research/integrity.py:118` — `verify_dataflow`
