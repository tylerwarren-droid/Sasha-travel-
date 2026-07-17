// Hardcoded single demo user — stands in for a real auth flow (added later). This is the one
// source of truth for "who is signed in": the session token personalizes the avatar greeting
// with it, the conductor addresses them by name, and chat history is stored against it.
export const CURRENT_USER = {
  id: '11111111-1111-4111-8111-111111111111',
  firstName: 'Jon',
  displayName: 'Jon Peters',
  email: 'jon@kanoe.ai',
}
