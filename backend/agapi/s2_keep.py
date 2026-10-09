"""CR 63 · THE KEEP on Sasha — a person's numbers and codes, on the SAME logic as the AgAPI sandbox's keep.* (agapi/keep.py).
Wiring is the Sasha tab's (docs/sasha/s2-keep-wiring.md).

  THE RULE  the model never sees a value: keep_list gives masks ("Passport ES ••••456"); keep_use binds an item to the next
            booking or sends it to the person's own screen — it never returns the value. Values arrive only from the person's
            own /keep page (never through the chat; a passport or DNI typed in the chat is withheld — guard()).
  FILL      at the moment of use, in code: after the payment, basket_book opens the passport for the Duffel order
            (identity_documents) and drops it. A tier-`yes` item only when the read-back the person HEARD named it and they said
            yes to that read-back (approve(), from book()).
  ENVELOPE  per account: one data key wrapped by Google Cloud KMS — the KMS S-78's vault already uses (booking_signer/vault/kms.py).
            No KMS, or 037 not applied → the Keep is CLOSED and says so; never a fallback that keeps secrets in memory.
  ACTIVITY  every save, use, show and deletion: an s2_acts row with its proof (agapi/s2_records.py), in the Activity view.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from agapi import keep as K

log = logging.getLogger("agapi.keep")
NOW = lambda: datetime.now(timezone.utc)
BIND_TTL = timedelta(minutes=30)          # bound to the next booking: the read-back must come within this
PAY_TTL = timedelta(minutes=60)           # approved: the payment (and the fill) must come within this
STORE: Any = None                         # tests: MemoryKeepStore(); otherwise Postgres (037), or the Keep is closed


class KeepError(Exception):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule, self.message = rule, message


# ── storage ───────────────────────────────────────────────────────────────────────────────────────────────────────────────

class MemoryKeepStore:
    """Tests only — the same contract as the Postgres store."""

    def __init__(self) -> None:
        self.keys: Dict[str, dict] = {}
        self.items: Dict[str, dict] = {}
        self.fills: Dict[str, dict] = {}

    async def key(self, account):
        return self.keys.get(account)

    async def put_key(self, account, wrapped, version):
        self.keys[account] = {"wrapped_dek": wrapped, "kek_version": version}

    async def drop_key(self, account):
        return 1 if self.keys.pop(account, None) else 0

    async def items_of(self, account):
        return sorted((i for i in self.items.values() if i["account_id"] == account), key=lambda i: i["created_at"])

    async def item(self, account, item_id):
        i = self.items.get(item_id)
        return i if i and i["account_id"] == account else None

    async def by_fingerprint(self, account, fp):
        return next((i for i in self.items.values() if i["account_id"] == account and i["fingerprint"] == fp), None)

    async def add_item(self, row):
        self.items[row["id"]] = row

    async def touch(self, item_id):
        self.items[item_id]["last_used_at"] = NOW()

    async def drop_item(self, account, item_id):
        self.fills = {k: f for k, f in self.fills.items() if f["item_id"] != item_id}
        return 1 if self.items.pop(item_id, None) else 0

    async def drop_all(self, account):
        n = [i for i in self.items if self.items[i]["account_id"] == account]
        for i in n:
            del self.items[i]
        self.fills = {k: f for k, f in self.fills.items() if f["account_id"] != account}
        return len(n)

    async def add_fill(self, row):
        self.fills[row["id"]] = row

    async def fills_of(self, account, states):
        return [f for f in self.fills.values() if f["account_id"] == account and f["state"] in states]

    async def set_fill(self, fill_id, **kw):
        self.fills[fill_id].update(kw)


class PostgresKeepStore:
    """037_keep.sql. The ONLY module that reads a ciphertext (a test holds that)."""

    def __init__(self, run) -> None:
        self._run = run

    async def _q(self, fn):
        return await self._run(fn)

    async def key(self, account):
        return await self._q(lambda c: c.fetchrow("select wrapped_dek, kek_version from keep_keys where account_id = $1::uuid", account))

    async def put_key(self, account, wrapped, version):
        await self._q(lambda c: c.execute("insert into keep_keys (account_id, wrapped_dek, kek_version) values ($1::uuid, $2, $3) "
                                          "on conflict (account_id) do nothing", account, wrapped, version))

    async def drop_key(self, account):
        r = await self._q(lambda c: c.execute("delete from keep_keys where account_id = $1::uuid", account))
        return int(str(r).split()[-1])

    async def items_of(self, account):
        rows = await self._q(lambda c: c.fetch("select * from keep_items where account_id = $1::uuid order by created_at", account))
        return [dict(r) for r in rows]

    async def item(self, account, item_id):
        try:
            iid = uuid.UUID(str(item_id))
        except ValueError:
            return None
        r = await self._q(lambda c: c.fetchrow("select * from keep_items where account_id = $1::uuid and id = $2", account, iid))
        return dict(r) if r else None

    async def by_fingerprint(self, account, fp):
        r = await self._q(lambda c: c.fetchrow("select * from keep_items where account_id = $1::uuid and fingerprint = $2", account, fp))
        return dict(r) if r else None

    async def add_item(self, row):
        await self._q(lambda c: c.execute(
            "insert into keep_items (id, account_id, type, tier, masked, fingerprint, nonce, ciphertext) values ($1, $2::uuid, $3, $4, $5, $6, $7, $8)",
            uuid.UUID(row["id"]), row["account_id"], row["type"], row["tier"], row["masked"], row["fingerprint"], row["nonce"], row["ciphertext"]))

    async def touch(self, item_id):
        await self._q(lambda c: c.execute("update keep_items set last_used_at = now() where id = $1", uuid.UUID(str(item_id))))

    async def drop_item(self, account, item_id):
        r = await self._q(lambda c: c.execute("delete from keep_items where account_id = $1::uuid and id = $2", account, uuid.UUID(str(item_id))))
        return int(str(r).split()[-1])

    async def drop_all(self, account):
        r = await self._q(lambda c: c.execute("delete from keep_items where account_id = $1::uuid", account))
        return int(str(r).split()[-1])

    async def add_fill(self, row):
        await self._q(lambda c: c.execute(
            "insert into keep_fills (id, account_id, item_id, purpose, line, state, expires_at) values ($1, $2::uuid, $3, $4, $5, $6, $7)",
            uuid.UUID(row["id"]), row["account_id"], uuid.UUID(str(row["item_id"])), row["purpose"], row["line"], row["state"], row["expires_at"]))

    async def fills_of(self, account, states):
        rows = await self._q(lambda c: c.fetch("select * from keep_fills where account_id = $1::uuid and state = any($2::text[])", account, list(states)))
        return [{**dict(r), "id": str(r["id"]), "item_id": str(r["item_id"])} for r in rows]

    async def set_fill(self, fill_id, **kw):
        cols = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(kw))
        await self._q(lambda c: c.execute(f"update keep_fills set {cols} where id = $1", uuid.UUID(str(fill_id)), *kw.values()))


def _store():
    if STORE is not None:
        return STORE
    from booking_signer import plan_store as PS
    run = PS._run()
    if run is None:
        raise KeepError("keep_closed", "The Keep isn't open on this server yet — nothing was saved or used.")
    return PostgresKeepStore(run)


def _kms():
    from booking_signer.vault import kms
    try:
        return kms.kek()
    except kms.VaultClosed as e:
        raise KeepError("keep_closed", f"The Keep's key service isn't set up yet ({e.rule}) — nothing was saved or used.") from None


async def _dek(account: str, create: bool) -> Optional[bytes]:
    st, kek = _store(), _kms()
    try:
        row = await st.key(account)
        if row:
            return await kek.unwrap(bytes(row["wrapped_dek"]), K.dek_aad(account, account), row["kek_version"])
        if not create:
            return None
        dek = K.new_dek()
        wrapped, version = await kek.wrap(dek, K.dek_aad(account, account))
        await st.put_key(account, wrapped, version)
        row = await st.key(account)          # a concurrent first save: whichever key landed is the account's one key
        return dek if bytes(row["wrapped_dek"]) == wrapped else await kek.unwrap(bytes(row["wrapped_dek"]), K.dek_aad(account, account), row["kek_version"])
    except KeepError:
        raise
    except Exception as e:
        log.warning("[keep] the key couldn't be opened: %s", type(e).__name__)   # the type only: never a value, never a key
        raise KeepError("keep_unreachable", "The Keep's key service didn't answer — nothing was saved or used.") from None


def _out(i: dict) -> dict:
    return {"item_id": str(i["id"]), "type": i["type"], "tier": i["tier"], "masked": i["masked"],
            **({"last_used_at": i["last_used_at"].isoformat() if hasattr(i["last_used_at"], "isoformat") else i["last_used_at"]}
               if i.get("last_used_at") else {})}


async def _activity(account: str, kind: str, item: dict, proof: dict) -> None:
    try:
        from agapi import s2_records as REC
        await REC.record(account, kind, "done", {"at": NOW().isoformat(timespec="seconds"), **proof}, item["masked"])
    except Exception as e:
        log.info("[keep] activity not recorded: %s", type(e).__name__)


# ── the person's own page (/keep): the only way a value comes in or goes out ──────────────────────────────────────────────

async def put(account: str, kind: str, value: dict) -> dict:
    try:
        values = K.normalise(kind, value)
    except K.Refused as e:
        raise KeepError(e.rule, e.message) from None
    kind = kind.strip().lower()
    dek = await _dek(account, create=True)
    fp = K.fingerprint(dek, kind, values)
    st = _store()
    same = await st.by_fingerprint(account, fp)
    if same:
        return {**_out(same), "created": False}
    iid = str(uuid.uuid4())
    nonce, ct = K.seal(dek, K.item_aad(account, account, iid, kind), values)
    row = {"id": iid, "account_id": account, "type": kind, "tier": K.tier_of(kind), "masked": K.mask(kind, values), "fingerprint": fp,
           "nonce": nonce, "ciphertext": ct, "created_at": NOW(), "last_used_at": None}
    values = None
    await st.add_item(row)
    await _activity(account, "keep_save", row, {"reference": "keep:" + iid, "item": row["masked"]})
    return {**_out(row), "created": True}


async def list_(account: str) -> List[dict]:
    return [_out(i) for i in await _store().items_of(account)]


async def show(account: str, item_id: str) -> Dict[str, str]:
    """A read-back-only item, to the signed-in person's OWN screen (the route returns it to their browser, never to the model)."""
    st = _store()
    it = await st.item(account, item_id)
    if not it:
        raise KeepError("not_found", "That isn't in your Keep.")
    try:
        K.check_use(it["type"], "show")
    except K.Refused as e:
        raise KeepError(e.rule, e.message) from None
    dek = await _dek(account, create=False)
    values = K.open_(dek, K.item_aad(account, account, str(it["id"]), it["type"]), bytes(it["nonce"]), bytes(it["ciphertext"]))
    await st.touch(it["id"])
    await _activity(account, "keep_show", it, {"reference": "keep:" + str(it["id"]), "item": it["masked"]})
    return values


