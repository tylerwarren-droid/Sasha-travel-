"""
Chat persistence — stores every conversation turn (user + Sasha) in a local SQLite DB.

Why SQLite: it needs zero infrastructure (no DATABASE_URL, no running Postgres), so chat
history is captured reliably for the demo out of the box. All writes run in a worker thread
(`asyncio.to_thread`) because sqlite3 is synchronous — calling it directly in an async handler
would block the FastAPI event loop and stall other turns. Writes are best-effort: a DB failure
must never break a live conversation.

Single-user demo: there is one hardcoded user (Jon Peters). When a real auth flow lands,
swap `DEMO_USER_*` for the authenticated principal and pass a real user_id into save_turn().
To move to Postgres later, this module is the only thing to reimplement (the API talks to it,
not to sqlite directly).
"""

import asyncio
import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

# backend/app/services/chat_store.py -> backend/
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.getenv("CHAT_DB_PATH", os.path.join(_BACKEND_ROOT, "sasha_chats.db"))

# The one hardcoded demo user (no auth flow yet).
DEMO_USER_ID = "11111111-1111-4111-8111-111111111111"
DEMO_USER_EMAIL = "jon@kanoe.ai"
DEMO_USER_NAME = "Jon Peters"

_inited = False


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # concurrent reads while writing
    return conn


