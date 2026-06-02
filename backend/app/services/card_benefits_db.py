# ─────────────────────────────────────────────
# CARD BENEFITS DATABASE
# Source of truth for all card earn rates,
# credits, transfer partners, and rental coverage
# Adding a new card = add one entry to CARD_DB
# Last verified: June 2026
# ─────────────────────────────────────────────

CARD_DB = {

    "amex_platinum": {
        "name": "American Express Platinum Card",
        "issuer": "American Express",
        "points_currency": "Membership Rewards",
        "annual_fee": 695,
        "base_earn": 1,
        "category_earn": {
            "flights_direct": 5,       # booked directly with airline or amex travel
            "flights_portal": 5,
            "hotels_portal": 5,        # amex fine hotels & resorts
            "hotels_direct": 1,
            "dining": 1,
            "transport": 1,
            "groceries": 1,
            "streaming": 1,
        },
        "annual_credits": {
            "airline_fee": {"amount": 200, "type": "incidental_fees", "note": "Select one airline. Covers fees, not tickets."},
            "hotel": {"amount": 200, "type": "prepaid_hotels", "note": "Fine Hotels + Resorts or The Hotel Collection via Amex Travel"},
            "digital_entertainment": {"amount": 240, "note": "$20/month on eligible streaming/digital services"},
            "walmart_plus": {"amount": 155, "note": "Monthly Walmart+ membership reimbursement"},
            "equinox": {"amount": 300, "note": "Equinox membership credit"},
            "saks": {"amount": 100, "note": "$50 Jan-Jun, $50 Jul-Dec at Saks Fifth Avenue"},
            "clear": {"amount": 189, "note": "CLEAR Plus membership"},
        },
        "lounge_access": ["Centurion Lounges", "Priority Pass (limited guest policy)", "Delta Sky Clubs (when flying Delta)", "Lufthansa Business Lounges"],
        "transfer_partners": {
            "airlines": [
                {"name": "Air Canada Aeroplan", "ratio": "1:1"},
                {"name": "Air France/KLM Flying Blue", "ratio": "1:1"},
                {"name": "ANA Mileage Club", "ratio": "1:1"},
                {"name": "British Airways Avios", "ratio": "1:1"},
                {"name": "Cathay Pacific Asia Miles", "ratio": "1:1"},
                {"name": "Delta SkyMiles", "ratio": "1:1"},
                {"name": "Emirates Skywards", "ratio": "1:1"},
                {"name": "Etihad Guest", "ratio": "1:1"},
                {"name": "Hawaiian Miles", "ratio": "1:1"},
                {"name": "Iberia Plus", "ratio": "1:1"},
                {"name": "JetBlue TrueBlue", "ratio": "1:0.8"},
                {"name": "Qantas Frequent Flyer", "ratio": "1:1"},
                {"name": "Singapore KrisFlyer", "ratio": "1:1"},
                {"name": "Virgin Atlantic Flying Club", "ratio": "1:1"},
            ],
            "hotels": [
                {"name": "Hilton Honors", "ratio": "1:2"},
                {"name": "Marriott Bonvoy", "ratio": "1:1"},
            ]
        },
        "point_value_cpp": 2.0,   # cents per point (conservative estimate)
        "last_verified": "2026-06-01",
        "source_url": "https://www.americanexpress.com/us/credit-cards/card/platinum/",
    },

    "amex_gold": {
        "name": "American Express Gold Card",
        "issuer": "American Express",
        "points_currency": "Membership Rewards",
        "annual_fee": 250,
        "base_earn": 1,
        "category_earn": {
            "flights_direct": 3,
            "flights_portal": 3,
            "hotels_direct": 1,
            "hotels_portal": 1,
            "dining": 4,              # restaurants worldwide
            "us_supermarkets": 4,     # up to $25k/year
            "transport": 1,
            "groceries": 4,
            "streaming": 1,
        },
        "annual_credits": {
            "dining": {"amount": 120, "note": "$10/month at Grubhub, The Cheesecake Factory, Goldbelly, Wine.com, and others"},
            "uber_cash": {"amount": 120, "note": "$10/month Uber Cash (Uber Eats or Uber rides)"},
            "dunkin": {"amount": 84, "note": "$7/month at Dunkin'"},
        },
        "lounge_access": [],
        "transfer_partners": "same_as_amex_platinum",
        "point_value_cpp": 2.0,
        "last_verified": "2026-06-01",
        "source_url": "https://www.americanexpress.com/us/credit-cards/card/gold-card/",
    },

    "chase_sapphire_reserve": {
        "name": "Chase Sapphire Reserve",
        "issuer": "Chase",
        "points_currency": "Ultimate Rewards",
        "annual_fee": 550,
        "base_earn": 1,
        "category_earn": {
            "flights_direct": 3,
            "flights_portal": 5,       # through Chase Travel
            "hotels_direct": 3,
            "hotels_portal": 5,        # through Chase Travel
            "dining": 3,
            "transport": 3,            # Lyft 10x, other transport 3x
            "groceries": 1,
            "streaming": 1,
        },
        "annual_credits": {
            "travel": {"amount": 300, "type": "any_travel", "note": "Automatic credit on first $300 travel purchases each year"},
        },
        "lounge_access": ["Priority Pass Select (unlimited guests)"],
        "transfer_partners": {
            "airlines": [
                {"name": "Air Canada Aeroplan", "ratio": "1:1"},
                {"name": "Air France/KLM Flying Blue", "ratio": "1:1"},
                {"name": "British Airways Avios", "ratio": "1:1"},
                {"name": "Emirates Skywards", "ratio": "1:1"},
                {"name": "Iberia Plus", "ratio": "1:1"},
                {"name": "JetBlue TrueBlue", "ratio": "1:1"},
                {"name": "Singapore KrisFlyer", "ratio": "1:1"},
                {"name": "Southwest Rapid Rewards", "ratio": "1:1"},
                {"name": "United MileagePlus", "ratio": "1:1"},
                {"name": "Virgin Atlantic Flying Club", "ratio": "1:1"},
            ],
            "hotels": [
                {"name": "Hyatt World of Hyatt", "ratio": "1:1"},
                {"name": "IHG Rewards", "ratio": "1:1"},
                {"name": "Marriott Bonvoy", "ratio": "1:1"},
            ]
        },
        "point_value_cpp": 1.5,    # 1.5cpp through Chase Travel portal
        "last_verified": "2026-06-01",
        "source_url": "https://creditcards.chase.com/travel-credit-cards/sapphire/reserve",
    },

    "chase_sapphire_preferred": {
        "name": "Chase Sapphire Preferred",
        "issuer": "Chase",
        "points_currency": "Ultimate Rewards",
        "annual_fee": 95,
        "base_earn": 1,
        "category_earn": {
            "flights_direct": 2,
            "flights_portal": 5,       # through Chase Travel
            "hotels_direct": 2,
            "hotels_portal": 5,        # through Chase Travel
            "dining": 3,
            "transport": 2,
            "groceries": 3,            # online grocery (not Walmart/Target/wholesale)
            "streaming": 2,
        },
        "annual_credits": {
            "hotel": {"amount": 50, "note": "Annual $50 hotel stay credit through Chase Travel"},
        },
        "lounge_access": [],
        "transfer_partners": "same_as_chase_sapphire_reserve",
        "point_value_cpp": 1.25,   # 1.25cpp through Chase Travel portal
        "last_verified": "2026-06-01",
        "source_url": "https://creditcards.chase.com/travel-credit-cards/sapphire/preferred",
    },

    "capital_one_venture_x": {
        "name": "Capital One Venture X Rewards",
        "issuer": "Capital One",
        "points_currency": "Capital One Miles",
        "annual_fee": 395,
        "base_earn": 2,
        "category_earn": {
            "flights_portal": 5,       # through Capital One Travel
            "hotels_portal": 10,       # through Capital One Travel
            "rental_cars_portal": 10,
            "flights_direct": 2,
            "hotels_direct": 2,
            "dining": 2,
            "transport": 2,
            "groceries": 2,
            "streaming": 2,
        },
        "annual_credits": {
            "travel": {"amount": 300, "note": "$300 annual credit for bookings through Capital One Travel"},
            "anniversary_miles": {"amount": 10000, "note": "10,000 bonus miles every account anniversary (worth ~$100)"},
        },
        "lounge_access": ["Capital One Lounges", "Priority Pass (unlimited guests)"],
        "transfer_partners": {
            "airlines": [
                {"name": "Air Canada Aeroplan", "ratio": "1:1"},
                {"name": "Air France/KLM Flying Blue", "ratio": "1:1"},
                {"name": "Avianca LifeMiles", "ratio": "1:1"},
                {"name": "British Airways Avios", "ratio": "1:1"},
                {"name": "Emirates Skywards", "ratio": "1:1"},
                {"name": "Etihad Guest", "ratio": "1:1"},
                {"name": "Singapore KrisFlyer", "ratio": "1:1"},
                {"name": "Turkish Airlines Miles&Smiles", "ratio": "1:1"},
                {"name": "Virgin Atlantic Flying Club", "ratio": "1:1"},
            ],
            "hotels": [
                {"name": "Accor Live Limitless", "ratio": "2:1"},
                {"name": "Wyndham Rewards", "ratio": "1:1"},
            ]
        },
        "point_value_cpp": 1.0,
        "last_verified": "2026-06-01",
        "source_url": "https://capitalone.com/credit-cards/venture-x/",
    },

    "citi_aadvantage_executive": {
        "name": "Citi AAdvantage Executive World Elite Mastercard",
        "issuer": "Citi",
        "points_currency": "American Airlines AAdvantage Miles",
        "annual_fee": 595,
        "base_earn": 1,
        "category_earn": {
            "flights_aa": 4,           # American Airlines purchases
            "flights_direct": 1,
            "hotels_direct": 1,
            "dining": 1,
            "transport": 1,
            "groceries": 1,
            "streaming": 1,
        },
        "annual_credits": {
            "aa_companion": {"amount": 0, "note": "Companion certificate for domestic economy after $30k spend"},
        },
        "lounge_access": ["Admirals Club (up to 2 guests)"],
        "transfer_partners": {
            "airlines": [
                {"name": "Alaska Airlines Mileage Plan", "ratio": "1:1"},
                {"name": "British Airways Avios", "ratio": "1:1"},
                {"name": "Cathay Pacific Asia Miles", "ratio": "1:1"},
                {"name": "Finnair Plus", "ratio": "1:1"},
                {"name": "Iberia Plus", "ratio": "1:1"},
                {"name": "Japan Airlines Mileage Bank", "ratio": "1:1"},
                {"name": "Malaysia Airlines Enrich", "ratio": "1:1"},
                {"name": "Qantas Frequent Flyer", "ratio": "1:1"},
                {"name": "Qatar Airways Privilege Club", "ratio": "1:1"},
                {"name": "Singapore KrisFlyer", "ratio": "1:1"},
            ],
            "hotels": []
        },
        "point_value_cpp": 1.5,
        "last_verified": "2026-06-01",
        "source_url": "https://www.citi.com/credit-cards/citi-aadvantage-executive-world-elite-mastercard",
    },

    "discover_it_miles": {
        "name": "Discover it Miles",
        "issuer": "Discover",
        "points_currency": "Discover Miles",
        "annual_fee": 0,
        "base_earn": 1.5,             # 1.5x on everything
        "category_earn": {
            "flights_direct": 1.5,
            "hotels_direct": 1.5,
            "dining": 1.5,
            "transport": 1.5,
            "groceries": 1.5,
            "streaming": 1.5,
        },
        "annual_credits": {
            "first_year_match": {"amount": 0, "note": "Discover matches all miles earned at end of first year"},
        },
        "lounge_access": [],
        "transfer_partners": {
            "airlines": [],
            "hotels": []
        },
        "point_value_cpp": 1.0,
        "last_verified": "2026-06-01",
        "source_url": "https://www.discover.com/credit-cards/travel/discover-it-miles.html",
    },

    "bofa_travel_rewards": {
        "name": "Bank of America Travel Rewards",
        "issuer": "Bank of America",
        "points_currency": "Points",
        "annual_fee": 0,
        "base_earn": 1.5,
        "category_earn": {
            "flights_direct": 1.5,
            "hotels_direct": 1.5,
            "dining": 1.5,
            "transport": 1.5,
            "groceries": 1.5,
            "streaming": 1.5,
        },
        "annual_credits": {},
        "lounge_access": [],
        "transfer_partners": {
            "airlines": [],
            "hotels": []
        },
        "point_value_cpp": 1.0,
        "last_verified": "2026-06-01",
        "source_url": "https://www.bankofamerica.com/credit-cards/products/travel-rewards-credit-card/",
    },

    "bilt_mastercard": {
        "name": "Bilt Mastercard",
        "issuer": "Wells Fargo (Bilt)",
        "points_currency": "Bilt Points",
        "annual_fee": 0,
        "base_earn": 1,
        "category_earn": {
            "rent": 1,                 # up to 100k points/year — no transaction fee
            "flights_direct": 2,
            "hotels_direct": 2,
            "dining": 3,
            "transport": 2,
            "groceries": 1,
            "streaming": 1,
        },
        "annual_credits": {},
        "lounge_access": [],
        "transfer_partners": {
            "airlines": [
                {"name": "Air Canada Aeroplan", "ratio": "1:1"},
                {"name": "Air France/KLM Flying Blue", "ratio": "1:1"},
                {"name": "British Airways Avios", "ratio": "1:1"},
                {"name": "Cathay Pacific Asia Miles", "ratio": "1:1"},
                {"name": "Emirates Skywards", "ratio": "1:1"},
                {"name": "Singapore KrisFlyer", "ratio": "1:1"},
                {"name": "Turkish Airlines Miles&Smiles", "ratio": "1:1"},
                {"name": "United MileagePlus", "ratio": "1:1"},
                {"name": "Virgin Atlantic Flying Club", "ratio": "1:1"},
            ],
            "hotels": [
                {"name": "Hyatt World of Hyatt", "ratio": "1:1"},
                {"name": "IHG Rewards", "ratio": "1:1"},
                {"name": "Marriott Bonvoy", "ratio": "1:1"},
            ]
        },
        "point_value_cpp": 1.5,
        "last_verified": "2026-06-01",
        "source_url": "https://www.biltrewards.com/card",
    },

    "wells_fargo_autograph": {
        "name": "Wells Fargo Autograph Card",
        "issuer": "Wells Fargo",
        "points_currency": "Rewards Points",
        "annual_fee": 0,
        "base_earn": 1,
        "category_earn": {
            "flights_direct": 3,
            "hotels_direct": 3,
            "dining": 3,
            "transport": 3,            # gas, transit, rideshare, EV charging
            "streaming": 3,
            "phone_plans": 3,
            "groceries": 1,
        },
        "annual_credits": {},
        "lounge_access": [],
        "transfer_partners": {
            "airlines": [],
            "hotels": []
        },
        "point_value_cpp": 1.0,
        "last_verified": "2026-06-01",
        "source_url": "https://www.wellsfargo.com/credit-cards/autograph/",
    },
}


