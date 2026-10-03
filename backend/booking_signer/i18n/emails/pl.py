"""Polish (pl) · ⚠ AI-written, NOT native-reviewed (STATUS). Formal "Państwo". Counts in the accusative after "na", as
Poles book: na 1 osobę · na 2–4 osoby · na 5–21 osób · na 22–24 osoby. Names follow "w imieniu:" / "na nazwisko" so they
never need declining."""
CODE, NAME, STATUS = "pl", "Polish", "ai_unreviewed"
from booking_signer.wordings import DISCLOSURE as _DISCLOSURE  # noqa: E402  (the single source: calls and emails)
DISCLOSURE = _DISCLOSURE["pl"]
TABLE = "stolik"


def count(n: int) -> str:
    """The accusative after "na": osobę (1) · osoby (x2–x4, not 12–14) · osób (otherwise)."""
    if n == 1:
        return "1 osobę"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} osoby"
    return f"{n} osób"


CORE = "{what} — {d} o {t}, na {n}, na nazwisko {name}"
_SIGN = "Sasha (konsjerżka AI, Kanoe Technologies SL), w imieniu: {guest_short}"
T = {
    "request_table": ("Prośba o rezerwację stolika — na {n}, {d} o {t}",
                      "Dzień dobry, piszę jako {disclosure}. Piszę w imieniu: {who}, z prośbą o rezerwację stolika na {n} na {d} o godz. {t}.\n\n"
                      "Czy mogliby Państwo odpowiedzieć na tę wiadomość, aby potwierdzić rezerwację, lub dać nam znać, jeśli nie jest to możliwe?\n\n"
                      "Nie możemy mailowo zgodzić się w imieniu {guest_short} na zadatek ani na inną godzinę; jeśli to konieczne, prosimy o informację — decyzję podejmie {guest_short}.\n\n"
                      "Dziękuję,\n" + _SIGN),
    "request_generic": ("Prośba o rezerwację — {what}, {d} o {t}",
                        "Dzień dobry, piszę jako {disclosure}. Piszę w imieniu: {who}, z prośbą o rezerwację: {what}, na {n}, na {d} o godz. {t}.\n\n"
                        "Czy mogliby Państwo odpowiedzieć na tę wiadomość, aby potwierdzić rezerwację, lub dać nam znać, jeśli nie jest to możliwe?\n\n"
                        "Nie możemy mailowo zgodzić się w imieniu {guest_short} na zadatek, opłaty ani na inną godzinę; jeśli to konieczne, prosimy o informację — decyzję podejmie {guest_short}.\n\n"
                        "Dziękuję,\n" + _SIGN),
    "cancel": ("Odwołanie rezerwacji na nazwisko {name}",
               "Dzień dobry, piszę jako {disclosure}. Piszę w imieniu: {name}, aby odwołać następującą rezerwację:\n\n{core}.\n\n"
               "Czy mogliby Państwo potwierdzić odwołanie, odpowiadając na tę wiadomość? Serdecznie dziękuję.\n\n"
               "Sasha (konsjerżka AI, Kanoe Technologies SL), w imieniu: {name}"),
    "confirm": ("Potwierdzenie rezerwacji na nazwisko {name}",
                "Dzień dobry, piszę jako {disclosure}. Przed chwilą rozmawialiśmy telefonicznie i piszę, aby potwierdzić na piśmie rezerwację, którą Państwo potwierdzili:\n\n{core}.\n\n"
                "Jeśli coś się nie zgadza, prosimy o odpowiedź na tę wiadomość — poprawimy to. W sprawie zmian prosimy pisać tutaj: {me}.\n\n"
                "Dziękuję,\n" + _SIGN),
    "ask": ("Czy mogliby Państwo potwierdzić rezerwację na nazwisko {name}?",
            "Dzień dobry, piszę jako {disclosure}. Przed chwilą rozmawiałam z Państwem telefonicznie, ale nie jest dla mnie jasne, czy rezerwacja została potwierdzona:\n\n{core}.\n\n"
            "Czy mogliby Państwo potwierdzić to, odpowiadając na tę wiadomość? Jeśli nie jest to możliwe lub proponują Państwo inną godzinę, prosimy o informację — skonsultujemy to z {guest_short}.\n\n"
            "Dziękuję,\n" + _SIGN),
}
BACK = {
    "request_table": ("Request to book a table — for {n}, {d} at {t}",
                      "Good day, I am writing as Sasha, a concierge based on artificial intelligence, run by Kanoe Technologies SL. I am writing on behalf of: {who}, with a request to book a table for {n} on {d} at {t}.\n\n"
                      "Could you reply to this message to confirm the booking, or let us know if it is not possible?\n\n"
                      "We cannot agree by email on behalf of {guest_short} to a deposit or to another time; if necessary, please let us know — {guest_short} will make the decision.\n\n"
                      "Thank you,\nSasha (AI concierge, Kanoe Technologies SL), on behalf of: {guest_short}"),
    "request_generic": ("Booking request — {what}, {d} at {t}",
                        "Good day, I am writing as Sasha, … I am writing on behalf of: {who}, with a request to book: {what}, for {n}, on {d} at {t}.\n\n"
                        "Could you reply to this message to confirm the booking, or let us know if it is not possible?\n\n"
                        "We cannot agree by email on behalf of {guest_short} to a deposit, fees or another time; if necessary, please let us know — {guest_short} will make the decision.\n\n"
                        "Thank you,\nSasha (…), on behalf of: {guest_short}"),
    "cancel": ("Cancelling the booking in the name of {name}",
               "Good day, I am writing as Sasha, … I am writing on behalf of: {name}, to cancel the following booking:\n\n{core}.\n\n"
               "Could you confirm the cancellation by replying to this message? Warm thanks.\n\nSasha (…), on behalf of: {name}"),
    "confirm": ("Confirmation of the booking in the name of {name}",
                "Good day, I am writing as Sasha, … We spoke by phone a moment ago and I am writing to confirm in writing the booking that you confirmed:\n\n{core}.\n\n"
                "If something does not match, please reply to this message — we will correct it. About changes, please write here: {me}.\n\nThank you,\nSasha (…), on behalf of: {guest_short}"),
    "ask": ("Could you confirm the booking in the name of {name}?",
            "Good day, I am writing as Sasha, … A moment ago I spoke with you by phone, but it is not clear to me whether the booking was confirmed:\n\n{core}.\n\n"
            "Could you confirm this by replying to this message? If it is not possible or you propose another time, please let us know — we will consult {guest_short}.\n\nThank you,\nSasha (…), on behalf of: {guest_short}"),
}
CORE_BACK = "{what} — {d} at {t}, for {n}, in the name of {name}"
