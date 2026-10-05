"""Sasha 74 · THE FOUNDER'S REDUNDANCY RULES, now that the email rung can send and receive on booking.kanoe.ai.

  1. Sasha gives the venue HER OWN email on every phone booking, alongside the guest's name (the call says it, in the
     venue's language, after the recap) — and a reply to it lands on the reservation (the inbound handler matches it).
  2. After every phone booking the venue said YES to: a confirmation email to the venue's published address (its OWN
     site — Sasha 64), the guest copied privately (BCC), restating what, when, how many and the name.
  3. After an UNCLEAR call: the "I just spoke with you… could you confirm…" email. The venue's reply is read with the
     same field checks as a call (heard.py / recap.restates): an explicit yes restating the day, time and number turns
     the reservation CONFIRMED; another time turns it PROPOSED; anything else leaves it as it is, the reply shown.

  ⛔ Covered by the guest's ONE yes: the call's read-back says, before the yes, that this email will follow and to which
     address (the brief carries it, inside the sha256 the yes binds). With no published address, the read-back says
     there will be no written confirmation — nothing is sent anywhere else.
  ⛔ Never twice: the follow-up's id is derived from the call (uuid5), so the sweeper and a page read cannot both send it.
  ⛔ Sasha's own address is said only once something answers it: the sending key, the from-address, the inbound domain
     and the webhook's secret are all set (own_email()).
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime
from typing import Any, List, Mapping, Optional

from . import emailing as E

log = logging.getLogger("booking_signer.followup")
_NS = uuid.UUID("5a5ba000-0000-4000-8000-0000000000a4")

#: Sasha's address, as a venue hears it on the phone — spelled the way each language says "@" and "."
_SPOKEN_AT = {"es": ("arroba", "punto"), "pt": ("arroba", "ponto"), "fr": ("arobase", "point"), "it": ("chiocciola", "punto"),
              "de": ("at", "Punkt"), "en": ("at", "dot")}


def own_email() -> Optional[str]:
    """Sasha's own address — only when mail to it is SENT and RECEIVED by this server (S-32: never an address nobody reads)."""
    m = E._EMAIL.search(os.getenv("SASHA_EMAIL_FROM", ""))
    ready = all(os.getenv(v, "").strip() for v in ("SASHA_RESEND_API_KEY", "SASHA_INBOUND_DOMAIN", "RESEND_WEBHOOK_SECRET"))
    if not (m and ready):
        return None
    addr = m.group(0).lower()
    return addr if addr.split("@", 1)[1] == os.getenv("SASHA_INBOUND_DOMAIN", "").strip().lower() else None


def spoken(addr: str, lang_code: str) -> str:
    at, dot = _SPOKEN_AT.get(lang_code, _SPOKEN_AT["en"])
    local, dom = addr.split("@", 1)
    return f"{local} {at} {f' {dot} '.join(dom.split('.'))}"


def venue_email(read: Optional[Mapping[str, Any]]) -> Optional[dict]:
    """The address the venue publishes on its OWN site (a listing never carries one), with where it was read."""
    for f in (read or {}).get("facts") or []:
        if f.get("kind") == "email" and f.get("value") and f.get("source_kind") == "site":
            return {"to": f["value"], "source_label": f.get("source_label") or "their website"}
    return None


# ── rule 1 and the read-back that covers rules 2–3 ───────────────────────────────────────────────────────────────────

#: Sasha 90 (a) · after the recap's yes, she asks for it IN WRITING — to the guest's mobile, or to her own address
CONFIRM_ASK = {
    "es": ("¿Nos podrían enviar una confirmación por SMS o por email? Al móvil del cliente, {mobile}, o a {email}.",
           "¿Nos podrían enviar una confirmación por email a {email}?"),
    "en": ("Could you send us a confirmation by text or email? To the guest's mobile, {mobile}, or to {email}.",
           "Could you send us a confirmation by email to {email}?"),
    "fr": ("Pourriez-vous nous envoyer une confirmation par SMS ou par e-mail ? Au portable du client, {mobile}, ou à {email}.",
           "Pourriez-vous nous envoyer une confirmation par e-mail à {email} ?"),
    "it": ("Potreste inviarci una conferma via SMS o email? Al cellulare del cliente, {mobile}, oppure a {email}.",
           "Potreste inviarci una conferma via email a {email}?"),
    "pt": ("Poderiam enviar-nos uma confirmação por SMS ou por email? Para o telemóvel do cliente, {mobile}, ou para {email}.",
           "Poderiam enviar-nos uma confirmação por email para {email}?"),
    "de": ("Könnten Sie uns eine Bestätigung per SMS oder E-Mail schicken? An das Handy des Gastes, {mobile}, oder an {email}.",
           "Könnten Sie uns eine Bestätigung per E-Mail an {email} schicken?"),
}


