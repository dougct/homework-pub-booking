# Ex6 — Rasa structured half

## Your answer

Ex6 had four moving parts. (1) `canonicalise_venue_id` in `validator.py`
maps loose strings like `"Haymarket Tap"` to the slug `haymarket_tap`
via lowercase + `\s|-` → `_` + drop non-alphanumeric. (2)
`normalise_booking_payload` composes the existing helpers
(`_normalise_date`, `parse_time_24h`, `parse_party_size`,
`parse_currency_gbp`) and produces the Rasa-shaped message
`{sender, message: "/confirm_booking", metadata: {booking: {...}}}`.
The `sender` is a stable 8-char SHA-1 of `venue-date-time` so retries
within a session share a tracker.

(3) `RasaStructuredHalf.run` serializes the normalised message to UTF-8
JSON, POSTs it to `self.rasa_url` via `urllib_request.Request`, and runs
the blocking `urlopen` inside `asyncio.run_in_executor` so the structured
half doesn't block the event loop. The response array is scanned for
`custom.action == "committed"` or `"rejected"` and translated into the
correct `HalfResult` (`next_action="complete"` vs `"escalate"`). Network
errors return `success=False` with `SA_EXT_SERVICE_UNAVAILABLE` rather
than raising — the bridge decides whether to retry.

(4) On the Rasa side, `ActionValidateBooking` reads `tracker.latest_message.metadata.booking`,
emits `SlotSet` events for every booking field, and rejects with
`"party_too_large"` if `party > 8` or `"deposit_too_high"` if
`deposit > £300`. The success branch generates a `BK-<SHA1[:8]>`
reference. The `flows.yml` step list runs `action_validate_booking`,
then branches on the `validation_error` slot to either `utter_booking_rejected`
or `utter_booking_confirmed`.

Validation in `make ex6` (stdlib mock): `sess_27851f8bbfc8` confirmed
party=6, deposit=£200 → `BK-7D401E9E`.

## Citations

- `starter/rasa_half/validator.py:62, 64-100, 201-205`
- `starter/rasa_half/structured_half.py:95-149` — HTTP + response parsing
- `rasa_project/actions/actions.py:118-135` — rule checks + booking ref
- `rasa_project/data/flows.yml:41-51` — validate/rejected/confirmed steps
