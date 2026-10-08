// Sasha 212 · NEVER AN EMPTY BUBBLE. The agent's reply text arrives with her voice (one utterance per step, Sasha 210), so a
// turn that starts with a tool (propose_trip after "Flying from London.") used to leave an empty placeholder bubble on
// screen for the whole tool run — rendered before the spinner. The reply's bubble is added with its first words, never
// before; and the chat renders no message without words.

/** The messages after the reply's text `t` arrives: appended the first time (`first`), replaced after; nothing for no words. */
export function placeReply(prev, t, first) {
  if (!String(t ?? '').trim()) return prev
  const msg = { role: 'assistant', content: t }
  return first ? [...prev, msg] : [...prev.slice(0, -1), msg]
}

/** What the chat renders: never a message without words, hers or theirs. */
export function visible(msg) {
  return Boolean(String(msg?.content ?? '').trim())
}
