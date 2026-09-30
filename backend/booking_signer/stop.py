"""S-56 · STOP — a venue that says stop, in any language, on any channel, is never contacted by Sasha again.

S-49 §5, built before the first real venue opts in. When a venue's words say stop:
  1. RECORDED, verbatim: a `withdrawn` venue_optins row for the channel it was said on (email · phone · whatsapp · sms),
     carrying its exact words and where they came from — plus a withdrawn row closing every opt-in chain the venue has
     live, under every id it goes by;
  2. EVERY channel ends at once: the refusal check (optins.py) refuses phone, email, WhatsApp and form submission from
     that moment, including a read-back already prepared and waiting for its yes;
  3. ONE acknowledgement, where the channel allows it — "Done: Sasha won't contact you again." by email reply; on a call
     the agent says it before hanging up (calls.py). A second stop gets no second reply: then nothing more;
  4. every GUEST with a request still pending at that venue is told, on their reservation: the venue asked Sasha to stop,
     the request was not confirmed, they can contact the venue themselves (trip item → `escalated`, with the words).

What counts as stop (`detect`):
  · a WHOLE line that is only a stop word — STOP, PARA, PARE, BAJA, DUR, STOPP, ARRÊT, BASTA, UNSUBSCRIBE… A single word
    only counts alone on its line: "para" is Spanish for "for" ("mesa para 4"), and "stop" is ordinary English;
  · a stop PHRASE anywhere — "don't contact us again", "no nos llaméis más", "dadnos de baja", "não nos contactem"…
  · on a CALL, phrases only, never a lone word: speech is full of "para" and "stop".
The words are matched with accents folded and case ignored; what is stored is the venue's original text.

Wired today: email replies (the inbound webhook) and call transcripts (the sweeper). ⚠ WhatsApp and SMS have no
inbound yet — Sasha has no number (S-48) — so `on_venue_words` is ready for them and nothing calls it from there yet.

SQL: sql/010_withdrawal_channels.sql lets a withdrawal row name email, phone or sms as the channel it was said on.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from . import optins as O

log = logging.getLogger("sasha.stop")

SAID_ON = ("email", "phone", "whatsapp", "sms")
PENDING = ("pending", "prepared", "attempting", "requested", "unclear", "unreachable")
LOOK_BACK = timedelta(days=120)


def _fold(s: str) -> str:
    # Turkish ı has no decomposition to i — fold it by hand, or "aramayın" never matches "aramayin"
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch)).casefold().replace("ı", "i")


#: alone on a line (after folding, punctuation stripped)
_WORDS = {"stop", "stopp", "para", "pare", "parar", "baja", "dur", "arret", "basta", "unsubscribe", "desuscribir",
          "no mas", "nao quero", "stop please", "stop por favor", "baja por favor", "please stop"}

#: anywhere in the text (folded). Kept explicit: every phrase here is one a venue would only use to mean "stop"
_PHRASES = [
    # en
    r"\bunsubscribe\b", r"\bopt(?:ed)? out\b", r"\bstop (?:contacting|messaging|emailing|calling|texting) us\b",
    r"\b(?:do not|don'?t|dont) (?:contact|call|message|email|text) us\b", r"\bremove us from\b", r"\bno more (?:messages|calls|emails)\b",
    r"\bnever (?:contact|call) us\b",
    # es
    r"\bno nos (?:contacteis|contacten|contactes|llameis|llamen|llames|escribais|escriban|escribas|mandeis|manden)\b",
    r"\b(?:dejad|dejen|deja|deje) de (?:contactar|escribir|llamar|mandar|enviar)", r"\b(?:darnos|dadnos|denos|dennos) de baja\b",
    r"\bno queremos (?:recibir|que nos (?:contacten|llamen|escriban))", r"\bno (?:vuelvan|volvais|vuelvas) a (?:llamar|escribir|contactar)",
    # pt
    r"\bnao nos (?:contactem|contacte|liguem|ligue|escrevam|enviem)\b", r"\b(?:parem|pare) de (?:contactar|ligar|escrever|enviar)",
    r"\bnao quero (?:receber|mais)\b", r"\bnao queremos (?:receber|mais)\b", r"\bcancelar a subscricao\b",
    # fr
    r"\bne nous (?:contactez|appelez|ecrivez) plus\b", r"\bne plus nous (?:contacter|appeler|ecrire)\b", r"\bdesabonner\b",
    r"\barretez de nous (?:contacter|appeler|ecrire)",
    # de
    r"\bnicht mehr (?:kontaktieren|anrufen|schreiben)\b", r"\babmelden\b", r"\babbestellen\b",
    # it
    r"\bnon (?:contattateci|chiamateci|scriveteci) piu\b", r"\bsmettete(?:la)? di (?:contattarci|chiamarci|scriverci)",
    # tr
    r"\bbizi (?:aramayin|aramayiniz)\b", r"\bbize (?:yazmayin|yazmayiniz|mesaj atmayin)\b", r"\babonelikten cik",
]
_PHRASE = re.compile("|".join(_PHRASES))

#: where a reply's own text ends and the quoted message begins
_QUOTE = re.compile(r"^(?:>|-{2,}\s*original message|_{5,}|(?:on|el|em|le|am|il) .{3,160}(?:wrote|escribio|escreveu|a ecrit|schrieb|ha scritto):?\s*$|(?:from|de|von|da):\s)", re.I)


def own_text(reply: str) -> str:
    """A reply's own words, above whatever it quotes."""
    out = []
    for line in reply.splitlines():
        if _QUOTE.match(_fold(line.strip())):
            break
        out.append(line)
    return "\n".join(out)


