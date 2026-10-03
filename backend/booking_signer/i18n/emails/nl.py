"""Dutch (nl) · ⚠ AI-written, NOT native-reviewed (STATUS). Formal "u"; Netherlands usage (Flemish readers will follow it)."""
CODE, NAME, STATUS = "nl", "Dutch", "ai_unreviewed"
DISCLOSURE = "Sasha, een AI-conciërge van Kanoe Technologies SL"
TABLE = "een tafel"


def count(n: int) -> str:
    return "1 persoon" if n == 1 else f"{n} personen"


CORE = "{what} — op {d} om {t}, voor {n}, op naam van {name}"
_SIGN = "Sasha (AI-conciërge, Kanoe Technologies SL), namens {guest_short}"
T = {
    "request_table": ("Reserveringsaanvraag tafel — {n}, {d} om {t}",
                      "Goedendag, u spreekt met {disclosure}. Ik schrijf namens {who} met het verzoek om een tafel voor {n} op {d} om {t}.\n\n"
                      "Zou u op deze e-mail willen antwoorden om de reservering te bevestigen, of ons laten weten als het niet mogelijk is?\n\n"
                      "Een aanbetaling of een ander tijdstip kunnen wij per e-mail niet namens {guest_short} toezeggen; als dat nodig is, laat het ons dan weten, dan beslist {guest_short} zelf.\n\n"
                      "Met vriendelijke groet,\n" + _SIGN),
    "request_generic": ("Reserveringsaanvraag — {what}, {d} om {t}",
                        "Goedendag, u spreekt met {disclosure}. Ik schrijf namens {who} met het verzoek om {what} te reserveren voor {n} op {d} om {t}.\n\n"
                        "Zou u op deze e-mail willen antwoorden om de reservering te bevestigen, of ons laten weten als het niet mogelijk is?\n\n"
                        "Een aanbetaling, kosten of een ander tijdstip kunnen wij per e-mail niet namens {guest_short} toezeggen; als dat nodig is, laat het ons dan weten, dan beslist {guest_short} zelf.\n\n"
                        "Met vriendelijke groet,\n" + _SIGN),
    "cancel": ("Annulering van de reservering op naam van {name}",
               "Goedendag, u spreekt met {disclosure}. Ik schrijf namens {name} om de volgende reservering te annuleren:\n\n{core}.\n\n"
               "Zou u de annulering willen bevestigen door op deze e-mail te antwoorden? Hartelijk dank.\n\n"
               "Sasha (AI-conciërge, Kanoe Technologies SL), namens {name}"),
    "confirm": ("Bevestiging van de reservering op naam van {name}",
                "Goedendag, u spreekt met {disclosure}. We spraken elkaar zojuist telefonisch, en ik leg hierbij schriftelijk vast welke reservering u ons heeft bevestigd:\n\n{core}.\n\n"
                "Klopt er iets niet, antwoord dan op deze e-mail, dan passen we het aan. Voor wijzigingen kunt u ons hier schrijven: {me}.\n\n"
                "Met vriendelijke groet,\n" + _SIGN),
    "ask": ("Kunt u de reservering op naam van {name} bevestigen?",
            "Goedendag, u spreekt met {disclosure}. Ik heb u zojuist telefonisch gesproken, maar het is mij niet duidelijk of de reservering is bevestigd:\n\n{core}.\n\n"
            "Zou u dat willen bevestigen door op deze e-mail te antwoorden? Als het niet mogelijk is, of als u een ander tijdstip voorstelt, laat het ons dan weten; dan overleggen we met {guest_short}.\n\n"
            "Met vriendelijke groet,\n" + _SIGN),
}
BACK = {
    "request_table": ("Table reservation request — {n}, {d} at {t}",
                      "Good day, you are speaking with Sasha, an AI concierge from Kanoe Technologies SL. I am writing on behalf of {who} with the request for a table for {n} on {d} at {t}.\n\n"
                      "Would you reply to this email to confirm the reservation, or let us know if it is not possible?\n\n"
                      "We cannot promise a deposit or another time by email on behalf of {guest_short}; if that is needed, let us know, then {guest_short} decides themselves.\n\n"
                      "Kind regards,\nSasha (AI concierge, Kanoe Technologies SL), on behalf of {guest_short}"),
    "request_generic": ("Reservation request — {what}, {d} at {t}",
                        "Good day, you are speaking with Sasha, … I am writing on behalf of {who} with the request to reserve {what} for {n} on {d} at {t}.\n\n"
                        "Would you reply to this email to confirm the reservation, or let us know if it is not possible?\n\n"
                        "We cannot promise a deposit, costs or another time by email on behalf of {guest_short}; if that is needed, let us know, then {guest_short} decides themselves.\n\n"
                        "Kind regards,\nSasha (…), on behalf of {guest_short}"),
    "cancel": ("Cancellation of the reservation in the name of {name}",
               "Good day, you are speaking with Sasha, … I am writing on behalf of {name} to cancel the following reservation:\n\n{core}.\n\n"
               "Would you confirm the cancellation by replying to this email? Many thanks.\n\nSasha (…), on behalf of {name}"),
    "confirm": ("Confirmation of the reservation in the name of {name}",
                "Good day, you are speaking with Sasha, … We just spoke by phone, and I hereby record in writing which reservation you confirmed to us:\n\n{core}.\n\n"
                "If something is not right, reply to this email and we will adjust it. For changes you can write to us here: {me}.\n\nKind regards,\nSasha (…), on behalf of {guest_short}"),
    "ask": ("Can you confirm the reservation in the name of {name}?",
            "Good day, you are speaking with Sasha, … I just spoke with you by phone, but it is not clear to me whether the reservation has been confirmed:\n\n{core}.\n\n"
            "Would you confirm that by replying to this email? If it is not possible, or if you propose another time, let us know; then we will consult {guest_short}.\n\nKind regards,\nSasha (…), on behalf of {guest_short}"),
}
CORE_BACK = "{what} — on {d} at {t}, for {n}, in the name of {name}"
