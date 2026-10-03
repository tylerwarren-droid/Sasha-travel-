/**
 * Sasha 123 · A-4 (kanoe-site-scope.md §0, §9.2; default ON — the founder may strike it): one line above every archive
 * page. The archive's own content is unchanged. The portal's nav is fixed at the top, so the banner is too, and the nav
 * and the page sit below it.
 */
import Link from 'next/link'

export default function ArchiveBanner() {
  return (
    <>
      <style>{`nav{top:34px !important} body.portal-body{padding-top:34px}`}</style>
      <div role="note" style={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 300, minHeight: 34, padding: '7px 16px',
        background: '#fdf3d8', color: '#3d2f00', fontSize: 13, lineHeight: 1.4, textAlign: 'center', fontFamily: 'system-ui, sans-serif' }}>
        Original vision (archive) — Kanoe&rsquo;s earlier travel-platform plan, kept for reference. It describes plans, not the current
        product; see the main site for what is built today. <Link href="/" style={{ color: '#3d2f00', textDecoration: 'underline' }}>→ kanoe.ai</Link>
      </div>
    </>
  )
}
