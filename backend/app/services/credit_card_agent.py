import anthropic
import json
from app.services.card_benefits_db import CARD_DB, get_card, get_earn_rate, list_cards

from app.services.prompts import VOICE_BREVITY
client = anthropic.AsyncAnthropic()

# ─────────────────────────────────────────────
# CREDIT CARD INTELLIGENCE AGENT
# Level A: guest tells Sasha which cards they have
# Level B: Plaid connected (richer data, future)
# ─────────────────────────────────────────────

CCI_TOOLS = [
    {
        "name": "get_card_recommendation",
        "description": "Recommend the best credit card for a specific purchase category based on the guest's cards.",
        "input_schema": {
            "type": "object",
            "properties": {
                "guest_cards": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of card IDs the guest has. E.g. ['amex_platinum', 'chase_sapphire_reserve']"
                },
                "purchase_category": {
                    "type": "string",
                    "description": "Category of purchase: flights_direct, flights_portal, hotels_direct, hotels_portal, dining, transport, groceries, streaming, rent"
                },
                "purchase_amount_usd": {
                    "type": "number",
                    "description": "Amount of the purchase in USD"
                },
                "purchase_description": {
                    "type": "string",
                    "description": "Brief description of what is being purchased"
                }
            },
            "required": ["guest_cards", "purchase_category"]
        }
    },
    {
        "name": "analyze_trip_payment_strategy",
        "description": "Analyze a full trip and recommend which card to use for each component (flight, hotel, dining, transport).",
        "input_schema": {
            "type": "object",
            "properties": {
                "guest_cards": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of card IDs the guest has"
                },
                "trip_components": {
                    "type": "object",
                    "description": "Trip components with estimated costs. E.g. {'flight': 2000, 'hotel': 1500, 'dining': 300, 'transport': 100}",
                    "additionalProperties": {"type": "number"}
                },
                "destination": {
                    "type": "string",
                    "description": "Trip destination"
                }
            },
            "required": ["guest_cards", "trip_components"]
        }
    },
    {
        "name": "check_unused_credits",
        "description": "Check which annual credits the guest likely has unused on their cards.",
        "input_schema": {
            "type": "object",
            "properties": {
                "guest_cards": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of card IDs the guest has"
                }
            },
            "required": ["guest_cards"]
        }
    },
    {
        "name": "find_transfer_partner_opportunity",
        "description": "Find the best transfer partner redemption opportunity given the guest's cards and a target airline or hotel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "guest_cards": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of card IDs the guest has"
                },
                "target_program": {
                    "type": "string",
                    "description": "Target airline or hotel loyalty programme. E.g. 'Hyatt', 'Singapore Airlines', 'British Airways'"
                },
                "points_needed": {
                    "type": "number",
                    "description": "Approximate points needed for the redemption"
                }
            },
            "required": ["guest_cards", "target_program"]
        }
    },
    {
        "name": "list_guest_cards",
        "description": "Get details about all cards in our database to help identify which cards the guest has.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]


def get_card_recommendation(
    guest_cards: list,
    purchase_category: str,
    purchase_amount_usd: float = 0,
    purchase_description: str = ""
) -> dict:
    """Find the best card for a purchase category."""
    best_card_id = None
    best_earn_rate = 0
    best_points_value = 0
    recommendations = []

    for card_id in guest_cards:
        card = get_card(card_id)
        if not card:
            continue
        earn_rate = get_earn_rate(card_id, purchase_category)
        cpp = card.get("point_value_cpp", 1.0)
        effective_value = earn_rate * cpp  # effective cents per dollar spent

        recommendations.append({
            "card_id": card_id,
            "card_name": card["name"],
            "points_currency": card["points_currency"],
            "earn_rate": earn_rate,
            "point_value_cpp": cpp,
            "effective_value_per_dollar": round(effective_value, 2),
            "points_earned": round((purchase_amount_usd or 100) * earn_rate, 0),
            "estimated_value_usd": round((purchase_amount_usd or 100) * earn_rate * cpp / 100, 2),
        })

        if effective_value > best_points_value:
            best_points_value = effective_value
            best_earn_rate = earn_rate
            best_card_id = card_id

    recommendations.sort(key=lambda x: x["effective_value_per_dollar"], reverse=True)

    # Check for relevant credits on best card
    credits_applicable = []
    if best_card_id:
        card = get_card(best_card_id)
        if purchase_category in ["flights_direct", "flights_portal"] and "airline_fee" in card.get("annual_credits", {}):
            credits_applicable.append(card["annual_credits"]["airline_fee"])
        if purchase_category in ["hotels_direct", "hotels_portal"] and "hotel" in card.get("annual_credits", {}):
            credits_applicable.append(card["annual_credits"]["hotel"])
        if purchase_category == "dining" and "dining" in card.get("annual_credits", {}):
            credits_applicable.append(card["annual_credits"]["dining"])
        if "travel" in card.get("annual_credits", {}) and purchase_category in ["flights_direct", "hotels_direct", "transport"]:
            credits_applicable.append(card["annual_credits"]["travel"])

    return {
        "best_card_id": best_card_id,
        "best_card_name": get_card(best_card_id)["name"] if best_card_id else None,
        "best_earn_rate": best_earn_rate,
        "purchase_category": purchase_category,
        "purchase_amount_usd": purchase_amount_usd,
        "all_recommendations": recommendations,
        "credits_applicable": credits_applicable,
    }


def analyze_trip_payment_strategy(
    guest_cards: list,
    trip_components: dict,
    destination: str = ""
) -> dict:
    """Recommend card for each trip component."""
    CATEGORY_MAP = {
        "flight": "flights_direct",
        "flights": "flights_direct",
        "hotel": "hotels_direct",
        "hotels": "hotels_direct",
        "accommodation": "hotels_direct",
        "dining": "dining",
        "food": "dining",
        "restaurants": "dining",
        "transport": "transport",
        "taxi": "transport",
        "uber": "transport",
        "lyft": "transport",
        "car_rental": "transport",
        "activities": "base_earn",
        "shopping": "base_earn",
    }

    strategy = {}
    total_estimated_value = 0

    for component, amount in trip_components.items():
        category = CATEGORY_MAP.get(component.lower(), "base_earn")
        rec = get_card_recommendation(guest_cards, category, amount)
        strategy[component] = {
            "recommended_card": rec["best_card_name"],
            "card_id": rec["best_card_id"],
            "earn_rate": rec["best_earn_rate"],
            "amount_usd": amount,
            "estimated_points_value_usd": rec["all_recommendations"][0]["estimated_value_usd"] if rec["all_recommendations"] else 0,
        }
        total_estimated_value += strategy[component]["estimated_points_value_usd"]

    return {
        "destination": destination,
        "strategy": strategy,
        "total_trip_cost": sum(trip_components.values()),
        "total_estimated_points_value_usd": round(total_estimated_value, 2),
        "summary": f"By optimizing card usage across this trip, you could earn approximately ${round(total_estimated_value, 2)} in points value."
    }


def check_unused_credits(guest_cards: list) -> dict:
    """Summarize credits available on guest's cards."""
    credits_summary = []

    for card_id in guest_cards:
        card = get_card(card_id)
        if not card:
            continue
        card_credits = card.get("annual_credits", {})
        if card_credits:
            credits_summary.append({
                "card": card["name"],
                "card_id": card_id,
                "credits": card_credits,
                "total_credit_value": sum(
                    c.get("amount", 0) for c in card_credits.values()
                    if isinstance(c, dict)
                )
            })

    credits_summary.sort(key=lambda x: x["total_credit_value"], reverse=True)
    return {
        "cards_with_credits": credits_summary,
        "note": "These are annual credits that reset each year. Verify what you have already used."
    }


def find_transfer_partner_opportunity(
    guest_cards: list,
    target_program: str,
    points_needed: float = 0
) -> dict:
    """Find which card can transfer to target programme."""
    matches = []

    for card_id in guest_cards:
        card = get_card(card_id)
        if not card:
            continue
        partners = card.get("transfer_partners", {})
        if isinstance(partners, str):
            continue

        all_partners = partners.get("airlines", []) + partners.get("hotels", [])
        for partner in all_partners:
            if target_program.lower() in partner["name"].lower():
                matches.append({
                    "card": card["name"],
                    "card_id": card_id,
                    "points_currency": card["points_currency"],
                    "partner": partner["name"],
                    "ratio": partner["ratio"],
                    "points_needed_from_card": points_needed if partner["ratio"] == "1:1" else round(points_needed * 1.25, 0),
                })

    return {
        "target_program": target_program,
        "transfer_options": matches,
        "found": len(matches) > 0,
        "note": "Transfer ratios may change. Always verify on the card issuer's website before transferring."
    }


def list_guest_cards_tool() -> dict:
    """Return all available cards."""
    return {"available_cards": list_cards()}


SYSTEM_PROMPT = """You are Sasha's Credit Card Intelligence specialist. You help guests maximize the value of their credit cards for every travel purchase.

Your capabilities:
- Recommend which card to use for specific purchases (flights, hotels, dining, transport)
- Analyze a full trip and create a payment strategy to maximize points
- Surface unused annual credits the guest should use before they expire
- Find transfer partner opportunities to redeem points for maximum value
- Explain the real effective cost of purchases after points value

How to help guests:
1. First find out which cards they have (ask or use list_guest_cards to show options)
2. Understand what they are purchasing or planning
3. Use tools to calculate the best strategy
4. Explain the recommendation clearly with the numbers — show them the effective cost after points

Key principle: "Cheapest" is not just the price. A $4,000 Lufthansa flight on Amex Platinum earning 5x points at 2cpp is effectively $3,600 after points value. Always show the real cost.

Always include:
- Which card to use and why (earn rate + relevant credits)
- How many points they will earn and what those points are worth
- Any relevant unused credits they should apply
- What to do at checkout (pay with X card, decline Y insurance, apply Z credit)

If the guest does not know their card IDs, show them the list and ask them to identify their cards.

If the guest mentions a card not in the database, tell them:
"I don't have [card name] in my database yet. You can submit it at /api/cards/submit and our team will verify and add it within 24-48 hours. In the meantime, I can help with your other cards or give general advice based on the card's known benefits."

Never make up earn rates or benefits for cards not in the database. Always be honest about the limits of your knowledge and direct guests to verify benefits directly with their card issuer."""


async def run_credit_card_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []

    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []

    while True:
        response = await client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT + VOICE_BREVITY,
            tools=CCI_TOOLS,
            messages=messages
        )

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "get_card_recommendation":
                        result = get_card_recommendation(**inp)
                    elif block.name == "analyze_trip_payment_strategy":
                        result = analyze_trip_payment_strategy(**inp)
                    elif block.name == "check_unused_credits":
                        result = check_unused_credits(**inp)
                    elif block.name == "find_transfer_partner_opportunity":
                        result = find_transfer_partner_opportunity(**inp)
                    elif block.name == "list_guest_cards":
                        result = list_guest_cards_tool()
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
                "response": "Credit card intelligence agent error.",
                "tools_used": [],
                "messages": messages
            }
