"""CR 136 · WhatsApp evidence onto Applied Diligence's case: in AD's space a file, a voice note or a reply to a case message is handed to
AgAPI's ONE inbound op with its media (Twilio's MediaUrlN / MediaContentTypeN — AgAPI reads them through its one Twilio client) and the
message it answers (OriginalRepliedMessageSid). A voice note there is the AUDIO (AD transcribes it): Sasha does not turn it into words.
Outside AD's space nothing changes. Offline: AgAPI's op is stood in, the real WhatsApp turn runs.

    cd backend && python -m unittest tests.test_cr136_ad_evidence -v
"""
from __future__ import annotations

from unittest import mock

from agapi import venue_submit as VS
from booking_signer import guest_whatsapp as GW
from tests import test_cr128_diligence as T128
from tests import test_guest_whatsapp_s75 as TG

run = TG.run
OGG = "https://api.twilio.com/2010-04-01/Accounts/AC00/Messages/MM11/Media/ME22"


class InADsSpace(T128.Base):
    def send(self, body="", media=(), replied_to=None):
        ch = run(GW.STORE.channel_for(GW.wa_key(TG.GUEST)))
        p = {"From": f"whatsapp:{TG.GUEST}", "To": f"whatsapp:{TG.SANDBOX}", "Body": body, "NumMedia": str(len(media)),
             "MessageSid": "SM" + str(len(self.ad.call_args_list)).zfill(32)}
        for i, (u, t) in enumerate(media):
            p[f"MediaUrl{i}"], p[f"MediaContentType{i}"] = u, t
        if replied_to:
            p["OriginalRepliedMessageSid"] = replied_to
        return run(GW.turn(ch, TG.SANDBOX, p))

    def test_a_a_voice_note_goes_to_ad_as_audio_never_as_words(self):
        self.say("diligence")
        n = len(self.bodies())
        with mock.patch.object(GW, "voice_text", mock.AsyncMock(return_value="words Sasha heard")) as vt:
            self.send(media=[(OGG, "audio/ogg")])
        vt.assert_not_called()                                                    # the audio is the evidence: AD transcribes it
        c = self.ad.call_args_list[-1]
        self.assertEqual((c.args[1], c.kwargs["space"], c.kwargs["media"]), ("", "diligence", [{"url": OGG, "type": "audio/ogg"}]))
        self.assertEqual(len(self.bodies()), n)                                   # never "who should I investigate?": AgAPI answers

    def test_b_a_pdf_with_a_reply_to_a_case_message(self):
        self.say("diligence")
        self.send(media=[(OGG.replace("ME22", "ME33"), "application/pdf")], replied_to="SM" + "a" * 32)
        c = self.ad.call_args_list[-1]
        self.assertEqual((c.kwargs["media"][0]["type"], c.kwargs["replied_to"]), ("application/pdf", "SM" + "a" * 32))

    def test_c_words_still_go_as_before(self):
        self.say("diligence")
        self.send("add this to Northwind")
        c = self.ad.call_args_list[-1]
        self.assertEqual((c.args[1], c.kwargs["media"], c.kwargs["replied_to"]), ("add this to Northwind", [], None))

    def test_d_outside_ads_space_a_voice_note_is_still_heard_as_words(self):
        self.say("sasha")
        with mock.patch.object(GW, "voice_text", mock.AsyncMock(return_value=None)) as vt:
            self.send(media=[(OGG, "audio/ogg")])
        vt.assert_called_once()
        self.assertEqual(self.sent_to_ad(), [])


class TheHandOver(TG.Base):
    def test_media_and_replied_to_are_sent_only_in_a_space(self):
        sent = []

        async def call(_k, op, body):
            sent.append(body)
            return {"ok": True, "result": {"matched": True, "ad": "door"}}
        with mock.patch.object(VS, "_call", call):
            run(VS.whatsapp_inbound("+447700900131", "", message_id="SM1", guest=True, space="diligence",
                                    media=[{"url": OGG, "type": "audio/ogg"}], replied_to="SM2"))
            run(VS.whatsapp_inbound("+447700900131", "hi", message_id="SM3", media=[{"url": OGG, "type": "audio/ogg"}], replied_to="SM2"))
        self.assertEqual((sent[0]["media"], sent[0]["replied_to"]), ([{"url": OGG, "type": "audio/ogg"}], "SM2"))
        self.assertNotIn("media", sent[1])                                        # no space: a venue's reply carries no files to AgAPI
        self.assertNotIn("replied_to", sent[1])
