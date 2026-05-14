"""Ex5 tools. Four tools the agent uses to research an Edinburgh booking.

Each tool:
  1. Reads its fixture from sample_data/ (DO NOT modify the fixtures).
  2. Logs its arguments and output into _TOOL_CALL_LOG (see integrity.py).
  3. Returns a ToolResult with success=True/False, output=dict, summary=str.

The grader checks for:
  * Correct parallel_safe flags (reads True, generate_flyer False).
  * Every tool's results appear in _TOOL_CALL_LOG.
  * Tools fail gracefully on missing fixtures or bad inputs (ToolError,
    not RuntimeError).
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from sovereign_agent.errors import ToolError
from sovereign_agent.session.directory import Session
from sovereign_agent.tools.registry import ToolRegistry, ToolResult, _RegisteredTool

from starter.edinburgh_research.integrity import record_tool_call

_SAMPLE_DATA = Path(__file__).parent / "sample_data"


def _load_fixture(name: str) -> object:
    """Load a JSON fixture from sample_data/. Raise ToolError on missing file."""
    path = _SAMPLE_DATA / name
    if not path.exists():
        raise ToolError(
            code="SA_TOOL_DEPENDENCY_MISSING",
            message=f"missing fixture: {name}",
            context={"path": str(path)},
        )
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# TODO 1 — venue_search
# ---------------------------------------------------------------------------
def venue_search(near: str, party_size: int, budget_max_gbp: int = 1000) -> ToolResult:
    """Search for Edinburgh venues near <near> that can seat the party."""
    args = {"near": near, "party_size": party_size, "budget_max_gbp": budget_max_gbp}
    try:
        venues = _load_fixture("venues.json")
    except ToolError as exc:
        out: dict = {"error": exc.to_dict()}
        record_tool_call("venue_search", args, out)
        return ToolResult(success=False, output=out, summary=str(exc), error=exc)

    needle = (near or "").strip().lower()
    matches = [
        v
        for v in venues
        if v.get("open_now")
        and needle in (v.get("area", "").lower())
        and v.get("seats_available_evening", 0) >= party_size
        and v.get("hire_fee_gbp", 0) + v.get("min_spend_gbp", 0) <= budget_max_gbp
    ]

    output = {
        "near": near,
        "party_size": party_size,
        "budget_max_gbp": budget_max_gbp,
        "results": matches,
        "count": len(matches),
    }
    summary = f"venue_search({near}, party={party_size}): {len(matches)} result(s)"
    record_tool_call("venue_search", args, output)
    return ToolResult(success=True, output=output, summary=summary)


# ---------------------------------------------------------------------------
# TODO 2 — get_weather
# ---------------------------------------------------------------------------
def get_weather(city: str, date: str) -> ToolResult:
    """Look up the scripted weather for <city> on <date> (YYYY-MM-DD)."""
    args = {"city": city, "date": date}
    try:
        weather = _load_fixture("weather.json")
    except ToolError as exc:
        out: dict = {"error": exc.to_dict()}
        record_tool_call("get_weather", args, out)
        return ToolResult(success=False, output=out, summary=str(exc), error=exc)

    key = (city or "").strip().lower()
    city_data = weather.get(key)
    if city_data is None:
        err = ToolError(
            code="SA_TOOL_INVALID_INPUT",
            message=f"unknown city: {city!r}",
            context={"city": city, "available": sorted(weather.keys())},
        )
        out = {"error": err.to_dict()}
        record_tool_call("get_weather", args, out)
        return ToolResult(success=False, output=out, summary=str(err), error=err)

    entry = city_data.get(date)
    if entry is None:
        err = ToolError(
            code="SA_TOOL_INVALID_INPUT",
            message=f"no weather for {city} on {date}",
            context={"city": city, "date": date, "available_dates": sorted(city_data.keys())},
        )
        out = {"error": err.to_dict()}
        record_tool_call("get_weather", args, out)
        return ToolResult(success=False, output=out, summary=str(err), error=err)

    output = {"city": city, "date": date, **entry}
    summary = (
        f"get_weather({city}, {date}): {entry.get('condition')}, {entry.get('temperature_c')}C"
    )
    record_tool_call("get_weather", args, output)
    return ToolResult(success=True, output=output, summary=summary)


# ---------------------------------------------------------------------------
# TODO 3 — calculate_cost
# ---------------------------------------------------------------------------
def calculate_cost(
    venue_id: str,
    party_size: int,
    duration_hours: int,
    catering_tier: str = "bar_snacks",
) -> ToolResult:
    """Compute the total cost for a booking."""
    args = {
        "venue_id": venue_id,
        "party_size": party_size,
        "duration_hours": duration_hours,
        "catering_tier": catering_tier,
    }
    try:
        catering = _load_fixture("catering.json")
        venues = _load_fixture("venues.json")
    except ToolError as exc:
        out: dict = {"error": exc.to_dict()}
        record_tool_call("calculate_cost", args, out)
        return ToolResult(success=False, output=out, summary=str(exc), error=exc)

    rates = catering.get("base_rates_gbp_per_head", {})
    modifiers = catering.get("venue_modifiers", {})
    if catering_tier not in rates:
        err = ToolError(
            code="SA_TOOL_INVALID_INPUT",
            message=f"unknown catering_tier: {catering_tier!r}",
            context={"available": sorted(rates.keys())},
        )
        out = {"error": err.to_dict()}
        record_tool_call("calculate_cost", args, out)
        return ToolResult(success=False, output=out, summary=str(err), error=err)
    if venue_id not in modifiers:
        err = ToolError(
            code="SA_TOOL_INVALID_INPUT",
            message=f"unknown venue_id: {venue_id!r}",
            context={"available": sorted(modifiers.keys())},
        )
        out = {"error": err.to_dict()}
        record_tool_call("calculate_cost", args, out)
        return ToolResult(success=False, output=out, summary=str(err), error=err)

    venue = next((v for v in venues if v.get("id") == venue_id), {})
    base_per_head = rates[catering_tier]
    venue_mult = modifiers[venue_id]
    effective_hours = max(1, duration_hours)
    subtotal = base_per_head * venue_mult * party_size * effective_hours
    service = subtotal * catering.get("service_charge_percent", 0) / 100.0
    venue_floor = venue.get("hire_fee_gbp", 0) + venue.get("min_spend_gbp", 0)
    total = subtotal + service + venue_floor

    # Deposit policy lookup
    policy = catering.get("deposit_policy", {})
    if total < 300:
        rule = policy.get("under_gbp_300", "no_deposit_required")
    elif total <= 1000:
        rule = policy.get("gbp_300_to_1000", "deposit_20_percent")
    else:
        rule = policy.get("over_gbp_1000", "deposit_30_percent")

    if rule == "no_deposit_required":
        deposit = 0
    elif rule == "deposit_20_percent":
        deposit = total * 0.20
    elif rule == "deposit_30_percent":
        deposit = total * 0.30
    else:
        deposit = 0

    output = {
        "venue_id": venue_id,
        "party_size": party_size,
        "duration_hours": duration_hours,
        "catering_tier": catering_tier,
        "subtotal_gbp": int(round(subtotal)),
        "service_gbp": int(round(service)),
        "total_gbp": int(round(total)),
        "deposit_required_gbp": int(round(deposit)),
        "deposit_rule": rule,
    }
    summary = (
        f"calculate_cost({venue_id}, party={party_size}): "
        f"total £{output['total_gbp']}, deposit £{output['deposit_required_gbp']}"
    )
    record_tool_call("calculate_cost", args, output)
    return ToolResult(success=True, output=output, summary=summary)


# ---------------------------------------------------------------------------
# TODO 4 — generate_flyer
# ---------------------------------------------------------------------------
def generate_flyer(session: Session, event_details: dict) -> ToolResult:
    """Produce an HTML flyer and write it to workspace/flyer.html."""
    details = dict(event_details or {})

    def _e(key: str, default: str = "") -> str:
        val = details.get(key, default)
        return html.escape(str(val)) if val is not None else ""

    venue_name = _e("venue_name", "TBD")
    venue_address = _e("venue_address", "")
    date = _e("date", "")
    time = _e("time", "")
    party_size = _e("party_size", "")
    condition = _e("condition", "")
    temperature_c = _e("temperature_c", "")
    total_gbp = details.get("total_gbp", "")
    deposit_required_gbp = details.get("deposit_required_gbp", "")

    total_str = f"£{total_gbp}" if total_gbp != "" else ""
    deposit_str = f"£{deposit_required_gbp}" if deposit_required_gbp != "" else ""

    flyer = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Pub Booking Flyer</title>
  <style>
    body {{ font-family: -apple-system, sans-serif; max-width: 640px; margin: 2em auto; padding: 0 1em; }}
    h1 {{ border-bottom: 2px solid #333; padding-bottom: .3em; }}
    dt {{ font-weight: bold; margin-top: .6em; }}
    dd {{ margin-left: 1em; }}
    .weather, .cost {{ background: #f6f6f6; padding: .8em 1em; border-radius: 6px; margin: 1em 0; }}
  </style>
</head>
<body>
  <article>
    <h1 data-testid="title">Pub Booking — <span data-testid="venue_name">{venue_name}</span></h1>
    <dl>
      <dt>Venue address</dt><dd data-testid="venue_address">{venue_address}</dd>
      <dt>Date</dt><dd data-testid="date">{date}</dd>
      <dt>Time</dt><dd data-testid="time">{time}</dd>
      <dt>Party size</dt><dd data-testid="party_size">{party_size}</dd>
    </dl>
    <section class="weather">
      <h2>Weather</h2>
      <p>Condition: <span data-testid="condition">{condition}</span></p>
      <p>Temperature: <span data-testid="temperature_c">{temperature_c}</span>C</p>
    </section>
    <section class="cost">
      <h2>Cost</h2>
      <p>Total: <span data-testid="total">{total_str}</span></p>
      <p>Deposit required: <span data-testid="deposit">{deposit_str}</span></p>
    </section>
  </article>
</body>
</html>
"""

    flyer_path = session.path("workspace/flyer.html")
    flyer_path.parent.mkdir(parents=True, exist_ok=True)
    flyer_path.write_text(flyer, encoding="utf-8")

    output = {
        "path": "workspace/flyer.html",
        "bytes_written": len(flyer.encode("utf-8")),
    }
    summary = f"generate_flyer: wrote workspace/flyer.html ({len(flyer)} chars)"
    record_tool_call("generate_flyer", {"event_details": details}, output)
    return ToolResult(success=True, output=output, summary=summary)


