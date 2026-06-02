import anthropic
import json
import re
from datetime import datetime, timedelta
from typing import Optional

client = anthropic.Anthropic()

# ─────────────────────────────────────────────
# SMART SASHA — FUZZY PARAMETER EXTRACTION
# Turns vague travel requests into structured
# search parameters. No API dependencies —
# pure extraction and assumption logic.
# Search layer plugs in when RateHawk/Duffel land.
# ─────────────────────────────────────────────

# ── Default assumptions when params are fuzzy ──

SUMMER_DATES = {
    "early":  {"start": "June 15",  "end": "June 30"},
    "mid":    {"start": "July 1",   "end": "July 31"},
    "late":   {"start": "August 1", "end": "August 31"},
    "default":{"start": "July 1",   "end": "August 31"},
}

SEASON_DEFAULTS = {
    "spring": {"start": "March 15", "end": "May 31"},
    "summer": {"start": "June 15",  "end": "August 31"},
    "fall":   {"start": "September 1", "end": "November 30"},
    "autumn": {"start": "September 1", "end": "November 30"},
    "winter": {"start": "December 1",  "end": "February 28"},
    "christmas": {"start": "December 20", "end": "January 3"},
    "thanksgiving": {"start": "November 25", "end": "December 1"},
    "easter": {"start": "April 1", "end": "April 15"},
}

REGION_AIRPORTS = {
    "western europe": ["LHR", "CDG", "AMS", "FRA"],
    "europe":         ["LHR", "CDG", "AMS", "FRA"],
    "southern europe":["FCO", "BCN", "MAD", "ATH"],
    "eastern europe": ["PRG", "VIE", "BUD", "WAW"],
    "scandinavia":    ["CPH", "ARN", "OSL"],
    "uk":             ["LHR", "LGW", "MAN"],
    "france":         ["CDG", "NCE", "LYS"],
    "italy":          ["FCO", "MXP", "VCE"],
    "spain":          ["MAD", "BCN"],
    "southeast asia": ["SIN", "BKK", "KUL", "HKG"],
    "asia":           ["NRT", "SIN", "HKG", "ICN"],
    "japan":          ["NRT", "OSA"],
    "caribbean":      ["SJU", "MBJ", "NAS"],
    "mexico":         ["CUN", "MEX", "GDL"],
    "latin america":  ["GRU", "BOG", "LIM", "EZE"],
    "middle east":    ["DXB", "DOH", "AUH"],
    "africa":         ["NBO", "JNB", "CMN"],
    "australia":      ["SYD", "MEL", "BNE"],
    "new zealand":    ["AKL", "CHC"],
}

CABIN_ALIASES = {
    "business": "business",
    "business class": "business",
    "biz": "business",
    "first": "first",
    "first class": "first",
    "premium economy": "premium_economy",
    "premium": "premium_economy",
    "economy": "economy",
    "coach": "economy",
    "economy class": "economy",
}

DURATION_DEFAULTS = {
    "weekend": 3,
    "long weekend": 4,
    "week": 7,
    "a week": 7,
    "one week": 7,
    "two weeks": 14,
    "2 weeks": 14,
    "ten days": 10,
    "10 days": 10,
    "month": 30,
}

HOTEL_STAR_DEFAULTS = {
    "budget": 2,
    "cheap": 2,
    "affordable": 3,
    "moderate": 3,
    "mid range": 3,
    "mid-range": 3,
    "nice": 4,
    "good": 4,
    "luxury": 5,
    "luxurious": 5,
    "5 star": 5,
    "5-star": 5,
    "4 star": 4,
    "4-star": 4,
    "3 star": 3,
    "3-star": 3,
}

# Question priority — highest impact unknown asked first
QUESTION_PRIORITY = [
    {"param": "duration_days",   "impact": "high",   "question": "How long are you thinking — a week, two weeks, longer?"},
    {"param": "destination",     "impact": "high",   "question": "Any specific countries or cities in mind, or are you fully open?"},
    {"param": "party_size",      "impact": "medium", "question": "Travelling solo or with someone?"},
    {"param": "budget_level",    "impact": "medium", "question": "Any budget in mind, or purely going for the best value?"},
    {"param": "airline_pref",    "impact": "low",    "question": "Any airlines you prefer or want to avoid?"},
    {"param": "hotel_amenities", "impact": "low",    "question": "Any hotel must-haves — pool, gym, specific neighbourhood?"},
]


# ─────────────────────────────────────────────
# EXTRACTION ENGINE
# ─────────────────────────────────────────────