async def delete(account: str, item_id: Optional[str] = None) -> dict:
    """One item, or everything — the items AND the account's wrapped key, so every value is shredded (deletion on request)."""
    st = _store()
    if item_id:
        it = await st.item(account, item_id)
        if not it:
            raise KeepError("not_found", "That isn't in your Keep.")
        await st.drop_item(account, it["id"])
        await _activity(account, "keep_delete", it, {"reference": "keep:" + str(it["id"]), "item": it["masked"]})
        return {"deleted": 1, "key_destroyed": False}
    n = await st.drop_all(account)
    gone = await st.drop_key(account)
    await _activity(account, "keep_delete", {"masked": f"Everything in your Keep ({n})"}, {"reference": "keep:all", "items": n})
    return {"deleted": n, "key_destroyed": bool(gone)}


# ── the booking: bind (the tool) → the read-back names it (hold_booking) → the yes (book) → the fill (after payment) ─────────

async def bind(account: str, item_id: str, purpose: str) -> dict:
    st = _store()
    it = await st.item(account, item_id)
    if not it:
        raise KeepError("not_found", "That isn't in their Keep — keep_list shows what is.")
    try:
        K.check_use(it["type"], purpose)
    except K.Refused as e:
        raise KeepError(e.rule, e.message) from None
    if purpose == "show":
        return {"state": "on_their_screen", "masked": it["masked"], "screen": f"/keep#{it['id']}",
                "say": "It's on their Keep screen — tap Show. Never read it out: you don't have it."}
    for f in await st.fills_of(account, ("bound", "approved")):   # one at a time per item: a re-bind replaces the old one
        if f["item_id"] == str(it["id"]):
            await st.set_fill(f["id"], state="replaced")
    line = K.use_line(it["masked"]) if it["tier"] == K.YES else None
    await st.add_fill({"id": str(uuid.uuid4()), "account_id": account, "item_id": str(it["id"]), "purpose": "fill", "line": line,
                       "state": "bound", "expires_at": NOW() + BIND_TTL})
    if line:
        return {"state": "needs_yes", "masked": it["masked"], "line": line,
                "say": "It's added to the booking's read-back: hold_booking reads it out, and their yes covers it."}
    return {"state": "ready", "masked": it["masked"], "say": "It will be filled into the next booking."}