def detect(text: Optional[str], spoken: bool = False) -> Optional[str]:
    """The venue's own words that say stop — the line or sentence, verbatim — or None."""
    if not text:
        return None
    body = text if spoken else own_text(text)
    for line in body.splitlines():
        raw = line.strip()
        f = _fold(raw)
        if not f:
            continue
        if not spoken and re.sub(r"[^\w' ]+", "", f).strip() in _WORDS:
            return raw
        if _PHRASE.search(f):
            return raw
    return None


ACK = {
    "en": ("Done: Sasha won't contact you again.", "Understood. Sasha won't contact you again."),
    "es": ("Hecho: Sasha no volverá a contactaros.", "Entendido. Sasha no volverá a contactarles."),
    "pt": ("Feito: a Sasha não voltará a contactar-vos.", "Entendido. A Sasha não voltará a contactá-los."),
    "fr": ("C'est fait : Sasha ne vous contactera plus.", "Entendu. Sasha ne vous contactera plus."),
    "de": ("Erledigt: Sasha wird Sie nicht mehr kontaktieren.", "Verstanden. Sasha wird Sie nicht mehr kontaktieren."),
    "it": ("Fatto: Sasha non vi contatterà più.", "Capito. Sasha non vi contatterà più."),
    "tr": ("Tamam: Sasha sizinle bir daha iletişime geçmeyecek.", "Anlaşıldı. Sasha sizinle bir daha iletişime geçmeyecek."),
}


def ack_email_text(lang: str) -> str:
    return ACK.get(lang, ACK["en"])[0] + "\n\nSasha · Kanoe Technologies SL"


def ack_spoken(lang_code: str) -> str:
    return ACK.get(lang_code, ACK["en"])[1]


GUEST_NOTE = ("The venue asked Sasha to stop contacting them ({when}: \"{words}\"). This request was not confirmed; "
              "you can still contact them yourself.")


@dataclass(frozen=True)
class Stopped:
    first: bool            #: the venue was not already withdrawn — so this stop gets the one acknowledgement
    rows: int              #: withdrawn rows written
    guests_told: int       #: pending trip items marked, one per guest request


