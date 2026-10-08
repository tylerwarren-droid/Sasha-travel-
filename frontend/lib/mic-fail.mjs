// Sasha 215 · CR 56 #9 — THE MIC NEVER FAILS SILENTLY. A mic that can't be set up (permission, no device, the voice service's
// key, a socket that won't stay open) is SHOWN on the page and SAID by Sasha, once per kind of failure, and she says what to do.

/** The key the browser may use: the backend's short-lived key, or — only when the backend says the proxy isn't configured
 *  (501, local development) — the public dev key. Any other failure is a failure, never a silent fallback. */
export function keyOrFail(status, key, publicKey) {
  if (key) return { key }
  if (status === 501 && publicKey) return { key: publicKey }
  return { key: '', error: 'Voice service unavailable' }
}

/** After this many reconnects in a row without the socket opening, the mic is said to be down. */
export const RECONNECTS_BEFORE_SAYING = 3

/** What Sasha says for a mic error (null: say nothing — no error, or one that's only a passing state). */
export function micFailLine(error) {
  if (!error) return null
  if (/reconnecting/i.test(error)) return null
  if (/permission/i.test(error)) return "I can't hear you — your browser has blocked the microphone. Allow it, or just type to me below."
  if (/no microphone/i.test(error)) return "I can't find a microphone on this device — type to me below and I'll answer."
  if (/in use/i.test(error)) return "Another app is using your microphone, so I can't hear you — type to me below for now."
  return "I can't hear you right now — please type to me below."
}

/** Once per kind of failure per conversation: the lines already said are remembered by the caller. */
export function shouldSay(error, said) {
  const line = micFailLine(error)
  return line && !said.has(line) ? line : null
}
