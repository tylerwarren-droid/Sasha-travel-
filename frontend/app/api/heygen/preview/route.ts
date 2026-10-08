// Sasha 215 · S2 — the start screen shows HER: the configured LiveAvatar avatar's own preview still, fetched with the key
// that lives only on the server (HEYGEN_API_KEY) and served from here, cached for a day. No still → 404 and the page hides
// the image (never a stand-in photo). public/sasha-preview.jpg, which the page used to point at, was never in the repo.
export const dynamic = 'force-dynamic'

const AVATAR_ID = 'ab0765ad-69de-41fb-9f8a-bd01c3c52d6f'   // the same avatar the token route opens

function imageUrlIn(obj: unknown): string | null {
  // the avatar's preview image, wherever the API puts it (preview_url, preview_image_url, image_url…)
  if (!obj || typeof obj !== 'object') return null
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    if (typeof v === 'string' && /^https:\/\//.test(v) && (/preview|image|thumbnail|poster/i.test(k) || /\.(jpe?g|png|webp)(\?|$)/i.test(v))) return v
  }
  for (const v of Object.values(obj as Record<string, unknown>)) {
    const u = typeof v === 'object' ? imageUrlIn(v) : null
    if (u) return u
  }
  return null
}

export async function GET(): Promise<Response> {
  const key = process.env.HEYGEN_API_KEY
  if (!key) return new Response('no LiveAvatar key', { status: 404 })
  try {
    const r = await fetch(`https://api.liveavatar.com/v1/avatars/${AVATAR_ID}`, { headers: { 'X-API-KEY': key }, cache: 'no-store' })
    const url = r.ok ? imageUrlIn(await r.json().catch(() => null)) : null
    if (!url) return new Response('no preview', { status: 404 })
    const img = await fetch(url)
    if (!img.ok || !img.body) return new Response('no preview', { status: 404 })
    const said = img.headers.get('content-type') ?? ''
    const type = said.startsWith('image/') ? said : /\.png(\?|$)/i.test(url) ? 'image/png' : /\.jpe?g(\?|$)/i.test(url) ? 'image/jpeg' : 'image/webp'
    return new Response(img.body, { status: 200, headers: { 'content-type': type,
      'cache-control': 'public, max-age=86400, s-maxage=86400' } })
  } catch {
    return new Response('no preview', { status: 404 })
  }
}
