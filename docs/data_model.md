# Sasha Data Model

Full technical specification for all 10 entities. Database: PostgreSQL (Supabase). Encrypted fields use pgcrypto at the application layer — stored as `text` ciphertext. JSONB fields use Postgres native JSON.

---

## users

Core identity record. One per person across all roles.

| Column | Type | Notes |
|---|---|---|
| id | uuid | PK, gen_random_uuid() |
| email | text | unique, not null |
| name | text | |
| role | text | traveler \| agent \| operator \| admin |
| created_at | timestamptz | default now() |

---

## organizations

Hotels, travel agencies, concierge operators. Each can have its own Sasha persona and config.

| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| name | text | not null |
| type | text | hotel \| agency \| operator \| enterprise |
| sasha_config | jsonb | persona_name, welcome_message, enabled_agents[], primary_color, logo_url, notification_email |
| created_at | timestamptz | default now() |

---

## traveler_profiles

Personal travel preferences and sensitive documents for a user. Sensitive fields encrypted with pgcrypto.

| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| user_id | uuid | FK → users.id, unique |
| passport_number | text | encrypted |
| passport_expiry | text | encrypted |
| nationality | text | |
| date_of_birth | text | encrypted |
| dietary_requirements | text | e.g. vegetarian, nut allergy |
| seat_preference | text | e.g. aisle, window, extra legroom |
| loyalty_programs | jsonb | [{program, member_number, status, points}] |
| credit_cards | jsonb | [{nickname, last_four, network, best_for}] — no full PANs |
| emergency_contact | text | encrypted — name, phone, relationship |
| updated_at | timestamptz | auto-updated via trigger |

---

## trips

The top-level travel plan. Can have multiple travelers and multiple items.

| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| owner_id | uuid | FK → users.id |
| organization_id | uuid | FK → organizations.id, nullable |
| title | text | e.g. "Vietnam & Cambodia — March 2026" |
| status | text | draft \| active \| completed \| cancelled |
| destinations | jsonb | [{city, country, arrive_date, depart_date}] |
| depart_date | date | |
| return_date | date | |
| travelers | jsonb | [{user_id, name, passport_nationality}] |
| total_cost_usd | numeric(10,2) | |
| currency | text | default 'USD' |
| shared_with | jsonb | [{user_id, permission: view\|edit}] |
| created_at | timestamptz | default now() |
| updated_at | timestamptz | auto-updated via trigger |

---

## trip_items

Every bookable element of a trip — flights, hotels, restaurants, transfers, etc. The booking state machine lives here.

| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| trip_id | uuid | FK → trips.id |
| type | text | flight \| hotel \| restaurant \| golf \| transfer \| experience \| visa \| insurance \| doctor \| beauty \| dog_walking \| coworking |
| status | text | pending \| attempting \| confirmed \| failed \| escalated \| cancelled |
| booking_reference | text | confirmation number from provider |
| provider_name | text | |
| provider_email | text | |
| provider_phone | text | |
| date_time | timestamptz | |
| duration_minutes | integer | |
| location_name | text | |
| location_address | text | |
| location_lat | numeric(9,6) | |
| location_lng | numeric(9,6) | |
| price_usd | numeric(10,2) | |
| currency | text | |
| confirmation_deadline | timestamptz | when the item needs to be confirmed by |
| escalated_at | timestamptz | when status moved to escalated |
| escalation_notes | text | |
| created_at | timestamptz | default now() |
| updated_at | timestamptz | auto-updated via trigger |

---

## booking_attempts

Audit trail for every method used to confirm a trip item — email, phone, or web form. Supports multi-attempt retry logic.

| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| trip_item_id | uuid | FK → trip_items.id |
| method | text | email \| phone \| web_form |
| attempted_at | timestamptz | default now() |
| status | text | sent \| delivered \| confirmed \| failed \| no_response |
| response_received | text | raw response text or summary |
| response_at | timestamptz | |
| bland_call_id | text | from Bland.ai if method = phone |
| resend_email_id | text | from Resend if method = email |
| browserbase_session_id | text | from Browserbase if method = web_form |

---

## documents

Visa approvals, insurance policies, booking confirmations, passport scans — attached to a trip or traveler profile.

| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| trip_id | uuid | FK → trips.id, nullable |
| traveler_profile_id | uuid | FK → traveler_profiles.id, nullable |
| type | text | visa \| insurance \| booking_confirmation \| passport \| other |
| file_url | text | Supabase Storage URL |
| expires_at | date | for visas, insurance policies, passports |
| issued_for_destination | text | country code |
| created_at | timestamptz | default now() |

---

## escalations

When Sasha can't confirm a booking automatically, it escalates to a human agent with full context and SLA tracking.

| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| trip_item_id | uuid | FK → trip_items.id |
| assigned_to | uuid | FK → users.id (human agent), nullable |
| status | text | open \| in_progress \| resolved \| closed |
| priority | text | low \| medium \| high \| urgent |
| sla_deadline | timestamptz | when this must be resolved |
| context | jsonb | full booking context snapshot at time of escalation |
| resolution_notes | text | |
| resolved_at | timestamptz | |
| created_at | timestamptz | default now() |

---

## conversations

Full conversation history per trip session. Stores messages and which agents fired — for debugging and context replay.

| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| trip_id | uuid | FK → trips.id, nullable |
| user_id | uuid | FK → users.id |
| messages | jsonb | [{role: user\|assistant, content, timestamp}] |
| agent_intents_fired | jsonb | [{intent, agent, response_length, tools_used[], timestamp}] |
| created_at | timestamptz | default now() |

---

## calendar_events

Syncs confirmed trip items to Google Calendar and Apple Calendar.

| Column | Type | Notes |
|---|---|---|
| id | uuid | PK |
| trip_item_id | uuid | FK → trip_items.id |
| user_id | uuid | FK → users.id |
| google_event_id | text | |
| apple_event_id | text | |
| synced_at | timestamptz | |

---

## Key relationships

```
users ──< trips (owner_id)
users ──< traveler_profiles (1:1)
organizations ──< trips
trips ──< trip_items
trips ──< documents
trips ──< conversations
trip_items ──< booking_attempts
trip_items ──< escalations
trip_items ──< calendar_events
traveler_profiles ──< documents
```

---

## JSONB schemas

**organizations.sasha_config**
```json
{
  "persona_name": "Sasha",
  "welcome_message": "Hi, I'm Sasha...",
  "enabled_agents": ["restaurant", "golf", "weather"],
  "primary_color": "#1a1a2e",
  "logo_url": "https://...",
  "notification_email": "concierge@hotel.com"
}
```

**traveler_profiles.loyalty_programs**
```json
[{"program": "Singapore Airlines KrisFlyer", "member_number": "...", "status": "Gold", "points": 45000}]
```

**trips.destinations**
```json
[{"city": "Hoi An", "country": "Vietnam", "arrive_date": "2026-03-10", "depart_date": "2026-03-17"}]
```

**escalations.context**
```json
{
  "trip_title": "Vietnam March 2026",
  "item_type": "restaurant",
  "provider_name": "The Deck",
  "attempts": [{"method": "email", "status": "no_response"}, {"method": "phone", "status": "failed"}],
  "guest_name": "Tyler Warren",
  "date": "2026-03-12",
  "party_size": 4
}
```
