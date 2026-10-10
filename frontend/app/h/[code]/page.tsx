import { redirect } from 'next/navigation'

// Sasha 228 · the short link on /next's "Add from your phone" card (and in its QR code) → /s2, straight to Add my passport.
export default async function Handoff({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params
  redirect(/^[a-z0-9]{6,32}$/.test(code) ? `/s2?handoff=${code}` : '/s2')
}
