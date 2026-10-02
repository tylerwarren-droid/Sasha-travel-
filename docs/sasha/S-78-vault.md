# S-78 · Vault: a per-guest encrypted store for third-party accesses — build-ready

*EU session, 2 Oct 2026 (EU 113). For the Sasha tab, which owns this repo's git. Read-only: code read at `7c58986`.
Nothing was run or changed.*

> **Renumbered S-78** (founder, EU 114). It was drafted as "S-76 Vault", but S-76 is `S-76-AD-inbound-fix.md`.
>
> **Founder defaults (EU 114):**
> - **V-1:** Google Cloud KMS.
> - **V-2:** standing permission **off**.
> - **V-3:** plaintext export **off**.
> - **V-4:** a DPIA before **any** health item.

**What it is:** a guest's own logins and accesses that Sasha may need to act for them: a grocery account, a clinic
portal, an airline or hotel loyalty login, a membership number. They're stored so that:
- **the AI model never sees them**;
- they're decrypted **only inside the executing action, at the moment of use**;
- **every use is logged and shown to the guest**;
- one tap revokes them.

**What it isn't:**
- **Not a payment store.** Card numbers are never stored (§8).
- **Not a way to skip the guest's yes.** A secret is used only under that booking's approval (§5).

---

## 0. What exists today (so nothing is assumed)

- **No secret storage or encryption helpers** exist in Sasha's code. All secrets are environment variables.
  - The Ed25519 signer's seed is `SASHA_BOOKING_TASK_SIGNING_KEY`, loaded at `booking_signer/keys.py:71`.
  - `BLAND_ENCRYPTED_KEY` is an env value passed to Bland, not local crypto.
