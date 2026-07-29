"""
Curated hotel recommendations per Vietnam destination, with one-click booking links.

When Sasha talks about a destination, we surface a few real, well-known hotels there with a
"Book" link that drops the user onto that exact property on Booking.com. No Booking.com API
key is needed — it's a deep search link pre-filled with the hotel name + city.
"""

from datetime import date, timedelta
from urllib.parse import quote_plus

from app.services.booking_links import _find_destinations

# name, stars, price_from (USD/night), blurb — a few notable stays per destination.
VIETNAM_HOTELS = {
    "Hanoi": [
        {"name": "Sofitel Legend Metropole Hanoi", "stars": 5, "price_from": 350, "blurb": "Iconic French-colonial landmark by the Old Quarter."},
        {"name": "Capella Hanoi", "stars": 5, "price_from": 320, "blurb": "Opera-inspired luxury steps from Hoan Kiem Lake."},
        {"name": "La Siesta Premium Hang Be", "stars": 4, "price_from": 110, "blurb": "Boutique favourite in the heart of the Old Quarter."},
    ],
    "Ho Chi Minh City": [
        {"name": "Park Hyatt Saigon", "stars": 5, "price_from": 290, "blurb": "Colonial elegance in the city centre."},
        {"name": "The Reverie Saigon", "stars": 5, "price_from": 300, "blurb": "Opulent riverside tower with skyline views."},
        {"name": "Hotel des Arts Saigon MGallery", "stars": 5, "price_from": 150, "blurb": "Art-deco style with a rooftop pool."},
    ],
    "Hoi An": [
        {"name": "Four Seasons The Nam Hai", "stars": 5, "price_from": 480, "blurb": "Beachfront villas between Hoi An and Da Nang."},
        {"name": "Anantara Hoi An Resort", "stars": 5, "price_from": 220, "blurb": "Riverside resort a short walk from the ancient town."},
        {"name": "La Siesta Hoi An Resort & Spa", "stars": 4, "price_from": 120, "blurb": "Lantern-lit boutique resort with a great spa."},
    ],
    "Da Nang": [
        {"name": "InterContinental Danang Sun Peninsula", "stars": 5, "price_from": 420, "blurb": "Award-winning clifftop resort on Son Tra peninsula."},
        {"name": "Hyatt Regency Danang Resort & Spa", "stars": 5, "price_from": 200, "blurb": "Beachfront resort on My Khe Beach."},
        {"name": "Furama Resort Danang", "stars": 5, "price_from": 180, "blurb": "Classic beach resort with lagoon pools."},
    ],
    "Sapa": [
        {"name": "Hotel de la Coupole MGallery", "stars": 5, "price_from": 160, "blurb": "Grand colonial-style hotel by the cable-car base."},
        {"name": "Topas Ecolodge", "stars": 4, "price_from": 180, "blurb": "Mountain bungalows with rice-terrace views."},
    ],
    "Ha Long Bay": [
        {"name": "Paradise Elegance Cruise", "stars": 5, "price_from": 280, "blurb": "Luxury overnight cruise through the karst islands."},
        {"name": "Vinpearl Resort & Spa Ha Long", "stars": 5, "price_from": 150, "blurb": "Island resort overlooking the bay."},
    ],
    "Phu Quoc": [
        {"name": "JW Marriott Phu Quoc Emerald Bay", "stars": 5, "price_from": 380, "blurb": "Whimsical Bensley-designed beach resort."},
        {"name": "InterContinental Phu Quoc Long Beach", "stars": 5, "price_from": 250, "blurb": "Long Beach luxury with a rooftop bar."},
        {"name": "Salinda Resort Phu Quoc", "stars": 5, "price_from": 200, "blurb": "Boutique beachfront resort near Duong Dong."},
    ],
    "Nha Trang": [
        {"name": "Six Senses Ninh Van Bay", "stars": 5, "price_from": 700, "blurb": "Secluded villas reached by boat."},
        {"name": "InterContinental Nha Trang", "stars": 5, "price_from": 160, "blurb": "Beachfront tower on the main promenade."},
    ],
    "Hue": [
        {"name": "Azerai La Residence Hue", "stars": 5, "price_from": 170, "blurb": "Art-deco riverside hotel by the Perfume River."},
    ],
    "Da Lat": [
        {"name": "Ana Mandara Villas Dalat", "stars": 5, "price_from": 150, "blurb": "Restored French villas in the highlands."},
        {"name": "Dalat Palace Heritage Hotel", "stars": 5, "price_from": 140, "blurb": "Grand colonial landmark above the lake."},
    ],
    "Ninh Binh": [
        {"name": "Emeralda Resort Ninh Binh", "stars": 5, "price_from": 120, "blurb": "Village-style resort near Tam Coc."},
    ],
    "Mui Ne": [
        {"name": "Anantara Mui Ne Resort", "stars": 5, "price_from": 160, "blurb": "Beachfront resort near the sand dunes."},
    ],
}