#: Sasha 92 · once her own number is live, an SMS to IT is asked for too — it lands on the reservation (inbound_phone)
CONFIRM_ASK_SASHA = {
    "es": "¿Nos podrían enviar una confirmación por SMS a nuestro número, {sasha}, o por email a {email}?",
    "en": "Could you send us a confirmation by text to our number, {sasha}, or by email to {email}?",
    "fr": "Pourriez-vous nous envoyer une confirmation par SMS à notre numéro, {sasha}, ou par e-mail à {email} ?",
    "it": "Potreste inviarci una conferma via SMS al nostro numero, {sasha}, oppure via email a {email}?",
    "pt": "Poderiam enviar-nos uma confirmação por SMS para o nosso número, {sasha}, ou por email para {email}?",
    "de": "Könnten Sie uns eine Bestätigung per SMS an unsere Nummer, {sasha}, oder per E-Mail an {email} schicken?",
}


#: Sasha 118 · the shortest ask to SASHA's own number alone — a text to it lands on the booking by itself
CONFIRM_ASK_SMS = {
    "es": "¿Nos lo pueden confirmar por SMS al {sasha}?", "en": "Could you confirm it by text to {sasha}?",
    "fr": "Pourriez-vous le confirmer par SMS au {sasha} ?", "it": "Può confermarlo con un SMS al {sasha}?",
    "pt": "Pode confirmar por SMS para o {sasha}?", "de": "Können Sie es per SMS an {sasha} bestätigen?",
}


def confirm_ask(lang_code: str, me: str, mobile: Optional[str]) -> List[str]:
    """The ask, as she says it, longest first — always to SASHA (Sasha 118: never the guest's mobile; what reaches her lands
    on the booking by itself): her number and her email; her number alone; her email alone. `mobile` is no longer used."""
    from . import calls as C, spoken as SP
    c = SP.code(lang_code)
    _with_mobile, email_only = CONFIRM_ASK.get(c, CONFIRM_ASK["en"])
    out = []
    sasha = C.sasha_number()
    if sasha:
        out.append(CONFIRM_ASK_SASHA.get(c, CONFIRM_ASK_SASHA["en"]).format(sasha=SP.digits(sasha, c), email=spoken(me, c)))
        out.append(CONFIRM_ASK_SMS.get(c, CONFIRM_ASK_SMS["en"]).format(sasha=SP.digits(sasha, c)))
    return out + [email_only.format(email=spoken(me, c))]