async def lines(account: str) -> List[str]:
    """hold_booking appends these to what she reads out."""
    try:
        fills = await _store().fills_of(account, ("bound",))
    except KeepError:
        return []
    now = NOW()
    return [f["line"] for f in fills if f["line"] and f["expires_at"] > now]


async def approve(account: str, heard: List[str], said: str, session_id: str) -> int:
    """book(): the person said yes to a read-back they HEARD. Each bound fill whose line was in it (or a tier-free fill) is
    approved for THIS payment only, with their words and the read-back's hash as its proof."""
    try:
        st = _store()
        fills = await st.fills_of(account, ("bound",))
    except KeepError:
        return 0
    rsha, now, n = "sha256:" + hashlib.sha256("\n".join(heard).encode()).hexdigest(), NOW(), 0
    for f in fills:
        if f["expires_at"] <= now or (f["line"] and f["line"] not in heard):
            continue
        await st.set_fill(f["id"], state="approved", session_id=session_id, said=(said or "")[:300], read_back_sha256=rsha,
                          expires_at=now + PAY_TTL)
        n += 1
    return n


class Fill:
    """What basket_book holds for the length of one order: the opened items, dropped on exit."""

    def __init__(self, docs: List[dict]) -> None:
        self._docs = docs
        self.references: List[str] = []
        self.ok = False

    def duffel(self) -> List[dict]:
        """Duffel identity_documents for the account holder's passenger."""
        out = []
        for d in self._docs:
            v = d["values"]
            if d["type"] == "passport":
                out.append({"type": "passport", "unique_identifier": v["number"], "issuing_country_code": v["country"],
                            "expires_on": v["expires_on"]})
            elif d["type"] == "trusted_traveller" and v.get("program") in ("global_entry", "tsa_precheck"):
                out.append({"type": "known_traveler_number", "unique_identifier": v["number"], "issuing_country_code": "US"})
        return out

    def masked(self) -> List[str]:
        return [d["masked"] for d in self._docs]

    def result(self, reference: Optional[str], ok: bool) -> None:
        """Once per order in the payment (a round trip is two): the item is 'used' if any order took it."""
        if ok and reference:
            self.references.append(reference)
        self.ok = self.ok or ok

    def _drop(self) -> None:
        for d in self._docs:
            d["values"] = None
        self._docs.clear()


