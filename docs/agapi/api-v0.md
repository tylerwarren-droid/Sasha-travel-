# AgAPI v0 — the contract

*Generated from `backend/agapi/v0.py` by `backend/scripts/agapi_doc.py`. Do not edit by hand.*

One contract for every client.

- **Today:** Sasha's own agent at `/next` uses it.
- **Later:** the same tools as a REST API (`POST /agapi/v0/{tool}`) and as an MCP server (one MCP tool per entry,
  the same input schema).

## Rules every call obeys

- **Scope.** Every call runs for ONE account: the caller's authenticated account. It's never an id in the input.
- **Mode.** `test` only in v0: Duffel TEST, Stripe TEST, TEST hotel bookings. `live` is refused with `mode_not_available`.
- **Idempotency.** Austen's calls require `idempotency_key`. The same key returns the first result (`replayed: true`)
  and never repeats the action.
- **Explicit yes.** `book` requires `approval.said`: the person's own words in the current turn, an explicit yes
  ("Yes", "Then book it.", "Go ahead"). Anything else is refused with `no_explicit_yes`. A client fills it
  from the person's real message, never from a model.
- **Truth.** Prices and totals only from results. Booked / paid / confirmed only from Pacioli (`get_status`).
- **Errors.** Errors are `{"ok": false, "error": {"code", "message"}}`, honest, for the caller to explain.
  Success is `{"ok": true, "result": …}`.

## The agents

| Agent | Role | Tools |
|---|---|---|
| **Magellan** | finds | `search_flights`, `search_stays`, `search_venues`, `prepare_trip`, `propose_trip`, `swap_stay` |
| **Sherlock** | checks | `check_offer`, `read_booking_route` |
| **Austen** | acts (idempotent; book needs a yes) | `choose_offer`, `save_travellers`, `hold_booking`, `book`, `hold_venue`, `book_venue`, `cancel_venue` |
| **Pacioli** | records — the only source of booked/paid | `get_status`, `get_trip`, `get_total` |

## Magellan

### `search_flights`

Flights between two places on a day, cheapest first (TEST fares). Shown flights become the trip's suggestions for that leg.

**Errors:** `no_flights`, `airline_unreachable`, `missing_input`, `internal`

**Input**

```json
{
 "type": "object",
 "properties": {
  "origin": {
   "type": "string"
  },
  "destination": {
   "type": "string"
  },
  "date": {
   "type": "string",
   "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
  },
  "leg": {
   "enum": [
    "out",
    "back"
   ],
   "description": "out (there) or back (home); default out"
  },
  "passengers": {
   "type": "integer",
   "minimum": 1,
   "maximum": 9
  },
  "preferences": {
   "type": "string",
   "description": "e.g. direct, morning"
  }
 },
 "required": [
  "origin",
  "destination",
  "date"
 ],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "flights": {
   "type": "array",
   "items": {
    "type": "object",
    "properties": {
     "offer_id": {
      "type": "string"
     },
     "airline": {
      "type": "string"
     },
     "flights": {
      "type": "string"
     },
     "from": {
      "type": "string"
     },
     "to": {
      "type": "string"
     },
     "departs": {
      "type": "string"
     },
     "arrives": {
      "type": "string"
     },
     "stops": {
      "type": "integer"
     },
     "duration_minutes": {
      "type": "integer"
     },
     "price_eur": {
      "type": "number"
     },
     "test": {
      "const": true
     }
    }
   }
  }
 }
}
```

### `search_stays`

Places to stay in a city, best rated first: real hotels (Google), each with an ESTIMATED nightly price.

**Errors:** `city_not_covered`, `missing_input`, `internal`

**Input**

```json
{
 "type": "object",
 "properties": {
  "city": {
   "type": "string"
  },
  "preference": {
   "type": "string",
   "description": "e.g. on the beach, boutique"
  }
 },
 "required": [
  "city"
 ],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "stays": {
   "type": "array"
  }
 }
}
```

### `search_venues`

Restaurants, spas or other places in a city (Google listings; nothing contacted). The person sees them as photo cards and picks one by tap or voice; booking it goes through that venue's own route.