def _init() -> None:
    global _inited
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id           TEXT PRIMARY KEY,
                email        TEXT UNIQUE,
                display_name TEXT,
                created_at   TEXT
            );
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id         TEXT PRIMARY KEY,
                user_id    TEXT,
                title      TEXT,
                language   TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT,
                user_id     TEXT,
                role        TEXT,
                content     TEXT,
                intents     TEXT,
                booking_ref TEXT,
                created_at  TEXT
            );
            -- Every itinerary Sasha actually builds. This is the server's record of what a
            -- trip IS and what it COSTS. Without it, "is there a plan?" could only be guessed
            -- from Sasha's own words, and a checkout amount could only be taken on trust from
            -- the browser. Both were real bugs.
            CREATE TABLE IF NOT EXISTS itineraries (
                id         TEXT PRIMARY KEY,
                session_id TEXT,
                user_id    TEXT,
                title      TEXT,
                total_usd  REAL,
                payload    TEXT,
                created_at TEXT
            );
            -- One row per Checkout attempt, written BEFORE the guest is sent to Stripe, so the
            -- amount and trip are pinned server-side and the return leg has something
            -- authoritative to verify against.
            CREATE TABLE IF NOT EXISTS bookings (
                id                TEXT PRIMARY KEY,
                stripe_session_id TEXT UNIQUE,
                itinerary_id      TEXT,
                user_id           TEXT,
                amount_usd        REAL,
                status            TEXT,
                booking_ref       TEXT,
                created_at        TEXT,
                paid_at           TEXT
            );
            -- One row per bookable card (hotel / flight / cab / activity) Sasha surfaces. Same
            -- reason the itineraries table exists: an individual item's PRICE must be pinned
            -- server-side so checkout is priced from here, never from an amount the browser sends.
            -- Flight/cab fares are LLM-generated per turn and would be unverifiable otherwise.
            CREATE TABLE IF NOT EXISTS offers (
                id         TEXT PRIMARY KEY,
                session_id TEXT,
                user_id    TEXT,
                kind       TEXT,
                name       TEXT,
                label      TEXT,
                amount_usd REAL,
                currency   TEXT,
                meta       TEXT,
                created_at TEXT
            );
            -- Booking cards (restaurants / flights / cabs / hotels) surfaced in a session,
            -- cached by (session, kind, destination) so the SAME options persist across turns.
            -- Without this, every turn re-runs live web search and returns different places, so
            -- "book Cha Ca La Vong" fails to match the list the guest is looking at (which has
            -- since changed under them) — the exact confusion behind booking the wrong item.
            CREATE TABLE IF NOT EXISTS session_cards (
                session_id TEXT,
                kind       TEXT,
                dest       TEXT,
                payload    TEXT,
                created_at TEXT,
                PRIMARY KEY (session_id, kind, dest)
            );
            CREATE INDEX IF NOT EXISTS idx_msg_session  ON chat_messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_sess_user    ON chat_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_itin_session ON itineraries(session_id);
            CREATE INDEX IF NOT EXISTS idx_book_stripe  ON bookings(stripe_session_id);
            CREATE INDEX IF NOT EXISTS idx_offer_session ON offers(session_id);
            """
        )
        # Migration: an already-seeded DB predates the individual-item columns on `bookings`.
        # ADD COLUMN is a no-op error if the column exists, so try each independently.
        for col, decl in (("offer_id", "TEXT"), ("kind", "TEXT"), ("label", "TEXT")):
            try:
                conn.execute(f"ALTER TABLE bookings ADD COLUMN {col} {decl}")
            except Exception:
                pass
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, display_name, created_at) VALUES (?, ?, ?, ?)",
            (DEMO_USER_ID, DEMO_USER_EMAIL, DEMO_USER_NAME, datetime.utcnow().isoformat()),
        )
        # The row above is keyed by a fixed id, so INSERT OR IGNORE is a no-op on a DB that was
        # already seeded — an existing file would keep serving the previous demo identity after
        # DEMO_USER_NAME/EMAIL change here. Re-assert them so the seed always matches this file.
        conn.execute(
            "UPDATE users SET email = ?, display_name = ? WHERE id = ?",
            (DEMO_USER_EMAIL, DEMO_USER_NAME, DEMO_USER_ID),
        )
        conn.commit()
    _inited = True


def _ensure() -> None:
    if not _inited:
        _init()


def _save_turn(session_id, user_id, user_message, assistant_response, intents, booking_ref, language, title) -> None:
    _ensure()
    now = datetime.utcnow().isoformat()
    with _connect() as conn:
        # Create the session on its first turn; title it from the opening user message.
        conn.execute(
            "INSERT OR IGNORE INTO chat_sessions (id, user_id, title, language, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, user_id, (title or "New chat")[:80], language or "en", now, now),
        )
        conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        conn.execute(
            "INSERT INTO chat_messages (session_id, user_id, role, content, intents, booking_ref, created_at) "
            "VALUES (?, ?, 'user', ?, NULL, NULL, ?)",
            (session_id, user_id, user_message, now),
        )
        conn.execute(
            "INSERT INTO chat_messages (session_id, user_id, role, content, intents, booking_ref, created_at) "
            "VALUES (?, ?, 'assistant', ?, ?, ?, ?)",
            (session_id, user_id, assistant_response, json.dumps(intents or []), booking_ref, now),
        )
        conn.commit()


def _list_sessions(user_id) -> list:
    _ensure()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT s.id, s.title, s.language, s.created_at, s.updated_at, "
            "       (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id) AS message_count "
            "FROM chat_sessions s WHERE s.user_id = ? ORDER BY s.updated_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def _get_messages(session_id) -> list:
    _ensure()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content, intents, booking_ref, created_at "
            "FROM chat_messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("intents"):
                try:
                    d["intents"] = json.loads(d["intents"])
                except Exception:
                    d["intents"] = []
            out.append(d)
        return out


def _save_itinerary(itinerary_id, session_id, user_id, title, total_usd, payload) -> None:
    _ensure()
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO itineraries (id, session_id, user_id, title, total_usd, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (itinerary_id, session_id, user_id, (title or "")[:200], float(total_usd or 0),
             json.dumps(payload or {}), datetime.utcnow().isoformat()),
        )
        conn.commit()


def _get_itinerary(itinerary_id) -> "Optional[dict]":
    _ensure()
    with _connect() as conn:
        r = conn.execute("SELECT * FROM itineraries WHERE id = ?", (itinerary_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        try:
            d["payload"] = json.loads(d["payload"] or "{}")
        except Exception:
            d["payload"] = {}
        return d


def _latest_itinerary_for_session(session_id) -> "Optional[dict]":
    _ensure()
    with _connect() as conn:
        r = conn.execute(
            "SELECT * FROM itineraries WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if not r:
            return None
        d = dict(r)
        try:
            d["payload"] = json.loads(d["payload"] or "{}")
        except Exception:
            d["payload"] = {}
        return d


def _create_booking(booking_id, stripe_session_id, itinerary_id, user_id, amount_usd,
                    offer_id=None, kind=None, label=None) -> None:
    _ensure()
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO bookings (id, stripe_session_id, itinerary_id, user_id, amount_usd, "
            "status, booking_ref, created_at, paid_at, offer_id, kind, label) "
            "VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?, NULL, ?, ?, ?)",
            (booking_id, stripe_session_id, itinerary_id, user_id, float(amount_usd or 0),
             datetime.utcnow().isoformat(), offer_id, kind, label),
        )
        conn.commit()


def _create_offer(offer_id, session_id, user_id, kind, name, label, amount_usd, currency, meta) -> None:
    _ensure()
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO offers (id, session_id, user_id, kind, name, label, amount_usd, "
            "currency, meta, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (offer_id, session_id, user_id, kind, name, label, float(amount_usd or 0),
             currency, json.dumps(meta or {}), datetime.utcnow().isoformat()),
        )
        conn.commit()


def _get_offer(offer_id) -> "Optional[dict]":
    _ensure()
    with _connect() as conn:
        r = conn.execute("SELECT * FROM offers WHERE id = ?", (offer_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        try:
            d["meta"] = json.loads(d.get("meta") or "{}")
        except Exception:
            d["meta"] = {}
        return d


def _save_session_card(session_id, kind, dest, payload) -> None:
    _ensure()
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO session_cards (session_id, kind, dest, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, kind, (dest or "").lower(), json.dumps(payload), datetime.utcnow().isoformat()),
        )
        conn.commit()


def _get_session_card(session_id, kind, dest):
    _ensure()
    with _connect() as conn:
        r = conn.execute(
            "SELECT payload FROM session_cards WHERE session_id = ? AND kind = ? AND dest = ?",
            (session_id, kind, (dest or "").lower()),
        ).fetchone()
        if not r:
            return None
        try:
            return json.loads(r["payload"])
        except Exception:
            return None


def _clear_session_cards(session_id, kind=None) -> None:
    _ensure()
    with _connect() as conn:
        if kind:
            conn.execute("DELETE FROM session_cards WHERE session_id = ? AND kind = ?",
                         (session_id, kind))
        else:
            conn.execute("DELETE FROM session_cards WHERE session_id = ?", (session_id,))
        conn.commit()


def _get_booking_by_stripe(stripe_session_id) -> "Optional[dict]":
    _ensure()
    with _connect() as conn:
        r = conn.execute(
            "SELECT * FROM bookings WHERE stripe_session_id = ?", (stripe_session_id,)
        ).fetchone()
        return dict(r) if r else None


def _mark_booking_paid(stripe_session_id, booking_ref) -> "Optional[dict]":
    """Flip a booking to paid and assign its reference — idempotently.

    Stripe can tell us about the same payment twice (the redirect AND the webhook, or a webhook
    retry). Only the first call assigns a ref; later calls return the existing row, so a guest
    can never end up with two references for one trip.
    """
    _ensure()
    with _connect() as conn:
        r = conn.execute(
            "SELECT * FROM bookings WHERE stripe_session_id = ?", (stripe_session_id,)
        ).fetchone()
        if not r:
            return None
        row = dict(r)
        if row.get("status") == "paid" and row.get("booking_ref"):
            return row
        conn.execute(
            "UPDATE bookings SET status = 'paid', booking_ref = ?, paid_at = ? WHERE stripe_session_id = ?",
            (booking_ref, datetime.utcnow().isoformat(), stripe_session_id),
        )
        conn.commit()
        r2 = conn.execute(
            "SELECT * FROM bookings WHERE stripe_session_id = ?", (stripe_session_id,)
        ).fetchone()
        return dict(r2) if r2 else None


def _list_booked_trips(user_id) -> list:
    """Trips this guest has actually paid for, newest first — the real 'where you've been'."""
    _ensure()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT b.booking_ref, b.amount_usd, b.paid_at, i.title, i.payload "
            "FROM bookings b JOIN itineraries i ON i.id = b.itinerary_id "
            "WHERE b.user_id = ? AND b.status = 'paid' ORDER BY b.paid_at DESC",
            (user_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d["payload"] or "{}")
            except Exception:
                d["payload"] = {}
            out.append(d)
        return out


