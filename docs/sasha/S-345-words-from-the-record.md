# Sasha 345 · Her words come from the record (the SME demo on S2)

## Found (Tyler's dry run, 5 Nov 17:50–18:09 Madrid, S2)

Sasha's request logs carry no turn content. The S2 chat store is a SQLite file inside the Railway container, which I can't reach. So the dry run is read from the STORED RECORD, sasha-prod `group_movements`, plus the code.

- **Six movements in four minutes** for the same account: "Jean Incorporated → London", 17–21 Nov, near Canary Wharf, each one new. The account is the shared DEMO account `11111111-…`, an anonymous S2 visitor, not a signed-in one. `group_start` made a new movement every call, so the limits were set on one movement while the list was read from another.
- **The limits as stored** (latest movement): €500 a night for three members and €250 for two. **€400 was never stored.** Nowhere in the record is there a "729" or a dollar figure. Her "$729" was her own figure, and the reply guard let it out because it read only € figures.
- **Planning DID happen (corrected, Tyler):** planning runs on Sasha's own Duffel search (`groups._quote`), not through AgAPI, so the sandbox's logs prove nothing about it. The group's own record shows all 5 workers of the latest movement planned, 3 trip rows each, 17:03:49–17:04:09, right after the limits were saved. That is what Tyler sees on /group. Still, `group_limits` itself started nothing; planning waited for her to call `group_plan`.
- **No card:** `group_list` rendered "inline", words only. Her "here's the list" went out over nothing.
- **Same class as 051:** `group_movements.rules` was stored as a JSON string (the pool's jsonb codec plus `json.dumps(...)::jsonb`).

## Root test (written first)

**One source:** the group's stored record. The limits are what `group_movements.rules` holds, read back after the save. The master list is the view of each worker's trip, which follows AgAPI's booking record (Sasha 340).

**Two deciders is a PATCH:** a reply that states a number or promises a card the reply doesn't carry. So:

1. **`group_limits` says what was SAVED.** It reads back from storage, in euros, per grade and per person by name (`groups.limits_said`): "Saved: worker: €250 a night; executive: €400 a night." It then STARTS planning when the list is in, as the organiser's next step: "I'm planning all 5 now…". It re-plans after a limits change, because each worker's over-limit flags are stamped at plan time and must follow the new limits.
2. **`group_list` always carries the list:** the master-list card (S2 kind `group_list`: its rows, the counts, "Open the master list" → /group). With nothing planned it says so plainly: "Nobody is planned yet — 5 on the list, not planned." On WhatsApp, the same in lines.
3. **The guard, before anything is sent** (`sasha.guard_check`):
   - a figure in ANY currency ($, £, USD, GBP) must be a tool's, in THAT currency;
   - "here's the list / the list is below / on your screen" goes out only when a card reached the screen this turn (`voice.promises_card`). Otherwise the sentence goes and she says what's missing.
4. **One movement per trip:** `group_start` with the same company, destination and dates as their latest movement returns THAT one.
5. **`rules` is stored as an object** (`$3::text::jsonb`); 052 repairs the old rows.

**The whole class** (`tests/test_s345_words_from_the_record.py`): Tyler's words through the real tools:

- the read-back is the stored figures, in €;
- planning starts;
- the list comes as a card, or says nobody is planned;
- "$729" and "here's the list" over nothing are both caught;
- six starts make one movement;
- `rules` round-trips as an object on real Postgres.