@asynccontextmanager
async def fill(account: str, session_id: str):
    """AT THE MOMENT OF USE (basket_book, after payment): the approved items for this payment, opened, then dropped — around
    the payment's whole loop of orders (a round trip is two flights; both carry the passport):
        async with KEEP.fill(account, sid) as kept:
            for each flight:  o = await T.order(c, …, documents=kept.duffel());  kept.result(o.get("booking_reference"), "why" not in o)"""
    try:
        st = _store()
        fills = [f for f in await st.fills_of(account, ("approved",)) if f.get("session_id") == session_id and f["expires_at"] > NOW()]
    except KeepError:
        fills = []
    docs: List[dict] = []
    for f in fills:
        it = await st.item(account, f["item_id"])
        if not it:
            continue
        dek = await _dek(account, create=False)
        docs.append({"fill": f, "item": it, "type": it["type"], "masked": it["masked"],
                     "values": K.open_(dek, K.item_aad(account, account, str(it["id"]), it["type"]), bytes(it["nonce"]), bytes(it["ciphertext"]))})
    kept = Fill(docs)
    items = [(d["fill"], d["item"]) for d in docs]
    try:
        yield kept
    finally:
        kept._drop()
        for f, it in items:
            await st.set_fill(f["id"], state="used" if kept.ok else "failed", used_at=NOW())
            if kept.ok:
                await st.touch(it["id"])
                await _activity(account, "keep_use", it, {"reference": ", ".join(kept.references), "said": f.get("said"),
                                                          "read_back_sha256": f.get("read_back_sha256"), "item": it["masked"]})