# ---------------------------------------------------------------------------
# Registry builder — DO NOT MODIFY the name, signature, or registration calls.
# The grader imports and calls this to pick up your tools.
# ---------------------------------------------------------------------------
def build_tool_registry(session: Session) -> ToolRegistry:
    """Build a session-scoped tool registry with all four Ex5 tools plus
    the sovereign-agent builtins (read_file, write_file, list_files,
    handoff_to_structured, complete_task).

    DO NOT change the tool names — the tests and grader call them by name.
    """
    from sovereign_agent.tools.builtin import make_builtin_registry

    reg = make_builtin_registry(session)

    # venue_search
    reg.register(
        _RegisteredTool(
            name="venue_search",
            description="Search Edinburgh venues by area, party size, and max budget.",
            fn=venue_search,
            parameters_schema={
                "type": "object",
                "properties": {
                    "near": {"type": "string"},
                    "party_size": {"type": "integer"},
                    "budget_max_gbp": {"type": "integer", "default": 1000},
                },
                "required": ["near", "party_size"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # read-only
            examples=[
                {
                    "input": {"near": "Haymarket", "party_size": 6, "budget_max_gbp": 800},
                    "output": {"count": 1, "results": [{"id": "haymarket_tap"}]},
                }
            ],
        )
    )

    # get_weather
    reg.register(
        _RegisteredTool(
            name="get_weather",
            description="Get scripted weather for a city on a YYYY-MM-DD date.",
            fn=get_weather,
            parameters_schema={
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "date": {"type": "string"},
                },
                "required": ["city", "date"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # read-only
            examples=[
                {
                    "input": {"city": "Edinburgh", "date": "2026-04-25"},
                    "output": {"condition": "cloudy", "temperature_c": 12},
                }
            ],
        )
    )

    # calculate_cost
    reg.register(
        _RegisteredTool(
            name="calculate_cost",
            description="Compute total cost and deposit for a booking.",
            fn=calculate_cost,
            parameters_schema={
                "type": "object",
                "properties": {
                    "venue_id": {"type": "string"},
                    "party_size": {"type": "integer"},
                    "duration_hours": {"type": "integer"},
                    "catering_tier": {
                        "type": "string",
                        "enum": ["drinks_only", "bar_snacks", "sit_down_meal", "three_course_meal"],
                        "default": "bar_snacks",
                    },
                },
                "required": ["venue_id", "party_size", "duration_hours"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # pure compute, no shared state
            examples=[
                {
                    "input": {
                        "venue_id": "haymarket_tap",
                        "party_size": 6,
                        "duration_hours": 3,
                    },
                    "output": {"total_gbp": 540, "deposit_required_gbp": 0},
                }
            ],
        )
    )

    # generate_flyer — parallel_safe=False because it writes a file
    def _flyer_adapter(event_details: dict) -> ToolResult:
        return generate_flyer(session, event_details)

    reg.register(
        _RegisteredTool(
            name="generate_flyer",
            description="Write an HTML flyer for the event to workspace/flyer.html.",
            fn=_flyer_adapter,
            parameters_schema={
                "type": "object",
                "properties": {"event_details": {"type": "object"}},
                "required": ["event_details"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=False,  # writes a file — MUST be False
            examples=[
                {
                    "input": {
                        "event_details": {
                            "venue_name": "Haymarket Tap",
                            "date": "2026-04-25",
                            "party_size": 6,
                        }
                    },
                    "output": {"path": "workspace/flyer.html"},
                }
            ],
        )
    )

    return reg


__all__ = [
    "build_tool_registry",
    "venue_search",
    "get_weather",
    "calculate_cost",
    "generate_flyer",
]
