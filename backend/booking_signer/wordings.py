"""S-52 · Who Sasha says she is — ONE place, every channel, every language.

Founder decision (Sasha 23): Sasha is **"an AI concierge operated by Kanoe Technologies SL"**, never "an AI assistant",
and the disclosure is the FIRST thing said or written (EU AI Act Art. 50: disclosed at first interaction).

Used by: the phone and cancellation openers (calls.py), the email rung (emailing.py), WhatsApp Mode A's pre-filled
message (frontend Ladder.tsx carries the same text, pinned by a test), and the venue opt-in wordings (S-49).

⚠ Versioned. A venue's opt-in stores the wording it agreed to (`wording_version`, `wording_sha256`, `wording_text`),
so a wording is never edited in place: a change is a new version. v1 (S-48/S-49, "an AI assistant") stays here,
unused for new consent, so every stored v1 opt-in can still be shown and checked against its hash.

⚠ The non-English texts are ours; a native speaker should read ES, PT and TR before a venue sees them.
"""
from __future__ import annotations

import hashlib

#: "this is <DISCLOSURE>" — the phrase as it appears inside a sentence, per language
DISCLOSURE = {
    "en": "Sasha, an AI concierge operated by Kanoe Technologies SL",
    "es": "Sasha, una concierge de inteligencia artificial operada por Kanoe Technologies SL",
    "pt": "Sasha, uma concierge de inteligência artificial operada pela Kanoe Technologies SL",
    "tr": "Sasha; Kanoe Technologies SL tarafından işletilen bir yapay zekâ konsiyerjiyim",
    "fr": "Sasha, une concierge d'intelligence artificielle exploitée par Kanoe Technologies SL",
    "de": "Sasha, eine KI-Concierge von Kanoe Technologies SL",
    "it": "Sasha, una concierge di intelligenza artificiale gestita da Kanoe Technologies SL",
    # CR 7 i18n · the 11 below are AI-written, NOT native-reviewed (booking_signer/i18n/emails/, review sheets in
    # docs/sasha/i18n/emails/). One wording per language for calls AND emails. "vi" is for EMAILS only: Bland has no
    # Vietnamese voice (Sasha 129), so Vietnam is called in English.
    "zh": "Sasha，由 Kanoe Technologies SL 运营的人工智能礼宾助理",
    "ja": "Kanoe Technologies SL が運営する AI コンシェルジュの Sasha",
    "ko": "Kanoe Technologies SL이 운영하는 AI 컨시어지 Sasha",
    "ar": "ساشا، مساعدة استقبال (كونسيرج) تعمل بالذكاء الاصطناعي وتديرها شركة Kanoe Technologies SL",
    "hi": "Sasha, Kanoe Technologies SL द्वारा संचालित एक AI कंसीयर्ज (कृत्रिम बुद्धिमत्ता सहायक)",
    "ru": "Саша (Sasha), ИИ-консьерж, работающий от имени компании Kanoe Technologies SL",
    "nl": "Sasha, een AI-conciërge van Kanoe Technologies SL",
    "pl": "Sasha, konsjerżka oparta na sztucznej inteligencji, prowadzona przez Kanoe Technologies SL",
    "id": "Sasha, concierge kecerdasan buatan (AI) yang dikelola oleh Kanoe Technologies SL",
    "sv": "Sasha, en AI-concierge som drivs av Kanoe Technologies SL",
    "vi": "Sasha, trợ lý AI (concierge trí tuệ nhân tạo) do Kanoe Technologies SL vận hành",
}

#: S-48 §3 · the first-contact WhatsApp text, v2. {who} {n} {date} {time}. The same text is Mode A's pre-filled message.
WHATSAPP_TEMPLATE_V2 = {
    "en": "Hello, this is Sasha, an AI concierge operated by Kanoe Technologies SL, writing on behalf of {who} to ask for a table for {n} people on {date} at {time}. Could you tell us whether that is possible? We will not agree to a deposit or fee without asking {who} first. Thank you.",
    "es": "Hola, soy Sasha, una concierge de inteligencia artificial operada por Kanoe Technologies SL, y escribo en nombre de {who} para pedir una mesa para {n} personas el {date} a las {time}. ¿Nos puede decir si es posible? No aceptaremos ningún depósito ni cargo sin consultarlo antes con {who}. Gracias.",
    "pt": "Olá, sou a Sasha, uma concierge de inteligência artificial operada pela Kanoe Technologies SL, e escrevo em nome de {who} para pedir uma mesa para {n} pessoas no dia {date} às {time}. Pode dizer-nos se é possível? Não aceitaremos qualquer depósito ou taxa sem consultar primeiro {who}. Obrigada.",
    "tr": "Merhaba, ben Sasha; Kanoe Technologies SL tarafından işletilen bir yapay zekâ konsiyerjiyim. {who} adına {date} tarihinde saat {time} için {n} kişilik bir masa rica etmek üzere yazıyorum. Bunun mümkün olup olmadığını bize bildirebilir misiniz? {who} ile önceden görüşmeden hiçbir depozito veya ücreti kabul etmeyeceğiz. Teşekkürler.",
}

