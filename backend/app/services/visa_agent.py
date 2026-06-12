import os
import anthropic
import json
import re
from browserbase import Browserbase
from playwright.sync_api import sync_playwright

client = anthropic.Anthropic()
BROWSERBASE_API_KEY = os.getenv("BROWSERBASE_API_KEY", "").strip()
BROWSERBASE_PROJECT_ID = os.getenv("BROWSERBASE_PROJECT_ID", "").strip()

VISA_TOOLS = [
    {
        "name": "check_visa_requirements",
        "description": "Search for current visa requirements, passport validity rules, entry restrictions, visa on arrival availability, and application processes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nationality": {"type": "string", "description": "Traveler's passport nationality, e.g. American, British, Australian"},
                "destination": {"type": "string", "description": "Country or countries being visited"},
                "travel_date": {"type": "string", "description": "Approximate travel date or month/year"}
            },
            "required": ["nationality", "destination"]
        }
    },
    {
        "name": "start_visa_application",
        "description": "Navigate to a visa application portal and pre-fill the form with the applicant's details using a remote browser session. Always call check_visa_requirements first to get the application_link. Never auto-submits — returns a live session URL for the traveler to review, upload documents, and complete payment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "application_url": {"type": "string", "description": "The visa application portal URL obtained from check_visa_requirements"},
                "applicant_name": {"type": "string", "description": "Full name exactly as printed on passport"},
                "nationality": {"type": "string", "description": "Nationality / country of passport"},
                "email": {"type": "string", "description": "Applicant email address"},
                "travel_date": {"type": "string", "description": "Intended arrival date (YYYY-MM-DD preferred)"},
                "destination": {"type": "string", "description": "Destination country"},
                "passport_number": {"type": "string", "description": "Passport number"},
                "date_of_birth": {"type": "string", "description": "Date of birth (YYYY-MM-DD preferred)"},
                "passport_expiry": {"type": "string", "description": "Passport expiry date (YYYY-MM-DD preferred)"},
                "phone": {"type": "string", "description": "Phone number with country code"},
                "hotel_name": {"type": "string", "description": "Hotel or accommodation name in destination"}
            },
            "required": ["application_url", "applicant_name", "nationality", "email", "travel_date", "destination"]
        }
    }
]


async def check_visa_requirements(nationality: str, destination: str, travel_date: str = "") -> dict:
    date_ctx = " traveling in " + travel_date if travel_date else ""
    query = (
        nationality + " passport holder" + date_ctx + " visiting " + destination +
        ". Return ONLY a JSON object with: visa_type (e.g. visa-free, visa on arrival, e-visa, embassy visa), "
        "cost_usd, processing_days, passport_validity_required, application_link, entry_restrictions, notes. "
        "Use empty string for unknown fields. No other text."
    )
    try:
        response = client.messages.create(
            model="claude-haiku-4-5", max_tokens=600,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": query}]
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            return {"requirements": json.loads(m.group()), "nationality": nationality, "destination": destination}
        return {"requirements": {}, "raw": text}
    except Exception as e:
        return {"requirements": {}, "error": str(e)}


async def start_visa_application(
    application_url: str, applicant_name: str, nationality: str, email: str,
    travel_date: str, destination: str,
    passport_number: str = "", date_of_birth: str = "", passport_expiry: str = "",
    phone: str = "", hotel_name: str = ""
) -> dict:
    if not BROWSERBASE_API_KEY or not BROWSERBASE_PROJECT_ID:
        return {"started": False, "error": "Browserbase not configured"}
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _fill_visa_application_sync,
            application_url, applicant_name, nationality, email,
            travel_date, destination, passport_number, date_of_birth,
            passport_expiry, phone, hotel_name)
        return result
    except Exception as e:
        return {"started": False, "error": str(e)}


