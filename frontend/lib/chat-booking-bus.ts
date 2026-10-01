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
  try { return handler ? handler(text) : false } catch { return false }
}