def withdrawal_rows(venue_ids: Sequence[str], said_on: str, scope: str, words: str, evidence: Dict[str, Any],
                    live: List[tuple], now: datetime) -> List[dict]:
    """The row for where it was said, and one closing each live chain (venue_id, channel, scope)."""
    ev = {**evidence, "verbatim": words, "said_on": said_on}
    chains = list(dict.fromkeys([(venue_ids[0], said_on, scope), *live]))
    return [{"venue_id": v, "channel": ch, "scope": sc, "status": "withdrawn", "recorded_at": now, "withdrawn_at": now,
             "withdrawn_how": f"said stop by {said_on}", "withdrawn_evidence": ev} for v, ch, sc in chains]


def _live(rows: List[dict]) -> List[tuple]:
    latest: Dict[tuple, dict] = {}
    for r in sorted(rows, key=lambda r: (r["recorded_at"], r["id"])):
        latest[(r["venue_id"], r["channel"], r["scope"])] = r
    return [k for k, r in latest.items() if r["status"] == "active"]


def _already(rows: List[dict]) -> bool:
    return bool(rows) and sorted(rows, key=lambda r: (r["recorded_at"], r["id"]))[-1]["status"] == "withdrawn"


# ── stores ─────────────────────────────────────────────────────────────────────────────────────

class MemoryStopStore:
    """Over the memory stores the routes already use (tests)."""
    def __init__(self, optins: O.MemoryOptinStore, ladder=None, calls=None) -> None:
        self.optins, self.ladder, self.calls = optins, ladder, calls

    async def email_venue(self, email_id: str) -> Optional[dict]:
        e = self.ladder.emails.get(email_id) if self.ladder else None
        r = self.ladder.reads.get(str(e.get("read_id"))) if e else None
        return {"venue_ids": O.venue_ids_of(r["read"]), "country": r["read"].get("country")} if r else None

    async def address_venue(self, addr: str) -> Optional[str]:
        for eid, e in sorted((self.ladder.emails if self.ladder else {}).items(), key=lambda kv: kv[1]["created_at"], reverse=True):
            if str(e["email"].get("to", "")).lower() == addr.lower():
                return eid
        return None

    async def record(self, venue_ids, said_on, scope, words, evidence, now) -> Stopped:
        rows = [r for r in self.optins.rows if r["venue_id"] in venue_ids]
        first = not _already(rows)
        new = withdrawal_rows(venue_ids, said_on, scope, words, evidence, _live(rows), now)
        for row in new:
            await self.optins.add(row)
        told = 0
        for store, kind in ((self.ladder, "emails"), (self.ladder, "links"), (self.calls, "calls")):
            for rec in (getattr(store, kind, {}) or {}).values() if store else []:
                ids = (rec.get("brief") or {}).get("venue_ids") if kind == "calls" else \
                    (O.venue_ids_of(store.reads[str(rec["read_id"])]["read"]) if str(rec.get("read_id")) in store.reads else [])
                item = store.trip_items.get(rec.get("trip_item_id")) if rec.get("trip_item_id") else None
                if item and set(ids or []) & set(venue_ids) and item["status"] in PENDING:
                    item.update(status="escalated", escalated_at=now, escalation_notes=GUEST_NOTE.format(when=now.date().isoformat(), words=words))
                    told += 1
        return Stopped(first, len(new), told)