# When hotels should be surfaced even without the word "hotel" — accommodation-y phrasing.
_HOTEL_TRIGGERS = [
    "hotel", "stay", "accommodation", "accomodation", "resort", "where to stay",
    "place to stay", "lodging", "villa", "room", "5 star", "five star", "luxury",
    "boutique", "cruise", "book", "sleep",
]



# ── Depth expansion (2026-07-28): wider pools so hotel choice, swap/cheaper/upgrade
# revisions and richer suggestions all have real options. Additive merge — never
# duplicates a property that's already listed above. ALL LOCAL, no network.
_EXTRA_HOTELS = {
    "Hanoi": [
        {"name": "Apricot Hotel", "stars": 4, "price_from": 95, "blurb": "Gallery-style hotel overlooking Hoan Kiem Lake."},
        {"name": "The Oriental Jade Hotel", "stars": 4, "price_from": 85, "blurb": "Rooftop infinity pool above the Old Quarter."},
    ],
    "Ho Chi Minh City": [
        {"name": "Hotel Majestic Saigon", "stars": 4, "price_from": 120, "blurb": "Riverside grande dame from 1925."},
        {"name": "Liberty Central Saigon Citypoint", "stars": 4, "price_from": 80, "blurb": "Modern rooms steps from Ben Thanh Market."},
    ],
    "Hoi An": [
        {"name": "Allegro Hoi An", "stars": 4, "price_from": 90, "blurb": "All-suite boutique two blocks from the old town."},
        {"name": "Little Riverside Hoi An", "stars": 4, "price_from": 100, "blurb": "Thu Bon riverfront with balcony views."},
    ],
    "Da Nang": [
        {"name": "Fusion Maia Da Nang", "stars": 5, "price_from": 310, "blurb": "Pool villas with daily spa treatments included."},
        {"name": "Melia Vinpearl Danang Riverfront", "stars": 4, "price_from": 90, "blurb": "Han River views, minutes from My Khe beach."},
    ],
    "Phu Quoc": [
        {"name": "La Veranda Resort Phu Quoc", "stars": 5, "price_from": 180, "blurb": "Colonial-style beachfront MGallery classic."},
        {"name": "Mango Bay Resort", "stars": 3, "price_from": 90, "blurb": "Eco-resort on its own quiet stretch of beach."},
    ],
    "Hue": [
        {"name": "Azerai La Residence Hue", "stars": 5, "price_from": 180, "blurb": "Art-deco landmark on the Perfume River."},
        {"name": "Pilgrimage Village Boutique Resort", "stars": 4, "price_from": 95, "blurb": "Garden sanctuary just outside the citadel."},
    ],
    "Sapa": [
        {"name": "Hotel de la Coupole MGallery", "stars": 5, "price_from": 160, "blurb": "Bill Bensley-designed grande dame by the cable car."},
        {"name": "Topas Ecolodge", "stars": 4, "price_from": 150, "blurb": "Hilltop bungalows with rice-terrace panoramas."},
    ],
    "Ha Long Bay": [
        {"name": "Wyndham Legend Halong", "stars": 4, "price_from": 85, "blurb": "Bay views close to the cruise marina."},
    ],
    "Nha Trang": [
        {"name": "InterContinental Nha Trang", "stars": 5, "price_from": 150, "blurb": "Beachfront rooms on the main promenade."},
    ],
    "Da Lat": [
        {"name": "Ana Mandara Villas Dalat", "stars": 4, "price_from": 120, "blurb": "Restored French villas in the pine hills."},
    ],
    "Ninh Binh": [
        {"name": "Tam Coc Garden Resort", "stars": 4, "price_from": 130, "blurb": "Boutique hideaway amid the rice paddies."},
        {"name": "Emeralda Resort Ninh Binh", "stars": 4, "price_from": 110, "blurb": "Village-style resort near Van Long reserve."},
    ],
    "Mui Ne": [
        {"name": "Anantara Mui Ne Resort", "stars": 5, "price_from": 140, "blurb": "Peaceful beachfront pool villas."},
    ],
    "Mekong Delta": [
        {"name": "Azerai Can Tho", "stars": 5, "price_from": 180, "blurb": "Private river island reached by boat."},
        {"name": "Victoria Can Tho Resort", "stars": 4, "price_from": 110, "blurb": "Colonial riverfront near Ninh Kieu wharf."},
    ],
    "Con Dao": [
        {"name": "Six Senses Con Dao", "stars": 5, "price_from": 650, "blurb": "Barefoot-luxury villas on Dat Doc beach."},
        {"name": "Poulo Condor Boutique Resort", "stars": 4, "price_from": 120, "blurb": "Quiet colonial-style resort and spa."},
    ],
    "Cat Ba": [
        {"name": "Hotel Perle d'Orient Cat Ba MGallery", "stars": 5, "price_from": 130, "blurb": "Indochine elegance above Cat Co cove."},
        {"name": "Cat Ba Island Resort & Spa", "stars": 3, "price_from": 60, "blurb": "Hillside pools over Cat Co 1 beach."},
    ],
    "Phong Nha": [
        {"name": "Victory Road Villas", "stars": 4, "price_from": 120, "blurb": "Riverside villas at the gateway to the caves."},
        {"name": "Phong Nha Farmstay", "stars": 3, "price_from": 45, "blurb": "The original countryside stay, rice-field views."},
    ],
    "Ha Giang": [
        {"name": "P'apiu Resort", "stars": 4, "price_from": 150, "blurb": "Hillside hideaway on the way to the loop."},
        {"name": "Truong Xuan Resort", "stars": 3, "price_from": 40, "blurb": "Riverside stilt bungalows in Ha Giang town."},
    ],
}
for _c, _hs in _EXTRA_HOTELS.items():
    _existing = {h["name"] for h in VIETNAM_HOTELS.get(_c, [])}
    VIETNAM_HOTELS.setdefault(_c, []).extend(h for h in _hs if h["name"] not in _existing)

