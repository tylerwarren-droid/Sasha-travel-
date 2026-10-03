"""Indonesian (id) · ⚠ AI-written, NOT native-reviewed (STATUS). Formal register (Bapak/Ibu, Anda)."""
CODE, NAME, STATUS = "id", "Indonesian", "ai_unreviewed"
from booking_signer.wordings import DISCLOSURE as _DISCLOSURE  # noqa: E402  (the single source: calls and emails)
DISCLOSURE = _DISCLOSURE["id"]
TABLE = "meja"


def count(n: int) -> str:
    return f"{n} orang"


CORE = "{what} — tanggal {d} pukul {t}, untuk {n}, atas nama {name}"
_SIGN = "Sasha (concierge AI, Kanoe Technologies SL), atas nama {guest_short}"
T = {
    "request_table": ("Permintaan reservasi meja — {n}, {d} pukul {t}",
                      "Dengan hormat, saya {disclosure}. Saya menulis atas nama {who} untuk memesan meja untuk {n} pada tanggal {d} pukul {t}.\n\n"
                      "Mohon kesediaan Bapak/Ibu untuk membalas email ini sebagai konfirmasi, atau memberi tahu kami jika tidak memungkinkan.\n\n"
                      "Kami tidak dapat menyetujui uang muka atau perubahan waktu melalui email atas nama {guest_short}; bila diperlukan, mohon beri tahu kami dan {guest_short} sendiri yang akan memutuskan.\n\n"
                      "Terima kasih,\n" + _SIGN),
    "request_generic": ("Permintaan reservasi — {what}, {d} pukul {t}",
                        "Dengan hormat, saya {disclosure}. Saya menulis atas nama {who} untuk memesan {what} untuk {n} pada tanggal {d} pukul {t}.\n\n"
                        "Mohon kesediaan Bapak/Ibu untuk membalas email ini sebagai konfirmasi, atau memberi tahu kami jika tidak memungkinkan.\n\n"
                        "Kami tidak dapat menyetujui uang muka, biaya, atau perubahan waktu melalui email atas nama {guest_short}; bila diperlukan, mohon beri tahu kami dan {guest_short} sendiri yang akan memutuskan.\n\n"
                        "Terima kasih,\n" + _SIGN),
    "cancel": ("Pembatalan reservasi atas nama {name}",
               "Dengan hormat, saya {disclosure}. Saya menulis atas nama {name} untuk membatalkan reservasi berikut:\n\n{core}.\n\n"
               "Mohon konfirmasi pembatalan ini dengan membalas email ini. Terima kasih banyak.\n\n"
               "Sasha (concierge AI, Kanoe Technologies SL), atas nama {name}"),
    "confirm": ("Konfirmasi reservasi atas nama {name}",
                "Dengan hormat, saya {disclosure}. Kita baru saja berbicara melalui telepon, dan saya menulis untuk mencatat secara tertulis reservasi yang telah Bapak/Ibu konfirmasi:\n\n{core}.\n\n"
                "Jika ada yang tidak sesuai, mohon balas email ini dan kami akan memperbaikinya. Untuk perubahan apa pun, silakan menulis ke: {me}.\n\n"
                "Terima kasih,\n" + _SIGN),
    "ask": ("Bisakah Bapak/Ibu mengonfirmasi reservasi atas nama {name}?",
            "Dengan hormat, saya {disclosure}. Saya baru saja berbicara dengan Bapak/Ibu melalui telepon, tetapi belum jelas apakah reservasi sudah dikonfirmasi:\n\n{core}.\n\n"
            "Mohon konfirmasi dengan membalas email ini. Jika tidak memungkinkan, atau jika Bapak/Ibu mengusulkan waktu lain, mohon beri tahu kami dan kami akan menanyakannya kepada {guest_short}.\n\n"
            "Terima kasih,\n" + _SIGN),
}
BACK = {
    "request_table": ("Table reservation request — {n} people, {d} at {t}",
                      "With respect (formal letter opening), I am Sasha, an artificial-intelligence (AI) concierge managed by Kanoe Technologies SL. I am writing on behalf of {who} to book a table for {n} people on {d} at {t}.\n\n"
                      "We kindly ask your willingness to reply to this email as confirmation, or to let us know if it is not possible.\n\n"
                      "We cannot agree to a down payment or a change of time by email on behalf of {guest_short}; if needed, please let us know and {guest_short} will decide themselves.\n\n"
                      "Thank you,\nSasha (AI concierge, Kanoe Technologies SL), on behalf of {guest_short}"),
    "request_generic": ("Reservation request — {what}, {d} at {t}",
                        "With respect (formal letter opening), I am Sasha, … I am writing on behalf of {who} to book {what} for {n} people on {d} at {t}.\n\n"
                        "We kindly ask your willingness to reply to this email as confirmation, or to let us know if it is not possible.\n\n"
                        "We cannot agree to a down payment, fees or a change of time by email on behalf of {guest_short}; if needed, please let us know and {guest_short} will decide themselves.\n\n"
                        "Thank you,\nSasha (…), on behalf of {guest_short}"),
    "cancel": ("Cancellation of the reservation in the name of {name}",
               "With respect (formal letter opening), I am Sasha, … I am writing on behalf of {name} to cancel the following reservation:\n\n{core}.\n\n"
               "Please confirm this cancellation by replying to this email. Many thanks.\n\nSasha (…), on behalf of {name}"),
    "confirm": ("Confirmation of the reservation in the name of {name}",
                "With respect (formal letter opening), I am Sasha, … We just spoke by phone, and I am writing to record in writing the reservation you confirmed:\n\n{core}.\n\n"
                "If anything does not match, please reply to this email and we will fix it. For any changes, please write to: {me}.\n\nThank you,\nSasha (…), on behalf of {guest_short}"),
    "ask": ("Could you confirm the reservation in the name of {name}?",
            "With respect (formal letter opening), I am Sasha, … I just spoke with you by phone, but it is not yet clear whether the reservation has been confirmed:\n\n{core}.\n\n"
            "Please confirm by replying to this email. If it is not possible, or if you propose another time, please let us know and we will ask {guest_short}.\n\nThank you,\nSasha (…), on behalf of {guest_short}"),
}
CORE_BACK = "{what} — on {d} at {t}, for {n} people, in the name of {name}"