**Errors:** `what_invalid`, `where_invalid`, `places_not_configured`, `missing_input`, `internal`

**Input**

```json
{
 "type": "object",
 "properties": {
  "what": {
   "type": "string"
  },
  "where": {
   "type": "string"
  },
  "country": {
   "type": "string",
   "pattern": "^[A-Z]{2}$"
  },
  "open_at": {
   "type": "string",
   "description": "the local date-time wanted, YYYY-MM-DDTHH:MM (on the trip's day)"
  },
  "party": {
   "type": "integer",
   "minimum": 1,
   "maximum": 20
  }
 },
 "required": [
  "what",
  "where"
 ],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "venues": {
   "type": "array"
  }
 }
}
```

### `prepare_trip`

Start getting the trip ready in the background the moment destination, dates and party are known (and again once the origin is): the itinerary, then both legs' flights. Returns at once — keep chatting; propose_trip with the same details picks it up.

**Errors:** `start_date_invalid`, `book_not_replan`, `missing_input`, `internal`

**Input**

```json
{
 "type": "object",
 "properties": {
  "destination": {
   "type": "string"
  },
  "start_date": {
   "type": "string",
   "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
  },
  "nights": {
   "type": "integer",
   "minimum": 1,
   "maximum": 30,
   "description": "NIGHTS away: \"10 days\" is 9 nights, \"a week\" is 7"
  },
  "party": {
   "type": "integer",
   "minimum": 1,
   "maximum": 9
  },
  "interests": {
   "type": "string"
  },
  "origin": {
   "type": "string"
  }
 },
 "required": [
  "destination",
  "start_date",
  "nights",
  "party"
 ],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "preparing": {
   "type": "array"
  }
 }
}
```

### `propose_trip`

THE PROPOSAL: a day-by-day itinerary with somewhere to stay each night, a flight that fits on each leg (there and back) already chosen, and the whole trip's total. Replaces the account's current proposal. Nothing is booked.

**Errors:** `start_date_invalid`, `size_invalid`, `plan_failed`, `plan_not_saved`, `book_not_replan`, `missing_input`, `internal`

**Input**

```json
{
 "type": "object",
 "properties": {
  "destination": {
   "type": "string"
  },
  "start_date": {
   "type": "string",
   "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
  },
  "nights": {
   "type": "integer",
   "minimum": 1,
   "maximum": 30,
   "description": "NIGHTS away: \"10 days\" is 9 nights, \"a week\" is 7"
  },
  "party": {
   "type": "integer",
   "minimum": 1,
   "maximum": 9
  },
  "interests": {
   "type": "string"
  },
  "origin": {
   "type": "string",
   "description": "where they fly from"
  }
 },
 "required": [
  "destination",
  "start_date",
  "nights",
  "party",
  "origin"
 ],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "trip_id": {
   "type": "string"
  },
  "days": {
   "type": "array"
  },
  "flight_out": {
   "type": "object",
   "properties": {
    "offer_id": {
     "type": "string"
    },
    "airline": {
     "type": "string"
    },
    "flights": {
     "type": "string"
    },
    "from": {
     "type": "string"
    },
    "to": {
     "type": "string"
    },
    "departs": {
     "type": "string"
    },
    "arrives": {
     "type": "string"
    },
    "stops": {
     "type": "integer"
    },
    "duration_minutes": {
     "type": "integer"
    },
    "price_eur": {
     "type": "number"
    },
    "test": {
     "const": true
    }
   }
  },
  "flight_back": {
   "type": "object",
   "properties": {
    "offer_id": {
     "type": "string"
    },
    "airline": {
     "type": "string"
    },
    "flights": {
     "type": "string"
    },
    "from": {
     "type": "string"
    },
    "to": {
     "type": "string"
    },
    "departs": {
     "type": "string"
    },
    "arrives": {
     "type": "string"
    },
    "stops": {
     "type": "integer"
    },
    "duration_minutes": {
     "type": "integer"
    },
    "price_eur": {
     "type": "number"
    },
    "test": {
     "const": true
    }
   }
  },
  "total_eur": {
   "type": "number"
  }
 }
}
```

