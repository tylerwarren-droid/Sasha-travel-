# Sasha Agents

23 agents live as of June 12, 2026. All dispatched by `conductor.py` via keyword classification. Multiple agents can fire in parallel on a single message.

---

## Dispatch architecture

`classify_intents(message, history)` → list of intent strings → `AGENT_REGISTRY` maps each to a runner → `asyncio.gather` with 30s timeout per agent → responses merged by a single Sonnet call and sent to the frontend.

All agents use `claude-haiku-4-5` for tool call loops. Only the conductor merge step uses Sonnet.

---

## Agents

### 1. golf
**Triggers:** golf, tee time, tee-time, fairway, caddy, green fee, golf course, play golf, montgomerie, hoiana, bluffs, ba na hills, vinpearl golf
**Capabilities:** Tee time availability, course recommendations, caddy and cart info, green fees
**Tools:** web_search

---

### 2. booking_confirmation
**Triggers:** confirm booking, hotel reference, pms, booking.com ref, expedia ref, booking number, confirm my booking, reservation number
**Capabilities:** Hotel booking reference lookups, PMS reservation confirmation, booking detail retrieval
**Tools:** web_search

---

### 3. beauty
**Triggers:** massage, spa, nails, facial, manicure, pedicure, beauty, salon, treatment, relaxation, wellness
**Capabilities:** Spa and salon recommendations, treatment options, booking assistance
**Tools:** web_search

---

### 4. health
**Triggers:** doctor, medical, sick, pharmacy, clinic, hospital, hurt, ill, prescription, nurse, health, medicine
**Capabilities:** Nearest clinics and hospitals, pharmacy locations, medical referrals
**Tools:** web_search

---

### 5. dog_walking
**Triggers:** dog, pet, dog walk, dog sit, kennel, grooming, puppy
**Capabilities:** Dog walking, pet sitting, kennel and grooming service recommendations
**Tools:** web_search

---

### 6. foto
**Triggers:** show me, photo, picture, image, what does, what do, look like
**Capabilities:** Destination and hotel photos, visual context for locations
**Tools:** web_search, photo lookup

---

### 7. restaurant
**Triggers:** restaurant, dinner, lunch, breakfast, eat, food, table, reservation, book a table, dining, cuisine, cafe, bar, rooftop, where to eat, hungry — **plus** an action word (find, book, reserve, recommend, where to, etc.)
**Capabilities:** Find restaurants by location/cuisine/budget/occasion, send reservation email, AI phone booking
**Tools:** `find_restaurant` (web_search), `send_reservation_email` (Resend API), `call_restaurant` (Bland.ai API)

---

### 8. smart_sasha
**Triggers:** cheapest, best deal, find me a flight, search for flights, plan a trip, want to travel, trip to, fly to, vacation to — combined with a destination keyword (flight, fly, travel, trip, europe, asia, etc.)
**Capabilities:** Trip planning, flight search guidance, itinerary suggestions
**Tools:** web_search

---

### 9. credit_card
**Triggers:** credit card, which card, points, miles, rewards, amex, chase sapphire, capital one, bilt, card to use, earn points, transfer points, annual credit, card benefits, maximize points, best card
**Capabilities:** Card recommendations for travel purchases, points/miles optimization, transfer partner advice
**Tools:** web_search

---

### 10. car_rental
**Triggers:** rental car, car rental, rent a car, hire a car, rental insurance, cdw, collision waiver, rental coverage, hertz, avis, enterprise rental, europcar, should i take insurance
**Capabilities:** Car rental recommendations, CDW/insurance advice, rental platform comparisons
**Tools:** web_search

---

### 11. visa
**Triggers:** visa, entry requirements, passport, do i need a visa, travel documents, entry restriction, visa on arrival, evisa, e-visa, tourist visa, transit visa
**Capabilities:** Visa type, cost, processing time, passport validity requirements, application links, entry restrictions
**Tools:** `check_visa_requirements` (web_search)
**Model:** claude-haiku-4-5

---

### 12. currency
**Triggers:** currency, exchange rate, money, atm, cash, should i use my card, tipping, tip, local money, how much is, convert, dong, baht, peso, rupiah, ringgit, won
**Capabilities:** Live exchange rates, ATM availability, cash vs card advice, tipping customs
**Tools:** `get_exchange_rate` (web_search)

