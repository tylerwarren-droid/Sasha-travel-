# Sasha Agents

17 agents live as of June 12, 2026. All are dispatched by `conductor.py` based on keyword classification of the user message. Multiple agents can fire in parallel on a single message.

---

## Dispatch architecture

`classify_intents(message, history)` → list of intent strings → `AGENT_REGISTRY` maps each to a runner → `asyncio.gather` with 30s timeout per agent → responses merged and sent to the frontend.

---

## Agents

### 1. golf
**Trigger keywords:** golf, tee time, tee-time, fairway, caddy, green fee, golf course, play golf, montgomerie, hoiana, bluffs, ba na hills, vinpearl golf
**Capabilities:** Tee time availability, course recommendations, caddy and cart info, green fees
**Tools:** web_search

---

### 2. booking_confirmation
**Trigger keywords:** confirm booking, hotel reference, pms, booking.com ref, expedia ref, booking number, confirm my booking, reservation number
**Capabilities:** Looks up hotel booking references, confirms PMS reservations, retrieves booking details
**Tools:** web_search

---

### 3. beauty
**Trigger keywords:** massage, spa, nails, facial, manicure, pedicure, beauty, salon, treatment, relaxation, wellness
**Capabilities:** Spa and salon recommendations, treatment options, booking assistance
**Tools:** web_search

---

### 4. health
**Trigger keywords:** doctor, medical, sick, pharmacy, clinic, hospital, hurt, ill, prescription, nurse, health, medicine
**Capabilities:** Nearest clinics and hospitals, pharmacy locations, medical advice referrals
**Tools:** web_search

---

### 5. dog_walking
**Trigger keywords:** dog, pet, dog walk, dog sit, kennel, grooming, puppy
**Capabilities:** Dog walking, pet sitting, kennel and grooming service recommendations
**Tools:** web_search

---

### 6. foto
**Trigger keywords:** show me, photo, picture, image, what does, what do, look like
**Capabilities:** Returns destination photos and visual context for locations
**Tools:** web_search, photo lookup

---

### 7. restaurant
**Trigger keywords:** restaurant, dinner, lunch, breakfast, eat, food, table, reservation, book a table, dining, cuisine, cafe, bar, rooftop, where to eat, hungry
**Trigger logic:** Requires both a restaurant topic word AND an action word (find, book, reserve, recommend, etc.), or restaurant context in conversation history
**Capabilities:** Find restaurants by location/cuisine/budget/occasion, send reservation email via Resend, make AI phone booking via Bland.ai
**Tools:** `find_restaurant` (web_search), `send_reservation_email` (Resend API), `call_restaurant` (Bland.ai API)

---

### 8. smart_sasha
**Trigger keywords:** cheapest, best deal, find me a flight, search for flights, plan a trip, want to travel, trip to, fly to, vacation to + destination keyword (flight, fly, travel, trip, vacation, holiday, europe, asia, etc.)
**Capabilities:** Trip planning, flight search guidance, itinerary suggestions
**Tools:** web_search

---

### 9. credit_card
**Trigger keywords:** credit card, which card, points, miles, rewards, amex, chase sapphire, capital one, bilt, card to use, earn points, transfer points, annual credit, card benefits, maximize points, best card
**Capabilities:** Card recommendations for travel purchases, points/miles optimization, transfer partner advice, benefits guidance
**Tools:** web_search

---

### 10. car_rental
**Trigger keywords:** rental car, car rental, rent a car, hire a car, rental insurance, cdw, collision waiver, rental coverage, hertz, avis, enterprise rental, europcar, should i take insurance
**Capabilities:** Car rental recommendations, CDW/insurance advice, rental platform comparisons
**Tools:** web_search

---

### 11. visa
**Trigger keywords:** visa, entry requirements, passport, do i need a visa, travel documents, entry restriction, visa on arrival, evisa, e-visa, tourist visa, transit visa
**Capabilities:** Visa type and cost, processing time, passport validity requirements, application links, entry restrictions
**Tools:** `check_visa_requirements` (web_search via claude-haiku-4-5)
**Model:** claude-haiku-4-5 (outer loop)

---

### 12. currency
**Trigger keywords:** currency, exchange rate, money, atm, cash, should i use my card, tipping, tip, local money, how much is, convert, dong, baht, peso, rupiah, ringgit, won
**Capabilities:** Live exchange rates, ATM availability, cash vs card advice, tipping customs
**Tools:** `get_exchange_rate` (web_search)

---

### 13. weather
**Trigger keywords:** weather, what to pack, climate, best time to visit, rainy season, temperature, hot or cold, forecast, will it rain, typhoon, monsoon, dry season
**Capabilities:** Current and seasonal weather, temperature ranges, rainfall, humidity, packing recommendations by season
**Tools:** `get_weather_info` (web_search)

---

### 14. emergency
**Trigger keywords:** emergency, lost passport, stolen, hospital, police, help me, robbery, accident, embassy, arrested, lost my, stolen my, hurt badly, need help urgently, crisis
**Capabilities:** Embassy and consulate contacts, emergency hotlines, police/hospital locations, lost passport procedures
**Tools:** `get_emergency_info` (web_search)

---

### 15. language
**Trigger keywords:** language, phrases, how do i say, translation, etiquette, customs, culture, local words, speak, greetings, thank you in, hello in, dress code, cultural
**Capabilities:** Essential phrases with pronunciation, cultural dos/don'ts, dining etiquette, bargaining tips, dress codes, religious customs
**Tools:** `get_language_info` (web_search)

---

### 16. packing
**Trigger keywords:** packing, what to bring, luggage, what should i pack, suitcase, carry on, what do i need to bring, what to pack, packing list, bag, baggage
**Capabilities:** Personalized packing lists by destination, duration, activities, weather, and traveler type
**Tools:** `create_packing_list` (web_search)

---

### 17. family
**Trigger keywords:** kids, children, family, baby, toddler, kid-friendly, family travel, stroller, car seat, with children, my kids, travelling with kids, child friendly, infant
**Capabilities:** Kid-friendly hotels and restaurants, age-appropriate activities, stroller accessibility, baby/toddler essentials, safety notes
**Tools:** `get_family_info` (web_search)