### `swap_stay`

Change where they stay in one city of the trip (take a name from search_stays). Returns the new total.

**Errors:** `no_trip`, `city_not_in_trip`, `swap_failed`, `not_priced`, `missing_input`, `internal`

**Input**

```json
{
 "type": "object",
 "properties": {
  "city": {
   "type": "string"
  },
  "stay_name": {
   "type": "string"
  }
 },
 "required": [
  "city",
  "stay_name"
 ],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "total_eur": {
   "type": "number"
  },
  "items": {
   "type": "integer"
  },
  "price_sources": {
   "type": "array",
   "items": {
    "type": "string"
   }
  }
 }
}
```

## Sherlock

### `check_offer`

Is this flight offer still available, and at what price?

**Errors:** `airline_unreachable`, `missing_input`, `internal`

**Input**

```json
{
 "type": "object",
 "properties": {
  "offer_id": {
   "type": "string"
  }
 },
 "required": [
  "offer_id"
 ],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "available": {
   "type": "boolean"
  },
  "price_eur": {
   "type": "number"
  }
 }
}
```

### `read_booking_route`

How a venue takes bookings (its own form, a platform page, email, phone, WhatsApp) — read from its site and listing. Use the venue card's place_id.

**Errors:** `name_invalid`, `city_invalid`, `missing_input`, `internal`

**Input**

```json
{
 "type": "object",
 "properties": {
  "name": {
   "type": "string"
  },
  "city": {
   "type": "string"
  },
  "country": {
   "type": "string"
  },
  "place_id": {
   "type": "string"
  },
  "website": {
   "type": "string"
  },
  "type": {
   "type": "string",
   "description": "the card's type, e.g. Seafood restaurant"
  },
  "what": {
   "type": "string",
   "description": "what they want, e.g. dinner"
  }
 },
 "required": [
  "name",
  "city"
 ],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "routes": {
   "type": "array"
  },
  "how": {
   "type": "string"
  }
 }
}
```

## Austen

### `choose_offer`

Put another flight into the trip, replacing the flight on that leg. Returns the new total. Give its offer_id, OR describe one of the trip's options (the proposal's flight cards, a search's): its leg and the airline and/or departure time a tap or the person named ("the British Airways flight out at 08:30"), or pick cheapest/fastest.

**Errors:** `no_trip`, `offer_not_in_trip`, `not_choosable`, `missing_input`, `internal` · **idempotent** (`idempotency_key` required)

**Input**

```json
{
 "type": "object",
 "properties": {
  "offer_id": {
   "type": "string"
  },
  "leg": {
   "enum": [
    "out",
    "back"
   ]
  },
  "airline": {
   "type": "string"
  },
  "departs": {
   "type": "string",
   "description": "HH:MM"
  },
  "pick": {
   "enum": [
    "cheapest",
    "fastest"
   ]
  },
  "idempotency_key": {
   "type": "string",
   "minLength": 8,
   "maxLength": 128,
   "description": "Idempotency key: the same key returns the first result."
  }
 },
 "required": [
  "idempotency_key"
 ],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "chosen": {
   "type": "object",
   "properties": {
    "offer_id": {
     "type": "string"
    },
    "airline": {
     "type": "string"
    },
    "flights": {
     "type": "string"
    },
    "from": {
     "type": "string"
    },
    "to": {
     "type": "string"
    },
    "departs": {
     "type": "string"
    },
    "arrives": {
     "type": "string"
    },
    "stops": {
     "type": "integer"
    },
    "duration_minutes": {
     "type": "integer"
    },
    "price_eur": {
     "type": "number"
    },
    "test": {
     "const": true
    }
   }
  },
  "total_eur": {
   "type": "number"
  },
  "items": {
   "type": "integer"
  },
  "price_sources": {
   "type": "array",
   "items": {
    "type": "string"
   }
  }
 }
}
```

### `save_travellers`

Save the travellers the airline needs (asked once, kept on the account).

**Errors:** `missing_input`, `internal` · **idempotent** (`idempotency_key` required)

**Input**

