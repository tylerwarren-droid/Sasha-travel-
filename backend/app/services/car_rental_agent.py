import anthropic
import json
from app.services.card_benefits_db import RENTAL_COVERAGE_DB, get_card, get_rental_coverage

from app.services.prompts import VOICE_BREVITY
client = anthropic.AsyncAnthropic()

# ─────────────────────────────────────────────
# CAR RENTAL INSURANCE MICROSERVICE
# Tells guests exactly what their card covers,
# what to decline at the counter, and what gaps exist
# ─────────────────────────────────────────────

RENTAL_TOOLS = [
    {
        "name": "check_rental_coverage",
        "description": "Check what rental car insurance a guest's card provides for a specific rental scenario.",
        "input_schema": {
            "type": "object",
            "properties": {
                "card_id": {
                    "type": "string",
                    "description": "The card ID to check coverage for. E.g. 'chase_sapphire_reserve'"
                },
                "rental_country": {
                    "type": "string",
                    "description": "Country where the car is being rented. E.g. 'Italy', 'United States', 'Vietnam'"
                },
                "vehicle_type": {
                    "type": "string",
                    "description": "Type of vehicle. E.g. 'standard sedan', 'SUV', 'luxury', 'exotic', 'truck', 'motorcycle'",
                },
                "rental_days": {
                    "type": "integer",
                    "description": "Number of days renting the car"
                }
            },
            "required": ["card_id", "rental_country"]
        }
    },
    {
        "name": "compare_rental_coverage",
        "description": "Compare rental car coverage across multiple cards to find the best one for a rental.",
        "input_schema": {
            "type": "object",
            "properties": {
                "guest_cards": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of card IDs the guest has"
                },
                "rental_country": {
                    "type": "string",
                    "description": "Country where the car is being rented"
                },
                "rental_days": {
                    "type": "integer",
                    "description": "Number of days renting"
                }
            },
            "required": ["guest_cards", "rental_country"]
        }
    }
]


def check_rental_coverage(
    card_id: str,
    rental_country: str,
    vehicle_type: str = "standard",
    rental_days: int = 7
) -> dict:
    """Check rental coverage for a specific scenario."""
    coverage = get_rental_coverage(card_id)
    card = get_card(card_id)

    if not coverage or not card:
        return {
            "covered": False,
            "card_id": card_id,
            "error": "Card not found in database. Please verify coverage directly with your card issuer."
        }

    # Check geographic exclusions
    country_excluded = any(
        rental_country.lower() in excl.lower()
        for excl in coverage["geographic_exclusions"]
    )

    # Check vehicle exclusions
    vehicle_excluded = False
    vehicle_lower = vehicle_type.lower()
    for excl in coverage["vehicle_exclusions"]:
        if any(word in vehicle_lower for word in excl.lower().split()):
            vehicle_excluded = True
            break

    # Check duration
    days_exceeded = rental_days > coverage["max_rental_days"]

    # Determine overall coverage status
    covered = (
        coverage["collision"]
        and not country_excluded
        and not vehicle_excluded
        and not days_exceeded
    )

    # Build verdict
    what_to_decline = []
    what_to_consider = []
    caveats = []

    if covered:
        what_to_decline.append("CDW / LDW (Collision Damage Waiver / Loss Damage Waiver)")
        if not coverage["liability"]:
            what_to_consider.append("Supplemental Liability Insurance — your card does NOT cover liability")
        if coverage["coverage_type"] == "secondary":
            caveats.append("Your personal auto insurance pays first — this card covers the remainder")
        caveats.append(f"You MUST pay the entire rental with your {card['name']}")
        caveats.append(f"You MUST decline the rental company's CDW/LDW at the counter")
    else:
        reasons = []
        if country_excluded:
            reasons.append(f"{rental_country} is excluded from coverage on this card")
        if vehicle_excluded:
            reasons.append(f"Vehicle type '{vehicle_type}' is excluded from coverage")
        if days_exceeded:
            reasons.append(f"Rental exceeds maximum {coverage['max_rental_days']} days covered")
        what_to_consider.append("Consider purchasing the rental company's CDW — your card does not cover this rental")

    return {
        "card": card["name"],
        "card_id": card_id,
        "rental_country": rental_country,
        "vehicle_type": vehicle_type,
        "rental_days": rental_days,
        "covered": covered,
        "coverage_type": coverage["coverage_type"] if covered else "none",
        "collision_covered": coverage["collision"] and not country_excluded and not vehicle_excluded and not days_exceeded,
        "theft_covered": coverage["theft"] and not country_excluded and not vehicle_excluded and not days_exceeded,
        "liability_covered": coverage["liability"],
        "what_to_decline_at_counter": what_to_decline,
        "what_to_consider_adding": what_to_consider,
        "caveats": caveats,
        "note": coverage["note"],
        "last_verified": coverage["last_verified"],
        "source_url": coverage["source_url"],
    }


def compare_rental_coverage(
    guest_cards: list,
    rental_country: str,
    rental_days: int = 7
) -> dict:
    """Compare rental coverage across all guest cards."""
    results = []

    for card_id in guest_cards:
        coverage_result = check_rental_coverage(card_id, rental_country, "standard", rental_days)
        results.append(coverage_result)

    # Sort: primary coverage first, then secondary, then none
    coverage_rank = {"primary": 0, "secondary": 1, "none": 2}
    results.sort(key=lambda x: coverage_rank.get(x.get("coverage_type", "none"), 2))

    best = results[0] if results else None

    return {
        "rental_country": rental_country,
        "rental_days": rental_days,
        "best_card": best["card"] if best and best["covered"] else None,
        "best_card_id": best["card_id"] if best and best["covered"] else None,
        "coverage_type": best["coverage_type"] if best and best["covered"] else "none",
        "all_cards": results,
        "recommendation": (
            f"Use your {best['card']} — it provides {best['coverage_type']} coverage in {rental_country}."
            if best and best["covered"]
            else f"None of your cards provide rental coverage in {rental_country} for this scenario. Consider purchasing CDW from the rental company."
        )
    }


SYSTEM_PROMPT = """You are Sasha's rental car insurance specialist. You help guests understand exactly what their credit card covers for rental cars — and what they need to buy or skip at the rental counter.

This is one of the most confusing and high-stakes decisions travellers make. Be definitive and clear.

How to help:
1. Find out which card(s) the guest has
2. Find out where they are renting (country), what vehicle, and how many days
3. Use check_rental_coverage or compare_rental_coverage to get the facts
4. Give them a clear, actionable answer:
   - WHAT to decline at the counter (save them money)
   - WHAT to consider adding (fill coverage gaps)
   - WHAT caveats to know (must pay with card, must decline CDW to activate coverage)

Always explain:
- Primary vs secondary coverage (primary = your card pays first, no personal insurance needed)
- The difference between CDW/LDW (damage to rental car) and liability (damage to others)
- The geographic exclusions — some cards don't cover certain countries

Never give uncertain advice on financial or legal protection. If unsure, recommend they call their card issuer directly.

Always include the verification date and suggest they confirm with their issuer before relying on coverage."""


async def run_car_rental_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []

    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []

    while True:
        response = await client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT + VOICE_BREVITY,
            tools=RENTAL_TOOLS,
            messages=messages
        )

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "check_rental_coverage":
                        result = check_rental_coverage(**inp)
                    elif block.name == "compare_rental_coverage":
                        result = compare_rental_coverage(**inp)
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
                "response": "Car rental insurance agent error.",
                "tools_used": [],
                "messages": messages
            }
