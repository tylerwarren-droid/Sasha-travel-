"""Chinese, Simplified (zh) · ⚠ AI-written, NOT native-reviewed (STATUS). Mainland usage; formal 您.
⚠ A venue in Taiwan or Hong Kong reads Traditional characters — not drafted; the reviewer should say if zh-Hant is needed."""
CODE, NAME, STATUS = "zh", "Chinese (Simplified)", "ai_unreviewed"
DISCLOSURE = "Sasha，由 Kanoe Technologies SL 运营的人工智能礼宾助理"
TABLE = "一张餐桌"


def count(n: int) -> str:
    return f"{n}位"


CORE = "{what}——{d} {t}，共{n}，预订人：{name}"
_SIGN = "Sasha（人工智能礼宾助理，Kanoe Technologies SL），代表{guest_short}"
T = {
    "request_table": ("订座请求——{n}，{d} {t}",
                      "您好，我是{disclosure}。我代表{who}写信，想预订{d} {t}的座位，共{n}。\n\n"
                      "能否请您回复此邮件确认，或告知我们是否无法安排？\n\n"
                      "我们无法通过邮件代表{guest_short}同意支付定金或更改时间——如有需要，请告知，由{guest_short}本人决定。\n\n"
                      "谢谢！\n" + _SIGN),
    "request_generic": ("预订请求——{what}，{d} {t}",
                        "您好，我是{disclosure}。我代表{who}写信，想预订{d} {t}的{what}，共{n}。\n\n"
                        "能否请您回复此邮件确认，或告知我们是否无法安排？\n\n"
                        "我们无法通过邮件代表{guest_short}同意支付定金、费用或更改时间——如有需要，请告知，由{guest_short}本人决定。\n\n"
                        "谢谢！\n" + _SIGN),
    "cancel": ("取消{name}名下的预订",
               "您好，我是{disclosure}。我代表{name}写信，取消以下预订：\n\n{core}。\n\n"
               "能否请您回复此邮件确认取消？非常感谢。\n\nSasha（人工智能礼宾助理，Kanoe Technologies SL），代表{name}"),
    "confirm": ("确认{name}名下的预订",
                "您好，我是{disclosure}。我们刚刚通过电话，现以书面形式记录您已确认的预订：\n\n{core}。\n\n"
                "如有任何不符，请回复此邮件，我们会更正。如需更改，请写信至：{me}。\n\n谢谢！\n" + _SIGN),
    "ask": ("能否确认{name}名下的预订？",
            "您好，我是{disclosure}。我刚刚与您通过电话，但不确定预订是否已确认：\n\n{core}。\n\n"
            "能否请您回复此邮件确认？如无法安排，或您建议其他时间，请告知我们，我们会与{guest_short}商量。\n\n谢谢！\n" + _SIGN),
}
BACK = {
    "request_table": ("Table reservation request — {n}, {d} {t}",
                      "Hello, I am Sasha, an artificial-intelligence concierge assistant operated by Kanoe Technologies SL. I am writing on behalf of {who} and would like to reserve seats at {d} {t}, {n} in all.\n\n"
                      "Could you please reply to this email to confirm, or tell us if it cannot be arranged?\n\n"
                      "We cannot, by email, agree on behalf of {guest_short} to pay a deposit or change the time — if needed, please tell us, and {guest_short} will decide personally.\n\n"
                      "Thank you!\nSasha (AI concierge assistant, Kanoe Technologies SL), on behalf of {guest_short}"),
    "request_generic": ("Reservation request — {what}, {d} {t}",
                        "Hello, I am Sasha, … I am writing on behalf of {who}, wishing to reserve {what} at {d} {t}, {n} in all.\n\n"
                        "Could you please reply to this email to confirm, or tell us if it cannot be arranged?\n\n"
                        "We cannot, by email, agree on behalf of {guest_short} to a deposit, fees or a change of time — if needed, please tell us, and {guest_short} will decide personally.\n\n"
                        "Thank you!\nSasha (…), on behalf of {guest_short}"),
    "cancel": ("Cancel the reservation under {name}'s name",
               "Hello, I am Sasha, … I am writing on behalf of {name} to cancel the following reservation:\n\n{core}.\n\n"
               "Could you please reply to this email to confirm the cancellation? Many thanks.\n\nSasha (…), on behalf of {name}"),
    "confirm": ("Confirming the reservation under {name}'s name",
                "Hello, I am Sasha, … We just spoke by phone; I am now recording in writing the reservation you confirmed:\n\n{core}.\n\n"
                "If anything does not match, please reply to this email and we will correct it. For changes, please write to: {me}.\n\nThank you!\nSasha (…), on behalf of {guest_short}"),
    "ask": ("Could you confirm the reservation under {name}'s name?",
            "Hello, I am Sasha, … I just spoke with you by phone, but I am not sure whether the reservation was confirmed:\n\n{core}.\n\n"
            "Could you please reply to this email to confirm? If it cannot be arranged, or you suggest another time, please tell us and we will discuss it with {guest_short}.\n\nThank you!\nSasha (…), on behalf of {guest_short}"),
}
CORE_BACK = "{what} — {d} {t}, {n} in all, reserved by: {name}"
