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
| en | English | ✅ | ✅ | ⏳ pending (§2) | ✅ (and English abroad) |
| es | Spanish | ✅ | ✅ (S-33, used live in Madrid) | ⏳ | ✅ |
| pt | Portuguese | ✅ (Bland: pt-BR voice) | ✅ | ⏳ | ✅ |
| fr | French | ✅ | ✅ | ⏳ | ✅ |
| de | German | ✅ | ✅ | ⏳ | ✅ |
| it | Italian | ✅ | ✅ | ⏳ | ✅ |
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

## 2. The 17-language test calls: not placed. Why, and what's needed

**Blocked: there is no "own line" to call.**
- `SASHA_TEST_CALL_NUMBER` is **not set** on Railway, so the test line doesn't exist on the server today.
- Sasha's own Twilio number (`SASHA_CALLER_ID`, +44) is the number calls go **out** from. It has no answering setup to
  receive and listen to a test call.

**Needed to run it**
1. **The founder sets the test line** in Railway as `SASHA_TEST_CALL_NUMBER`. It is a phone he controls, and he sets
   the value himself; it is not given in chat.
2. **Someone answers and listens.** It's 17 short calls, about 30 s each. The test is whether the voice speaks the
   language intelligibly. A transcript can't prove that: Bland's transcript of Sasha's side is the text we sent, not
   what was heard.
3. **A fixed test sentence per language.** It is the AI disclosure plus one line. For the 11 languages without a script
   I would write it myself, marked unreviewed. It is used **only** on our own line, never at a venue.

**Proposed run:** one sitting. The calls go to our line in sequence, with a pause between them. The listener marks each
language ✅ / ⚠ / ❌ in this matrix, and each call's Bland id is recorded.

**Cost:** Bland bills per minute; 17 calls of about 30 s is roughly 9 minutes in total.
