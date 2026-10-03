"""Russian (ru) · ⚠ AI-written, NOT native-reviewed (STATUS). Formal «Вы». Counts follow the number after «на»:
на 1 человека · на 2–4 человека · на 5–20 человек · на 21 человека · на 22 человека · на 25 человек."""
CODE, NAME, STATUS = "ru", "Russian", "ai_unreviewed"
DISCLOSURE = "Саша (Sasha), ИИ-консьерж, работающий от имени компании Kanoe Technologies SL"
TABLE = "столик"


def count(n: int) -> str:
    """The accusative after «на»: человека for x1 (not 11) and x2–x4 (not 12–14); человек otherwise."""
    if n % 10 in (1, 2, 3, 4) and n % 100 not in (11, 12, 13, 14):
        return f"{n} человека"
    return f"{n} человек"


CORE = "{what} — {d} в {t}, на {n}, на имя {name}"
_SIGN = "Саша (ИИ-консьерж, Kanoe Technologies SL), от имени {guest_short}"
T = {
    "request_table": ("Запрос на бронирование столика — на {n}, {d} в {t}",
                      "Здравствуйте! Вам пишет {disclosure}. Я пишу от имени {who}, чтобы забронировать столик на {n} {d} в {t}.\n\n"
                      "Не могли бы Вы ответить на это письмо, чтобы подтвердить бронирование, или сообщить нам, если это невозможно?\n\n"
                      "Мы не можем по электронной почте соглашаться от имени {guest_short} на предоплату или другое время; если это необходимо, пожалуйста, сообщите нам, и {guest_short} примет решение сам(а).\n\n"
                      "Спасибо,\n" + _SIGN),
    "request_generic": ("Запрос на бронирование — {what}, {d} в {t}",
                        "Здравствуйте! Вам пишет {disclosure}. Я пишу от имени {who}, чтобы забронировать {what} на {n} {d} в {t}.\n\n"
                        "Не могли бы Вы ответить на это письмо, чтобы подтвердить бронирование, или сообщить нам, если это невозможно?\n\n"
                        "Мы не можем по электронной почте соглашаться от имени {guest_short} на предоплату, сборы или другое время; если это необходимо, пожалуйста, сообщите нам, и {guest_short} примет решение сам(а).\n\n"
                        "Спасибо,\n" + _SIGN),
    "cancel": ("Отмена бронирования на имя {name}",
               "Здравствуйте! Вам пишет {disclosure}. Я пишу от имени {name}, чтобы отменить следующее бронирование:\n\n{core}.\n\n"
               "Не могли бы Вы подтвердить отмену ответом на это письмо? Большое спасибо.\n\n"
               "Саша (ИИ-консьерж, Kanoe Technologies SL), от имени {name}"),
    "confirm": ("Подтверждение бронирования на имя {name}",
                "Здравствуйте! Вам пишет {disclosure}. Мы только что говорили по телефону, и я пишу, чтобы письменно зафиксировать бронирование, которое Вы подтвердили:\n\n{core}.\n\n"
                "Если что-то указано неверно, пожалуйста, ответьте на это письмо — мы исправим. По любым изменениям пишите нам сюда: {me}.\n\n"
                "Спасибо,\n" + _SIGN),
    "ask": ("Не могли бы Вы подтвердить бронирование на имя {name}?",
            "Здравствуйте! Вам пишет {disclosure}. Я только что говорила с Вами по телефону, но мне не ясно, подтверждено ли бронирование:\n\n{core}.\n\n"
            "Не могли бы Вы подтвердить это ответом на это письмо? Если это невозможно или Вы предлагаете другое время, сообщите нам, пожалуйста, и мы согласуем это с {guest_short}.\n\n"
            "Спасибо,\n" + _SIGN),
}
BACK = {
    "request_table": ("Request to book a table — for {n}, {d} at {t}",
                      "Hello! Writing to you is Sasha, an AI concierge working on behalf of the company Kanoe Technologies SL. I am writing on behalf of {who} to book a table for {n} on {d} at {t}.\n\n"
                      "Could you reply to this letter to confirm the booking, or let us know if it is impossible?\n\n"
                      "We cannot agree by email on behalf of {guest_short} to prepayment or another time; if this is necessary, please let us know, and {guest_short} will decide him/herself.\n\n"
                      "Thank you,\nSasha (AI concierge, Kanoe Technologies SL), on behalf of {guest_short}"),
    "request_generic": ("Booking request — {what}, {d} at {t}",
                        "Hello! Writing to you is Sasha, … I am writing on behalf of {who} to book {what} for {n} on {d} at {t}.\n\n"
                        "Could you reply to this letter to confirm the booking, or let us know if it is impossible?\n\n"
                        "We cannot agree by email on behalf of {guest_short} to prepayment, fees or another time; if this is necessary, please let us know, and {guest_short} will decide him/herself.\n\n"
                        "Thank you,\nSasha (…), on behalf of {guest_short}"),
    "cancel": ("Cancellation of the booking in the name of {name}",
               "Hello! Writing to you is Sasha, … I am writing on behalf of {name} to cancel the following booking:\n\n{core}.\n\n"
               "Could you confirm the cancellation by replying to this letter? Thank you very much.\n\nSasha (…), on behalf of {name}"),
    "confirm": ("Confirmation of the booking in the name of {name}",
                "Hello! Writing to you is Sasha, … We just spoke on the phone, and I am writing to record in writing the booking that you confirmed:\n\n{core}.\n\n"
                "If something is stated incorrectly, please reply to this letter — we will correct it. For any changes write to us here: {me}.\n\nThank you,\nSasha (…), on behalf of {guest_short}"),
    "ask": ("Could you confirm the booking in the name of {name}?",
            "Hello! Writing to you is Sasha, … I just spoke with you on the phone, but it is not clear to me whether the booking is confirmed:\n\n{core}.\n\n"
            "Could you confirm this by replying to this letter? If it is impossible or you propose another time, please let us know, and we will agree it with {guest_short}.\n\nThank you,\nSasha (…), on behalf of {guest_short}"),
}
CORE_BACK = "{what} — {d} at {t}, for {n}, in the name of {name}"
