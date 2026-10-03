'use client'

/**
 * Sasha 123 · A-4 (kanoe-site-scope.md §0, §9.2; default ON — the founder may strike it): one line above every archive
 * page. The archive's own content is unchanged. The portal's nav is fixed at the top, so the banner is too, and the nav
 * and the page sit below it — by the banner's MEASURED height (on a phone it wraps to two or three lines).
 */
import Link from 'next/link'
import { useLayoutEffect, useRef } from 'react'

export default function ArchiveBanner() {
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const set = () => document.documentElement.style.setProperty('--archive-banner-h', `${el.offsetHeight}px`)
    set()
    const ro = new ResizeObserver(set)
    ro.observe(el)
    return () => { ro.disconnect(); document.documentElement.style.removeProperty('--archive-banner-h') }
  }, [])
  return (
    <>
      <style>{`nav{top:var(--archive-banner-h,34px) !important} body.portal-body{padding-top:var(--archive-banner-h,34px)}`}</style>
      <div ref={ref} role="note" style={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 300, padding: '7px 16px',
        background: '#fdf3d8', color: '#3d2f00', fontSize: 13, lineHeight: 1.4, textAlign: 'center', fontFamily: 'system-ui, sans-serif' }}>
        Original vision (archive) — Kanoe&rsquo;s earlier travel-platform plan, kept for reference. It describes plans, not the current
        product; see the main site for what is built today. <Link href="/" style={{ color: '#3d2f00', textDecoration: 'underline' }}>→ kanoe.ai</Link>
      </div>
    </>
  )
}