class PostgresStopStore:
    def __init__(self, base) -> None:
        self._base = base

    async def email_venue(self, email_id: str) -> Optional[dict]:
        import uuid
        try:
            eid = uuid.UUID(str(email_id))
        except ValueError:
            return None
        r = await self._base._run(lambda c: c.fetchrow(
            "select r.read from booking_emails e join venue_reads r on r.read_id = e.read_id where e.email_id = $1", eid))
        return {"venue_ids": O.venue_ids_of(r["read"]), "country": r["read"].get("country")} if r else None

    async def address_venue(self, addr: str) -> Optional[str]:
        v = await self._base._run(lambda c: c.fetchval(
            "select email_id from booking_emails where lower(email->>'to') = lower($1) order by created_at desc limit 1", addr))
        return str(v) if v else None

    async def record(self, venue_ids, said_on, scope, words, evidence, now) -> Stopped:
        ids = list(venue_ids)

        async def tx(c):
            async with c.transaction():
                # one stop at a time per venue: the "first" decision (and so the one acknowledgement) cannot race
                await c.execute("select pg_advisory_xact_lock(hashtext($1))", ids[0])
                rows = [dict(r) for r in await c.fetch(
                    "select id, venue_id, channel, scope, status, recorded_at from venue_optins where venue_id = any($1::text[])", ids)]
                first = not _already(rows)
                new = withdrawal_rows(ids, said_on, scope, words, evidence, _live(rows), now)
                for row in new:
                    await c.execute(
                        "insert into venue_optins (venue_id, channel, scope, status, recorded_at, withdrawn_at, withdrawn_how, withdrawn_evidence) "
                        "values ($1,$2,$3,'withdrawn',$4,$4,$5,$6)",
                        row["venue_id"], row["channel"], row["scope"], now, row["withdrawn_how"], row["withdrawn_evidence"])
                # the guests: every Sasha request at this venue still pending
                cands = await c.fetch(
                    "select e.trip_item_id as item, r.read as read, null::jsonb as brief from booking_emails e join venue_reads r on r.read_id = e.read_id "
                    " join trip_items t on t.id = e.trip_item_id where t.status = any($1::text[]) and e.created_at > $2 "
                    "union all select l.trip_item_id, r.read, null from booking_links l join venue_reads r on r.read_id = l.read_id "
                    " join trip_items t on t.id = l.trip_item_id where t.status = any($1::text[]) and l.created_at > $2 "
                    "union all select k.trip_item_id, null, k.brief from booking_calls k "
                    " join trip_items t on t.id = k.trip_item_id where t.status = any($1::text[]) and k.created_at > $2",
                    list(PENDING), now - LOOK_BACK)
                items = {r["item"] for r in cands if r["item"] and set(
                    ((r["brief"] or {}).get("venue_ids") or []) if r["read"] is None else O.venue_ids_of(r["read"])) & set(ids)}
                if items:
                    await c.execute(
                        "update trip_items set status = 'escalated', escalated_at = $2, escalation_notes = $3, updated_at = $2 "
                        "where id = any($1::uuid[]) and status = any($4::text[])",
                        list(items), now, GUEST_NOTE.format(when=now.date().isoformat(), words=words), list(PENDING))
                return Stopped(first, len(new), len(items))
        return await self._base._run(tx)


STOP_STORE: Any = None   # set by routes.py


async def on_venue_words(venue_ids: Optional[Sequence[str]], said_on: str, scope: str, text: Optional[str],
                         evidence: Dict[str, Any], now: datetime, spoken: bool = False) -> Optional[Stopped]:
    """THE entry point for every channel: the venue's words in, a recorded stop out (or None: not a stop).
    ⚠ Raises if the stop cannot be recorded — a caller must not swallow that (the email webhook answers non-2xx so the
    mail service retries; the sweeper retries the call next minute)."""
    if said_on not in SAID_ON:
        raise ValueError(f"not a channel a venue can say stop on: {said_on!r}")
    words = detect(text, spoken=spoken)
    if not words:
        return None
    if not venue_ids:
        log.error("[stop] %s said stop (%r) but the venue is not known, so nothing could be recorded against it", said_on, words)
        return None
    out = await STOP_STORE.record(list(venue_ids), said_on, scope, words, evidence, now)
    log.info("[stop] venue %s said stop by %s: %r — %d row(s), %d guest(s) told", list(venue_ids)[0], said_on, words, out.rows, out.guests_told)
    return out