def _fill_visa_application_sync(
    application_url, applicant_name, nationality, email,
    travel_date, destination, passport_number, date_of_birth,
    passport_expiry, phone, hotel_name
) -> dict:
    bb = Browserbase(api_key=BROWSERBASE_API_KEY)
    session = bb.sessions.create(project_id=BROWSERBASE_PROJECT_ID)
    session_url = f"https://browserbase.com/sessions/{session.id}"

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(session.connect_url)
        context = browser.contexts[0]
        page = context.pages[0]
        try:
            # Split name for portals that have separate first/last fields
            name_parts = applicant_name.strip().split()
            first_name = name_parts[0] if name_parts else applicant_name
            last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

            # Detect portal type so we can navigate intelligently
            url_lower = application_url.lower()
            if "ivisa.com" in url_lower:
                portal_type = "ivisa"
            elif "vfsglobal.com" in url_lower:
                portal_type = "vfs"
            elif "evisa.xuatnhapcanh" in url_lower or ("evisa" in url_lower and "vietnam" in url_lower):
                portal_type = "vietnam_evisa"
            elif "indianvisaonline" in url_lower or ("evisa" in url_lower and "india" in url_lower):
                portal_type = "india_evisa"
            elif "evisa.gov.tr" in url_lower:
                portal_type = "turkey_evisa"
            elif "eta.immigration" in url_lower or "eta.gov" in url_lower:
                portal_type = "eta"
            else:
                portal_type = "generic"

            page.goto(application_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            filled_fields = []

            def try_fill(selectors: list, value: str, field_name: str):
                for sel in selectors:
                    try:
                        loc = page.locator(sel).first
                        if loc.count() > 0 and loc.is_visible():
                            loc.fill(value)
                            filled_fields.append(field_name)
                            return True
                    except Exception:
                        pass
                return False

            def try_select(selectors: list, value: str, field_name: str):
                for sel in selectors:
                    try:
                        loc = page.locator(sel).first
                        if loc.count() > 0 and loc.is_visible():
                            # Try by label first, then by value
                            try:
                                page.select_option(sel, label=value)
                            except Exception:
                                try:
                                    page.select_option(sel, value=value)
                                except Exception:
                                    continue
                            filled_fields.append(field_name)
                            return True
                    except Exception:
                        pass
                return False

            # ── First name ──
            try_fill([
                'input[name*="first_name" i]', 'input[name*="firstname" i]',
                'input[name*="given_name" i]', 'input[name*="givenname" i]',
                'input[id*="first_name" i]', 'input[id*="firstname" i]',
                'input[id*="given" i]', 'input[placeholder*="first name" i]',
                'input[placeholder*="given name" i]',
            ], first_name, "first_name")

            # ── Last / family name ──
            if last_name:
                try_fill([
                    'input[name*="last_name" i]', 'input[name*="lastname" i]',
                    'input[name*="surname" i]', 'input[name*="family_name" i]',
                    'input[id*="last_name" i]', 'input[id*="surname" i]',
                    'input[id*="family" i]', 'input[placeholder*="last name" i]',
                    'input[placeholder*="surname" i]',
                ], last_name, "last_name")

            # ── Full name (for portals that use a single field) ──
            if "first_name" not in filled_fields:
                try_fill([
                    'input[name*="full_name" i]', 'input[name*="fullname" i]',
                    'input[id*="full_name" i]', 'input[placeholder*="full name" i]',
                    'input[placeholder*="name as on passport" i]',
                ], applicant_name, "full_name")

            # ── Email ──
            try_fill([
                'input[type="email"]',
                'input[name*="email" i]', 'input[id*="email" i]',
                'input[placeholder*="email" i]',
            ], email, "email")

            # ── Phone ──
            if phone:
                try_fill([
                    'input[type="tel"]',
                    'input[name*="phone" i]', 'input[name*="mobile" i]',
                    'input[id*="phone" i]', 'input[placeholder*="phone" i]',
                ], phone, "phone")

            # ── Passport number ──
            if passport_number:
                try_fill([
                    'input[name*="passport_no" i]', 'input[name*="passport_number" i]',
                    'input[name*="passportnumber" i]', 'input[name*="document_number" i]',
                    'input[id*="passport_no" i]', 'input[id*="passport_number" i]',
                    'input[placeholder*="passport number" i]', 'input[placeholder*="passport no" i]',
                ], passport_number, "passport_number")

            # ── Date of birth ──
            if date_of_birth:
                try_fill([
                    'input[name*="dob" i]', 'input[name*="date_of_birth" i]',
                    'input[name*="dateofbirth" i]', 'input[name*="birth_date" i]',
                    'input[id*="dob" i]', 'input[id*="date_of_birth" i]',
                    'input[placeholder*="date of birth" i]', 'input[placeholder*="birth date" i]',
                    'input[type="date"][id*="birth" i]',
                ], date_of_birth, "date_of_birth")

            # ── Passport expiry ──
            if passport_expiry:
                try_fill([
                    'input[name*="expiry" i]', 'input[name*="expiration" i]',
                    'input[name*="passport_expiry" i]', 'input[name*="passport_exp" i]',
                    'input[id*="expiry" i]', 'input[id*="expiration" i]',
                    'input[placeholder*="expiry" i]', 'input[placeholder*="expiration" i]',
                ], passport_expiry, "passport_expiry")

            # ── Arrival / travel date ──
            try_fill([
                'input[name*="arrival_date" i]', 'input[name*="arrivaldate" i]',
                'input[name*="travel_date" i]', 'input[name*="entry_date" i]',
                'input[name*="intended_arrival" i]',
                'input[id*="arrival" i]', 'input[id*="entry_date" i]',
                'input[placeholder*="arrival date" i]', 'input[placeholder*="entry date" i]',
            ], travel_date, "travel_date")

            # ── Nationality (dropdown) ──
            try_select([
                'select[name*="nationality" i]', 'select[id*="nationality" i]',
                'select[name*="citizenship" i]', 'select[id*="citizenship" i]',
                'select[name*="country_of_passport" i]',
            ], nationality, "nationality")

            # ── Hotel / accommodation ──
            if hotel_name:
                try_fill([
                    'input[name*="hotel" i]', 'input[name*="accommodation" i]',
                    'input[id*="hotel" i]', 'input[placeholder*="hotel" i]',
                    'input[placeholder*="accommodation" i]',
                ], hotel_name, "hotel_name")

            page.screenshot(path="/tmp/visa_form_filled.png")

            remaining = []
            if "passport_number" not in filled_fields:
                remaining.append("passport number (sensitive — enter manually)")
            if "date_of_birth" not in filled_fields and date_of_birth:
                remaining.append("date of birth")
            remaining += ["passport photo upload", "payment of visa fee", "final review and submission"]

            return {
                "started": True,
                "portal_type": portal_type,
                "filled_fields": filled_fields,
                "message": (
                    f"Form pre-filled on {portal_type} portal ({len(filled_fields)} fields). "
                    f"Filled: {', '.join(filled_fields) or 'none detected — portal may need manual entry'}."
                ),
                "next_steps": remaining,
                "important": "Do NOT auto-submit. Open the session link to review all fields, upload documents, and pay.",
                "session_url": session_url
            }

        except Exception as e:
            return {
                "started": False,
                "error": str(e),
                "session_url": session_url,
                "message": "Could not pre-fill the form automatically. Open the session link to apply manually."
            }
        finally:
            browser.close()


SYSTEM_PROMPT = """You are Sasha's visa and entry requirements specialist. Search for current visa requirements, passport validity rules, entry restrictions, visa on arrival availability, and application processes for any country pair.

WORKFLOW:
1. Always call check_visa_requirements first to find visa type, cost, processing time, and application_link.
2. If an application_link is found AND the traveler has an e-visa or online application option, offer to start the application using start_visa_application.
3. Never auto-submit — the session is handed back to the traveler for document upload, payment, and final review.

COLLECT before starting an application: full name as on passport, date of birth, passport number, passport expiry date, email, phone, intended arrival date, hotel/accommodation name.

Always remind traveler: review all fields carefully before submitting and paying."""


async def run_visa_agent(user_message: str, conversation_history: list = None) -> dict:
    if conversation_history is None:
        conversation_history = []
    messages = conversation_history + [{"role": "user", "content": user_message}]
    tools_used = []
    while True:
        response = client.messages.create(model="claude-sonnet-4-5", max_tokens=1024,
            system=SYSTEM_PROMPT, tools=VISA_TOOLS, messages=messages)
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    inp = block.input
                    if block.name == "check_visa_requirements":
                        result = await check_visa_requirements(**inp)
                    elif block.name == "start_visa_application":
                        result = await start_visa_application(**inp)
                    else:
                        result = {"error": "Unknown tool: " + block.name}
                    tools_used.append({"tool": block.name, "result": result})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            return {"response": "".join(b.text for b in response.content if hasattr(b, "text")), "tools_used": tools_used, "messages": messages}
        else:
            return {"response": "Visa agent error.", "tools_used": [], "messages": messages}
