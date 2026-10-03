"""Vietnamese (vi) · ⚠ AI-written, NOT native-reviewed (STATUS). Polite written register (quý vị / quý nhà hàng)."""
CODE, NAME, STATUS = "vi", "Vietnamese", "ai_unreviewed"
DISCLOSURE = "Sasha, trợ lý AI (concierge trí tuệ nhân tạo) do Kanoe Technologies SL vận hành"
TABLE = "một bàn"


def count(n: int) -> str:
    return f"{n} người"


CORE = "{what} — ngày {d} lúc {t}, {n}, đứng tên {name}"
_SIGN = "Sasha (trợ lý AI, Kanoe Technologies SL), thay mặt {guest_short}"
T = {
    "request_table": ("Yêu cầu đặt bàn — {n}, ngày {d} lúc {t}",
                      "Xin chào, tôi là {disclosure}. Tôi viết thư này thay mặt {who} để xin đặt một bàn cho {n} vào ngày {d} lúc {t}.\n\n"
                      "Quý nhà hàng vui lòng trả lời email này để xác nhận, hoặc cho chúng tôi biết nếu không thể đáp ứng.\n\n"
                      "Chúng tôi không thể thay mặt {guest_short} đồng ý đặt cọc hoặc đổi giờ qua email — nếu cần, xin vui lòng cho biết và {guest_short} sẽ quyết định.\n\n"
                      "Xin cảm ơn,\n" + _SIGN),
    "request_generic": ("Yêu cầu đặt chỗ — {what}, ngày {d} lúc {t}",
                        "Xin chào, tôi là {disclosure}. Tôi viết thư này thay mặt {who} để đặt {what} cho {n} vào ngày {d} lúc {t}.\n\n"
                        "Quý vị vui lòng trả lời email này để xác nhận, hoặc cho chúng tôi biết nếu không thể đáp ứng.\n\n"
                        "Chúng tôi không thể thay mặt {guest_short} đồng ý đặt cọc, phí hoặc đổi giờ qua email — nếu cần, xin vui lòng cho biết và {guest_short} sẽ quyết định.\n\n"
                        "Xin cảm ơn,\n" + _SIGN),
    "cancel": ("Hủy đặt chỗ đứng tên {name}",
               "Xin chào, tôi là {disclosure}. Tôi viết thư này thay mặt {name} để hủy đặt chỗ sau:\n\n{core}.\n\n"
               "Quý vị vui lòng trả lời email này để xác nhận việc hủy. Xin chân thành cảm ơn.\n\n"
               "Sasha (trợ lý AI, Kanoe Technologies SL), thay mặt {name}"),
    "confirm": ("Xác nhận đặt chỗ đứng tên {name}",
                "Xin chào, tôi là {disclosure}. Chúng ta vừa nói chuyện qua điện thoại, và tôi viết thư này để ghi lại bằng văn bản đặt chỗ mà quý vị đã xác nhận:\n\n{core}.\n\n"
                "Nếu có điều gì chưa đúng, xin vui lòng trả lời email này để chúng tôi điều chỉnh. Mọi thay đổi xin gửi về: {me}.\n\n"
                "Xin cảm ơn,\n" + _SIGN),
    "ask": ("Quý vị có thể xác nhận đặt chỗ đứng tên {name} không?",
            "Xin chào, tôi là {disclosure}. Tôi vừa nói chuyện với quý vị qua điện thoại nhưng chưa rõ đặt chỗ đã được xác nhận hay chưa:\n\n{core}.\n\n"
            "Quý vị vui lòng xác nhận bằng cách trả lời email này. Nếu không thể, hoặc nếu quý vị đề xuất giờ khác, xin cho chúng tôi biết và chúng tôi sẽ hỏi ý kiến {guest_short}.\n\n"
            "Xin cảm ơn,\n" + _SIGN),
}
BACK = {
    "request_table": ("Table booking request — {n}, date {d} at {t}",
                      "Hello, I am Sasha, an AI assistant (artificial-intelligence concierge) operated by Kanoe Technologies SL. I am writing this letter on behalf of {who} to request a table for {n} on {d} at {t}.\n\n"
                      "Would the restaurant please reply to this email to confirm, or let us know if it cannot be accommodated.\n\n"
                      "We cannot agree to a deposit or a change of time by email on behalf of {guest_short} — if needed, please let us know and {guest_short} will decide.\n\n"
                      "Thank you,\nSasha (AI assistant, Kanoe Technologies SL), on behalf of {guest_short}"),
    "request_generic": ("Booking request — {what}, date {d} at {t}",
                        "Hello, I am Sasha, … I am writing this letter on behalf of {who} to book {what} for {n} on {d} at {t}.\n\n"
                        "Would you please reply to this email to confirm, or let us know if it cannot be accommodated.\n\n"
                        "We cannot agree to a deposit, a fee or a change of time by email on behalf of {guest_short} — if needed, please let us know and {guest_short} will decide.\n\n"
                        "Thank you,\nSasha (AI assistant, Kanoe Technologies SL), on behalf of {guest_short}"),
    "cancel": ("Cancelling the booking under the name {name}",
               "Hello, I am Sasha, … I am writing on behalf of {name} to cancel the following booking:\n\n{core}.\n\n"
               "Would you please reply to this email to confirm the cancellation. Sincere thanks.\n\nSasha (AI assistant, Kanoe Technologies SL), on behalf of {name}"),
    "confirm": ("Confirmation of the booking under the name {name}",
                "Hello, I am Sasha, … We have just spoken by phone, and I am writing to record in writing the booking you confirmed:\n\n{core}.\n\n"
                "If anything is not right, please reply to this email so we can adjust it. Please send any changes to: {me}.\n\n"
                "Thank you,\nSasha (AI assistant, Kanoe Technologies SL), on behalf of {guest_short}"),
    "ask": ("Could you confirm the booking under the name {name}?",
            "Hello, I am Sasha, … I have just spoken with you by phone but it is not clear whether the booking was confirmed:\n\n{core}.\n\n"
            "Please confirm by replying to this email. If it is not possible, or if you propose another time, please let us know and we will ask {guest_short}.\n\n"
            "Thank you,\nSasha (AI assistant, Kanoe Technologies SL), on behalf of {guest_short}"),
}
CORE_BACK = "{what} — on {d} at {t}, {n} people, under the name {name}"