- **The crypto library is already a dependency:** `backend/requirements*.txt` pins **`cryptography==43.0.3`**
  (`AESGCM` and key wrapping are available, so there's nothing new to vet).
- **Executors that could use a login:** none today.
  - The rungs are the phone (Bland, `calls.py`), forms (`form_rung.py`, `formfill.py`), email (`emailing.py`) and the
    slot link (`slot_link.py`, which the guest presses).
  - **No browser automation exists** (no Playwright, Browserbase or Selenium in code; only
    `booking_attempts.browserbase_session_id` in `backend/migrations/001_initial_schema.sql`).
  - **So the vault can be built and filled before anything can use it.** The first consumer is a separate ticket
    (§11, step 9).
- **Where the model is called:** `run_general` (`backend/app/services/conductor.py:819–845`) sends
  `system = general_prompt + …` and **the full conversation history** every turn.
  - ⚠ **So a guest who types a password into the chat today sends it to the model, and into stored history.** §4 closes
    that before the vault exists.
- **Database:** Postgres on Supabase via asyncpg (`booking_signer/store.py:181–189`). Booking tables run "RLS on, no
  policies (backend only)" (`015_guest_contacts.sql:3`). The latest migration is `019_inbound_email.sql`; S-75 drafts
  `020`, so this is **`021`**.

---

## 1. The rules (each one is enforced in code, not policy)

| # | Rule | Enforced by |
|---|---|---|
| R1 | Secrets are encrypted with a per-item data key; the data key is wrapped by a key **outside the database** | §2 envelope; the DB holds only ciphertext and the wrapped key |
| R2 | **The AI model never receives a secret** | §4: the model sees a handle and a label only; a chat/WhatsApp input guard; an output scrubber |
| R3 | A secret is decrypted only inside the executing action, at the moment of use, and dropped after | §5 `vault.use()` is a context manager, the only decrypt path |
| R4 | **Never used without that booking's yes** | §5: `use()` requires an approval whose read-back **names the access** |
| R5 | Every use is logged and shown to the guest | §6 `vault_uses`, the vault page and the receipt line |
| R6 | One-tap revoke | §7: crypto-shred plus a provider-side revoke where one exists |
| R7 | Prefer OAuth, passkeys and app passwords over raw passwords | §3: the kinds, ordered, and the UI offers the strongest the provider supports first |
| R8 | **Never store card numbers** | §8: a Luhn guard on every vault field; payments are Stripe-tokenised |
| R9 | GDPR deletion and export | §9 |

---

## 2. Envelope encryption

```
secret ──AES-256-GCM(DEK, nonce, aad=account_id‖item_id‖kind)──► ciphertext      (DB)
DEK  (random 32 bytes per item, per write) ──KMS.Encrypt(KEK)──► wrapped_dek     (DB)
KEK  never leaves the KMS                                                         (outside the DB)
```

- **The KEK lives in a cloud KMS, not an env var.** **V-1 decided (EU 114): Google Cloud KMS.** Either way,
  Railway's backend holds only a narrowly-scoped service credential that can Encrypt/Decrypt with that one key.
  - An env-var KEK on the same host as the database credentials would make "outside the database" true in letter only:
    one host compromise would yield both. So it's **not** used, even for phase 1.
  - **Sandbox/dev** may use a local KEK file, and the code refuses it when `ENV=production`.
- **The AAD binds** the ciphertext to its account, item and kind, so a row copied to another account or item fails
  to decrypt.
- **Nonce:** 96-bit random per encryption. A re-save gets a new DEK (no nonce reuse across a DEK's life).
- **Rotation:** KMS key versions. A rewrap job decrypts each `wrapped_dek` with the old version and encrypts it with the
  new one (the DEK and ciphertext are untouched), logged in `vault_events`.
- **Where:** a new `backend/booking_signer/vault/crypto.py` (`seal(account, item, kind, plaintext) -> (ct, nonce,
  wrapped_dek, kek_version)`, `open_(…) -> bytes`), using `cryptography.hazmat.primitives.ciphers.aead.AESGCM`, plus a
  `kms.py` adapter with one interface and two backends (cloud, local-dev).

---

## 3. What can be stored (strongest first)

| Kind | Stored | Used how | Notes |
|---|---|---|---|
| `oauth` | refresh token (+ scopes, provider) | token exchange at use time; access token in memory only | **Preferred.** Revocable at the provider. Few grocery or clinic sites offer it |
| `app_password` | a site-issued, scoped password | as a password, but revocable at the provider | Preferred over the main password where offered |
| `passkey` | **nothing secret.** A passkey is device-bound and can't be used by a server | the **guest** presses (the BACKLOG item 1 `guest` value) | Stored only as the fact "this provider uses a passkey: the guest signs in". Honest: Sasha can't use it |
| `password` | username + password | the executor types it at the moment of use | **Last resort.** The UI says so: *"If {site} offers an app password or 'sign in with Google', use that instead. It can be revoked without changing your password."* |
| `identifier` | a non-secret-ish number (loyalty number, membership ID, *tarjeta sanitaria* CIP: see S-77) | pasted into a form | Still encrypted (it identifies a person). For a health identifier, see §9.3 |

Each item carries: `provider` (the site's domain), `label` (the guest's words, e.g. "Mercadona login"), `kind`,
`created_at`, `last_used_at`, and `use_policy` (§5: `ask_every_time`, the default and only option in phase 1).

---

## 4. The model never sees a secret (R2)

1. **What the model sees:** only a **handle** and **label**, e.g. `vault:9f3c… "Mercadona login" (password)`, through a
   capability fact appended in `run_general` (`conductor.py:819–845`). Never the value, a partial value, or the
   username.
2. **Input guard (before the model, and before storage).** Secrets must never arrive by chat.
   - In `app/api/conductor.py`, before `user_message=body.message` is passed on (`:121`, `:134`), and before
     `chat_store.save_turn`, run `vault/guard.py: looks_like_secret(message)`. It fires on:
     - "password is/:", "pwd", "contraseña", "PIN", a token-shaped string (≥20 chars mixed class, no spaces), or a Luhn
       13–19 digit run (R8).
   - On a hit, the turn is **not stored and not sent to the model.** The guest gets *"Please don't type passwords
     here. Add it in your Vault instead: {link}. I've not kept what you typed."*
   - The same guard runs in S-75's `guest_whatsapp.dispatch` before `conduct()`.
3. **Output scrubber.** Anything an executor returns (transcripts, form answer pages, error text) passes through
   `vault/scrub.py` before it's logged, stored or shown to a model. It replaces any decrypted value used in that action
   with `[vault:label]`. The decrypted values are known to the action (§5), so the scrub is exact, not pattern-guessing.
4. **Test:** a fixture conversation where the guest types "my Mercadona password is hunter2!": the model mock is **not
   called**, `chat_store` has **no** turn containing `hunter2`, and the reply is the fixed sentence.

---

## 5. Use only inside the action, only under that booking's yes (R3, R4)

```python
async with vault.use(account_id, item_id, approval=approval_row, action=action_ref) as secret:
    await executor.sign_in(provider, secret)        # secret: bytes / a small dataclass, in memory only
# on exit: buffers overwritten (best effort in Python), handles closed, vault_uses row completed
```

- **`vault.use` is the only decrypt path.** `open_()` is private to the module, and a test asserts no other module
  imports it.
- **The approval check:**
  - `approval_row` is the existing approval jsonb on the booking row: `booking_calls.approval` (`003:54`),
    `booking_emails.approval` (`004:51`) or `booking_forms.approval` (`018:27`). It is `{by, how, said, at,
    read_back_sha256, …}` (`call_routes.py:533`), and must be **≤ 15 min old** (`APPROVAL_WINDOW`, `:48`).
  - **The read-back the guest approved must name the access.** The read-back gains a line, *"I'll sign in to {provider}
    with your saved {label}."*, built from the vault item, so its `read_back_sha256` covers it.
  - `use()` recomputes the line from the item and checks that it's in the approved read-back, so an approval for a
    plain booking can't unlock a login.
  - **One approval, one use:** the `vault_uses` row is claimed `pending → in_use` atomically before decrypting, as
    `003:37`'s *"ONE CALL PER APPROVAL, EVER"* does for calls.
- **No standing permission** in phase 1 ("Sasha may always use my Mercadona login"). **V-2 decided (EU 114): off.** Every use needs that
  booking's yes.

---

## 6. Every use logged and shown (R5)

- `vault_uses`: `id, account_id, item_id, action_kind, action_ref (call/form/email id), approval_sha256, status
  (pending|in_use|done|failed), started_at, ended_at, outcome_words`. It's append-only in spirit: no deletes except the
  account cascade.
- `vault_events`: created, updated, revoked, rewrapped, exported, deleted, with who and when.
- **Shown to the guest:**
  - the **Vault page** (`frontend/app/vault/page.tsx`, new): each item with *"Last used {date}, for {booking}"* and its
    full use history;
  - **the booking receipt** (`guest_receipt.py`): a line *"Used your saved {label} once, to sign in to {provider}."*;
  - on WhatsApp (S-75), the same line in the result message.

---

## 7. One-tap revoke (R6)

- **Revoke** sets `revoked_at`, **deletes `wrapped_dek` and `ciphertext`** (crypto-shred: with the wrapped DEK gone,
  the ciphertext is unrecoverable even from backups once they age out), writes `vault_events`, and **cancels any
  `pending` use.**
- **An `oauth` item:** also call the provider's revocation endpoint where it exists, and say whether it succeeded.
- **A `password` / `app_password` item:** the page says plainly *"Sasha has deleted her copy. To be sure nobody can use
  it, change the password at {provider}."* We can't revoke a password at the provider, and it says so.
- **"Revoke everything"** is one button.

---

## 8. Never store card numbers (R8)

- **Every vault write** runs a Luhn check over each 13–19 digit run (spaces and dashes stripped) in every field. A hit
  is **refused**: *"Card numbers can't be saved here. Payments go through Stripe, which never shows us your card."*
- **Payment** stays **Stripe** (`app/api/payments.py`, Checkout at `:261`, webhook verification at `:380–392`). Where a
  booking needs a card on file, use a Stripe **SetupIntent / saved PaymentMethod** (`pm_…`): we hold the token, never
  the PAN.
  - The "saved card" today is a mock (`conductor.py:643`, `SASHA_SAVED_CARD_LAST4`). Replacing it is outside S-78.
- The booking executors already refuse cards (`calls.py:392`, *"Never accept a deposit, fee, … or card (you have none)"*;
  `:431`). The vault doesn't change that.

---

## 9. GDPR (R9)

1. **Deletion:** a single **`DELETE /api/booking/account/data`**. None exists today; the only deletion is
   `DELETE /api/booking/contact`, `contacts.py:141`. It:
   - crypto-shreds every vault item;
   - deletes `vault_uses` / `vault_events` beyond what the law requires us to keep;
   - removes `guest_channels` (S-75) and `guest_contacts`;
   - and writes one `retention_log` line (S-53).
   - Re-auth is required.
   - S-75 §9 relies on this.
2. **Export:** `GET /api/booking/account/export` returns JSON of the guest's data: reservations, consents, vault
   **metadata and use history**. **V-3 decided (EU 114): secrets are NOT exported in plaintext.** Export is **metadata only**, with a per-item "reveal"
   behind re-auth on the Vault page.
3. **Health data (Art. 9).** A **clinic-portal login** gives access to health data, and a *tarjeta sanitaria* number
   identifies a patient. Storing and using them is processing **special-category data**, which needs **explicit
   consent (Art. 9(2)(a))** recorded per item (wording versioned and hashed, as `015`'s consent fields are). A **DPIA**
   should precede the first clinic item (**V-4 decided, EU 114: a DPIA before ANY health item**). The privacy notice (S-51) needs a vault section
   either way.
4. **Lawful basis** for non-health items: contract (Art. 6(1)(b)), as the privacy page states for bookings
   (`frontend/app/sasha-privacy/page.tsx:41`).

---

## 10. Migration `021_vault.sql` (draft, NOT applied, for the founder's go)

```sql
-- Preview: expect NULL twice
select to_regclass('public.vault_items'), to_regclass('public.vault_uses');
create table public.vault_items (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references auth.users(id) on delete cascade,
  provider text not null, label text not null,
  kind text not null check (kind in ('oauth','app_password','passkey','password','identifier')),
  ciphertext bytea, nonce bytea, wrapped_dek bytea, kek_version text,   -- null for 'passkey' and after revoke
  special_category boolean not null default false,                       -- health etc. (§9.3)
  consent_at timestamptz, consent_wording_version text, consent_text_sha256 text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  last_used_at timestamptz, revoked_at timestamptz,
  constraint sealed_or_revoked check (kind = 'passkey' or revoked_at is not null or (ciphertext is not null and wrapped_dek is not null)),
  constraint special_needs_consent check (not special_category or consent_at is not null)
);
create table public.vault_uses (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references auth.users(id) on delete cascade,
  item_id uuid not null references public.vault_items(id) on delete cascade,
  action_kind text not null, action_ref text not null, approval_sha256 text not null,
  status text not null check (status in ('pending','in_use','done','failed','cancelled')),
  started_at timestamptz not null default now(), ended_at timestamptz, outcome_words text
);
create unique index vault_uses_one_per_approval on public.vault_uses (item_id, approval_sha256);
create table public.vault_events (
  id bigserial primary key, account_id uuid not null references auth.users(id) on delete cascade,
  item_id uuid, event text not null, at timestamptz not null default now(), detail jsonb
);
alter table public.vault_items enable row level security;   -- backend only, no policies (as 015:3)
alter table public.vault_uses  enable row level security;
alter table public.vault_events enable row level security;
```

- **There's no policy that lets the browser read these tables.** The Vault page goes through backend routes that
  return metadata only.
- **Never `select ciphertext`** outside `vault/crypto.py`. A test greps the code for it.

---

## 11. Build steps, in order (each with its tests green)

1. **The input guard first (§4.2)**: chat and (when built) WhatsApp. It protects guests **today**, before any vault
   exists.
   - *Tests:* the hunter2 fixture (§4.4); a Luhn PAN typed in chat is refused and not stored.
2. **The KMS adapter + envelope crypto (§2)**, with the cloud backend on **Google Cloud KMS (V-1)**.
   - *Tests:* round-trip; a swapped AAD fails; a tampered ciphertext fails; the local-dev KEK is refused when
     `ENV=production`.
3. **Migration 021** (founder's go).
   - Verify with `information_schema` and `pg_constraint` that it applied as written.
4. **Vault API** (`/api/booking/vault`: list metadata, create, update, revoke, revoke-all), with the Luhn refusal on
   writes (R8).
   - *Tests:* create→list shows no secret; revoke shreds (`wrapped_dek is null`); a PAN is refused.
5. **The Vault page** (web), kinds ordered by R7, with the last-resort wording for passwords.
6. **`vault.use()` + approval binding (§5)** and `vault_uses` claim.
   - *Tests:*
     - a use with no approval, a stale one (>15 min), or one whose read-back lacks the access line → refused;
     - two uses of one approval → the second refused;
     - `open_` imported anywhere else → test fails.
7. **The scrubber (§4.3)** in every executor output path.
   - *Test:* a fixture executor echoing the secret → the stored transcript holds `[vault:label]`.
8. **GDPR endpoints (§9.1–9.2)**, plus the privacy-notice vault section and Art. 9 consent for special-category items.
9. **The first consumer**, a **separate ticket**. It needs a browser executor, which doesn't exist (§0). Before
   building it, read **each target site's terms and robots** (grocery chains and clinic portals often forbid automated
   access).
   - **⚠ Never from the founder's network** for any bot-protected host (TheFork incident, 30 Sept). Use an isolated
     egress.
   - Where a site forbids automation, the vault item is still useful: Sasha **prepares** and the guest presses (BACKLOG
     item 1, `guest`).

## Founder decisions

- **V-1: DECIDED (EU 114): Google Cloud KMS.** Required before step 2's production path.
- **V-2: DECIDED (EU 114): standing permission OFF.** Every use needs that booking's yes.
- **V-3: DECIDED (EU 114): plaintext export OFF.** Export is metadata and use history only; "reveal" stays per item behind re-auth on the Vault page.
- **V-4: DECIDED (EU 114): a DPIA before ANY health (special-category) item.** The vault refuses `special_category = true` until the DPIA is recorded: the vault API refuses a health item while the config `SASHA_VAULT_HEALTH_DPIA_REF` (the DPIA document's reference) is unset, and logs the refusal.
- **Numbering: DECIDED (EU 114): this is S-78.**

---

## Built, Sasha 102 (2 Oct 2026): steps 1–8 in code; step 9 stays a separate ticket

- **Step 1 (`267b71c`), the input guard:** `vault/guard.py`, first in `conduct()`, in `save_turn` and in the voice log
  line. Earlier history lines are blanked too (the browser sends them back). The same guard runs on WhatsApp (S-75).
  - Proven live on 2 Oct: a fake password to the production conductor got the fixed reply, and nothing came back in the
    history.
- **Step 2, `vault/kms.py` + `vault/crypto.py`:**
  - AES-256-GCM per item, a fresh DEK and nonce on every write, and AAD = account‖item‖kind.
  - **Google Cloud KMS over its REST API** (V-1), with a service-account token the module signs itself (RS256, the
    pinned `cryptography`). No new dependency.
  - The local KEK file is for tests and dev only, and is refused when `ENV` or `RAILWAY_ENVIRONMENT_NAME` is
    `production`.
  - Neither configured: the vault is closed, and says so.
- **Step 3:** migration **021** is drafted (`sql/021_vault.sql`) and handed to chat to apply. Not applied by this tab.
- **Step 4, `vault/api.py`:**
  - list (metadata and use history only), create, update (reseal with a new DEK), revoke (crypto-shred and cancel
    pending uses), revoke-all;
  - R8: Luhn over every field, the site and the label included;
  - `oauth` is listed but **not offered**: no site is connected by sign-in;
  - V-4: a health item is refused while `SASHA_VAULT_HEALTH_DPIA_REF` is unset, then accepted only with the Art. 9
    consent (versioned and hashed).
- **Step 5:** `/vault` (founder-gated, like the booking page). Kinds are strongest first; there's the last-resort
  wording, revoke and revoke-all, the use history, the data download and delete-everything.
- **Step 6, `crypto.use()`, the only decrypt path:**
  - the approval must be ≤ 15 minutes old;
  - its hash must match the approved lines;
  - those lines must contain *"I'll sign in to {provider} with your saved {label}."*;
  - one use per approval (`vault_uses` unique, claimed before decrypting).
  - Tests fail if `_open` appears in any other module, or if a ciphertext is SELECTed anywhere but `crypto.py`.
- **Step 7, the scrubber:** `Secret.scrub()` inside each use replaces every value it opened with `[vault:label]`, and a
  failing action's error is stored scrubbed.
  - **There's no executor to wire it into yet** (§0): each consumer must pass its outputs through it. That is part of
    step 9's ticket.
- **Step 8, `vault/gdpr.py`:**
  - `DELETE /api/booking/account/data`: a typed "delete everything" **and** a sign-in within the last 10 minutes (the
    token's `amr`; the founder's session header is not a sign-in). It removes the vault, the WhatsApp link, codes and
    state, and the saved contact, with one `retention_log` line per table;
  - `GET /api/booking/account/export`: metadata only (V-3).
  - The privacy notice (EN/ES) gains the vault section, Google Cloud KMS as a processor, and the self-service
    delete/download line.
- **Not built, on purpose:**
  - **"Reveal" behind re-auth (V-3's per-item reveal).** It would be a second decrypt path beside `use()`, so it needs
    its own decision.
  - **§4.1's handle-and-label capability fact for the model, the read-back access line in the rungs, and the receipt
    line:** each belongs to the first consumer (step 9). Nothing can use a saved access until then, and the page says
    so.
- **⚠ Before the vault opens in production (V-1), the founder's part:**
  1. Create a Cloud KMS key (symmetric, encrypt/decrypt) and a service account allowed only
     `cloudkms.cryptoKeyEncrypterDecrypter` on that key.
  2. Set `SASHA_VAULT_KMS_KEY` (the key's resource name) and `SASHA_VAULT_GCP_SA_JSON` (the service account's JSON key)
     on Railway.
  - Until then, `/api/booking/health` reports `vault: {open: false}` and nothing can be saved.