# ── Async wrappers (never raise on write; reads may raise and are caught by the API) ──

async def init_db() -> None:
    await asyncio.to_thread(_init)


async def save_itinerary(itinerary_id, session_id, user_id, title, total_usd, payload) -> None:
    try:
        await asyncio.to_thread(_save_itinerary, itinerary_id, session_id, user_id,
                                title, total_usd, payload)
    except Exception as e:
        print(f"[chat_store] save_itinerary failed (non-fatal): {e}")


async def get_itinerary(itinerary_id):
    return await asyncio.to_thread(_get_itinerary, itinerary_id)


async def latest_itinerary_for_session(session_id):
    try:
        return await asyncio.to_thread(_latest_itinerary_for_session, session_id)
    except Exception as e:
        print(f"[chat_store] latest_itinerary_for_session failed (non-fatal): {e}")
        return None


async def create_booking(booking_id, stripe_session_id, itinerary_id, user_id, amount_usd,
                         offer_id=None, kind=None, label=None) -> None:
    await asyncio.to_thread(_create_booking, booking_id, stripe_session_id,
                            itinerary_id, user_id, amount_usd, offer_id, kind, label)


async def create_offer(offer_id, session_id, user_id, kind, name, label, amount_usd,
                       currency="usd", meta=None) -> None:
    try:
        await asyncio.to_thread(_create_offer, offer_id, session_id, user_id, kind, name,
                                label, amount_usd, currency, meta)
    except Exception as e:
        print(f"[chat_store] create_offer failed (non-fatal): {e}")