def with_own_contact(built: dict, venue_name: str, read: Optional[Mapping[str, Any]], guest_email: Optional[str],
                     request: Optional[Mapping[str, Any]] = None) -> dict:
    """A booking call's brief and read-back, with Sasha's email given to the venue and the follow-up said before the yes.
    Applied before places_terms.seal_call (which recomputes both hashes)."""
    from . import calls as C
    from .ladder import emails_ready
    brief = dict(built["brief"])
    if brief.get("purpose") != "book":
        return built
    lines = list(built["read_back_lines"])
    extra = []
    me = own_email()
    if me:
        lang = brief.get("language") or "en"
        mobile = brief.get("phone")
        task = brief["task"]
        anchor = "If no, later, or unsure:"
        # Sasha 90 (a) · the written confirmation asked for, the longest wording that fits Bland's 2,000 — else, as before,
        # her email for any change. If none fits she says none of it, and the read-back does not claim it.
        # Sasha 118 · to SASHA only, said right after her own reference; for room, the venue's-reference question goes before
        # the written ask does (a text to her number is what lands on the booking)
        asks = [(a, f"Then ask: \"{a}\" Note their answer. ") for a in confirm_ask(lang, me, mobile)]
        asks.append((None, f"After the recap, give Sasha's email for any change: \"{spoken(me, lang)}\". Spell it if asked. "))
        ask_ref = re.search(r'After the yes, ask: "[^"]*" and repeat it back\. ', task)
        bases = [task] + ([task.replace(ask_ref[0], "", 1)] if ask_ref else [])
        sms = [x for x in asks if x[0] and x[0] in confirm_ask(lang, me, mobile)[:-1] and C.sasha_number()]
        rest = [x for x in asks if x not in sms]
        # her number first, keeping the venue's-reference question if it can; then her email; then the change line
        tried = [(a, s_, b) for b in bases for a, s_ in sms] + [(a, s_, b) for a, s_ in rest for b in bases]
        for ask, say, base in tried:
            new_task = base.replace(anchor, say + anchor, 1) if anchor in base else base + " " + say
            if len(new_task) <= 2000:
                brief["task"] = new_task
                brief["sasha_email"] = me
                if ask:
                    brief["confirm_ask"] = ask
                    from . import calls as _C
                    sasha = _C.sasha_number()
                    kinds = confirm_ask(lang, me, mobile)
                    by = (f"by text to my own number ({sasha}) or by email to me ({me})" if sasha and ask == kinds[0] else
                          f"by text to my own number ({sasha})" if sasha and ask == kinds[1] else f"by email to me ({me})")
                    extra.append(f"After their yes I'll ask them to confirm it in writing — {by}; what they send comes onto this booking.")
                else:
                    extra.append(f"I'll give them my own email, {me}, for any change — their reply comes to me and onto this booking.")
                break
    v = venue_email(read)
    if v and not emails_ready() and me and isinstance(request, Mapping) and (request.get("when") or {}).get("mode") == "at":
        # the follow-up's whole content is fixed now, inside the brief the guest's yes binds: where, to whom, and what it restates
        brief["followup"] = {"to": v["to"], "source_label": v["source_label"], "bcc": guest_email, "request": dict(request)}
        extra.append(f"After the call I'll email {venue_name} at {v['to']} (the address on {v['source_label']}) to confirm it in writing"
                     + (f" — you're copied privately at {guest_email}" if guest_email else "")
                     + ". If their answer is unclear, that email asks them to confirm, and their reply comes onto this booking.")
    elif me and not brief.get("confirm_ask"):
        extra.append(f"{venue_name} publishes no email address, so I can't confirm it with them in writing — the call's result is what you'll have.")
    if not extra:
        return built
    lines[len(lines) - 1:len(lines) - 1] = extra
    return {**built, "brief": brief, "read_back_lines": lines}


def _lang_key(code: str) -> str:
    from . import calls as C
    return next((k for k, l in C.LANGUAGES.items() if l.code == code), "en")


# ── rules 2–3 · the email after the call ─────────────────────────────────────────────────────────────────────────────