# Second depth layer (2026-07-28): famous properties across price tiers.
_EXTRA_HOTELS_2 = {
    "Hanoi": [
        {"name": "Lotte Hotel Hanoi", "stars": 5, "price_from": 180, "blurb": "Sky-high rooms and the 65th-floor observation deck."},
        {"name": "Melia Hanoi", "stars": 5, "price_from": 130, "blurb": "Business classic between the Opera House and the lake."},
        {"name": "Hanoi La Siesta Classic Ma May", "stars": 4, "price_from": 75, "blurb": "Old Quarter hospitality legend."},
    ],
    "Ho Chi Minh City": [
        {"name": "Caravelle Saigon", "stars": 5, "price_from": 160, "blurb": "Historic address on Lam Son Square."},
        {"name": "Rex Hotel Saigon", "stars": 5, "price_from": 140, "blurb": "The rooftop bar of wartime correspondents."},
    ],
    "Hoi An": [
        {"name": "Victoria Hoi An Beach Resort", "stars": 4, "price_from": 140, "blurb": "Cua Dai beachfront with old-town shuttle."},
        {"name": "Almanity Hoi An Wellness Resort", "stars": 4, "price_from": 110, "blurb": "Daily spa treatment included."},
    ],
    "Da Nang": [
        {"name": "Premier Village Danang Resort", "stars": 5, "price_from": 350, "blurb": "Beachfront pool villas for families."},
        {"name": "Pullman Danang Beach Resort", "stars": 5, "price_from": 180, "blurb": "Lush grounds right on Bac My An beach."},
    ],
    "Phu Quoc": [
        {"name": "Premier Village Phu Quoc Resort", "stars": 5, "price_from": 320, "blurb": "Villas straddling a private cape."},
    ],
    "Hue": [
        {"name": "Silk Path Grand Hue", "stars": 4, "price_from": 70, "blurb": "Palatial style near the railway station."},
    ],
    "Sapa": [
        {"name": "Pao's Sapa Leisure Hotel", "stars": 4, "price_from": 90, "blurb": "Valley-view rooms above Muong Hoa."},
    ],
    "Nha Trang": [
        {"name": "Mia Resort Nha Trang", "stars": 4, "price_from": 160, "blurb": "Clifftop villas on a private cove."},
    ],
    "Da Lat": [
        {"name": "Dalat Palace Heritage Hotel", "stars": 5, "price_from": 150, "blurb": "1922 grande dame above Xuan Huong lake."},
    ],
    "Ha Long Bay": [
        {"name": "Paradise Suites Hotel", "stars": 4, "price_from": 70, "blurb": "Boutique base on Tuan Chau marina."},
    ],
}
for _c, _hs in _EXTRA_HOTELS_2.items():
    _existing2 = {h["name"] for h in VIETNAM_HOTELS.get(_c, [])}
    VIETNAM_HOTELS.setdefault(_c, []).extend(h for h in _hs if h["name"] not in _existing2)




