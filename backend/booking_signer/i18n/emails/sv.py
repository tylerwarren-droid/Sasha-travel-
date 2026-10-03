"""Swedish (sv) · ⚠ AI-written, NOT native-reviewed (STATUS). Polite but plain ("du"-reform register; Swedish business
email does not use "Ni" today — the reviewer should confirm)."""
CODE, NAME, STATUS = "sv", "Swedish", "ai_unreviewed"
from booking_signer.wordings import DISCLOSURE as _DISCLOSURE  # noqa: E402  (the single source: calls and emails)
DISCLOSURE = _DISCLOSURE["sv"]
TABLE = "ett bord"


def count(n: int) -> str:
    return "1 person" if n == 1 else f"{n} personer"


CORE = "{what} — {d} kl. {t}, för {n}, i namnet {name}"
_SIGN = "Sasha (AI-concierge, Kanoe Technologies SL), för {guest_short}"
T = {
    "request_table": ("Bordsförfrågan — {n}, {d} kl. {t}",
                      "Hej, här är {disclosure}. Jag skriver på uppdrag av {who} och vill boka ett bord för {n} den {d} kl. {t}.\n\n"
                      "Kan ni svara på det här mejlet för att bekräfta, eller meddela oss om det inte går?\n\n"
                      "Vi kan inte via mejl godkänna en handpenning eller en annan tid på uppdrag av {guest_short}; om det behövs, säg till så bestämmer {guest_short} själv.\n\n"
                      "Tack,\n" + _SIGN),
    "request_generic": ("Bokningsförfrågan — {what}, {d} kl. {t}",
                        "Hej, här är {disclosure}. Jag skriver på uppdrag av {who} och vill boka {what} för {n} den {d} kl. {t}.\n\n"
                        "Kan ni svara på det här mejlet för att bekräfta, eller meddela oss om det inte går?\n\n"
                        "Vi kan inte via mejl godkänna en handpenning, avgifter eller en annan tid på uppdrag av {guest_short}; om det behövs, säg till så bestämmer {guest_short} själv.\n\n"
                        "Tack,\n" + _SIGN),
    "cancel": ("Avbokning av bokningen i namnet {name}",
               "Hej, här är {disclosure}. Jag skriver på uppdrag av {name} för att avboka följande bokning:\n\n{core}.\n\n"
               "Kan ni bekräfta avbokningen genom att svara på det här mejlet? Stort tack.\n\n"
               "Sasha (AI-concierge, Kanoe Technologies SL), för {name}"),
    "confirm": ("Bekräftelse av bokningen i namnet {name}",
                "Hej, här är {disclosure}. Vi talades vid i telefon alldeles nyss, och jag skriver för att skriftligen bekräfta bokningen som ni bekräftade:\n\n{core}.\n\n"
                "Om något inte stämmer, svara på det här mejlet så rättar vi det. För ändringar kan ni skriva till oss här: {me}.\n\n"
                "Tack,\n" + _SIGN),
    "ask": ("Kan ni bekräfta bokningen i namnet {name}?",
            "Hej, här är {disclosure}. Jag talade med er i telefon alldeles nyss, men det framgick inte tydligt om bokningen blev bekräftad:\n\n{core}.\n\n"
            "Kan ni bekräfta det genom att svara på det här mejlet? Om det inte går, eller om ni föreslår en annan tid, meddela oss så stämmer vi av med {guest_short}.\n\n"
            "Tack,\n" + _SIGN),
}
BACK = {
    "request_table": ("Table inquiry — {n}, {d} at {t}",
                      "Hi, this is Sasha, an AI concierge run by Kanoe Technologies SL. I am writing on behalf of {who} and would like to book a table for {n} on {d} at {t}.\n\n"
                      "Can you reply to this email to confirm, or let us know if it doesn't work?\n\n"
                      "We cannot approve a deposit or another time by email on behalf of {guest_short}; if it's needed, say so and {guest_short} will decide themselves.\n\n"
                      "Thanks,\nSasha (AI concierge, Kanoe Technologies SL), for {guest_short}"),
    "request_generic": ("Booking inquiry — {what}, {d} at {t}",
                        "Hi, this is Sasha, … I am writing on behalf of {who} and would like to book {what} for {n} on {d} at {t}.\n\n"
                        "Can you reply to this email to confirm, or let us know if it doesn't work?\n\n"
                        "We cannot approve a deposit, fees or another time by email on behalf of {guest_short}; if it's needed, say so and {guest_short} will decide themselves.\n\n"
                        "Thanks,\nSasha (…), for {guest_short}"),
    "cancel": ("Cancellation of the booking in the name {name}",
               "Hi, this is Sasha, … I am writing on behalf of {name} to cancel the following booking:\n\n{core}.\n\n"
               "Can you confirm the cancellation by replying to this email? Big thanks.\n\nSasha (…), for {name}"),
    "confirm": ("Confirmation of the booking in the name {name}",
                "Hi, this is Sasha, … We spoke on the phone just now, and I am writing to confirm in writing the booking that you confirmed:\n\n{core}.\n\n"
                "If anything isn't right, reply to this email and we'll correct it. For changes you can write to us here: {me}.\n\nThanks,\nSasha (…), for {guest_short}"),
    "ask": ("Can you confirm the booking in the name {name}?",
            "Hi, this is Sasha, … I spoke with you on the phone just now, but it didn't come across clearly whether the booking was confirmed:\n\n{core}.\n\n"
            "Can you confirm it by replying to this email? If it doesn't work, or if you propose another time, let us know and we'll check with {guest_short}.\n\nThanks,\nSasha (…), for {guest_short}"),
}
CORE_BACK = "{what} — {d} at {t}, for {n}, in the name {name}"
