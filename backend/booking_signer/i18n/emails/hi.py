"""Hindi (hi) · ⚠ AI-written, NOT native-reviewed (STATUS). Formal आप; Devanagari. The reviewer should say whether
English loanwords (टेबल, बुकिंग, ईमेल) — common in Indian business email — read better than शुद्ध alternatives."""
CODE, NAME, STATUS = "hi", "Hindi", "ai_unreviewed"
from booking_signer.wordings import DISCLOSURE as _DISCLOSURE  # noqa: E402  (the single source: calls and emails)
DISCLOSURE = _DISCLOSURE["hi"]
TABLE = "एक टेबल"


def count(n: int) -> str:
    return "1 व्यक्ति" if n == 1 else f"{n} लोगों"


CORE = "{what} — {d} को {t} बजे, {n} के लिए, {name} के नाम पर"
_SIGN = "Sasha (AI कंसीयर्ज, Kanoe Technologies SL), {guest_short} की ओर से"
T = {
    "request_table": ("टेबल बुकिंग का अनुरोध — {n} के लिए, {d} को {t} बजे",
                      "नमस्ते, मैं {disclosure} हूँ। मैं {who} की ओर से {d} को {t} बजे {n} के लिए एक टेबल बुक करने का अनुरोध करने हेतु लिख रही हूँ।\n\n"
                      "क्या आप इस ईमेल का उत्तर देकर पुष्टि कर सकते हैं, या बता सकते हैं कि यह संभव नहीं है?\n\n"
                      "हम {guest_short} की ओर से ईमेल पर किसी अग्रिम राशि या समय बदलने के लिए सहमति नहीं दे सकते — यदि इसकी आवश्यकता हो, तो कृपया बताएँ, निर्णय {guest_short} स्वयं लेंगे।\n\n"
                      "धन्यवाद,\n" + _SIGN),
    "request_generic": ("बुकिंग का अनुरोध — {what}, {d} को {t} बजे",
                        "नमस्ते, मैं {disclosure} हूँ। मैं {who} की ओर से {d} को {t} बजे {n} के लिए {what} बुक करने का अनुरोध करने हेतु लिख रही हूँ।\n\n"
                        "क्या आप इस ईमेल का उत्तर देकर पुष्टि कर सकते हैं, या बता सकते हैं कि यह संभव नहीं है?\n\n"
                        "हम {guest_short} की ओर से ईमेल पर किसी अग्रिम राशि, शुल्क या समय बदलने के लिए सहमति नहीं दे सकते — यदि इसकी आवश्यकता हो, तो कृपया बताएँ, निर्णय {guest_short} स्वयं लेंगे।\n\n"
                        "धन्यवाद,\n" + _SIGN),
    "cancel": ("{name} के नाम की बुकिंग रद्द करना",
               "नमस्ते, मैं {disclosure} हूँ। मैं {name} की ओर से निम्नलिखित बुकिंग रद्द करने के लिए लिख रही हूँ:\n\n{core}।\n\n"
               "क्या आप इस ईमेल का उत्तर देकर रद्दीकरण की पुष्टि कर सकते हैं? बहुत-बहुत धन्यवाद।\n\n"
               "Sasha (AI कंसीयर्ज, Kanoe Technologies SL), {name} की ओर से"),
    "confirm": ("{name} के नाम की बुकिंग की पुष्टि",
                "नमस्ते, मैं {disclosure} हूँ। अभी-अभी हमारी फ़ोन पर बात हुई, और आपने जो बुकिंग पक्की की है, उसे लिखित रूप में दर्ज करने के लिए मैं लिख रही हूँ:\n\n{core}।\n\n"
                "यदि कुछ भी गलत हो, तो कृपया इस ईमेल का उत्तर दें, हम उसे ठीक कर देंगे। किसी भी बदलाव के लिए हमें यहाँ लिखें: {me}।\n\n"
                "धन्यवाद,\n" + _SIGN),
    "ask": ("क्या आप {name} के नाम की बुकिंग की पुष्टि कर सकते हैं?",
            "नमस्ते, मैं {disclosure} हूँ। अभी-अभी मेरी आपसे फ़ोन पर बात हुई, लेकिन यह स्पष्ट नहीं हुआ कि बुकिंग पक्की हुई या नहीं:\n\n{core}।\n\n"
            "क्या आप इस ईमेल का उत्तर देकर पुष्टि कर सकते हैं? यदि यह संभव न हो, या आप कोई और समय सुझाना चाहें, तो कृपया बताएँ — हम {guest_short} से पूछ लेंगे।\n\n"
            "धन्यवाद,\n" + _SIGN),
}
BACK = {
    "request_table": ("Request for a table booking — for {n}, on {d} at {t} o'clock",
                      "Hello, I am Sasha, an AI concierge (artificial-intelligence assistant) operated by Kanoe Technologies SL. I am writing on behalf of {who} to request booking a table for {n} on {d} at {t} o'clock.\n\n"
                      "Can you confirm by replying to this email, or tell us that it is not possible?\n\n"
                      "We cannot give consent by email on behalf of {guest_short} to any advance amount or to changing the time — if this is needed, please tell us; {guest_short} will make the decision themselves.\n\n"
                      "Thank you,\nSasha (AI concierge, Kanoe Technologies SL), on behalf of {guest_short}"),
    "request_generic": ("Booking request — {what}, on {d} at {t} o'clock",
                        "Hello, I am Sasha, … I am writing on behalf of {who} to request booking {what} for {n} on {d} at {t} o'clock.\n\n"
                        "Can you confirm by replying to this email, or tell us that it is not possible?\n\n"
                        "We cannot give consent by email on behalf of {guest_short} to any advance amount, fee or changing the time — if this is needed, please tell us; {guest_short} will make the decision themselves.\n\n"
                        "Thank you,\nSasha (…), on behalf of {guest_short}"),
    "cancel": ("Cancelling the booking in {name}'s name",
               "Hello, I am Sasha, … I am writing on behalf of {name} to cancel the following booking:\n\n{core}.\n\n"
               "Can you confirm the cancellation by replying to this email? Many many thanks.\n\nSasha (…), on behalf of {name}"),
    "confirm": ("Confirmation of the booking in {name}'s name",
                "Hello, I am Sasha, … We just spoke on the phone, and I am writing to record in writing the booking you have made firm:\n\n{core}.\n\n"
                "If anything is wrong, please reply to this email and we will fix it. For any change, write to us here: {me}.\n\nThank you,\nSasha (…), on behalf of {guest_short}"),
    "ask": ("Can you confirm the booking in {name}'s name?",
            "Hello, I am Sasha, … I just spoke with you on the phone, but it did not become clear whether the booking was made firm or not:\n\n{core}.\n\n"
            "Can you confirm by replying to this email? If this is not possible, or you would like to suggest another time, please tell us — we will ask {guest_short}.\n\nThank you,\nSasha (…), on behalf of {guest_short}"),
}
CORE_BACK = "{what} — on {d} at {t} o'clock, for {n}, in {name}'s name"
