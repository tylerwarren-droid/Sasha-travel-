"""Turkish (tr) · ⚠ AI-written, NOT native-reviewed (STATUS). Formal "siz". The disclosure is wordings.DISCLOSURE["tr"]
VERBATIM (already used on calls/WhatsApp), so the venue reads the same words it hears."""
CODE, NAME, STATUS = "tr", "Turkish", "ai_unreviewed"
DISCLOSURE = "Sasha; Kanoe Technologies SL tarafından işletilen bir yapay zekâ konsiyerjiyim"
TABLE = "bir masa"


def count(n: int) -> str:
    return f"{n} kişilik"


CORE = "{what} — {d} tarihinde saat {t}, {n}, {name} adına"
_SIGN = "Sasha (yapay zekâ konsiyerji, Kanoe Technologies SL), {guest_short} adına"
T = {
    "request_table": ("Masa rezervasyonu talebi — {n}, {d} saat {t}",
                      "Merhaba, ben {disclosure}. {who} adına, {d} tarihinde saat {t} için {n} bir masa rica etmek üzere yazıyorum.\n\n"
                      "Onaylamak için bu e-postayı yanıtlayabilir veya mümkün değilse bize bildirebilir misiniz?\n\n"
                      "{guest_short} adına e-posta ile kapora veya farklı bir saat kabul edemeyiz; gerekirse lütfen bize bildirin, kararı {guest_short} kendisi verecektir.\n\n"
                      "Teşekkürler,\n" + _SIGN),
    "request_generic": ("Rezervasyon talebi — {what}, {d} saat {t}",
                        "Merhaba, ben {disclosure}. {who} adına, {d} tarihinde saat {t} için {n} {what} rezervasyonu rica etmek üzere yazıyorum.\n\n"
                        "Onaylamak için bu e-postayı yanıtlayabilir veya mümkün değilse bize bildirebilir misiniz?\n\n"
                        "{guest_short} adına e-posta ile kapora, ücret veya farklı bir saat kabul edemeyiz; gerekirse lütfen bize bildirin, kararı {guest_short} kendisi verecektir.\n\n"
                        "Teşekkürler,\n" + _SIGN),
    "cancel": ("{name} adına yapılan rezervasyonun iptali",
               "Merhaba, ben {disclosure}. {name} adına aşağıdaki rezervasyonu iptal etmek için yazıyorum:\n\n{core}.\n\n"
               "Bu e-postayı yanıtlayarak iptali onaylayabilir misiniz? Çok teşekkür ederim.\n\n"
               "Sasha (yapay zekâ konsiyerji, Kanoe Technologies SL), {name} adına"),
    "confirm": ("{name} adına yapılan rezervasyonun onayı",
                "Merhaba, ben {disclosure}. Az önce telefonda görüştük; onayladığınız rezervasyonu yazılı olarak kayda geçirmek için yazıyorum:\n\n{core}.\n\n"
                "Yanlış bir şey varsa lütfen bu e-postayı yanıtlayın, düzeltelim. Herhangi bir değişiklik için bize buradan yazabilirsiniz: {me}.\n\n"
                "Teşekkürler,\n" + _SIGN),
    "ask": ("{name} adına yapılan rezervasyonu onaylayabilir misiniz?",
            "Merhaba, ben {disclosure}. Az önce sizinle telefonda görüştüm, ancak rezervasyonun onaylanıp onaylanmadığı net değildi:\n\n{core}.\n\n"
            "Bu e-postayı yanıtlayarak onaylayabilir misiniz? Mümkün değilse veya başka bir saat önerirseniz lütfen bize bildirin; {guest_short} ile görüşeceğiz.\n\n"
            "Teşekkürler,\n" + _SIGN),
}
BACK = {
    "request_table": ("Table reservation request — for {n}, {d} at {t}",
                      "Hello, I am Sasha; I am an artificial-intelligence concierge operated by Kanoe Technologies SL. On behalf of {who}, I am writing to request a table for {n} on {d} at {t}.\n\n"
                      "Could you reply to this email to confirm, or let us know if it is not possible?\n\n"
                      "We cannot accept a deposit or a different time by email on behalf of {guest_short}; if necessary, please let us know, {guest_short} will make the decision themselves.\n\n"
                      "Thanks,\nSasha (AI concierge, Kanoe Technologies SL), on behalf of {guest_short}"),
    "request_generic": ("Reservation request — {what}, {d} at {t}",
                        "Hello, I am Sasha; … On behalf of {who}, I am writing to request a reservation of {what} for {n} on {d} at {t}.\n\n"
                        "Could you reply to this email to confirm, or let us know if it is not possible?\n\n"
                        "We cannot accept a deposit, a fee or a different time by email on behalf of {guest_short}; if necessary, please let us know, {guest_short} will make the decision themselves.\n\n"
                        "Thanks,\nSasha (…), on behalf of {guest_short}"),
    "cancel": ("Cancellation of the reservation made in the name of {name}",
               "Hello, I am Sasha; … I am writing on behalf of {name} to cancel the following reservation:\n\n{core}.\n\n"
               "Could you confirm the cancellation by replying to this email? Thank you very much.\n\nSasha (…), on behalf of {name}"),
    "confirm": ("Confirmation of the reservation made in the name of {name}",
                "Hello, I am Sasha; … We just spoke on the phone; I am writing to put on record in writing the reservation you confirmed:\n\n{core}.\n\n"
                "If something is wrong, please reply to this email and let us correct it. For any change you can write to us here: {me}.\n\nThanks,\nSasha (…), on behalf of {guest_short}"),
    "ask": ("Could you confirm the reservation made in the name of {name}?",
            "Hello, I am Sasha; … I just spoke with you on the phone, but it was not clear whether the reservation was confirmed:\n\n{core}.\n\n"
            "Could you confirm by replying to this email? If it is not possible or you propose another time, please let us know; we will talk with {guest_short}.\n\nThanks,\nSasha (…), on behalf of {guest_short}"),
}
CORE_BACK = "{what} — on {d} at {t}, for {n}, in the name of {name}"
