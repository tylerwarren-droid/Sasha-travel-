# Sasha 129: the call-language matrix

*3 Oct 2026.*

**Source:** Bland's live `GET /v1/models` on our account, read 3 Oct. The raw response is saved at
`docs/sasha/replies/2026-10-03_api_bland_ai_v1_models.json` (sha256 `3221d2d6…b8cfca6`). It confirms the list in
Bland's docs:

- **BTTS_V2** ("multilingual output") speaks 17 languages: en, de, es, fr, hi, it, ja, ko, nl, pl, pt, ru, tr, zh, ar,
  id, sv.
- **BTTS_V3**, Bland's recommended model, and **BTTS (V1)** are English only.
- **No Bland model lists Vietnamese.**

## The matrix

**Column key**
- **Our script** = a deterministic call script in `calls.LANGUAGES`. Without one, Sasha refuses a venue call in that
  language.
- **Test call** = one call to our own test line, in that language.

| Code | Language | Bland V2 | Our script | Test call | Venue calls today |
|---|---|---|---|---|---|
| en | English | ✅ | ✅ | ✅ connected, answered, ~1 min; Bland heard the reply (f4ec1671). Voice: founder's verdict | ✅ (and English abroad) |
| es | Spanish | ✅ | ✅ (S-33, used live in Madrid) | ✅ connected, answered, ~1 min; Bland heard the reply (bf660be8). Voice: founder's verdict | ✅ |
| pt | Portuguese | ✅ (Bland: pt-BR voice) | ✅ | ✅ connected, answered, ~1 min; Bland heard the reply (e5e4c099). Voice: founder's verdict | ✅ |
| fr | French | ✅ | ✅ | ✅ connected, answered, ~1 min; Bland heard the reply (0724b62e). Voice: founder's verdict | ✅ |
| de | German | ✅ | ✅ | ✅ connected, answered, ~1 min; Bland heard the reply (fff578fc). Voice: founder's verdict | ✅ |
| it | Italian | ✅ | ✅ | ✅ connected, answered, ~1 min; Bland heard the reply (3b2ce33d). Voice: founder's verdict | ✅ |
| hi | Hindi | ✅ | ❌ | ⏳ | ❌, English abroad instead |
| ja | Japanese | ✅ | ❌ | ⏳ | ❌, English abroad instead |
| ko | Korean | ✅ | ❌ | ⏳ | ❌, English abroad instead |
| nl | Dutch | ✅ | ❌ | ⏳ | ❌, English abroad instead |
| pl | Polish | ✅ | ❌ | ⏳ | ❌, English abroad instead |
| ru | Russian | ✅ | ❌ | ⏳ | ❌, English abroad instead |
| tr | Turkish | ✅ | ❌ | ⏳ | ❌, English abroad instead |
| zh | Chinese | ✅ | ❌ | ⏳ | ❌, English abroad instead |
| ar | Arabic | ✅ | ❌ | ⏳ | ❌, English abroad instead |
| id | Indonesian | ✅ | ❌ | ⏳ | ❌, English abroad instead |
| sv | Swedish | ✅ | ❌ | ⏳ | ❌, English abroad instead |
| **vi** | **Vietnamese** | **❌ NOT SUPPORTED** | ❌ | **not tested: no Bland model** | **❌ NOT SUPPORTED. English abroad instead (Sasha 128).** |

**Two notes on the table**
- **English abroad only reaches venues in countries `venue_read` knows.** Today those are ES, PT, FR, IT, DE, AT, GB,
  IE, VN and KE. A Japanese or Turkish venue isn't read at all yet.
- **Bland speaking a language is not the same as Sasha being allowed to call in it.** Each new script needs a native
  speaker's read before any venue hears it. That is the rule already written above `calls.LANGUAGES`.

## 1. Who could add Vietnamese calls later

Vietnamese stays NOT SUPPORTED for calls until a provider that speaks it is integrated and its script is reviewed by a
native speaker.

The candidates below are named from their **public documentation**:
- **None is integrated** and none has been tried on an account.
- Each must be checked before any build.

| Provider | Vietnamese, per its public docs | How it would fit |
|---|---|---|
| **Google Cloud Text-to-Speech** | vi-VN voices | TTS only. It needs a call layer (Twilio Media Streams, or a voice-agent platform that accepts a custom TTS). |
| **Microsoft Azure AI Speech** | vi-VN neural voices, plus vi-VN speech-to-text | TTS and STT. Same call-layer need. |
| **ElevenLabs** | Vietnamese in its multilingual v2.5 models | TTS. Also offers a conversational-agent product with telephony. |
| **Voice-agent platforms that take those voices** (e.g. Vapi, Retell) | Through the TTS/STT they plug in | They would replace Bland for Vietnam calls only. That would be a second call path, with its own approval, recap and transcript reading. |

**The other half:** recognising a Vietnamese "yes" also needs **speech-to-text in Vietnamese**, and the recap and yes
words (`recap.py`) in Vietnamese. Speaking it is half the work.

## 2. The test calls

### 2.1 The 6 scripted languages: placed on 3 Oct, 13:08–13:17 (Sasha 130)

- **Line:** the founder's own mobile, set as `SASHA_TEST_CALL_NUMBER` on 3 Oct, with his approval.
- **Each call:** one call per language, with the script's real opening sentence (AI disclosure first) and a 1-minute
  cap. Nothing was recorded or booked.
- **Outcome:** all 6 were placed by Bland, answered and completed, at about 1 minute each.
- **What Bland heard:** Bland transcribed the founder's replies in each language: "Sí. Correcto." / "É possível.
  Correto." / "Oui." / "Ja, ja." / "è corretto".
- **What this does not show:** the transcript proves the call connected and Bland understood the replies. It doesn't
  show how the voice sounded. **The founder's ear is the verdict** for each language: ✅ / ⚠ / ❌.

Bland call ids: en f4ec1671 · es bf660be8 · pt e5e4c099 · fr 0724b62e · de fff578fc · it 3b2ce33d.

### 2.2 The other 11: later

**The line exists now** (§2.1).

**Still needed**
1. **A fixed test sentence per language.** It is the AI disclosure plus one line, in hi, ja, ko, nl, pl, ru, tr, zh,
   ar, id and sv. CR 7 is drafting the disclosures in `wordings.DISCLOSURE`, and the calls will use them verbatim, so a
   venue never hears one disclosure and reads another. They are marked unreviewed and used **only** on our own line.
2. **A sitting with the founder:** 11 calls of about 1 minute each. He marks each ✅ / ⚠ / ❌ here.

**Cost:** Bland bills per minute; about 11 minutes in total.
