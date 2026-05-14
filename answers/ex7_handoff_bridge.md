# Ex7 — Handoff bridge

## Your answer

`HandoffBridge.run` is a bounded `while rounds < max_rounds` loop. Each
round emits `bridge.round_start`, runs the loop half, and dispatches on
`loop_result.next_action`: `complete` ends the bridge, `handoff_to_structured`
writes a forward handoff and invokes the structured half, anything else
fails the session.

The structured-half dispatch then branches three ways. `next_action="complete"`
marks the session complete and emits `session.state_changed{from:structured, to:complete}`.
`next_action="escalate"` is the interesting case: it builds a reverse
task via `build_reverse_task` (which injects the rejection reason into
`context.rejection_reason` and `retry=True`), emits a state-changed event
with the rejection reason inline, archives the stale
`ipc/handoff_to_structured.json` to
`logs/handoffs/round_<N>_forward.json`, and `continue`s. Anything else
fails the session with a structured reason.

The archive step is what enforces the "at most one handoff file in `ipc/`
at any time" invariant the grader checks. If you skip it, the second
round writes a new handoff *next to* the stale one — the file watcher
might pick up either, depending on iteration order. By moving it out of
`ipc/` you make the IPC directory a single-message channel.

End-to-end validation: `make ex7` returns `outcome=completed, rounds=2`
— round 1 rejects haymarket_tap (party=12 > 8), round 2 confirms
royal_oak with party=6. Real-mode `--real` session `sess_46683a0ffd83`
exercised the same orchestration against a live Nebius planner that
adapted on rejection: round 1 proposed `haymarket_tap, party=12`, round
2 proposed `royal_oak, party=6` after seeing the rejection_reason
in `current_input.context`.

## Citations

- `starter/handoff_bridge/bridge.py:64-160` — the orchestration loop
- `~/Library/Application Support/sovereign-agent/examples/ex7-handoff-bridge/sess_46683a0ffd83/logs/trace.jsonl` — real-mode trace
- `starter/handoff_bridge/integrity.py:24` — `verify_dataflow` checks bridge.round_start + state_changed + tool_called