async def get_offer(offer_id):
    return await asyncio.to_thread(_get_offer, offer_id)


async def save_session_card(session_id, kind, dest, payload) -> None:
    try:
        await asyncio.to_thread(_save_session_card, session_id, kind, dest, payload)
    except Exception as e:
        print(f"[chat_store] save_session_card failed (non-fatal): {e}")


async def get_session_card(session_id, kind, dest):
    try:
        return await asyncio.to_thread(_get_session_card, session_id, kind, dest)
    except Exception as e:
        print(f"[chat_store] get_session_card failed (non-fatal): {e}")
        return None


async def clear_session_cards(session_id, kind=None) -> None:
    try:
        await asyncio.to_thread(_clear_session_cards, session_id, kind)
    except Exception as e:
        print(f"[chat_store] clear_session_cards failed (non-fatal): {e}")


async def get_booking_by_stripe(stripe_session_id):
    return await asyncio.to_thread(_get_booking_by_stripe, stripe_session_id)


async def mark_booking_paid(stripe_session_id, booking_ref):
    return await asyncio.to_thread(_mark_booking_paid, stripe_session_id, booking_ref)


async def list_booked_trips(user_id=DEMO_USER_ID) -> list:
    try:
        return await asyncio.to_thread(_list_booked_trips, user_id)
    except Exception as e:
        print(f"[chat_store] list_booked_trips failed (non-fatal): {e}")
        return []


async def save_turn(session_id, user_id, user_message, assistant_response,
                    intents=None, booking_ref=None, language="en", title="") -> None:
    try:
        await asyncio.to_thread(
            _save_turn, session_id, user_id, user_message, assistant_response,
            intents, booking_ref, language, title,
        )
    except Exception as e:
        print(f"[chat_store] save_turn failed (non-fatal): {e}")


async def list_sessions(user_id=DEMO_USER_ID) -> list:
    return await asyncio.to_thread(_list_sessions, user_id)


async def get_messages(session_id) -> list:
    return await asyncio.to_thread(_get_messages, session_id)