# ── the chat never carries a value ────────────────────────────────────────────────────────────────────────────────────────

GUARD_REPLY = ("Please don't type passport or ID numbers in the chat — I haven't kept it, and it wasn't passed on. Save it in "
               "your Keep (/keep) and I'll use it only where it's needed, after your yes.")
_DOC_WORD = re.compile(r"(?i)\b(passport|pasaporte|dni|nie|national id|id card|global entry|precheck|known traveller|ktn|"
                       r"residence (?:permit|card)|tarjeta (?:de )?residencia|tie|visa (?:number|no)|policy (?:number|no)|"
                       r"health card|tarjeta sanitaria)\b")


def guard(text: str) -> bool:
    """True when a chat line carries a document number: a valid DNI/NIE anywhere, or a document word next to a number-like
    token. The S-78 guard path withholds it (wiring note) — the model never sees it."""
    t = text or ""
    for m in re.finditer(r"(?<![A-Za-z0-9])([0-9]{8}[A-Za-z]|[XYZxyz][0-9]{7}[A-Za-z])(?![A-Za-z0-9])", t):
        n = m.group(1).upper()
        if K._dni_ok("dni" if n[0].isdigit() else "nie", n):
            return True
    w = _DOC_WORD.search(t)
    if w:
        tail = t[w.end():w.end() + 60]
        if any(sum(ch.isdigit() for ch in tok) >= 4 for tok in re.findall(r"[A-Za-z0-9-]{6,22}", tail)):
            return True
    return False


def chat_guard(message: str) -> Optional[str]:
    """The /next turn's guard, BEFORE the model (wiring note): S-78's (a password, PIN, code, key or card number) and the Keep's
    (a passport / ID number). → the fixed reply, or None. Found in CR 63: /next had no S-78 guard at all."""
    from booking_signer.vault import guard as G
    hit = G.looks_like_secret(message or "")
    if hit:
        return G.CARD_REPLY if hit == "card" else G.SECRET_REPLY
    return GUARD_REPLY if guard(message) else None


def clean_history(history: List[dict]) -> List[dict]:
    """Every earlier user line that trips either guard, blanked before the model reads the history."""
    from booking_signer.vault import guard as G
    out = []
    for m in history or []:
        t = m.get("content") if isinstance(m, dict) else None
        if isinstance(m, dict) and m.get("role") == "user" and isinstance(t, str) and (G.looks_like_secret(t) or guard(t)):
            m = {**m, "content": G.REMOVED}
        out.append(m)
    return out


# ── the model's two tools ─────────────────────────────────────────────────────────────────────────────────────────────────

async def keep_list(ctx, a: dict) -> dict:
    from agapi.v0 import ToolError
    try:
        items = await list_(ctx.account)
    except KeepError as e:
        raise ToolError(e.rule, e.message)
    return {"items": items, "values": "never shown to you — only masks", "screen": "/keep"}


async def keep_use(ctx, a: dict) -> dict:
    from agapi.v0 import ToolError
    try:
        out = await bind(ctx.account, str(a.get("item_id") or ""), str(a.get("purpose") or ""))
    except KeepError as e:
        raise ToolError(e.rule, e.message)
    if out["state"] == "needs_yes":   # an earlier read-back didn't name it: book() must not reuse it — hold_booking reads it again
        from agapi import v0 as API
        API._HELD.pop(ctx.account, None)
    return out