#: S-49 §1 · the sentences a venue agrees to. {url} for web_submit. v1 = S-49 as written ("an AI assistant"); v2 = concierge.
OPTIN_WORDINGS = {
    "whatsapp": {
        "v1": {"en": "I agree that Sasha, an AI assistant operated by Kanoe Technologies SL, may send booking requests for our guests to this WhatsApp number. I can stop this at any time by replying STOP."},
        "v2": {
            "en": "I agree that Sasha, an AI concierge operated by Kanoe Technologies SL, may send booking requests for our guests to this WhatsApp number. I can stop this at any time by replying STOP.",
            "es": "Acepto que Sasha, una concierge de inteligencia artificial operada por Kanoe Technologies SL, envíe solicitudes de reserva de nuestros clientes a este número de WhatsApp. Puedo detenerlo en cualquier momento respondiendo STOP.",
            "pt": "Aceito que a Sasha, uma concierge de inteligência artificial operada pela Kanoe Technologies SL, envie pedidos de reserva dos nossos clientes para este número de WhatsApp. Posso parar a qualquer momento respondendo STOP.",
            "tr": "Kanoe Technologies SL tarafından işletilen bir yapay zekâ konsiyerji olan Sasha'nın misafirlerimiz adına bu WhatsApp numarasına rezervasyon talepleri göndermesini kabul ediyorum. İstediğim zaman STOP yanıtını vererek bunu durdurabilirim.",
        },
    },
    "web_submit": {
        "v1": {"en": "I agree that Sasha, an AI assistant operated by Kanoe Technologies SL, may fill in and submit our booking form at {url} on behalf of guests who have approved the booking. She will not pay, accept a deposit, or solve a CAPTCHA."},
        "v2": {
            "en": "I agree that Sasha, an AI concierge operated by Kanoe Technologies SL, may fill in and submit our booking form at {url} on behalf of guests who have approved the booking. She will not pay, accept a deposit, or solve a CAPTCHA.",
            "es": "Acepto que Sasha, una concierge de inteligencia artificial operada por Kanoe Technologies SL, rellene y envíe nuestro formulario de reservas en {url} en nombre de clientes que hayan aprobado la reserva. No pagará, no aceptará un depósito ni resolverá un CAPTCHA.",
            "pt": "Aceito que a Sasha, uma concierge de inteligência artificial operada pela Kanoe Technologies SL, preencha e envie o nosso formulário de reservas em {url} em nome de clientes que tenham aprovado a reserva. Não pagará, não aceitará um depósito nem resolverá um CAPTCHA.",
            "tr": "Kanoe Technologies SL tarafından işletilen bir yapay zekâ konsiyerji olan Sasha'nın, rezervasyonu onaylamış misafirler adına {url} adresindeki rezervasyon formumuzu doldurup göndermesini kabul ediyorum. Ödeme yapmayacak, depozito kabul etmeyecek ve CAPTCHA çözmeyecektir.",
        },
    },
    "email_confirm": {
        "v1": {"en": "We will confirm Sasha's booking requests by replying to her email, with our reference where we have one."},
        "v2": {
            "en": "We will confirm the booking requests of Sasha, an AI concierge operated by Kanoe Technologies SL, by replying to her email, with our reference where we have one.",
            "es": "Confirmaremos las solicitudes de reserva de Sasha, una concierge de inteligencia artificial operada por Kanoe Technologies SL, respondiendo a su correo, con nuestra referencia cuando la tengamos.",
            "pt": "Confirmaremos os pedidos de reserva da Sasha, uma concierge de inteligência artificial operada pela Kanoe Technologies SL, respondendo ao seu email, com a nossa referência quando a tivermos.",
            "tr": "Kanoe Technologies SL tarafından işletilen bir yapay zekâ konsiyerji olan Sasha'nın rezervasyon taleplerini, varsa referansımızla birlikte e-postasını yanıtlayarak onaylayacağız.",
        },
    },
}
CURRENT_OPTIN_VERSION = "v2"

#: S-64 · a party of ONE in the WhatsApp text: the template's "{n} people" becomes "1 person" (founder, Sasha 44).
#: ⚠ A copy is in frontend/lib/whatsapp-template.ts (WHATSAPP_ONE) — tests/test_wordings.py holds them equal.
WHATSAPP_ONE = {"en": ["{n} people", "{n} person"], "es": ["{n} personas", "{n} persona"], "pt": ["{n} pessoas", "{n} pessoa"]}


def optin_wording(channel: str, lang: str, version: str = CURRENT_OPTIN_VERSION, url: str = "") -> dict:
    """{version, text, sha256} — exactly what a venue is shown and what its opt-in row stores."""
    texts = OPTIN_WORDINGS[channel][version]
    text = texts.get(lang) or texts["en"]
    text = text.replace("{url}", url)
    return {"version": version, "lang": lang if lang in texts else "en", "text": text,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