async def extract_travel_params(user_message: str, conversation_history: list = None) -> dict:
    """
    Extract structured travel parameters from a fuzzy user message.
    Uses Claude Haiku for cost efficiency.
    Returns known params + list of unknown params + confidence scores.
    """
    history_context = ""
    if conversation_history:
        recent = conversation_history[-4:]  # last 2 turns
        history_context = "\n".join([
            f"{m['role'].upper()}: {m['content']}"
            for m in recent
        ])

    extraction_prompt = f"""Extract travel search parameters from this message. Return ONLY valid JSON.

Message: "{user_message}"
{f'Recent context:{chr(10)}{history_context}' if history_context else ''}

Return JSON with these fields (use null for unknown):
{{
  "origin_city": "city name or null",
  "origin_airport": "IATA code or null",
  "destination_city": "city/region or null — be specific if stated, keep fuzzy if fuzzy",
  "destination_region": "broad region or null (e.g. 'western europe', 'southeast asia')",
  "destination_airports": ["array of IATA codes if destination is specific, else null"],
  "cabin_class": "economy/premium_economy/business/first or null",
  "departure_date_from": "YYYY-MM-DD or null",
  "departure_date_to": "YYYY-MM-DD or null",
  "duration_days": number or null,
  "party_size": number or null,
  "hotel_min_stars": number or null,
  "budget_level": "budget/moderate/luxury or null",
  "budget_max_usd": number or null,
  "goal": "cheapest/fastest/best_value/most_comfortable or null",
  "airline_preference": "airline name or null",
  "airline_exclusion": "airline name or null",
  "flexibility": "exact/flexible/very_flexible",
  "fuzzy_params": ["list of params that are vague or missing"],
  "confidence": {{"origin": 0-1, "destination": 0-1, "dates": 0-1, "budget": 0-1}}
}}

Current year: {datetime.now().year}. If they say "this summer" use June 15 - Aug 31 of current year.
If they say "next year" add 1 to current year."""

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=600,
        messages=[{"role": "user", "content": extraction_prompt}]
    )

    text = response.content[0].text.strip()
    # Strip markdown code blocks if present
    text = re.sub(r'^```json\s*', '', text)
    text = re.sub(r'\s*```$', '', text)

    try:
        params = json.loads(text)
    except json.JSONDecodeError:
        # Fallback — extract what we can
        params = {
            "fuzzy_params": ["origin", "destination", "dates", "duration"],
            "confidence": {"origin": 0, "destination": 0, "dates": 0, "budget": 0}
        }

    return params


def apply_smart_defaults(params: dict) -> dict:
    """
    Fill in smart defaults for fuzzy parameters.
    Returns enriched params + list of assumptions made.
    """
    assumptions = []
    enriched = dict(params)

    # Destination: if region given, expand to top airports
    if not enriched.get("destination_airports") and enriched.get("destination_region"):
        region = enriched["destination_region"].lower()
        airports = REGION_AIRPORTS.get(region)
        if airports:
            enriched["destination_airports"] = airports
            assumptions.append(f"Searching top {len(airports)} airports in {enriched['destination_region']}: {', '.join(airports)}")

    # Dates: apply season defaults
    if not enriched.get("departure_date_from"):
        # Check for season keywords in original message (passed via metadata)
        season = enriched.get("_season_hint", "summer")
        if season in SEASON_DEFAULTS:
            year = datetime.now().year
            season_data = SEASON_DEFAULTS[season]
            enriched["departure_date_from"] = f"{year}-{_parse_date_str(season_data['start'])}"
            enriched["departure_date_to"] = f"{year}-{_parse_date_str(season_data['end'])}"
            assumptions.append(f"Assuming {season} dates: {season_data['start']} – {season_data['end']} {year}")

    # Duration: default to 7 nights if not specified
    if not enriched.get("duration_days"):
        enriched["duration_days"] = 7
        assumptions.append("Assuming 7 night trip")

    # Hotel stars: default based on cabin class
    if not enriched.get("hotel_min_stars"):
        cabin = enriched.get("cabin_class", "economy")
        if cabin in ["business", "first"]:
            enriched["hotel_min_stars"] = 4
            assumptions.append("Assuming 4-star+ hotels (matching business class travel style)")
        else:
            enriched["hotel_min_stars"] = 3
            assumptions.append("Assuming 3-star+ hotels")

    # Party size default
    if not enriched.get("party_size"):
        enriched["party_size"] = 1
        assumptions.append("Assuming solo traveller")

    enriched["_assumptions"] = assumptions
    return enriched


