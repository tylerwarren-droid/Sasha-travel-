# Sasha 322 · the mic always says the truth, fast

Tyler (1 Nov 2026): "takes quite a long time to get started… never quite clear what status is… not sure if she can hear you".

## Root test (written before the code)

1. **The one truth.** The mic's state is read from the audio pipeline itself: the browser's permission, the stream's track (live and
   not muted), the audio context (running), the speech socket (open), and audio frames arriving now (the last one within 1 s).
   It is never a timer, and never a flag a button set. `lib/mic-machine.mjs` `micState(snapshot)` is the one place that turns a
   snapshot of those five facts, plus her phase (thinking, speaking, asleep), into the state shown. It's pure and tested.
2. **PATCH test.** A label set on a timeout is a patch. The only clock in the machine is "the last frame arrived within
   `LIVE_FRAME_MS`", which is a fact about the pipeline. No state is ever set by `setTimeout`.
3. **Whole class.** Can the screen say "Listening" while no audio is reaching her?
   - No: Listening ⇔ `hears()` = track live and unmuted ∧ audio running ∧ socket open ∧ a frame within 1 s ∧ not gated (she isn't
     talking) ∧ not muted (a turn isn't in flight). Exactly then, the frame handler sends to the socket.

   And the reverse, audio reaching her while the screen says otherwise?
   - No: when frames are sent, `hears()` is true, and Listening outranks Speaking. A barge-in reaches her, and the screen says
     Listening.

   Before the socket opens, frames are captured and **buffered**, never sent, and the state is Connecting. They're flushed on open.

## The states (everywhere: /s2, New chat, her face, the chat, /next, /voice)

| state | words | look |
|---|---|---|
| off | Tap to talk | plain mic |
| connecting | Getting ready… | spinner |
| listening | Listening | green, and a live input-level bar that moves with his voice |
| thinking | Thinking… | soft pulse; mic paused (turn in flight) |
| speaking | Speaking | gold ring; mic paused (her voice) |

## Before (measured 1 Nov 2026)

- **Tyler's iPhone** (iOS 18.7, Safari 26.6.1, /s2), from the backend's `[mic]` events, connect → first frame heard over 8 sessions:
  1.36–2.76 s.
  - mic permission (granted): 0.24–0.5 s
  - Deepgram key mint: 0.73–1.09 s (the socket waited for it)
  - socket handshake: 0.37–0.6 s
  - worklet + first frame: 0.08–0.22 s
  - every reconnect outside a tap: +1 s and "deaf, audio suspended until a tap" (iOS starts a new audio context suspended)
- **Prod /mic-test** (headless Chromium, fake mic), tap → Listening: 2,510 / 1,509 / 1,839 ms. Key mint: 1.0–1.6 s of that.

## The cuts

1. **The key is minted before the tap.** It's fetched when the mic mounts and kept for 10 minutes (the key lives an hour), so a tap
   never waits on it. This asks for nothing: no mic, no permission prompt.
2. **The socket opens at the tap**, in parallel with the mic permission and the audio worklet (it was serial: mic → key → socket →
   worklet).
3. **The audio pipeline outlives the socket.** A dropped socket reconnects alone. The stream, the running audio context and the
   worklet stay, so iOS never needs a second tap and it's never "deaf". The state is Connecting the moment the socket drops.
4. **Words said during Connecting are kept.** Frames captured before the socket opens are buffered (up to 5 s) and sent first.
   See `flushed {ms}` in the mic log.
5. A preconnect to `api.deepgram.com` warms DNS and TLS on page load.
