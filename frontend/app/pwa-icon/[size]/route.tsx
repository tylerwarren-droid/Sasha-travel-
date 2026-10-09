import { ImageResponse } from 'next/og'

// Sasha 214 · the Home Screen icon, drawn here (no binary files): Sasha's gold "S" on the app's night background
export async function GET(_req: Request, ctx: { params: Promise<{ size: string }> }) {
  const { size } = await ctx.params
  const n = [180, 192, 512].includes(Number(size)) ? Number(size) : 512
  return new ImageResponse(
    (
      <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'linear-gradient(160deg,#1a1626 0%,#0b0b12 100%)' }}>
        <div style={{ width: n * 0.62, height: n * 0.62, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'linear-gradient(135deg,#E8B923,#B8860B)', color: '#0b0b12', fontSize: n * 0.4, fontWeight: 700 }}>S</div>
      </div>
    ),
    { width: n, height: n },
  )
}