---

### 13. weather
**Triggers:** weather, what to pack, climate, best time to visit, rainy season, temperature, hot or cold, forecast, will it rain, typhoon, monsoon, dry season
**Capabilities:** Seasonal weather, temperature ranges, rainfall, humidity, best/worst times to visit, packing by season
**Tools:** `get_weather_info` (web_search)

---

### 14. emergency
**Triggers:** emergency, lost passport, stolen, hospital, police, help me, robbery, accident, embassy, arrested, lost my, stolen my, hurt badly, need help urgently, crisis
**Capabilities:** Embassy and consulate contacts, emergency hotlines, police/hospital locations, lost passport procedures
**Tools:** `get_emergency_info` (web_search)

---

### 15. language
**Triggers:** language, phrases, how do i say, translation, etiquette, customs, culture, local words, speak, greetings, thank you in, hello in, dress code, cultural
**Capabilities:** Essential phrases with pronunciation, cultural dos/don'ts, dining etiquette, bargaining tips, dress codes, religious customs
**Tools:** `get_language_info` (web_search)

---

### 16. packing
**Triggers:** packing, what to bring, luggage, what should i pack, suitcase, carry on, what do i need to bring, what to pack, packing list, bag, baggage
**Capabilities:** Personalized packing lists by destination, duration, activities, weather, and traveler type
**Tools:** `create_packing_list` (web_search)

---

### 17. family
**Triggers:** kids, children, family, baby, toddler, kid-friendly, family travel, stroller, car seat, with children, my kids, travelling with kids, child friendly, infant
**Capabilities:** Kid-friendly hotels and restaurants, age-appropriate activities, stroller accessibility, baby/toddler essentials, safety notes
**Tools:** `get_family_info` (web_search)

---

### 18. airport_transfer
**Triggers:** airport transfer, taxi, pickup, airport shuttle, private car, transfer to hotel, how to get from airport, get from airport, from the airport, airport taxi, airport pickup
**Capabilities:** Transfer options across price tiers (shuttle, private car, luxury/SUV), pricing, duration, booking links
**Tools:** `find_transfer` (web_search — GetTransfer, Blacklane, local services)

---

### 19. experiences
**Triggers:** cooking class, tour, experience, activity, things to do, local guide, cultural tour, excursion, day trip, guided tour, food tour, walking tour, boat tour
**Capabilities:** Top 3 local experiences per destination — group tours, private tours, hands-on classes; price per person, duration, booking links
**Tools:** `find_experiences` (web_search — Viator, GetYourGuide, Airbnb Experiences, local operators)

---

### 20. coworking
**Triggers:** coworking, co-working, work remotely, wifi, coffee shop to work, laptop friendly, remote work, digital nomad, fast wifi, place to work, work from
**Capabilities:** Coworking spaces and laptop-friendly cafes — wifi speed, pricing, hours, vibe, address
**Tools:** `find_coworking` (web_search — Workfrom, NomadList, Coworker.com)

---

### 21. insurance
**Triggers:** travel insurance, insurance, coverage, medical coverage, trip cancellation, safetywing, world nomads, insure my trip, insure, travel cover, covered if
**Capabilities:** Side-by-side comparison of SafetyWing, World Nomads, InsureMyTrip — price, medical limit, evacuation, cancellation, adventure sports coverage
**Tools:** `compare_insurance` (web_search)

---

### 22. loyalty
**Triggers:** loyalty program, frequent flyer, hotel points, airline miles, status, which program, marriott, hilton, ihg, united miles, delta miles, british airways, oneworld, star alliance, skyteam, frequent traveler, elite status
**Capabilities:** Program recommendations by travel pattern, status tiers to target, transfer partners, quick wins to earn faster
**Tools:** `get_loyalty_advice` (web_search)

---

### 23. api_assimilation
**Triggers:** api, integrate, need an api, which api, travel api, booking api, flight api, hotel api, how do i connect, third party, third-party, api key, api documentation, connect to
**Capabilities:** Discover and rank travel APIs by vertical/region/use-case (coverage, pricing, approval difficulty, sandbox availability); generate working Python or TypeScript integration code templates
**Tools:** `discover_apis` (web_search), `generate_integration_code` (web_search → code template)
