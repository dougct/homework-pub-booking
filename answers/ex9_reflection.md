# Ex9 — Reflection

## Q1 — Planner handoff decision

### Your answer

In my Ex7 real-mode session `sess_46683a0ffd83` the planner produced a
single subgoal in `session.json`:

```
sg_1  assigned_half: "loop"
      description: "retry with larger venue after rejection"
      success_criterion: "different venue with enough seats"
```

Crucially, this is the planner's output *after* the first round's
reverse handoff — the planner kept the work in the loop half rather
than assigning a subgoal directly to `structured`. The actual handoff
was triggered by the executor inside `sg_1` calling the
`handoff_to_structured` tool, visible at `logs/trace.jsonl:5` of the
same session:

```
"tool": "handoff_to_structured",
"arguments": {"reason": "loop half identified a candidate venue;
                          passing to structured half for confirmation
                          under policy rules", ...}
```

The signal that drove the decision was the tool's *presence* in the
registry, not its name in the subgoal prose. Decision 8 of the
framework — registries are physics, prompts are advisory — explains
this: the planner saw the available halves and chose loop; the
executor saw the available tools and chose `handoff_to_structured`
when the subgoal description used the word "confirmation". The
handoff is therefore *prose-driven at the executor layer*, not at
the planner layer.

In a production system this is fragile: if a subgoal description
read "process this booking" instead of "confirm this booking", the
LLM may never reach for the tool. The robust fix is to push the
handoff trigger into the StructuredHalf's rules (Decision 8 again:
remove the temptation rather than fight it). I left it as-is for
the homework because the bridge orchestrates rounds anyway, but
this trace was the clearest example of the planner/executor split
producing a non-obvious dispatch.

### Citation

- `~/Library/Application Support/sovereign-agent/examples/ex7-handoff-bridge/sess_46683a0ffd83/session.json` — `planner.subgoals[0]`
- `~/Library/Application Support/sovereign-agent/examples/ex7-handoff-bridge/sess_46683a0ffd83/logs/trace.jsonl:5` — `handoff_to_structured` invocation
- `~/Library/Application Support/sovereign-agent/examples/ex7-handoff-bridge/sess_46683a0ffd83/logs/tickets/tk_e4ea73a6/summary.md` — "Planner produced 1 subgoals. 1 to loop half, 0 to structured half."

---

## Q2 — Dataflow integrity catch

### Your answer

Reproducible scenario: a flyer claims `Total: £540, Deposit: £0,
weather cloudy 12C`. All four numbers are plausible — they match the
formula in `catering.json` for `haymarket_tap, party=6, 3h, bar_snacks`
and the weather fixture for Edinburgh on 2026-04-25. A human reviewer
would scroll past it.

Now plant a single fabrication: change `£540` to `£9999`. The flyer
still parses, all other facts are real. I tested this by running
`make ex5` to produce a real flyer + tool log, then calling
`verify_dataflow` against two strings:

```
record_tool_call('calculate_cost', {...},
                 {'total_gbp': 540, 'deposit_required_gbp': 0})
record_tool_call('get_weather', {...},
                 {'condition': 'cloudy', 'temperature_c': 12})

verify_dataflow('<p>Total £540, deposit £0, weather cloudy 12C</p>')
  → "dataflow OK: verified 4 fact(s) against tool outputs"
verify_dataflow('<p>Total £9999, deposit £0, weather cloudy 12C</p>')
  → "dataflow FAIL: 1 unverified fact(s): ['£9999']"
```

The check catches it because `extract_money_facts` regex-extracts
every `£N` in the flyer and then `fact_appears_in_log` compares the
scalar against every value in `_TOOL_CALL_LOG[*].output`. The
fabrication has no source — no `record_tool_call` ever wrote 9999 —
so it's flagged. Manual review can't catch this because £9999 looks
no more suspicious than £999 or £999.99 in the right context.

The generalisable rule: any flyer fact that has units (£, °C, named
weather condition) must trace to a tool output. The check is
brittle on prose-only facts but solid on money, temperature, and
the small condition vocabulary in `weather.json`. For Ex5 that
covers every concrete claim in the flyer.

### Citation

- `starter/edinburgh_research/integrity.py:64-112` — `extract_money_facts` + `fact_appears_in_log`
- `starter/edinburgh_research/integrity.py:118-164` — `verify_dataflow`
- Reproducible from `make ex5` + the £9999 sed substitution shown above.

---

## Q3 — Removing one framework primitive

### Your answer

If forced to delete ONE primitive, I'd remove **the forward-only state
machine** first. Of the five candidates (session-as-directory, forward-only
state, tickets, atomic-rename IPC, planner-executor split) it's the most
narrowly load-bearing. The data is in the directory; the audit is in the
tickets; the IPC is in the file system; the dispatch is in the halves.
The state machine is policy laid over those — useful policy, but
reconstructible from the trace.

The specific failure mode it surfaces: **silent regression of session
state under retry**. In my Ex7 real-mode session the bridge looped
three times against an unreachable Rasa, and on each reverse-handoff
my code emits a `session.state_changed` event with `from="structured",
to="loop"`. Without `ALLOWED_TRANSITIONS` enforcement in
`sovereign_agent/session/state.py`, a bug where the bridge accidentally
moved `from="completed"` back to `"executing"` (e.g. on a late
notification from a half that ran past the bridge's deadline) would
look like a healthy retry — the trace would show forward motion, the
session.json would show "executing", and the booking would re-fire.
The forward-only check raises `InvalidStateTransition` and the run
fails loudly instead of silently double-booking.

The failure I'd expect first in production isn't an LLM error — it's a
late callback. Real Rasa or a real voice STT can return long after the
bridge has timed out and moved on. Without forward-only state, the
late return looks legitimate. With it, the session refuses the
transition and writes a structured error.

I'd keep session-as-directory as the LAST thing standing — it's what
makes the post-mortem possible at all.

### Citation

- `sovereign_agent/session/state.py:ALLOWED_TRANSITIONS` — the rule
- `~/Library/Application Support/sovereign-agent/examples/ex7-handoff-bridge/sess_46683a0ffd83/logs/trace.jsonl` — three reverse-handoff `session.state_changed` events from a single bridge run
- `starter/handoff_bridge/bridge.py:108-121` — the transition emit site