# Third depth layer (2026-07-28): target 100+ properties platform-wide.
_EXTRA_HOTELS_3 = {
    "Hanoi": [
        {"name": "InterContinental Hanoi Westlake", "stars": 5, "price_from": 190, "blurb": "Over-water pavilions on West Lake."},
        {"name": "Hanoi Pearl Hotel", "stars": 4, "price_from": 60, "blurb": "Polished Old Quarter value pick."},
    ],
    "Ho Chi Minh City": [
        {"name": "Le Meridien Saigon", "stars": 5, "price_from": 170, "blurb": "Riverside glass tower, District 1 edge."},
        {"name": "Sheraton Saigon Grand Opera", "stars": 5, "price_from": 175, "blurb": "Dong Khoi address with a famous rooftop bar."},
        {"name": "The Myst Dong Khoi", "stars": 4, "price_from": 120, "blurb": "Artful hideaway near the river."},
    ],
    "Hoi An": [
        {"name": "Bel Marina Hoi An Resort", "stars": 4, "price_from": 95, "blurb": "Island resort facing the night market."},
    ],
    "Da Nang": [
        {"name": "Danang Golden Bay", "stars": 5, "price_from": 110, "blurb": "Gold-tiled rooftop infinity pool."},
    ],
    "Phu Quoc": [
        {"name": "Regent Phu Quoc", "stars": 5, "price_from": 380, "blurb": "Lagoon suites on Long Beach."},
        {"name": "New World Phu Quoc Resort", "stars": 5, "price_from": 250, "blurb": "All-villa beachfront village."},
    ],
    "Sapa": [
        {"name": "Silk Path Grand Sapa Resort", "stars": 5, "price_from": 120, "blurb": "Hillside spa resort above the town."},
    ],
    "Ha Long Bay": [
        {"name": "Novotel Ha Long Bay", "stars": 4, "price_from": 80, "blurb": "Bayfront rooms along Bai Chay beach."},
    ],
    "Nha Trang": [
        {"name": "Evason Ana Mandara Nha Trang", "stars": 5, "price_from": 220, "blurb": "The only true beachfront villas in town."},
        {"name": "Sheraton Nha Trang", "stars": 5, "price_from": 140, "blurb": "Panoramic bay views, central promenade."},
    ],
    "Da Lat": [
        {"name": "Terracotta Hotel & Resort Dalat", "stars": 4, "price_from": 70, "blurb": "Pine-forest lakeside calm at Tuyen Lam."},
        {"name": "Swiss-Belresort Tuyen Lam", "stars": 4, "price_from": 75, "blurb": "Golf-course views in the highlands."},
    ],
    "Ninh Binh": [
        {"name": "Ninh Binh Hidden Charm Hotel", "stars": 4, "price_from": 80, "blurb": "Karst views near Tam Coc wharf."},
        {"name": "Bai Dinh Garden Resort", "stars": 4, "price_from": 70, "blurb": "Temple-side garden bungalows."},
    ],
    "Mui Ne": [
        {"name": "The Cliff Resort & Residences", "stars": 4, "price_from": 110, "blurb": "Terraced pools above the beach."},
        {"name": "Bamboo Village Beach Resort", "stars": 4, "price_from": 90, "blurb": "Garden bungalows on the sand."},
    ],
    "Mekong Delta": [
        {"name": "Nam Bo Boutique Hotel Can Tho", "stars": 4, "price_from": 85, "blurb": "Colonial corner house on the wharf."},
        {"name": "Mekong Riverside Boutique Resort", "stars": 4, "price_from": 95, "blurb": "Riverfront bungalows near Cai Be."},
    ],
    "Con Dao": [
        {"name": "The Secret Con Dao", "stars": 4, "price_from": 140, "blurb": "Design hotel on the seafront promenade."},
    ],
    "Cat Ba": [
        {"name": "Flamingo Cat Ba Resort", "stars": 5, "price_from": 150, "blurb": "Forest-facing towers above Cat Co 1&2."},
        {"name": "Sea Pearl Cat Ba Hotel", "stars": 4, "price_from": 55, "blurb": "Harbour-view rooms in town."},
    ],
    "Phong Nha": [
        {"name": "Chay Lap Farmstay", "stars": 4, "price_from": 60, "blurb": "Riverside pool amid the karst farmland."},
        {"name": "Sun Spa Resort Dong Hoi", "stars": 5, "price_from": 90, "blurb": "Beach resort by the airport gateway."},
    ],
    "Ha Giang": [
        {"name": "Yen Bien Luxury Hotel", "stars": 4, "price_from": 45, "blurb": "The comfortable night before the loop."},
    ],
}
_EXTRA_HOTELS_3["Hanoi"] += [
    {"name": "Movenpick Hotel Hanoi Centre", "stars": 5, "price_from": 120, "blurb": "Quiet luxury near the train street."},
    {"name": "La Sinfonia del Rey Hotel", "stars": 4, "price_from": 85, "blurb": "Rooftop bar over Hoan Kiem rooftops."},
]
_EXTRA_HOTELS_3["Ho Chi Minh City"] += [
    {"name": "Renaissance Riverside Saigon", "stars": 5, "price_from": 130, "blurb": "River-view club rooms, D1 corner."},
    {"name": "Liberty Central Saigon Riverside", "stars": 4, "price_from": 75, "blurb": "Rooftop pool over the Saigon river."},
]
_EXTRA_HOTELS_3["Hoi An"] += [
    {"name": "La Residencia Hoi An", "stars": 4, "price_from": 80, "blurb": "Boutique calm two lanes from the market."},
    {"name": "Hoi An Silk Marina Resort", "stars": 4, "price_from": 70, "blurb": "Riverside pools by the night market bridge."},
]
_EXTRA_HOTELS_3["Da Nang"] += [
    {"name": "Novotel Danang Premier Han River", "stars": 4, "price_from": 85, "blurb": "Skyline rooms over the dragon bridge."},
]
_EXTRA_HOTELS_3["Nha Trang"] += [
    {"name": "Amiana Resort Nha Trang", "stars": 5, "price_from": 180, "blurb": "Private-bay resort north of town."},
]
_EXTRA_HOTELS_3["Phu Quoc"] += [
    {"name": "Dusit Princess Moonrise Beach Resort", "stars": 5, "price_from": 160, "blurb": "Intimate Long Beach address."},
]
_EXTRA_HOTELS_3.setdefault("Hue", []).extend([
    {"name": "Eldora Hotel Hue", "stars": 4, "price_from": 55, "blurb": "Grand lobby, steps from the walking street."},
])
_EXTRA_HOTELS_3["Ha Long Bay"] += [
    {"name": "Muong Thanh Luxury Quang Ninh", "stars": 4, "price_from": 60, "blurb": "High-floor bay panoramas in Bai Chay."},
]
for _c, _hs in _EXTRA_HOTELS_3.items():
    _existing3 = {h["name"] for h in VIETNAM_HOTELS.get(_c, [])}
    VIETNAM_HOTELS.setdefault(_c, []).extend(h for h in _hs if h["name"] not in _existing3)

