import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import ProductTab from '../../components/products/ProductTab'
import { BRANDS, type ProductKey } from '../../components/products/brands'

/**
 * CR 16 · the product pages: RelocateMe, CampusMe, EspañaMe — linked from the AgAPI hub (/agapi, Sasha 143: the hub
 * supersedes the six-tab pages; /relocation, /campusme and /spain-services redirect to it). noindex, labelled PREVIEW.
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
        PREVIEW — this product’s page, linked from the AgAPI hub. Every line carries its mark; TEST bookings are TEST.
      </p>
      <ProductTab product={k} />
    </>
  )
}
