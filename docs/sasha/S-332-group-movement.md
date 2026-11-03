# Sasha 332 · Group movement v1: the group, the list upload, the master list, price limits

Tyler, 3 Nov 20:30–20:55: a company (an SME, for a beta demo) moves 20 workers to Madrid. Not in this ticket: the vault is 333, booking
with the vault's data plus swap and cancel is CR 163, and the invoice is 334.

## Root test (written before the code)

### 1. One trip record per worker

Each worker has ONE trip of their own (`trips`, owned by the organiser).
- Their planned flights and hotel are that trip's own rows (`trip_basket_items`), exactly as any trip holds what was found today.
- Once booked, they become `trip_items`.

`group_members.trip_id` points each worker at that trip.

### 2. The master list is a view

`groups.view()` reads each worker's trip NOW (transport, hotel, price, limit, status) every time the list is read. The group's tables
hold no price, transport, hotel or status: never a second copy (a test holds it).

### 3. One place for the group's rules

`group_movements.rules`:
- price limits per grade (`by_grade`) and per person (`by_member`);
- one reader, `limit_for`, used by the planner and the master list both.

### PATCH check

None.
- The upload reads a csv, xlsx, photo or text into ONE member shape (`members_from`).
- A photo goes through the same text reader after the model copies the table (cells it can't read are left empty and asked about —
  never guessed).

### Whole class impossible

- **A worker's plan can't live anywhere but their trip:** the planner writes only `basket.suggest` on that trip.
- **A status can't be stored stale:** it is computed from the trip's rows on every read.
- **A limit can't be read from a second place.**
- **Planning can't book:** a test holds that no choose, hold, booked or order call exists in the module.
- **An unclear row can't be guessed:** it isn't added, and it is in ONE batch question with every other unclear row.

## What it does

1. **The group (company) and its movement:** an organiser (the account), a destination, dates, ONE hotel area. Agent tool: `group_start`.
2. **The upload:**
   - On the master list page (`/group`): a .csv or .xlsx file, a photo of the list, or pasted text.
   - In the chat (S2 or WhatsApp): pasted or typed text (`group_upload`).
   - Columns are read by their headers (English and Spanish); with no header, the order is name, home city, out, back, grade.
   - A missing date takes the movement's date.
   - A row with an unreadable name, city or date, back before out, a grade the limits don't know, or a name listed twice: ONE batch
     question listing them all.
3. **Price limits** (`group_limits`): per grade (worker: flight ≤ €600 return, hotel ≤ €110/night; supervisor: flight ≤ €900) or per
   person by name.
4. **The master list:**
   - The `/group` page: one row per worker — transport, hotel, price, limit, status — refreshed every 6 s.
   - A WhatsApp or chat summary (`group_list`).
   - The statuses: not planned, planned, needs vault, over limit, booked, cancelled.
5. **One by one** (`group_plan`, in the background): each worker's cheapest flight out and back (Duffel TEST) and the hotel near the
   area (a per-night estimate).
   - **Over the limit:** flagged on the trip's own row, never booked.
   - **A flight with no passport on file:** "needs vault". The vault is 333; until it exists, every planned flight needs it.

## Not in v1, said plainly

- **A file or photo sent ON WhatsApp:** on WhatsApp the list is pasted or typed; files and photos go in on the page.
- **Booking (CR 163), the vault (333) and the invoice (334).**
- **Real searches:** the proof used fixture prices. A live `group_plan` runs Duffel TEST searches, 2 per worker, which takes minutes for
  20 people.