```json
{
 "type": "object",
 "properties": {
  "travellers": {
   "type": "array",
   "items": {
    "type": "object",
    "properties": {
     "given_name": {
      "type": "string"
     },
     "family_name": {
      "type": "string"
     },
     "date_of_birth": {
      "type": "string",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
     },
     "title": {
      "enum": [
       "mr",
       "ms",
       "mrs",
       "miss",
       "dr"
      ]
     },
     "gender": {
      "enum": [
       "male",
       "female"
      ]
     }
    },
    "required": [
     "given_name",
     "family_name",
     "date_of_birth",
     "title"
    ]
   }
  },
  "idempotency_key": {
   "type": "string",
   "minLength": 8,
   "maxLength": 128,
   "description": "Idempotency key: the same key returns the first result."
  }
 },
 "required": [
  "travellers",
  "idempotency_key"
 ],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "saved": {
   "type": "integer"
  },
  "travellers_on_file": {
   "type": "integer"
  },
  "invalid": {
   "type": "array"
  }
 }
}
```

### `hold_booking`

The read-back before booking: every item re-checked and priced, the total, and the sha256 the yes binds to. No money moves; nothing is booked.

**Errors:** `no_trip`, `travellers_missing`, `not_bookable`, `airline_unreachable`, `store_unreachable`, `missing_input`, `internal` · **idempotent** (`idempotency_key` required)

**Input**

```json
{
 "type": "object",
 "properties": {
  "origin": {
   "type": "string"
  },
  "idempotency_key": {
   "type": "string",
   "minLength": 8,
   "maxLength": 128,
   "description": "Idempotency key: the same key returns the first result."
  }
 },
 "required": [
  "idempotency_key"
 ],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "read_back": {
   "type": "array"
  },
  "read_back_sha256": {
   "type": "string"
  },
  "total_eur": {
   "type": "number"
  }
 }
}
```

### `book`

After the person's explicit yes in THIS turn: one payment (Stripe TEST) for exactly the read-back they just heard (the last hold_booking, unless read_back_sha256 is given), sent to their phone. Nothing is booked until it is paid — get_status says when.

**Errors:** `no_explicit_yes`, `no_read_back`, `read_back_stale`, `read_back_changed`, `not_bookable`, `already_done`, `payments_unreachable`, `store_unreachable`, `missing_input`, `internal` · **idempotent** (`idempotency_key` required)

**Input**

```json
{
 "type": "object",
 "properties": {
  "read_back_sha256": {
   "type": "string"
  },
  "approval": {
   "type": "object",
   "properties": {
    "said": {
     "type": "string"
    }
   },
   "description": "the person's own words (filled by the caller from the real message)"
  },
  "idempotency_key": {
   "type": "string",
   "minLength": 8,
   "maxLength": 128,
   "description": "Idempotency key: the same key returns the first result."
  }
 },
 "required": [
  "idempotency_key"
 ],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "status": {
   "const": "awaiting_payment"
  },
  "booked": {
   "const": false
  }
 }
}
```

### `hold_venue`

Prepare a venue booking (a restaurant, a spa…) by its route: the ladder's own question first when it has one (status choose_route: ask it, then call again with the route they pick), else the read-back the yes binds to (status awaiting_yes: say it in a line and ask them to go ahead). A place that books only by a WhatsApp or Instagram message (status draft_message): read the drafted message and offer to send it to their phone — they send it; it is never booked until the place replies. Nothing is sent.

**Errors:** `read_failed`, `when_invalid`, `contact_missing`, `no_route`, `missing_input`, `internal` · **idempotent** (`idempotency_key` required)

**Input**

