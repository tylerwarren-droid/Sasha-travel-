"""Korean (ko) · ⚠ AI-written, NOT native-reviewed (STATUS). Formal 합니다체."""
CODE, NAME, STATUS = "ko", "Korean", "ai_unreviewed"
DISCLOSURE = "Kanoe Technologies SL이 운영하는 AI 컨시어지 Sasha"
TABLE = "테이블"


def count(n: int) -> str:
    return f"{n}명"


CORE = "{what} — {d} {t}, {n}, 예약자 {name}"
_SIGN = "Sasha (AI 컨시어지, Kanoe Technologies SL), {guest_short} 님을 대신하여"
T = {
    "request_table": ("테이블 예약 요청 — {n}, {d} {t}",
                      "안녕하십니까, {disclosure}입니다. {who} 님을 대신하여 {d} {t}에 {n} 테이블 예약을 요청드리고자 연락드립니다.\n\n"
                      "이 이메일에 회신하여 확정해 주시거나, 어려운 경우 알려 주시겠습니까?\n\n"
                      "{guest_short} 님을 대신하여 이메일로 예약금이나 시간 변경에 동의할 수는 없습니다. 필요하시면 말씀해 주십시오. {guest_short} 님께서 직접 결정하실 것입니다.\n\n"
                      "감사합니다.\n" + _SIGN),
    "request_generic": ("예약 요청 — {what}, {d} {t}",
                        "안녕하십니까, {disclosure}입니다. {who} 님을 대신하여 {d} {t}에 {n} {what} 예약을 요청드리고자 연락드립니다.\n\n"
                        "이 이메일에 회신하여 확정해 주시거나, 어려운 경우 알려 주시겠습니까?\n\n"
                        "{guest_short} 님을 대신하여 이메일로 예약금, 요금 또는 시간 변경에 동의할 수는 없습니다. 필요하시면 말씀해 주십시오. {guest_short} 님께서 직접 결정하실 것입니다.\n\n"
                        "감사합니다.\n" + _SIGN),
    "cancel": ("{name} 님 명의 예약 취소",
               "안녕하십니까, {disclosure}입니다. {name} 님을 대신하여 다음 예약을 취소하고자 연락드립니다.\n\n{core}\n\n"
               "이 이메일에 회신하여 취소를 확인해 주시겠습니까? 대단히 감사합니다.\n\nSasha (AI 컨시어지, Kanoe Technologies SL), {name} 님을 대신하여"),
    "confirm": ("{name} 님 명의 예약 확인",
                "안녕하십니까, {disclosure}입니다. 방금 전화로 확정해 주신 예약을 서면으로 남기고자 연락드립니다.\n\n{core}\n\n"
                "틀린 내용이 있으면 이 이메일에 회신해 주십시오. 바로 수정하겠습니다. 변경 사항은 이곳으로 보내 주십시오: {me}\n\n"
                "감사합니다.\n" + _SIGN),
    "ask": ("{name} 님 명의 예약을 확인해 주시겠습니까?",
            "안녕하십니까, {disclosure}입니다. 방금 전화로 말씀을 나누었지만, 예약이 확정되었는지 분명하지 않았습니다.\n\n{core}\n\n"
            "이 이메일에 회신하여 확인해 주시겠습니까? 어려우시거나 다른 시간을 제안하신다면 알려 주십시오. {guest_short} 님께 여쭈어 보겠습니다.\n\n"
            "감사합니다.\n" + _SIGN),
}
BACK = {
    "request_table": ("Table reservation request — {n} people, {d} {t}",
                      "Hello, this is Sasha, an AI concierge operated by Kanoe Technologies SL. On behalf of {who}, I am contacting you to request a table reservation for {n} people at {d} {t}.\n\n"
                      "Would you reply to this email to confirm it, or let us know if it is difficult?\n\n"
                      "We cannot agree by email, on behalf of {guest_short}, to a deposit or a time change. If needed, please tell us. {guest_short} will decide personally.\n\n"
                      "Thank you.\nSasha (AI concierge, Kanoe Technologies SL), on behalf of {guest_short}"),
    "request_generic": ("Reservation request — {what}, {d} {t}",
                        "Hello, this is Sasha, … On behalf of {who}, I am contacting you to request a reservation of {what} for {n} people at {d} {t}.\n\n"
                        "Would you reply to this email to confirm it, or let us know if it is difficult?\n\n"
                        "We cannot agree by email, on behalf of {guest_short}, to a deposit, a fee or a time change. If needed, please tell us. {guest_short} will decide personally.\n\n"
                        "Thank you.\nSasha (…), on behalf of {guest_short}"),
    "cancel": ("Cancellation of the reservation in {name}'s name",
               "Hello, this is Sasha, … On behalf of {name}, I am contacting you to cancel the following reservation.\n\n{core}\n\n"
               "Would you reply to this email to confirm the cancellation? Thank you very much.\n\nSasha (…), on behalf of {name}"),
    "confirm": ("Confirmation of the reservation in {name}'s name",
                "Hello, this is Sasha, … I am contacting you to leave in writing the reservation you confirmed by phone just now.\n\n{core}\n\n"
                "If anything is wrong, please reply to this email. We will correct it right away. Please send changes here: {me}\n\nThank you.\nSasha (…), on behalf of {guest_short}"),
    "ask": ("Would you confirm the reservation in {name}'s name?",
            "Hello, this is Sasha, … We spoke by phone just now, but it was not clear whether the reservation was confirmed.\n\n{core}\n\n"
            "Would you reply to this email to confirm? If it is difficult or you propose another time, please let us know. We will ask {guest_short}.\n\nThank you.\nSasha (…), on behalf of {guest_short}"),
}
CORE_BACK = "{what} — {d} {t}, {n} people, booked by {name}"