# ─────────────────────────────────────────────
# CAR RENTAL INSURANCE DATABASE
# Per-card rental coverage details
# ─────────────────────────────────────────────

RENTAL_COVERAGE_DB = {

    "amex_platinum": {
        "coverage_type": "secondary",
        "collision": True,
        "theft": True,
        "liability": False,
        "must_decline_cdw": True,
        "max_rental_days": 30,
        "geographic_exclusions": ["Australia", "Ireland", "Israel", "Jamaica", "New Zealand"],
        "vehicle_exclusions": ["antique cars", "exotic cars", "trucks > 15 passengers", "motorcycles", "RVs"],
        "must_pay_full_with_card": True,
        "note": "Secondary coverage — your personal auto insurance pays first. Amex covers the gap.",
        "last_verified": "2026-06-01",
        "source_url": "https://www.americanexpress.com/us/benefits/car-rental/",
    },

    "amex_gold": {
        "coverage_type": "secondary",
        "collision": True,
        "theft": True,
        "liability": False,
        "must_decline_cdw": True,
        "max_rental_days": 30,
        "geographic_exclusions": ["Australia", "Ireland", "Israel", "Jamaica", "New Zealand"],
        "vehicle_exclusions": ["antique cars", "exotic cars", "trucks > 15 passengers", "motorcycles", "RVs"],
        "must_pay_full_with_card": True,
        "note": "Secondary coverage — your personal auto insurance pays first.",
        "last_verified": "2026-06-01",
        "source_url": "https://www.americanexpress.com/us/benefits/car-rental/",
    },

    "chase_sapphire_reserve": {
        "coverage_type": "primary",
        "collision": True,
        "theft": True,
        "liability": False,
        "must_decline_cdw": True,
        "max_rental_days": 31,
        "geographic_exclusions": ["Australia", "Ireland", "Israel", "Jamaica", "New Zealand"],
        "vehicle_exclusions": ["exotic cars over $125k", "antique cars", "motorcycles", "RVs", "trucks with open cargo beds"],
        "must_pay_full_with_card": True,
        "note": "PRIMARY coverage worldwide — does not require personal auto insurance to pay first. This is the gold standard for rental car coverage.",
        "last_verified": "2026-06-01",
        "source_url": "https://creditcards.chase.com/travel-credit-cards/sapphire/reserve/benefits",
    },

    "chase_sapphire_preferred": {
        "coverage_type": "primary",
        "collision": True,
        "theft": True,
        "liability": False,
        "must_decline_cdw": True,
        "max_rental_days": 31,
        "geographic_exclusions": ["Australia", "Ireland", "Israel", "Jamaica", "New Zealand"],
        "vehicle_exclusions": ["exotic cars", "antique cars", "motorcycles", "RVs"],
        "must_pay_full_with_card": True,
        "note": "PRIMARY coverage — does not require personal auto insurance to pay first.",
        "last_verified": "2026-06-01",
        "source_url": "https://creditcards.chase.com/travel-credit-cards/sapphire/preferred/benefits",
    },

    "capital_one_venture_x": {
        "coverage_type": "primary",
        "collision": True,
        "theft": True,
        "liability": False,
        "must_decline_cdw": True,
        "max_rental_days": 15,
        "geographic_exclusions": ["Australia", "Ireland", "Israel", "Jamaica", "New Zealand"],
        "vehicle_exclusions": ["antique cars", "exotic cars", "motorcycles", "RVs"],
        "must_pay_full_with_card": True,
        "note": "Primary coverage up to 15 days.",
        "last_verified": "2026-06-01",
        "source_url": "https://capitalone.com/credit-cards/venture-x/benefits/",
    },

    "citi_aadvantage_executive": {
        "coverage_type": "secondary",
        "collision": True,
        "theft": True,
        "liability": False,
        "must_decline_cdw": True,
        "max_rental_days": 31,
        "geographic_exclusions": ["Australia", "Ireland", "Israel", "Jamaica", "New Zealand"],
        "vehicle_exclusions": ["antique cars", "exotic cars", "motorcycles", "RVs"],
        "must_pay_full_with_card": True,
        "note": "Secondary coverage.",
        "last_verified": "2026-06-01",
        "source_url": "https://www.citi.com/credit-cards/citi-aadvantage-executive-world-elite-mastercard/benefits",
    },

    "discover_it_miles": {
        "coverage_type": "secondary",
        "collision": True,
        "theft": False,
        "liability": False,
        "must_decline_cdw": True,
        "max_rental_days": 31,
        "geographic_exclusions": [],
        "vehicle_exclusions": ["antique cars", "exotic cars", "motorcycles", "RVs"],
        "must_pay_full_with_card": True,
        "note": "Secondary collision coverage only — no theft protection.",
        "last_verified": "2026-06-01",
        "source_url": "https://www.discover.com/credit-cards/card-smarts/rental-car-insurance/",
    },

    "bofa_travel_rewards": {
        "coverage_type": "secondary",
        "collision": True,
        "theft": True,
        "liability": False,
        "must_decline_cdw": True,
        "max_rental_days": 15,
        "geographic_exclusions": [],
        "vehicle_exclusions": ["antique cars", "exotic cars", "motorcycles", "RVs"],
        "must_pay_full_with_card": True,
        "note": "Secondary coverage up to 15 days.",
        "last_verified": "2026-06-01",
        "source_url": "https://www.bankofamerica.com/credit-cards/",
    },

    "bilt_mastercard": {
        "coverage_type": "primary",
        "collision": True,
        "theft": True,
        "liability": False,
        "must_decline_cdw": True,
        "max_rental_days": 31,
        "geographic_exclusions": ["Australia", "Ireland", "Israel", "Jamaica", "New Zealand"],
        "vehicle_exclusions": ["antique cars", "exotic cars", "motorcycles", "RVs"],
        "must_pay_full_with_card": True,
        "note": "Primary coverage — strong for a no-annual-fee card.",
        "last_verified": "2026-06-01",
        "source_url": "https://www.biltrewards.com/card/benefits",
    },

    "wells_fargo_autograph": {
        "coverage_type": "secondary",
        "collision": True,
        "theft": True,
        "liability": False,
        "must_decline_cdw": True,
        "max_rental_days": 15,
        "geographic_exclusions": [],
        "vehicle_exclusions": ["antique cars", "exotic cars", "motorcycles", "RVs"],
        "must_pay_full_with_card": True,
        "note": "Secondary coverage up to 15 days.",
        "last_verified": "2026-06-01",
        "source_url": "https://www.wellsfargo.com/credit-cards/autograph/benefits/",
    },
}


def get_card(card_id: str) -> dict:
    """Get card data by ID. Returns None if not found."""
    card = CARD_DB.get(card_id)
    if card and card.get("transfer_partners") == "same_as_amex_platinum":
        card = dict(card)
        card["transfer_partners"] = CARD_DB["amex_platinum"]["transfer_partners"]
    if card and card.get("transfer_partners") == "same_as_chase_sapphire_reserve":
        card = dict(card)
        card["transfer_partners"] = CARD_DB["chase_sapphire_reserve"]["transfer_partners"]
    return card


def get_rental_coverage(card_id: str) -> dict:
    """Get rental car coverage for a card."""
    return RENTAL_COVERAGE_DB.get(card_id)


def list_cards() -> list:
    """Return all card IDs and names."""
    return [{"id": k, "name": v["name"]} for k, v in CARD_DB.items()]


def get_earn_rate(card_id: str, category: str) -> float:
    """Get earn rate for a card in a specific category."""
    card = get_card(card_id)
    if not card:
        return 0
    return card["category_earn"].get(category, card["base_earn"])
