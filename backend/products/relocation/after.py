"""CR 1 · after the form is prepared: the applicant signs (we never do), then lodges it themselves. M3 adds the official
appointment page (located from a fetched official page, never composed, never pressed), the checklist and reminders."""
from __future__ import annotations

from .. import store as ST


async def signed(ctx: dict) -> None:
    pend, out = ctx["st"]["pending"], ctx["out"]
    case = await ST.STORE.get(pend.get("case_id") or "")
    if case:
        st = case["state"]
        st.update(status="signed_on_your_word", signed_at=ctx["now"].isoformat())
        await ST.STORE.update(case["id"], st)
    pend["step"] = "signed"
    out.text("Noted — signed by you, on your word. I didn't sign or tick anything for you. You lodge it yourself; "
             "I never file anything in Spain.")


async def on_message(ctx: dict, body: str, payload: str) -> bool:
    ctx["out"].text("Your file is ready on its page. Say EXIT to go back to Sasha.")
    return True
