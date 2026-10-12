/**
 * Sasha 244 · /you never pushes a Gmail someone doesn't have (Jon signs in with iCloud; his work mail is Outlook). The connect form is
 * shown in full when the sign-in address is a Gmail one, or when a Gmail is already connected / expired; otherwise it waits behind
 * one line and an "I have a Gmail account" button. Who is invited is unchanged (SASHA_GMAIL_ACCOUNTS).
 */
export function isGmailAddress(email) {
  return /@(gmail|googlemail)\.com$/i.test(String(email || '').trim())
}

/** 'full' | 'quiet' */
export function gmailOffer({ email, connected, expired, opened }) {
  if (connected || expired || opened) return 'full'
  if (!email) return 'full'   // the founder (no address in whoami) and anyone unknown: as before
  return isGmailAddress(email) ? 'full' : 'quiet'
}

/** The quiet line: the sign-in's domain only, never the address. */
export function quietLine(email) {
  const domain = String(email || '').split('@')[1] || 'another'
  return `You signed in with ${/^(icloud|me|mac)\.com$/i.test(domain) ? 'an iCloud' : `a ${domain}`} address. Connect Gmail only if you have a Gmail account — for Outlook or Microsoft 365 mail, use the Outlook section below.`   // Sasha 245 · Outlook is read now (CR 86)
}