def _parse_date_str(date_str: str) -> str:
    """Convert 'June 15' to '06-15'."""
    months = {
        "January": "01", "February": "02", "March": "03", "April": "04",
        "May": "05", "June": "06", "July": "07", "August": "08",
        "September": "09", "October": "10", "November": "11", "December": "12"
    }
    parts = date_str.split()
    if len(parts) == 2:
        month = months.get(parts[0], "07")
        day = parts[1].zfill(2)
        return f"{month}-{day}"
    return "07-01"


def get_next_question(params: dict) -> Optional[str]:
    """
    Return the single highest-impact question to ask next.
    Returns None if we have enough to search.
    """
    fuzzy = params.get("fuzzy_params", [])
    confidence = params.get("confidence", {})

    for q in QUESTION_PRIORITY:
        param = q["param"]
        # Check if param is missing or low confidence
        if param in fuzzy:
            return q["question"]
        if param == "destination" and confidence.get("destination", 1) < 0.5:
            return q["question"]
        if param == "duration_days" and not params.get("duration_days"):
            return q["question"]

    return None  # We have enough to search


def build_search_manifest(params: dict) -> dict:
    """
    Build the search manifest — the list of parallel searches to run.
    Each search is one (origin, destination, dates, cabin) combination.
    Returns manifest ready for the search layer (RateHawk/Duffel).
    """
    origin = params.get("origin_airport") or params.get("origin_city", "")
    destinations = params.get("destination_airports", [])
    cabin = params.get("cabin_class", "economy")
    date_from = params.get("departure_date_from")
    date_to = params.get("departure_date_to")
    duration = params.get("duration_days", 7)

    if not destinations:
        return {"searches": [], "error": "No destination airports resolved"}

    # Generate date windows (up to 3 across the range)
    date_windows = _generate_date_windows(date_from, date_to)

    searches = []
    for dest in destinations:
        for window in date_windows:
            searches.append({
                "origin": origin,
                "destination": dest,
                "outbound_date": window["outbound"],
                "return_date": window["return"],
                "cabin": cabin,
                "adults": params.get("party_size", 1),
                "hotel_min_stars": params.get("hotel_min_stars", 3),
                "duration_days": duration,
                "goal": params.get("goal", "cheapest"),
            })

    return {
        "searches": searches,
        "total": len(searches),
        "destinations": destinations,
        "date_windows": date_windows,
        "assumptions": params.get("_assumptions", []),
        "status": "ready_for_search",
        "note": "Plug RateHawk/Duffel into execute_searches() when credentials available"
    }