_FU = {
    "es": {"confirm": ("Confirmación de la reserva a nombre de {name}",
                       "Hola, soy {disclosure}. Acabamos de hablar por teléfono y les escribo para dejar por escrito la reserva que nos confirmaron:\n\n"
                       "{core}.\n\nSi algo no es correcto, respondan a este correo y lo corregimos. Para cualquier cambio, escríbannos aquí: {me}.\n\n"
                       "Gracias,\nSasha (concierge de IA, Kanoe Technologies SL), en nombre de {guest_short}"),
           "ask": ("¿Podrían confirmar la reserva a nombre de {name}?",
                   "Hola, soy {disclosure}. Acabo de hablar con ustedes por teléfono y no me quedó claro si la reserva quedó confirmada:\n\n"
                   "{core}.\n\n¿Podrían confirmarlo respondiendo a este correo? Si no es posible, o si proponen otra hora, díganoslo y lo consultaremos con {guest_short}.\n\n"
                   "Gracias,\nSasha (concierge de IA, Kanoe Technologies SL), en nombre de {guest_short}")},
    "pt": {"confirm": ("Confirmação da reserva em nome de {name}",
                       "Olá, sou a {disclosure}. Acabámos de falar ao telefone e escrevo para deixar por escrito a reserva que nos confirmaram:\n\n"
                       "{core}.\n\nSe algo não estiver certo, respondam a este email e corrigimos. Para qualquer alteração, escrevam-nos aqui: {me}.\n\n"
                       "Obrigada,\nSasha (concierge de IA, Kanoe Technologies SL), em nome de {guest_short}"),
           "ask": ("Poderiam confirmar a reserva em nome de {name}?",
                   "Olá, sou a {disclosure}. Acabei de falar convosco ao telefone e não ficou claro se a reserva ficou confirmada:\n\n"
                   "{core}.\n\nPoderiam confirmar respondendo a este email? Se não for possível, ou se propuserem outra hora, digam-nos e falaremos com {guest_short}.\n\n"
                   "Obrigada,\nSasha (concierge de IA, Kanoe Technologies SL), em nome de {guest_short}")},
    "fr": {"confirm": ("Confirmation de la réservation au nom de {name}",
                       "Bonjour, ici {disclosure}. Nous venons de nous parler au téléphone et je vous écris pour confirmer par écrit la réservation que vous nous avez confirmée :\n\n"
                       "{core}.\n\nSi quelque chose n'est pas correct, répondez à cet e-mail et nous corrigerons. Pour tout changement, écrivez-nous ici : {me}.\n\n"
                       "Merci,\nSasha (concierge IA, Kanoe Technologies SL), pour {guest_short}"),
           "ask": ("Pourriez-vous confirmer la réservation au nom de {name} ?",
                   "Bonjour, ici {disclosure}. Je viens de vous parler au téléphone et il ne m'est pas clair si la réservation a été confirmée :\n\n"
                   "{core}.\n\nPourriez-vous le confirmer en répondant à cet e-mail ? Si ce n'est pas possible, ou si vous proposez un autre horaire, dites-le-nous et nous verrons avec {guest_short}.\n\n"
                   "Merci,\nSasha (concierge IA, Kanoe Technologies SL), pour {guest_short}")},
    "it": {"confirm": ("Conferma della prenotazione a nome {name}",
                       "Buongiorno, sono {disclosure}. Ci siamo appena sentiti al telefono e vi scrivo per mettere per iscritto la prenotazione che ci avete confermato:\n\n"
                       "{core}.\n\nSe qualcosa non è corretto, rispondete a questa email e correggeremo. Per qualsiasi modifica, scriveteci qui: {me}.\n\n"
                       "Grazie,\nSasha (concierge IA, Kanoe Technologies SL), per conto di {guest_short}"),
           "ask": ("Potreste confermare la prenotazione a nome {name}?",
                   "Buongiorno, sono {disclosure}. Vi ho appena parlato al telefono e non mi è chiaro se la prenotazione sia confermata:\n\n"
                   "{core}.\n\nPotreste confermarlo rispondendo a questa email? Se non è possibile, o se proponete un altro orario, ditecelo e ne parleremo con {guest_short}.\n\n"
                   "Grazie,\nSasha (concierge IA, Kanoe Technologies SL), per conto di {guest_short}")},
    "de": {"confirm": ("Bestätigung der Reservierung auf den Namen {name}",
                       "Guten Tag, hier ist {disclosure}. Wir haben gerade telefoniert, und ich halte die Reservierung, die Sie uns bestätigt haben, schriftlich fest:\n\n"
                       "{core}.\n\nFalls etwas nicht stimmt, antworten Sie bitte auf diese E-Mail, dann korrigieren wir es. Für Änderungen schreiben Sie uns bitte hier: {me}.\n\n"
                       "Vielen Dank,\nSasha (KI-Concierge, Kanoe Technologies SL), im Auftrag von {guest_short}"),
           "ask": ("Könnten Sie die Reservierung auf den Namen {name} bestätigen?",
                   "Guten Tag, hier ist {disclosure}. Ich habe gerade mit Ihnen telefoniert, und mir ist nicht klar, ob die Reservierung bestätigt ist:\n\n"
                   "{core}.\n\nKönnten Sie das bitte mit einer Antwort auf diese E-Mail bestätigen? Falls es nicht möglich ist oder Sie eine andere Uhrzeit vorschlagen, sagen Sie es uns, dann klären wir es mit {guest_short}.\n\n"
                   "Vielen Dank,\nSasha (KI-Concierge, Kanoe Technologies SL), im Auftrag von {guest_short}")},
    "en": {"confirm": ("Confirming the booking under the name {name}",
                       "Hello, this is {disclosure}. We just spoke on the phone, and I'm writing to put in writing the booking you confirmed:\n\n"
                       "{core}.\n\nIf anything isn't right, please reply to this email and we'll correct it. For any change, write to us here: {me}.\n\n"
                       "Thank you,\nSasha (AI concierge, Kanoe Technologies SL), for {guest_short}"),
           "ask": ("Could you confirm the booking under the name {name}?",
                   "Hello, this is {disclosure}. I just spoke with you on the phone, and it wasn't clear to me whether the booking was confirmed:\n\n"
                   "{core}.\n\nCould you confirm by replying to this email? If it isn't possible, or you'd suggest another time, tell us and we'll check with {guest_short}.\n\n"
                   "Thank you,\nSasha (AI concierge, Kanoe Technologies SL), for {guest_short}")},
}


