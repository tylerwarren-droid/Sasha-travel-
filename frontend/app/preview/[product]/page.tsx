import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import ProductTab from '../../components/products/ProductTab'
import { BRANDS, type ProductKey } from '../../components/products/brands'

/**
 * CR 16 · an UNLINKED preview of the product tabs while the site hold (Sasha 124) applies — the founder's choice, 4 Oct
 * 2026. noindex, no nav link, labelled PREVIEW. When the hold lifts, the Sasha tab mounts <ProductTab/> on the existing
 * routes (/relocation, /campusme, /spain-services) and this route goes.
 */
const SLUG: Record<string, ProductKey> = { relocateme: 'relocation', campusme: 'campus', espaname: 'espana' }

export const dynamic = 'force-dynamic'

export async function generateMetadata({ params }: { params: Promise<{ product: string }> }): Promise<Metadata> {
  const { product } = await params
  const k = SLUG[product]
  return { title: k ? `${BRANDS[k].name} — preview` : 'Preview', robots: { index: false, follow: false } }
}

export default async function Page({ params }: { params: Promise<{ product: string }> }) {
  const { product } = await params
  const k = SLUG[product]
  if (!k) notFound()
  return (
    <>
      <p style={{ margin: 0, padding: '8px 16px', background: '#1d1d1d', color: '#fff', fontSize: 13, textAlign: 'center' }}>
        PREVIEW — not linked from the site yet. Copy: EU 150; every line carries its mark.
      </p>
      <ProductTab product={k} />
    </>
  )
}
