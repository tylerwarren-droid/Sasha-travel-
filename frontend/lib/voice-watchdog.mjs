// Sasha 197 · the voice watchdog's decision, pure so a build-time test can hold it (scripts/check-voice-watchdog.mjs).
// Live 7 Oct: after Sasha's greeting the mic never came on — Sasha 192's "not listening → connect" fired WHILE a connect was
// still in flight (mic permission + Deepgram take seconds), so new connects kept replacing the one about to open.
//   s = { now, manualStop, ready, muted, connected, connecting, hadConnected, wsOpen, lastAlive, gated, gatedSince, heardAt }
// → 'rearm' (open a mic left closed) | 'restart' (speech, no transcript: restart the stream) | 'reconnect' | null
export function watchdogAction(s) {
  if (s.manualStop || !s.ready || s.muted) return null
  if (s.gated && s.gatedSince && s.now - s.gatedSince > 45000) return 'rearm'
  if (!s.gated && s.heardAt && s.now - s.heardAt > 8000 && s.connected) return 'restart'
  // only a connection that WAS up and is gone, with nothing in flight and the close handler's own retry given time
  if (!s.connected && !s.connecting && !s.wsOpen && s.hadConnected && s.now - s.lastAlive > 15000) return 'reconnect'
  return null
}
