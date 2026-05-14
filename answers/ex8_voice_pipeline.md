# Ex8 — Voice pipeline

## Your answer

I ran Ex8 in text-only mode (no Speechmatics or Rime credentials). The
core gradeable contract is shared between `run_text_mode` and
`run_voice_mode`: both emit `voice.utterance_in` and `voice.utterance_out`
trace events on every turn with payload `{text, turn, mode}`. The
`mode` field is `"text"` or `"voice"` so downstream analysis can
distinguish transports while applying the same grading rules.

`ManagerPersona` wraps an `OpenAICompatibleClient` pointed at
`meta-llama/Llama-3.3-70B-Instruct` on Nebius. The system prompt names
the pub manager Alasdair MacLeod, fixes the booking rules
(party ≤ 8 AND deposit ≤ £300 → accept; otherwise decline with a
specific reason), and caps responses at 60 words. Temperature is `0.0`
so the same conversation reproduces across runs.

`run_voice_mode` opens by checking `SPEECHMATICS_KEY` and the
`speechmatics` / `sounddevice` imports. If either is missing it prints
a warning to stderr and falls through to `run_text_mode` with the same
session and persona — no exception, no half-built state. This is what
the public test `test_voice_mode_falls_back_when_no_speechmatics_key`
verifies. I confirmed it locally: `make ex8-text` runs the text loop;
invoking voice mode without keys produces the same trace shape, just
under a simpler transport.

The only code I changed in this exercise was restoring `_speak_rime`'s
`httpx.AsyncClient` block, which PR #18 had stubbed out. Without that
fix, ruff flagged `payload`/`headers` as unused and `mp3_bytes` as
undefined — five mechanical points lost on dead code in an unreachable
path. The runtime behaviour is unchanged because no Rime key is set,
so the `_speak_rime` call site is never reached.

## Citations

- `starter/voice_pipeline/manager_persona.py:22-41` — system prompt
- `starter/voice_pipeline/voice_loop.py:41-77` — text-mode reference
- `starter/voice_pipeline/voice_loop.py:90-117` — graceful degradation
- `tests/public/test_ex8_scaffold.py` — five Ex8 tests, all green