def tools() -> List[dict]:
    from agapi.v0 import _t
    return [
        _t("keep_list", "Pacioli", keep_list, "What's in the person's Keep (passport, ID, loyalty numbers, door codes…) — as MASKS only "
           "(\"Passport ES ••••456\"). You never see a value. New items are added by the person on their Keep screen (/keep), never "
           "in the chat.", {}, [], {"type": "object", "properties": {"items": {"type": "array"}}}, ["keep_closed", "keep_unreachable"]),
        _t("keep_use", "Austen", keep_use, "Use a Keep item: purpose 'fill' puts it into the next booking (a passport, ID or "
           "insurance needs it named in the read-back — hold_booking does that — and their yes); 'show' puts a door code, Wi-Fi or "
           "booking reference on THEIR screen. Never returns the value, whatever you ask.",
           {"item_id": {"type": "string"}, "purpose": {"type": "string", "description": "fill or show"}}, ["item_id", "purpose"],
           {"type": "object", "properties": {"state": {"enum": ["needs_yes", "ready", "on_their_screen"]}}},
           ["not_found", "never_raw", "read_back_only", "fill_only", "keep_closed", "keep_unreachable"], austen=True),   # every Austen tool is keyed
    ]


# ── the /keep screen's API (included into the agent router by the wiring note → /api/agent/keep…) ────────────────────────────

from fastapi import APIRouter, Request                       # noqa: E402
from fastapi.responses import JSONResponse                   # noqa: E402

router = APIRouter()
_HTTP = {"not_found": 404, "keep_closed": 503, "keep_unreachable": 503}


async def _who(request: Request) -> Optional[str]:
    from app.services.chat_account import chat_account, signed_in
    account = await chat_account(request)
    return account if signed_in(account) else None


def _err(e: KeepError) -> JSONResponse:
    return JSONResponse({"ok": False, "rule": e.rule, "message": e.message}, status_code=_HTTP.get(e.rule, 400))


@router.get("/keep")
async def keep_get(request: Request):
    account = await _who(request)
    if not account:
        return JSONResponse({"ok": False, "rule": "sign_in"}, status_code=403)
    try:
        return JSONResponse({"ok": True, "items": await list_(account), "types": {k: {"tier": v["tier"], "name": v["name"],
                             "fields": list(v["fields"])} for k, v in K.TYPES.items()}}, headers={"Cache-Control": "no-store"})
    except KeepError as e:
        return _err(e)


@router.post("/keep")
async def keep_post(request: Request):
    """From the person's own /keep form: the value goes browser → here → sealed. Never logged, never echoed."""
    account = await _who(request)
    if not account:
        return JSONResponse({"ok": False, "rule": "sign_in"}, status_code=403)
    try:
        b = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "rule": "json", "message": "That wasn't a form we could read."}, status_code=400)
    try:
        out = await put(account, str(b.get("type") or ""), b.get("value") if isinstance(b.get("value"), dict) else {})
    except KeepError as e:
        return _err(e)
    finally:
        b = None
    return JSONResponse({"ok": True, **out}, status_code=201 if out["created"] else 200, headers={"Cache-Control": "no-store"})


@router.post("/keep/{item_id}/show")
async def keep_show(item_id: str, request: Request):
    account = await _who(request)
    if not account:
        return JSONResponse({"ok": False, "rule": "sign_in"}, status_code=403)
    try:
        return JSONResponse({"ok": True, "values": await show(account, item_id)}, headers={"Cache-Control": "no-store"})
    except KeepError as e:
        return _err(e)


@router.delete("/keep/{item_id}")
async def keep_delete_one(item_id: str, request: Request):
    account = await _who(request)
    if not account:
        return JSONResponse({"ok": False, "rule": "sign_in"}, status_code=403)
    try:
        return JSONResponse({"ok": True, **await delete(account, item_id)})
    except KeepError as e:
        return _err(e)


@router.delete("/keep")
async def keep_delete_all(request: Request):
    """Deletion on request: everything, and the key. The page asks them to type DELETE first."""
    account = await _who(request)
    if not account:
        return JSONResponse({"ok": False, "rule": "sign_in"}, status_code=403)
    if request.query_params.get("confirm") != "DELETE":
        return JSONResponse({"ok": False, "rule": "confirm", "message": "Type DELETE to delete everything in your Keep."}, status_code=400)
    try:
        return JSONResponse({"ok": True, **await delete(account)})
    except KeepError as e:
        return _err(e)