def _booking_url(name: str, city: str, adults: int = 2, nights: int = 2) -> str:
    # Deep link with a near-future date window + party size so the link lands on real
    # availability and pricing for that exact property, not a bare name search.
    checkin = date.today() + timedelta(days=30)
    checkout = checkin + timedelta(days=max(1, nights))
    return (
        "https://www.booking.com/searchresults.html?"
        f"ss={quote_plus(f'{name}, {city}, Vietnam')}"
        f"&checkin={checkin.isoformat()}&checkout={checkout.isoformat()}"
        f"&group_adults={max(1, adults)}&no_rooms=1&group_children=0"
    )


def social_proof(name: str, stars: int) -> dict:
    """Deterministic rating/review social-proof for a hotel (demo-grade, stable per name)."""
    rating = round(min(8.4 + (stars - 4) * 0.5 + (len(name) % 6) * 0.08, 9.7), 1)
    reviews = 400 + (len(name) * 37) % 2600
    tag = "Guest favourite" if rating >= 9.0 else "Highly rated"
    return {"rating": rating, "reviews": reviews, "tag": tag}


def recommend_hotels(user_message: str, response_text: str, intents: list, context: str = "") -> list:
    """Return up to 3 hotels (with booking links) for the destination in play, or [].

    `context` is recent conversation text, checked last so the destination carries across turns.
    """
    dests = _find_destinations(user_message) or _find_destinations(response_text) or _find_destinations(context)
    if not dests:
        return []  # no destination yet — nothing concrete to recommend
    text = f"{user_message} {response_text} {context}".lower()
    relevant = any(t in text for t in _HOTEL_TRIGGERS) or "smart_sasha" in (intents or [])
    # Once a destination is named, showing where to stay is almost always helpful for a
    # travel concierge — so default to showing hotels for the destination.
    if not relevant and not dests:
        return []

    primary = dests[0]
    hotels = list(VIETNAM_HOTELS.get(primary, []))
    # Tier-aware ordering: the pool is curated flagship-first, so a BUDGET ask sliced [:5]
    # used to show only the priciest properties. A luxury/budget wording reorders by nightly
    # rate (and stars) before the slice — deterministic, microseconds, no LLM.
    if any(w in text for w in ("luxur", "upscale", "high end", "high-end", "five star",
                               "5 star", "5-star", "premium", "fanciest", "finest")):
        hotels.sort(key=lambda h: (-(h.get("stars", 0)), -(h.get("price_from", 0))))
    elif any(w in text for w in ("cheap", "budget", "affordable", "inexpensive", "low cost",
                                 "low-cost", "hostel", "value")):
        hotels.sort(key=lambda h: (h.get("price_from", 10 ** 9)))
    return [
        {**h, "city": primary, "book_url": _booking_url(h["name"], primary), **social_proof(h["name"], h.get("stars", 4))}
        for h in hotels[:5]
    ]
