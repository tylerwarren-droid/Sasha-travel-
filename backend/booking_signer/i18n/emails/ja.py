"""Japanese (ja) · ⚠ AI-written, NOT native-reviewed (STATUS). Business keigo (です・ます / いただけますでしょうか)."""
CODE, NAME, STATUS = "ja", "Japanese", "ai_unreviewed"
from booking_signer.wordings import DISCLOSURE as _DISCLOSURE  # noqa: E402  (the single source: calls and emails)
DISCLOSURE = _DISCLOSURE["ja"]
TABLE = "お席"


def count(n: int) -> str:
    return f"{n}名"


CORE = "{what}：{d} {t}、{n}、{name} 様のお名前で"
_SIGN = "Sasha（AI コンシェルジュ、Kanoe Technologies SL）{guest_short} 様の代理として"
T = {
    "request_table": ("お席の予約のお願い — {n}、{d} {t}",
                      "お世話になっております。{disclosure}です。{who} 様に代わり、{d} {t}に{n}でお席の予約をお願いしたくご連絡いたしました。\n\n"
                      "ご確認のうえ、本メールにご返信いただけますでしょうか。ご対応が難しい場合も、その旨お知らせいただけますと幸いです。\n\n"
                      "なお、デポジットや時間の変更について、{guest_short} 様に代わってメールでお約束することはできません。必要な場合はお知らせください。{guest_short} 様ご本人が判断いたします。\n\n"
                      "よろしくお願いいたします。\n" + _SIGN),
    "request_generic": ("ご予約のお願い — {what}、{d} {t}",
                        "お世話になっております。{disclosure}です。{who} 様に代わり、{d} {t}に{n}で{what}の予約をお願いしたくご連絡いたしました。\n\n"
                        "ご確認のうえ、本メールにご返信いただけますでしょうか。ご対応が難しい場合も、その旨お知らせいただけますと幸いです。\n\n"
                        "なお、デポジット・料金・時間の変更について、{guest_short} 様に代わってメールでお約束することはできません。必要な場合はお知らせください。{guest_short} 様ご本人が判断いたします。\n\n"
                        "よろしくお願いいたします。\n" + _SIGN),
    "cancel": ("{name} 様のお名前でのご予約のキャンセル",
               "お世話になっております。{disclosure}です。{name} 様に代わり、以下のご予約のキャンセルをお願いしたくご連絡いたしました。\n\n{core}\n\n"
               "キャンセルを承った旨、本メールにご返信いただけますでしょうか。どうぞよろしくお願いいたします。\n\n"
               "Sasha（AI コンシェルジュ、Kanoe Technologies SL）{name} 様の代理として"),
    "confirm": ("{name} 様のお名前でのご予約の確認",
                "お世話になっております。{disclosure}です。先ほどお電話でお話しした、ご確認いただいたご予約を書面にて残すためにご連絡いたしました。\n\n{core}\n\n"
                "内容に誤りがございましたら、本メールにご返信ください。訂正いたします。変更のご連絡はこちらまでお願いいたします：{me}\n\n"
                "よろしくお願いいたします。\n" + _SIGN),
    "ask": ("{name} 様のお名前でのご予約をご確認いただけますでしょうか",
            "お世話になっております。{disclosure}です。先ほどお電話でお話ししましたが、ご予約が確定したかどうかがはっきりいたしませんでした。\n\n{core}\n\n"
            "本メールへのご返信にてご確認いただけますでしょうか。難しい場合や、別のお時間をご提案いただける場合もお知らせください。{guest_short} 様に確認いたします。\n\n"
            "よろしくお願いいたします。\n" + _SIGN),
}
BACK = {
    "request_table": ("Request for a table reservation — {n} people, {d} {t}",
                      "Thank you for your continued support. This is Sasha, an AI concierge operated by Kanoe Technologies SL. On behalf of Mr/Ms {who}, I am contacting you to request a table for {n} people at {d} {t}.\n\n"
                      "After checking, could you kindly reply to this email? If it is difficult to accommodate, we would be grateful if you could let us know that too.\n\n"
                      "Please note that we cannot promise by email, on behalf of Mr/Ms {guest_short}, a deposit or a change of time. If needed, please let us know. Mr/Ms {guest_short} will decide personally.\n\n"
                      "Thank you very much.\nSasha (AI concierge, Kanoe Technologies SL), as the representative of Mr/Ms {guest_short}"),
    "request_generic": ("Request for a reservation — {what}, {d} {t}",
                        "Thank you for your continued support. This is Sasha, … On behalf of Mr/Ms {who}, I am contacting you to request a reservation of {what} for {n} people at {d} {t}.\n\n"
                        "After checking, could you kindly reply to this email? If it is difficult to accommodate, we would be grateful if you could let us know that too.\n\n"
                        "Please note that we cannot promise by email, on behalf of Mr/Ms {guest_short}, a deposit, fees or a change of time. If needed, please let us know. Mr/Ms {guest_short} will decide personally.\n\n"
                        "Thank you very much.\nSasha (…), as the representative of Mr/Ms {guest_short}"),
    "cancel": ("Cancellation of the reservation under Mr/Ms {name}'s name",
               "Thank you for your continued support. This is Sasha, … On behalf of Mr/Ms {name}, I am contacting you to ask to cancel the following reservation.\n\n{core}\n\n"
               "Could you kindly reply to this email to say the cancellation has been accepted? Thank you very much.\n\nSasha (…), as the representative of Mr/Ms {name}"),
    "confirm": ("Confirmation of the reservation under Mr/Ms {name}'s name",
                "Thank you for your continued support. This is Sasha, … I am contacting you to leave in writing the reservation you confirmed when we spoke by phone a moment ago.\n\n{core}\n\n"
                "If anything is wrong, please reply to this email; we will correct it. Please send any changes here: {me}\n\nThank you very much.\nSasha (…), as the representative of Mr/Ms {guest_short}"),
    "ask": ("Could you kindly confirm the reservation under Mr/Ms {name}'s name?",
            "Thank you for your continued support. This is Sasha, … We spoke by phone a moment ago, but it was not clear whether the reservation was confirmed.\n\n{core}\n\n"
            "Could you kindly confirm by replying to this email? If it is difficult, or if you can propose another time, please let us know too. We will check with Mr/Ms {guest_short}.\n\nThank you very much.\nSasha (…), as the representative of Mr/Ms {guest_short}"),
}
CORE_BACK = "{what}: {d} {t}, {n} people, under the name of Mr/Ms {name}"