def restatement(lang_code: str, o: Mapping[str, Any]) -> str:
    """What, how many, when and the name, in the venue's language — the call's own closing recap, without its question."""
    from . import calls as C, render as R
    lang = C.LANGUAGES[_lang_key(lang_code)]
    s = R.recap(lang, o).strip()
    pre, _under, q = R._RECAP_PREFIX.get(lang_code, R._RECAP_PREFIX["en"])
    if s.endswith(q):
        s = s[: -len(q)].strip()
    if s.startswith(pre):
        s = s[len(pre):].strip()
    s = s.rstrip(".").strip()
    what = R.activity_phrase(lang, o)
    if what and what.casefold() not in s.casefold():   # a table's recap omits "una mesa": the email says what was booked
        s = f"{what}: {s[:1].lower() + s[1:]}"
    return s[:1].upper() + s[1:]


def compose(kind: str, lang_code: str, o: Mapping[str, Any], to: str, bcc: Optional[str], email_id: str,
            own_ref: Optional[str] = None) -> dict:
    from .wordings import DISCLOSURE
    from .i18n import emails as I18N   # CR 7 i18n
    if lang_code in I18N.LANGS and I18N.usable(lang_code, to):
        return I18N.followup_email(kind, lang_code, o, to, bcc, email_id, own_email() or os.getenv("SASHA_EMAIL_FROM", ""), own_ref)
    lang = lang_code if lang_code in _FU else "en"
    subj, body = _FU[lang][kind]
    name = o["who"]["name"]
    me = own_email() or os.getenv("SASHA_EMAIL_FROM", "")
    email = {"from": os.getenv("SASHA_EMAIL_FROM", "").strip(), "to": to, "reply_to": E.act_address(email_id),
             "subject": subj.format(name=name) + (f" · Ref. {own_ref}" if own_ref else ""),
             # Sasha 88 · her own reference, as she said it on the call, under the booking it restates
             "text": body.format(disclosure=DISCLOSURE.get(lang, DISCLOSURE["en"]),
                                 core=restatement(lang, o) + (f" (Ref. {own_ref})" if own_ref else ""), me=me, guest_short=name)}
    if bcc:
        email["bcc"] = bcc
    return email


def followup_id(call_id: str, kind: str) -> str:
    return str(uuid.uuid5(_NS, f"{call_id}:{kind}"))


