"""Arabic, Modern Standard (ar) · ⚠ AI-written, NOT native-reviewed (STATUS). Formal MSA, plural address (حضراتكم).
Digits are Western Arabic (0–9) for dates/times/counts — the reviewer may prefer Eastern Arabic (٠–٩) for some markets."""
CODE, NAME, STATUS = "ar", "Arabic", "ai_unreviewed"
DISCLOSURE = "ساشا، مساعدة استقبال (كونسيرج) تعمل بالذكاء الاصطناعي وتديرها شركة Kanoe Technologies SL"
TABLE = "طاولة"


def count(n: int) -> str:
    """1 شخص واحد · 2 شخصين (dual, after لعدد) · 3–10 n أشخاص · 11+ n شخصًا."""
    if n == 1:
        return "شخص واحد"
    if n == 2:
        return "شخصين"
    if 3 <= n <= 10:
        return f"{n} أشخاص"
    return f"{n} شخصًا"


CORE = "{what} — بتاريخ {d} الساعة {t}، لعدد {n}، باسم {name}"
_SIGN = "ساشا (مساعدة استقبال بالذكاء الاصطناعي، Kanoe Technologies SL)، نيابةً عن {guest_short}"
T = {
    "request_table": ("طلب حجز طاولة — لعدد {n}، بتاريخ {d} الساعة {t}",
                      "مرحبًا، معكم {disclosure}. أكتب إليكم نيابةً عن {who} لطلب حجز طاولة لعدد {n} بتاريخ {d} الساعة {t}.\n\n"
                      "هل يمكنكم الرد على هذه الرسالة للتأكيد، أو إعلامنا إن لم يكن ذلك ممكنًا؟\n\n"
                      "لا يمكننا الموافقة عبر البريد الإلكتروني نيابةً عن {guest_short} على دفع عربون أو تغيير الموعد؛ إن لزم ذلك، يُرجى إخبارنا وسيقرر {guest_short} بنفسه.\n\n"
                      "شكرًا لكم،\n" + _SIGN),
    "request_generic": ("طلب حجز — {what}، بتاريخ {d} الساعة {t}",
                        "مرحبًا، معكم {disclosure}. أكتب إليكم نيابةً عن {who} لطلب حجز {what} لعدد {n} بتاريخ {d} الساعة {t}.\n\n"
                        "هل يمكنكم الرد على هذه الرسالة للتأكيد، أو إعلامنا إن لم يكن ذلك ممكنًا؟\n\n"
                        "لا يمكننا الموافقة عبر البريد الإلكتروني نيابةً عن {guest_short} على دفع عربون أو رسوم أو تغيير الموعد؛ إن لزم ذلك، يُرجى إخبارنا وسيقرر {guest_short} بنفسه.\n\n"
                        "شكرًا لكم،\n" + _SIGN),
    "cancel": ("إلغاء الحجز باسم {name}",
               "مرحبًا، معكم {disclosure}. أكتب إليكم نيابةً عن {name} لإلغاء الحجز التالي:\n\n{core}.\n\n"
               "هل يمكنكم تأكيد الإلغاء بالرد على هذه الرسالة؟ شكرًا جزيلًا.\n\n"
               "ساشا (مساعدة استقبال بالذكاء الاصطناعي، Kanoe Technologies SL)، نيابةً عن {name}"),
    "confirm": ("تأكيد الحجز باسم {name}",
                "مرحبًا، معكم {disclosure}. تحدثنا قبل قليل عبر الهاتف، وأكتب إليكم لتوثيق الحجز الذي أكدتموه كتابيًا:\n\n{core}.\n\n"
                "إن كان هناك أي خطأ، يُرجى الرد على هذه الرسالة وسنصححه. ولأي تغيير، راسلونا هنا: {me}.\n\n"
                "شكرًا لكم،\n" + _SIGN),
    "ask": ("هل يمكنكم تأكيد الحجز باسم {name}؟",
            "مرحبًا، معكم {disclosure}. تحدثت معكم قبل قليل عبر الهاتف، ولم يتضح لي إن كان الحجز قد تأكد:\n\n{core}.\n\n"
            "هل يمكنكم التأكيد بالرد على هذه الرسالة؟ إن لم يكن ذلك ممكنًا، أو إن اقترحتم موعدًا آخر، يُرجى إخبارنا وسنستشير {guest_short}.\n\n"
            "شكرًا لكم،\n" + _SIGN),
}
BACK = {
    "request_table": ("Table booking request — for {n}, on {d} at {t}",
                      "Hello, with you is Sasha, a reception assistant (concierge) working with artificial intelligence and run by Kanoe Technologies SL. I am writing to you on behalf of {who} to request booking a table for {n} on {d} at {t}.\n\n"
                      "Could you reply to this message to confirm, or let us know if that is not possible?\n\n"
                      "We cannot agree by email on behalf of {guest_short} to paying a deposit or changing the time; if that is needed, please tell us and {guest_short} will decide personally.\n\n"
                      "Thank you,\nSasha (AI reception assistant, Kanoe Technologies SL), on behalf of {guest_short}"),
    "request_generic": ("Booking request — {what}, on {d} at {t}",
                        "Hello, with you is Sasha, … I am writing to you on behalf of {who} to request booking {what} for {n} on {d} at {t}.\n\n"
                        "Could you reply to this message to confirm, or let us know if that is not possible?\n\n"
                        "We cannot agree by email on behalf of {guest_short} to paying a deposit, fees or changing the time; if that is needed, please tell us and {guest_short} will decide personally.\n\n"
                        "Thank you,\nSasha (…), on behalf of {guest_short}"),
    "cancel": ("Cancelling the booking in the name of {name}",
               "Hello, with you is Sasha, … I am writing to you on behalf of {name} to cancel the following booking:\n\n{core}.\n\n"
               "Could you confirm the cancellation by replying to this message? Many thanks.\n\nSasha (…), on behalf of {name}"),
    "confirm": ("Confirming the booking in the name of {name}",
                "Hello, with you is Sasha, … We spoke a little while ago by phone, and I am writing to you to document in writing the booking you confirmed:\n\n{core}.\n\n"
                "If there is any error, please reply to this message and we will correct it. For any change, write to us here: {me}.\n\nThank you,\nSasha (…), on behalf of {guest_short}"),
    "ask": ("Could you confirm the booking in the name of {name}?",
            "Hello, with you is Sasha, … I spoke with you a little while ago by phone, and it was not clear to me whether the booking was confirmed:\n\n{core}.\n\n"
            "Could you confirm by replying to this message? If that is not possible, or if you propose another time, please tell us and we will consult {guest_short}.\n\nThank you,\nSasha (…), on behalf of {guest_short}"),
}
CORE_BACK = "{what} — on {d} at {t}, for {n}, in the name of {name}"
