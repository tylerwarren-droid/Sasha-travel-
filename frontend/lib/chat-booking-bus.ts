/**
 * S-66 (EU) · how a line TYPED in Sasha's chat reaches the booking thread before it goes to the conductor:
 * "the second one" picks a card; a "yes" binds to the newest pending read-back card (step 6; cards from step 9).
 * ChatBooking registers one handler; SashaChat asks it first (a Stage B line). It answers false for anything it does
 * not own, and the message goes to the conductor exactly as before.
 */
type Handler = (text: string) => boolean
let handler: Handler | null = null

export function setChatBookingHandler(h: Handler | null): void { handler = h }

/** true → the booking thread took the line (SashaChat shows it as the guest's message and sends nothing on) */
export function takeChatText(text: string): boolean {
  try { return (handler ? handler(text) : false) || takeTypedYes(text) } catch { return false }   // Sasha 169 · a card's yes with no search open
}

/** S-66 step 9 · the ONE pending read-back card a typed "yes" may approve (the newest; a new card replaces it). */
type Pending = (said: string) => void
let pending: Pending | null = null
export function setPendingYes(p: Pending | null): void { pending = p }
// S-75 step 1 · the SAME pattern string as backend/booking_signer/yes.py (a test compares them). (?!\w), not \b: in
// JavaScript \b never matched after the í of a typed "sí"
const YES = /^\s*(yes|yeah|yep|go ahead|ok(ay)?|s[ií]|vale|claro|sim|oui|ja|confirm(ed)?)(?!\w)/i
/** true → the typed line was a yes and went to the pending card (bound to ITS read-back hash by the server) */
export function takeTypedYes(text: string): boolean {
  if (!pending || !YES.test(text)) return false
  const p = pending
  pending = null
  p(text.trim())
  return true
}