async def after_call(call: Mapping[str, Any], outcome: Optional[str], now: datetime) -> Optional[str]:
    """Rules 2–3 · once a booking call's reading is recorded: the confirmation (yes) or the could-you-confirm (unclear)
    email, as the guest's yes already covered. Returns what happened, in words (for the log and the tests)."""
    from . import ladder_routes as LR
    from .ladder import emails_ready
    brief = call.get("brief") or {}
    fu = brief.get("followup")
    if brief.get("purpose") != "book" or outcome not in ("yes", "unclear") or not fu:
        return None
    kind = "confirm" if outcome == "yes" else "ask"
    why = emails_ready()
    if why:
        log.error("[followup] call %s: the %s email was promised but %s — nothing sent", call.get("call_id"), kind, why)
        return f"not sent: {why}"
    o = fu.get("request")
    if not isinstance(o, dict) or not o.get("what"):
        log.error("[followup] call %s: no reservation object to restate — nothing sent", call.get("call_id"))
        return "not sent: no reservation object"
    email_id = followup_id(str(call["call_id"]), kind)
    store = LR.LADDER_STORE
    if await store.email_exists(email_id):
        return "already sent"
    email = compose(kind, brief.get("language") or "en", o, fu["to"], fu.get("bcc"), email_id, brief.get("own_reference"))
    venue_key = str(brief.get("venue_key") or "")
    row = {"email_id": email_id, "account_id": str(call["account_id"]), "read_id": venue_key[5:] if venue_key.startswith("read:") else None,
           "email": email, "email_sha256": E.email_sha256(email), "read_back_lines": call["read_back_lines"],
           "read_back_sha256": call["read_back_sha256"], "created_at": now}
    if not row["read_id"]:
        return "not sent: the call has no venue read"
    try:
        await store.put_followup_email(row, str(call["trip_item_id"]))
    except Exception as e:   # a duplicate id means it already exists: never twice
        log.warning("[followup] call %s: the %s email was not recorded (%s: %s)", call.get("call_id"), kind, type(e).__name__, e)
        return "not recorded"
    approval = {"how": "auto", "after_call": str(call["call_id"]), "kind": kind, "outcome": outcome,
                "covered_by_read_back_sha256": call["read_back_sha256"], "at": now.isoformat()}
    claimed = await store.claim_email(str(call["account_id"]), email_id, approval, now, now - LR.APPROVAL_WINDOW,
                                      LR.email_cap(), LR.cap_window(now), LR.account_email_cap())
    if claimed != "claimed":
        log.error("[followup] call %s: the %s email was not sent (%s)", call.get("call_id"), kind, claimed)
        return f"not sent: {claimed}"
    sent = await E.send(LR.HTTP, email)
    await store.mark_sent(email_id, sent, now)
    return "sent" if sent.sent else f"not sent: {sent.why}"


SMS_ASK = {"es": "Hola, soy Sasha (Kanoe Technologies SL). Les llamé por esta reserva y se cortó: {what}. ¿Nos la pueden "
                  "confirmar respondiendo a este SMS? Gracias.",
           "en": "Hello, this is Sasha (Kanoe Technologies SL). I called about this booking and we were cut off: {what}. Could "
                 "you confirm it by replying to this text? Thank you."}


async def sms_ask(call: Mapping[str, Any]) -> str:
    """Sasha 108 · an unclear booking with no email to ask: a text to the MOBILE the venue publishes, from Sasha's own
    number (SASHA_SMS_TO_VENUES), whose reply lands on the booking (inbound_phone). Returns what happened, in words."""
    from . import cancel_routes as CNR, guest_receipt as GR, ladder_routes as LR
    brief = call.get("brief") or {}
    o = (brief.get("followup") or {}).get("request") or call.get("request")
    venue_key = str(brief.get("venue_key") or "")
    if not isinstance(o, dict) or not venue_key.startswith("read:"):
        return "sms not sent: no reservation or venue read to restate"
    row = await LR.LADDER_STORE.get_read(str(call["account_id"]), venue_key[5:])
    mob = CNR._mobile(((row or {}).get("read") or {}).get("facts") or [])
    if not mob:
        return "sms not sent: the venue publishes no mobile"
    lang = (brief.get("language") or "en")[:2]
    text = SMS_ASK.get(lang, SMS_ASK["en"]).format(what=restatement(brief.get("language") or "en", o))
    return await GR.send_sms(mob, text, "SASHA_SMS_TO_VENUES")


# ── rule 3 · the venue's reply, read with the field checks ───────────────────────────────────────────────────────────

#: where a mail client starts quoting our own email: "On … wrote:", "El … escribió:", "Le … a écrit :", "Il … ha scritto:",
#: "Am … schrieb …:", "Em … escreveu:", an Outlook header block, or a ">" line — however long the attribution line is
_QUOTE_START = re.compile(
    r"^\s*(?:>|-{2,}\s*(?:original message|mensaje original|mensagem original|message d'origine|messaggio originale|ursprüngliche nachricht)"
    r"|(?:from|de|von|da|de\s*:)\s*:.*@"
    r"|.*\b(?:wrote|escribi[oó]|a écrit|ha scritto|schrieb|escreveu)\s*:?\s*$)", re.I)