def _generate_date_windows(date_from: str, date_to: str, max_windows: int = 3) -> list:
    """Generate up to 3 evenly-spaced departure date windows across the range."""
    if not date_from:
        # Default to next month
        next_month = datetime.now() + timedelta(days=30)
        date_from = next_month.strftime("%Y-%m-%d")
        date_to = (next_month + timedelta(days=60)).strftime("%Y-%m-%d")

    try:
        start = datetime.strptime(date_from, "%Y-%m-%d")
        end = datetime.strptime(date_to or date_from, "%Y-%m-%d")
    except ValueError:
        start = datetime.now() + timedelta(days=30)
        end = start + timedelta(days=60)

    windows = []
    if start == end:
        windows.append({"outbound": start.strftime("%Y-%m-%d"), "return": (start + timedelta(days=7)).strftime("%Y-%m-%d")})
    else:
        span = (end - start).days
        step = max(span // max_windows, 1)
        for i in range(min(max_windows, span // step + 1)):
            outbound = start + timedelta(days=i * step)
            return_date = outbound + timedelta(days=7)
            windows.append({
                "outbound": outbound.strftime("%Y-%m-%d"),
                "return": return_date.strftime("%Y-%m-%d")
            })

    return windows


# ─────────────────────────────────────────────
# SCORING ENGINE
# Ranks search results by multiple factors
# Plug actual flight/hotel results in here
# ─────────────────────────────────────────────

def score_option(option: dict, goal: str = "cheapest", guest_prefs: dict = None) -> float:
    """
    Score a flight+hotel combination.
    Higher score = better match for guest's goal.

    option = {
        "flight_price": 2000,
        "hotel_price_per_night": 200,
        "duration_nights": 7,
        "flight_duration_hours": 9,
        "hotel_stars": 4,
        "carrier": "Lufthansa",
        "destination": "LHR",
        "points_value_usd": 180,  # from CCI agent
    }
    """
    if guest_prefs is None:
        guest_prefs = {}

    total_price = option.get("flight_price", 0) + (
        option.get("hotel_price_per_night", 0) * option.get("duration_nights", 7)
    )
    max_price = guest_prefs.get("budget_max_usd", 10000)
    min_price = 500

    score = 0.0

    # Price score (40%) — lower is better
    if total_price > 0:
        price_score = max(0, (max_price - total_price) / (max_price - min_price))
        score += price_score * 40

    # Quality floor met (20%)
    min_stars = guest_prefs.get("hotel_min_stars", 3)
    if option.get("hotel_stars", 0) >= min_stars:
        score += 20

    # Flight duration (15%) — shorter is better
    max_duration = 20
    flight_hours = option.get("flight_duration_hours", 10)
    duration_score = max(0, (max_duration - flight_hours) / max_duration)
    score += duration_score * 15

    # Points value (15%) — higher points value = lower effective cost
    points_value = option.get("points_value_usd", 0)
    points_score = min(1.0, points_value / 300)  # cap at $300 value
    score += points_score * 15

    # Airline preference (10%)
    preferred_airlines = guest_prefs.get("preferred_airlines", [])
    excluded_airlines = guest_prefs.get("excluded_airlines", [])
    carrier = option.get("carrier", "")
    if carrier in preferred_airlines:
        score += 10
    elif carrier in excluded_airlines:
        score -= 20  # heavy penalty for excluded airline

    # Goal modifier
    if goal == "fastest":
        score += (max(0, (max_duration - flight_hours) / max_duration)) * 20
    elif goal == "most_comfortable":
        stars = option.get("hotel_stars", 3)
        score += (stars / 5) * 20

    return round(score, 2)


def rank_options(options: list, goal: str = "cheapest", guest_prefs: dict = None) -> list:
    """Rank a list of flight+hotel options by score. Returns top 3."""
    scored = []
    for opt in options:
        opt["_score"] = score_option(opt, goal, guest_prefs)
        scored.append(opt)
    scored.sort(key=lambda x: x["_score"], reverse=True)
    return scored[:3]


# ─────────────────────────────────────────────
# SMART SASHA AGENT
# Conversational layer over the extraction engine
# ─────────────────────────────────────────────

SMART_SASHA_TOOLS = [
    {
        "name": "extract_and_plan_search",
        "description": "Extract travel parameters from a fuzzy request, apply smart defaults, and build a search plan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_message": {"type": "string", "description": "The user's travel request"},
                "season_hint": {"type": "string", "description": "Season mentioned: summer/winter/spring/fall or null"},
            },
            "required": ["user_message"]
        }
    }
]

SYSTEM_PROMPT = """You are Sasha's Smart Travel Search specialist. You turn vague travel requests into concrete search plans and deliver the best options.

Your approach:
1. Extract what you know from the request — be generous in what you infer
2. Apply smart defaults for unknowns (don't ask what you can assume)
3. Start searching immediately — tell the guest what you're searching
4. Ask ONE clarifying question — the most important unknown only
5. When results arrive, present top 3 ranked by total value (price + points)

Key principle: A guest saying "I want to go to Western Europe this summer in business class" has told you enough to start 12 parallel searches. Do it. Ask duration while you search.

Always tell the guest:
- What you're searching (destinations, dates, cabin)
- What assumptions you made
- Your one clarifying question
- When results will be ready

When you have results, present them as:
  Option 1 — [Destination]: [Airline] flight + [Hotel] — Total: $X (effective $Y after points)
  Option 2 — ...
  Option 3 — ...

Note: Search execution requires RateHawk/Duffel credentials. Until then, show the search plan and assumptions clearly."""


async def run_smart_sasha_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []

    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=SMART_SASHA_TOOLS,
            messages=messages
        )

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input

                    if block.name == "extract_and_plan_search":
                        # Extract params
                        params = await extract_travel_params(
                            inp["user_message"],
                            conversation_history
                        )
                        # Apply season hint if provided
                        if inp.get("season_hint"):
                            params["_season_hint"] = inp["season_hint"]

                        # Apply smart defaults
                        enriched = apply_smart_defaults(params)

                        # Get next question
                        next_question = get_next_question(enriched)

                        # Build search manifest
                        manifest = build_search_manifest(enriched)

                        result = {
                            "extracted_params": enriched,
                            "search_manifest": manifest,
                            "next_question": next_question,
                            "searches_planned": manifest.get("total", 0),
                            "assumptions": enriched.get("_assumptions", []),
                            "status": "ready_to_search" if manifest.get("searches") else "needs_more_info"
                        }
                    else:
                        result = {"error": "Unknown tool: " + block.name}

                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result)
                    })

            messages.append({"role": "user", "content": tool_results})

        elif response.stop_reason == "end_turn":
            return {
                "response": "".join(b.text for b in response.content if hasattr(b, "text")),
                "tools_used": tools_used,
                "messages": messages
            }
        else:
            return {
                "response": "Smart Sasha search agent error.",
                "tools_used": [],
                "messages": messages
            }