```json
{
 "type": "object",
 "properties": {
  "name": {
   "type": "string"
  },
  "city": {
   "type": "string"
  },
  "country": {
   "type": "string"
  },
  "place_id": {
   "type": "string"
  },
  "website": {
   "type": "string"
  },
  "type": {
   "type": "string",
   "description": "the card's type, e.g. Seafood restaurant"
  },
  "what": {
   "type": "string",
   "description": "e.g. dinner, a table, a massage"
  },
  "day": {
   "type": "string",
   "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
  },
  "time": {
   "type": "string",
   "description": "HH:MM, the venue's local time"
  },
  "party": {
   "type": "integer",
   "minimum": 1,
   "maximum": 20
  },
  "route": {
   "enum": [
    "form",
    "page",
    "email",
    "call",
    "whatsapp",
    "instagram",
    "no"
   ],
   "description": "the route they chose (from choose_route)"
  },
  "idempotency_key": {
   "type": "string",
   "minLength": 8,
   "maxLength": 128,
   "description": "Idempotency key: the same key returns the first result."
  }
 },
 "required": [
  "name",
  "city",
  "day",
  "time",
  "party",
  "idempotency_key"
 ],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "status": {
   "type": "string"
  },
  "read_back": {
   "type": "array"
  }
 }
}
```

### `book_venue`

After the person's explicit yes in THIS turn, to what hold_venue read back in an earlier turn: the booking, by its route — their form (any human step goes to their phone as Tap to finish), the platform's page to their phone, the email, or the call. Its status says what's true: confirmed only on the venue's own confirmation.

**Errors:** `no_explicit_yes`, `nothing_held`, `read_back_first`, `read_back_stale`, `not_sent`, `already_done`, `store_unreachable`, `missing_input`, `internal` · **idempotent** (`idempotency_key` required)

**Input**

```json
{
 "type": "object",
 "properties": {
  "approval": {
   "type": "object",
   "properties": {
    "said": {
     "type": "string"
    }
   }
  },
  "idempotency_key": {
   "type": "string",
   "minLength": 8,
   "maxLength": 128,
   "description": "Idempotency key: the same key returns the first result."
  }
 },
 "required": [
  "idempotency_key"
 ],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "status": {
   "type": "string"
  }
 }
}
```

### `cancel_venue`

Cancel a venue booking, back the way it was made. First call: the read-back (say it, ask); after their explicit yes in a LATER turn, call again to send it.

**Errors:** `booking_unknown`, `no_explicit_yes`, `not_cancelled`, `already_done`, `store_unreachable`, `missing_input`, `internal` · **idempotent** (`idempotency_key` required)

**Input**

```json
{
 "type": "object",
 "properties": {
  "trip_item_id": {
   "type": "string"
  },
  "venue": {
   "type": "string"
  },
  "approval": {
   "type": "object",
   "properties": {
    "said": {
     "type": "string"
    }
   }
  },
  "idempotency_key": {
   "type": "string",
   "minLength": 8,
   "maxLength": 128,
   "description": "Idempotency key: the same key returns the first result."
  }
 },
 "required": [
  "idempotency_key"
 ],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "status": {
   "type": "string"
  }
 }
}
```

## Pacioli

### `get_status`

What is booked, failed, cancelled or awaiting payment — the ONLY source for booked/paid/confirmed.

**Errors:** `no_trip`, `missing_input`, `internal`

**Input**

```json
{
 "type": "object",
 "properties": {},
 "required": [],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "booked": {
   "type": "array"
  },
  "anything_booked": {
   "type": "boolean"
  }
 }
}
```

### `get_trip`

The trip as it stands: days and stays, the chosen flights, each item's state.

**Errors:** `no_trip`, `missing_input`, `internal`

**Input**

```json
{
 "type": "object",
 "properties": {},
 "required": [],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object"
}
```

### `get_total`

The whole trip's total from the basket (what booking would charge).

**Errors:** `no_trip`, `missing_input`, `internal`

**Input**

```json
{
 "type": "object",
 "properties": {},
 "required": [],
 "additionalProperties": false
}
```

**Output** (`result`)

```json
{
 "type": "object",
 "properties": {
  "total_eur": {
   "type": "number"
  },
  "items": {
   "type": "integer"
  },
  "price_sources": {
   "type": "array",
   "items": {
    "type": "string"
   }
  }
 }
}
```

## Error envelope

```json
{
 "type": "object",
 "properties": {
  "ok": {
   "const": false
  },
  "error": {
   "type": "object",
   "properties": {
    "code": {
     "type": "string"
    },
    "message": {
     "type": "string"
    }
   },
   "required": [
    "code",
    "message"
   ]
  }
 }
}
```