#: a written yes, beyond the spoken one (recap._YES): the words a venue writes when it books it (folded: no accents)
_WRITTEN_YES = re.compile(r"\b(confirmad[oa]s?|confirmamos|lo confirmo|reservad[oa]s?|queda reservad[oa]|tienen la reserva|"
                          r"confirmed|booked|reserved|all set|"
                          r"confirme[e]?s?|reserve[e]?s?|"
                          r"confermat[oa]|prenotat[oa]|"
                          r"bestatigt|gebucht|reserviert)\b")


def own_words(text: Optional[str]) -> str:
    """What they WROTE, without the quote of our own email beneath it — so a bare "Sí" never confirms by our own words."""
    out = []
    for line in str(text or "").splitlines():
        if _QUOTE_START.match(line):
            break
        out.append(line)
    return "\n".join(out).strip()


def reply_reading(text: Optional[str], o: Mapping[str, Any]) -> dict:
    """{result: confirmed | proposed | declined | none, why, quote}. Conservative: only an explicit yes that restates the
    day, time and number, with nothing different, confirms. Never the reverse of what was written."""
    from . import heard as H, recap as RC
    t = " ".join(str(text or "").split())
    if not t:
        return {"result": "none", "why": "the reply had no text to read", "quote": None}
    body = own_words(text)   # their words, never our quoted email
    asked = H.asked_from(o)
    off = H.mismatches([body], asked)
    times = [m for m in off if m["what"] == "time"]
    if times:
        return {"result": "proposed", "why": f"they wrote another time: \"{times[0]['quote'][:200]}\"", "quote": times[0]["quote"][:300]}
    f = RC._f(body)
    yes = bool(RC._YES.search(f) or _WRITTEN_YES.search(f))
    no = bool(RC._NO.search(f))
    if no and not yes:
        return {"result": "declined", "why": "they wrote no", "quote": body.strip()[:300]}
    if yes and not no and not off and RC.restates(body, asked):   # any "no" in it: never read as a confirmation
        return {"result": "confirmed", "why": "an explicit yes restating the day, time and number", "quote": body.strip()[:300]}
    return {"result": "none", "why": "the reply neither confirms the day, time and number nor proposes another time — shown as written",
            "quote": body.strip()[:300]}


async def on_reply(email_id: str, text: Optional[str], now: datetime) -> Optional[dict]:
    """A reply to Sasha's email — the follow-up after a call, or an email-rung request (Sasha 75): read it, and move the
    reservation only as far as its words go."""
    from . import call_routes as CR, ladder_routes as LR
    e = await LR.LADDER_STORE.email_any(email_id)
    if not e:
        return None
    if (e.get("approval") or {}).get("kind") == "cancel":
        # Sasha 99 · a reply to Sasha's CANCEL email: cancelled only if their words say so
        from .cancel_routes import cancel_reading, _record
        r = cancel_reading(text)
        await _record(str(e["account_id"]), str(e.get("trip_item_id")), "email", r, text or "",
                      f"their reply to Sasha's cancellation email: {r['why']}", now)
        if r["result"] == "cancelled":
            from . import guest_receipt as GR
            await GR.send_for_route(str(e["account_id"]), (e.get("email") or {}).get("to") or "the venue", "their reply to Sasha's email",
                                    "Cancelled by the venue", {"their_words": text, "trip_item_id": e.get("trip_item_id")})
        return r
    after = (e.get("approval") or {}).get("after_call")
    if after:
        call = await CR.CALL_STORE.get_call(str(e["account_id"]), after)
        o = (((call or {}).get("brief") or {}).get("followup") or {}).get("request")
    else:
        o = await LR.LADDER_STORE.request_of_email(email_id)   # the email rung's own reservation/1 object
    if not isinstance(o, dict):
        return None
    r = reply_reading(text, o)
    # Sasha 157 · their written no is DECLINED (their words are shown with it); before, it was filed as unclear
    status = {"confirmed": "confirmed", "proposed": "proposed", "declined": "declined"}.get(r["result"])
    if status:
        await LR.LADDER_STORE.reply_outcome(email_id, status, {"confirmed": "confirmed", "declined": "declined"}.get(status, "unclear"),
                                            text or "", now)
    return r


__all__ = ["own_email", "spoken", "venue_email", "with_own_contact", "after_call", "reply_reading", "on_reply", "followup_id", "compose", "restatement"]
