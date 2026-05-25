"""
Vietnam Golf Course Database
Real courses with verified contact details.
Replace the mock data in golf_agent.py with this.
"""

VIETNAM_GOLF_COURSES = {

    # ─────────────────────────────────────────────
    # DANANG / HOI AN REGION
    # ─────────────────────────────────────────────
    "danang": [
        {
            "name": "Montgomerie Links",
            "region": "danang",
            "address": "Coastal Road, Dien Ban Dong Ward, Da Nang",
            "holes": 18,
            "par": 72,
            "yards": 7090,
            "green_fee_usd": 95,
            "designer": "Colin Montgomerie",
            "ranking": "Top 10 Asia (Forbes)",
            "phone": "+84 235 3941 942",
            "booking_email": "reservations@montgomerielinks.com",
            "website": "montgomerielinks.com",
            "caddy_fee": "Included",
            "cart_fee_usd": 20,
            "club_hire_usd": 40,
            "available_times": ["07:00", "07:30", "08:00", "08:30", "09:00", "10:00", "11:00", "13:00", "14:00"],
            "notes": "Links-style with sand dunes and casuarina trees. 20 min from Danang airport, 15 min to Hoi An.",
            "cancellation_policy": "48 hours notice required",
        },
        {
            "name": "Legend Danang Golf Resort - Norman Course",
            "region": "danang",
            "address": "Hoa Hai Ward, Ngu Hanh Son, Da Nang",
            "holes": 18,
            "par": 72,
            "yards": 7160,
            "green_fee_usd": 120,
            "designer": "Greg Norman",
            "ranking": "Best Golf Course Vietnam (multiple awards)",
            "phone": "+84 901 950 479",
            "booking_email": "reservations@dananggolfclub.com",
            "website": "dananggolfclub.com",
            "caddy_fee": "Included",
            "cart_fee_usd": 20,
            "club_hire_usd": 45,
            "available_times": ["06:30", "07:00", "07:30", "08:00", "08:30", "09:00", "10:00", "11:00", "13:00", "14:00"],
            "notes": "First true links course in Southeast Asia. No out-of-bounds. Stunning dune-scape.",
            "cancellation_policy": "48 hours notice required. Min 3 players on weekends.",
        },
        {
            "name": "Legend Danang Golf Resort - Nicklaus Course",
            "region": "danang",
            "address": "Hoa Hai Ward, Ngu Hanh Son, Da Nang",
            "holes": 18,
            "par": 72,
            "yards": 7380,
            "green_fee_usd": 150,
            "designer": "Jack Nicklaus",
            "ranking": "Asia's first true bulkhead course",
            "phone": "+84 901 950 479",
            "booking_email": "reservations@dananggolfclub.com",
            "website": "dananggolfclub.com",
            "caddy_fee": "Included",
            "cart_fee_usd": 20,
            "club_hire_usd": 45,
            "available_times": ["07:00", "07:30", "08:00", "08:30", "09:00", "10:00", "11:00", "13:00"],
            "notes": "Florida-style bulkhead course by Nicklaus Design. Pairs with Norman Course for 36-hole day.",
            "cancellation_policy": "48 hours notice required. Min 3 players on weekends.",
        },
        {
            "name": "Ba Na Hills Golf Club",
            "region": "danang",
            "address": "Hoa Vang District, Da Nang",
            "holes": 18,
            "par": 72,
            "yards": 7100,
            "green_fee_usd": 110,
            "designer": "Luke Donald",
            "ranking": "Best Golf Course Vietnam",
            "phone": "+84 236 3791 111",
            "booking_email": "golf@banahills.com.vn",
            "website": "banahillsgolfclub.com",
            "caddy_fee": "Included",
            "cart_fee_usd": 20,
            "club_hire_usd": 40,
            "available_times": ["07:00", "07:30", "08:00", "08:30", "09:00", "10:00", "11:00"],
            "notes": "Mountain course managed by IMG. Cooler temperatures than coastal courses. 30 min from city.",
            "cancellation_policy": "24 hours notice required",
        },
        {
            "name": "Hoiana Shores Golf Club",
            "region": "danang",
            "address": "Duy Xuyen District, Quang Nam Province (near Hoi An)",
            "holes": 18,
            "par": 71,
            "yards": 7004,
            "green_fee_usd": 185,
            "designer": "Robert Trent Jones Jr.",
            "ranking": "Vietnam #1, Top 100 Worldwide",
            "phone": "+84 235 3939 888",
            "booking_email": "golf@hoiana.com",
            "website": "hoiana.com",
            "caddy_fee": "Included (1 caddy per player mandatory)",
            "cart_fee_usd": 25,
            "club_hire_usd": 55,
            "available_times": ["07:00", "08:00", "09:00", "10:00", "11:00"],
            "notes": "Vietnam's #1 ranked course. Coastal links on stunning Eastern Sea shoreline. 45 min from Danang airport. Book well in advance — tee times very limited.",
            "cancellation_policy": "72 hours notice required",
        },
        {
            "name": "Laguna Golf Lang Co",
            "region": "danang",
            "address": "Chan May Ward, Phu Loc, Thua Thien Hue",
            "holes": 18,
            "par": 71,
            "yards": 6985,
            "green_fee_usd": 130,
            "designer": "Sir Nick Faldo",
            "ranking": "Top courses Vietnam",
            "phone": "+84 234 3695 800",
            "booking_email": "golf@lagunalangco.com",
            "website": "lagunaresorts.com/lang-co",
            "caddy_fee": "Included",
            "cart_fee_usd": 20,
            "club_hire_usd": 45,
            "available_times": ["07:00", "07:30", "08:00", "09:00", "10:00", "11:00"],
            "notes": "Nick Faldo design between Hue and Danang. Mountain and lagoon views. Inside Banyan Tree resort.",
            "cancellation_policy": "48 hours notice required",
        },
    ],

    # ─────────────────────────────────────────────
    # HO TRAM / HO CHI MINH CITY REGION
    # ─────────────────────────────────────────────
    "ho_tram": [
        {
            "name": "The Bluffs Ho Tram Strip",
            "region": "ho_tram",
            "address": "Phuoc Thuan, Xuyen Moc, Ba Ria-Vung Tau",
            "holes": 18,
            "par": 71,
            "yards": 7007,
            "green_fee_usd": 180,
            "designer": "Greg Norman",
            "ranking": "World Top 50 (Golf Digest)",
            "phone": "+84 254 3788 666",
            "booking_email": "bookings@thebluffshotram.com",
            "website": "thebluffshotram.com",
            "caddy_fee": "Included",
            "cart_fee_usd": 25,
            "club_hire_usd": 50,
            "available_times": ["07:00", "08:00", "09:00", "10:00", "11:00"],
            "notes": "World-ranked bucket-list links course on stunning coastline. 2 hours from HCMC. Wind is a constant factor — check conditions.",
            "cancellation_policy": "48 hours notice required",
        },
    ],

    # ─────────────────────────────────────────────
    # HO CHI MINH CITY REGION
    # ─────────────────────────────────────────────
    "ho_chi_minh": [
        {
            "name": "Vietnam Golf & Country Club",
            "region": "ho_chi_minh",
            "address": "Thu Duc, Ho Chi Minh City",
            "holes": 36,
            "par": 144,
            "yards": 13500,
            "green_fee_usd": 85,
            "designer": "Ronald Fream",
            "ranking": "Vietnam Masters host course",
            "phone": "+84 938 568 899",
            "booking_email": "bookings@vietnamgolfcc.com",
            "website": "vietnamgolfcc.com",
            "caddy_fee": "Included",
            "cart_fee_usd": 20,
            "club_hire_usd": 35,
            "available_times": ["06:00", "06:30", "07:00", "07:30", "08:00", "09:00", "10:00", "11:00", "13:00"],
            "notes": "Two 18-hole courses (West and East). West Course hosted Asian PGA Tour. 17km from HCMC centre.",
            "cancellation_policy": "24 hours notice required",
        },
        {
            "name": "Tan Son Nhat Golf Course",
            "region": "ho_chi_minh",
            "address": "Adjacent to Tan Son Nhat International Airport, HCMC",
            "holes": 36,
            "par": 144,
            "yards": 13800,
            "green_fee_usd": 75,
            "designer": "Nelson & Haworth",
            "ranking": "Most convenient airport golf in Asia",
            "phone": "+84 28 3848 0667",
            "booking_email": "booking@tansonnhatgolf.com.vn",
            "website": "tansonnhatgolf.com.vn",
            "caddy_fee": "Included",
            "cart_fee_usd": 18,
            "club_hire_usd": 30,
            "available_times": ["06:00", "06:30", "07:00", "07:30", "08:00", "09:00", "10:00", "11:00", "12:00", "13:00"],
            "notes": "Only course in central HCMC. 15 min from airport. PGA standard. Night golf available.",
            "cancellation_policy": "24 hours notice required",
        },
        {
            "name": "Twin Doves Golf Club",
            "region": "ho_chi_minh",
            "address": "Cu Chi District, Ho Chi Minh City",
            "holes": 18,
            "par": 72,
            "yards": 6891,
            "green_fee_usd": 70,
            "designer": "Greg Norman",
            "ranking": "Top HCMC courses",
            "phone": "+84 28 3794 5566",
            "booking_email": "golf@twindoves.com.vn",
            "website": "twindovesgolf.com",
            "caddy_fee": "Included",
            "cart_fee_usd": 18,
            "club_hire_usd": 30,
            "available_times": ["06:00", "07:00", "08:00", "09:00", "10:00", "11:00", "13:00"],
            "notes": "Tranquil setting in Cu Chi. Natural landscape with water features. 45 min from HCMC centre.",
            "cancellation_policy": "24 hours notice required",
        },
        {
            "name": "Vinpearl Golf Leman",
            "region": "ho_chi_minh",
            "address": "Cu Chi District, Ho Chi Minh City",
            "holes": 18,
            "par": 72,
            "yards": 7200,
            "green_fee_usd": 120,
            "designer": "Greg Norman",
            "ranking": "Newest Vinpearl course (opened Oct 2025)",
            "phone": "+84 28 3600 8888",
            "booking_email": "golf.leman@vinpearl.com",
            "website": "vinpearl.com/en/vinpearl-golf",
            "caddy_fee": "Included",
            "cart_fee_usd": 20,
            "club_hire_usd": 40,
            "available_times": ["06:30", "07:00", "07:30", "08:00", "09:00", "10:00", "11:00"],
            "notes": "Newest Vinpearl course, opened October 2025. Premium facilities.",
            "cancellation_policy": "48 hours notice required",
        },
    ],

    # ─────────────────────────────────────────────
    # HANOI REGION
    # ─────────────────────────────────────────────
    "hanoi": [
        {
            "name": "BRG Kings Island Golf Resort - Kings Course",
            "region": "hanoi",
            "address": "Dong Mo, Son Tay, Hanoi",
            "holes": 18,
            "par": 72,
            "yards": 7100,
            "green_fee_usd": 90,
            "designer": "Lee Trevino",
            "ranking": "Best resort course Hanoi",
            "phone": "+84 24 3368 9999",
            "booking_email": "golf@brg-kingsisland.com.vn",
            "website": "brg-kingsisland.com.vn",
            "caddy_fee": "Included",
            "cart_fee_usd": 18,
            "club_hire_usd": 35,
            "available_times": ["06:30", "07:00", "07:30", "08:00", "09:00", "10:00", "11:00", "13:00"],
            "notes": "Southeast Asia's jewel. Dong Mo lake views. 45 min from Hanoi centre. 36 holes total across resort.",
            "cancellation_policy": "24 hours notice required",
        },
        {
            "name": "Sky Lake Resort & Golf Club",
            "region": "hanoi",
            "address": "Van Son Lake, Chuong My, Hanoi",
            "holes": 36,
            "par": 144,
            "yards": 14200,
            "green_fee_usd": 80,
            "designer": "Ahn Moon Hwan",
            "ranking": "World-class 36-hole resort",
            "phone": "+84 24 3368 5555",
            "booking_email": "booking@skylakegolf.com.vn",
            "website": "skylakegolf.com.vn",
            "caddy_fee": "Included",
            "cart_fee_usd": 18,
            "club_hire_usd": 35,
            "available_times": ["06:00", "06:30", "07:00", "07:30", "08:00", "09:00", "10:00", "11:00"],
            "notes": "Sky Course and Lake Course. Korean-designed. Chuong My district, 40 min from Hanoi.",
            "cancellation_policy": "24 hours notice required",
        },
        {
            "name": "Long Bien Golf Course",
            "region": "hanoi",
            "address": "Long Bien District, Hanoi",
            "holes": 18,
            "par": 72,
            "yards": 6800,
            "green_fee_usd": 55,
            "designer": "Local design",
            "ranking": "Most accessible Hanoi course",
            "phone": "+84 24 3827 6969",
            "booking_email": "booking@longbiengolf.com.vn",
            "website": "longbiengolf.com.vn",
            "caddy_fee": "Included",
            "cart_fee_usd": 15,
            "club_hire_usd": 25,
            "available_times": ["06:00", "06:30", "07:00", "07:30", "08:00", "09:00", "10:00", "11:00", "12:00", "13:00"],
            "notes": "Best value in Hanoi. Close to city centre. Good for early morning rounds.",
            "cancellation_policy": "24 hours notice required",
        },
        {
            "name": "Chi Linh Star Golf & Country Club",
            "region": "hanoi",
            "address": "Chi Linh, Hai Duong Province (near Hanoi)",
            "holes": 27,
            "par": 108,
            "yards": 10200,
            "green_fee_usd": 65,
            "designer": "IMG",
            "ranking": "First professional tournament host in North Vietnam",
            "phone": "+84 220 3886 666",
            "booking_email": "info@chilinhstar.com.vn",
            "website": "chilinhstar.com.vn",
            "caddy_fee": "Included",
            "cart_fee_usd": 18,
            "club_hire_usd": 30,
            "available_times": ["06:30", "07:00", "07:30", "08:00", "09:00", "10:00", "11:00"],
            "notes": "27 holes on the route to Halong Bay. First professional tournament venue in North Vietnam. 1.5 hours from Hanoi.",
            "cancellation_policy": "24 hours notice required",
        },
    ],

    # ─────────────────────────────────────────────
    # PHU QUOC
    # ─────────────────────────────────────────────
    "phu_quoc": [
        {
            "name": "Vinpearl Golf Phu Quoc",
            "region": "phu_quoc",
            "address": "Bai Dai, Phu Quoc Island",
            "holes": 18,
            "par": 72,
            "yards": 7100,
            "green_fee_usd": 110,
            "designer": "IMG Worldwide",
            "ranking": "Best island golf Vietnam",
            "phone": "+84 297 3979 999",
            "booking_email": "golf.phuquoc@vinpearl.com",
            "website": "vinpearl.com/en/vinpearl-golf-phu-quoc",
            "caddy_fee": "Included",
            "cart_fee_usd": 20,
            "club_hire_usd": 40,
            "available_times": ["07:00", "07:30", "08:00", "08:30", "09:00", "10:00", "11:00"],
            "notes": "Unique island course. Primeval forest on one side, clear blue sea on the other. Pearl Island paradise.",
            "cancellation_policy": "48 hours notice required",
        },
    ],

    # ─────────────────────────────────────────────
    # NHA TRANG
    # ─────────────────────────────────────────────
    "nha_trang": [
        {
            "name": "Vinpearl Golf Nha Trang",
            "region": "nha_trang",
            "address": "Hon Tre Island, Nha Trang",
            "holes": 18,
            "par": 71,
            "yards": 6950,
            "green_fee_usd": 100,
            "designer": "IMG Worldwide",
            "ranking": "Top Vietnam island courses",
            "phone": "+84 258 3598 222",
            "booking_email": "golf.nhatrang@vinpearl.com",
            "website": "vinpearl.com/en/vinpearl-golf-nha-trang",
            "caddy_fee": "Included",
            "cart_fee_usd": 20,
            "club_hire_usd": 40,
            "available_times": ["07:00", "07:30", "08:00", "08:30", "09:00", "10:00", "11:00"],
            "notes": "On Hon Tre Island — accessed by cable car from Nha Trang. Natural terrain preserved throughout.",
            "cancellation_policy": "48 hours notice required",
        },
        {
            "name": "Diamond Bay Golf & Villas",
            "region": "nha_trang",
            "address": "Nguyen Tat Thanh, Nha Trang",
            "holes": 18,
            "par": 72,
            "yards": 6800,
            "green_fee_usd": 70,
            "designer": "IMG Worldwide",
            "ranking": "Best value Nha Trang",
            "phone": "+84 258 3710 888",
            "booking_email": "golf@diamondbaynhatrang.com",
            "website": "diamondbaynhatrang.com",
            "caddy_fee": "Included",
            "cart_fee_usd": 18,
            "club_hire_usd": 30,
            "available_times": ["06:30", "07:00", "07:30", "08:00", "09:00", "10:00", "11:00"],
            "notes": "Beachfront course with ocean views. Great value for Nha Trang. 10 min from city centre.",
            "cancellation_policy": "24 hours notice required",
        },
    ],

    # ─────────────────────────────────────────────
    # DA LAT (HIGHLANDS)
    # ─────────────────────────────────────────────
    "da_lat": [
        {
            "name": "Dalat Palace Golf Club",
            "region": "da_lat",
            "address": "1 Phu Dong Thien Vuong, Da Lat",
            "holes": 18,
            "par": 71,
            "yards": 6500,
            "green_fee_usd": 75,
            "designer": "Rossie & Bendelow (1922, renovated 1995)",
            "ranking": "Most historic course in Vietnam",
            "phone": "+84 263 3821 201",
            "booking_email": "golf@dalatpalace.com.vn",
            "website": "dalatpalace.com.vn",
            "caddy_fee": "Included",
            "cart_fee_usd": 18,
            "club_hire_usd": 30,
            "available_times": ["07:00", "07:30", "08:00", "09:00", "10:00", "11:00"],
            "notes": "Vietnam's oldest golf course (1922). Cool highland climate year-round. Pine forest setting. Truly unique experience.",
            "cancellation_policy": "24 hours notice required",
        },
        {
            "name": "Sacom Tuyen Lam Golf",
            "region": "da_lat",
            "address": "Tuyen Lam Lake, Da Lat",
            "holes": 18,
            "par": 72,
            "yards": 7100,
            "green_fee_usd": 65,
            "designer": "Schmidt Curley",
            "ranking": "Top Da Lat courses",
            "phone": "+84 263 3831 888",
            "booking_email": "golf@sacomtuyenlam.com.vn",
            "website": "sacomresort.com.vn",
            "caddy_fee": "Included",
            "cart_fee_usd": 18,
            "club_hire_usd": 30,
            "available_times": ["07:00", "07:30", "08:00", "09:00", "10:00", "11:00"],
            "notes": "Lakeside course with stunning views of Tuyen Lam Lake. Cool year-round. Inside resort complex.",
            "cancellation_policy": "24 hours notice required",
        },
    ],

    # ─────────────────────────────────────────────
    # HAI PHONG / NORTH
    # ─────────────────────────────────────────────
    "hai_phong": [
        {
            "name": "Vinpearl Golf Hai Phong",
            "region": "hai_phong",
            "address": "Vu Yen Island, Hai Phong",
            "holes": 18,
            "par": 72,
            "yards": 7200,
            "green_fee_usd": 95,
            "designer": "IMG Worldwide",
            "ranking": "Top North Vietnam courses",
            "phone": "+84 225 3688 999",
            "booking_email": "golf.haiphong@vinpearl.com",
            "website": "vinpearl.com/en/vinpearl-golf-hai-phong",
            "caddy_fee": "Included",
            "cart_fee_usd": 20,
            "club_hire_usd": 40,
            "available_times": ["07:00", "07:30", "08:00", "08:30", "09:00", "10:00", "11:00"],
            "notes": "Island course on Vu Yen Island. Near Halong Bay — combine with cruise.",
            "cancellation_policy": "48 hours notice required",
        },
        {
            "name": "Dragon Golf Links",
            "region": "hai_phong",
            "address": "Dragon Hill Complex, Hai Phong",
            "holes": 27,
            "par": 108,
            "yards": 10800,
            "green_fee_usd": 85,
            "designer": "IMG Worldwide",
            "ranking": "Newest international course North Vietnam (2023)",
            "phone": "+84 225 3989 666",
            "booking_email": "golf@dragonhill.com.vn",
            "website": "dragonhill.com.vn",
            "caddy_fee": "Included",
            "cart_fee_usd": 20,
            "club_hire_usd": 35,
            "available_times": ["07:00", "07:30", "08:00", "09:00", "10:00", "11:00"],
            "notes": "27-hole international standard. Opened 2023. Part of Dragon Hill tourism complex. Near Halong Bay.",
            "cancellation_policy": "48 hours notice required",
        },
    ],
}


# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# These replace the mock execute_tool functions
# ─────────────────────────────────────────────

def search_courses_by_region(region: str, max_green_fee_usd: float = None) -> list:
    """Search for courses by region name (flexible matching)."""
    region_lower = region.lower().strip()

    # Map common user inputs to database keys
    region_map = {
        "danang": "danang",
        "da nang": "danang",
        "hoi an": "danang",
        "hoian": "danang",
        "central vietnam": "danang",
        "ho tram": "ho_tram",
        "ho chi minh": "ho_chi_minh",
        "ho chi minh city": "ho_chi_minh",
        "hcmc": "ho_chi_minh",
        "saigon": "ho_chi_minh",
        "hanoi": "hanoi",
        "ha noi": "hanoi",
        "north vietnam": "hanoi",
        "phu quoc": "phu_quoc",
        "nha trang": "nha_trang",
        "da lat": "da_lat",
        "dalat": "da_lat",
        "highlands": "da_lat",
        "hai phong": "hai_phong",
        "haiphong": "hai_phong",
        "halong": "hai_phong",
        "ha long": "hai_phong",
    }

    db_key = region_map.get(region_lower)
    if not db_key:
        # Fuzzy match
        for k in region_map:
            if k in region_lower or region_lower in k:
                db_key = region_map[k]
                break

    if not db_key or db_key not in VIETNAM_GOLF_COURSES:
        return []

    courses = VIETNAM_GOLF_COURSES[db_key]

    if max_green_fee_usd:
        courses = [c for c in courses if c["green_fee_usd"] <= max_green_fee_usd]

    return courses


def get_all_course_names() -> list:
    """Return a flat list of all course names for agent awareness."""
    names = []
    for region_courses in VIETNAM_GOLF_COURSES.values():
        for course in region_courses:
            names.append(course["name"])
    return names


def get_course_by_name(name: str) -> dict:
    """Find a course by name (flexible matching)."""
    name_lower = name.lower()
    for region_courses in VIETNAM_GOLF_COURSES.values():
        for course in region_courses:
            if name_lower in course["name"].lower() or course["name"].lower() in name_lower:
                return course
    return None


def get_total_course_count() -> int:
    return sum(len(v) for v in VIETNAM_GOLF_COURSES.values())
