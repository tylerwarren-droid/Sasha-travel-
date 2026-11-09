'use client'
/**
 * Sasha 362 · S2's ONE TAB BAR (found in Tyler's dry run, iPhone Safari: "My Keep" and "Group" ran off the right edge and couldn't be reached).
 * Every tab is reachable at phone width: the tabs come from ONE list, each keeps its size, and the bar SCROLLS sideways when they don't fit
 * (right-aligned when they do). The active tab is scrolled into view. Tested at 375 px (scripts/s2-tabs-362.test.mjs + the live check).
 */
import { useEffect, useRef } from 'react'

export type Tab<K extends string> = { id: K; label: string; data?: string }

export default function TabBar<K extends string>({ tabs, tab, onTab, gold, line, dim }: {
  tabs: readonly Tab<K>[]; tab: K; onTab: (k: K) => void; gold: string; line: string; dim: string
}) {
  const bar = useRef<HTMLElement | null>(null)
  useEffect(() => {   // the chosen tab is never left off-screen
    const el = bar.current?.querySelector<HTMLElement>(`[data-tab="${tab}"]`)
    el?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  }, [tab])
  return (
    <nav ref={bar} data-s2-tabs aria-label="Sasha's screens"
      style={{ display: 'flex', flexWrap: 'nowrap', gap: 6, flex: '1 1 auto', minWidth: 0, overflowX: 'auto', WebkitOverflowScrolling: 'touch',
               scrollbarWidth: 'none', padding: '2px 0' }}>
      {tabs.map((t, i) => (
        <button key={t.id} type="button" data-tab={t.id} {...(t.data ? { [`data-${t.data}`]: '' } : {})} onClick={() => onTab(t.id)}
          aria-current={tab === t.id ? 'page' : undefined}
          style={{ flex: '0 0 auto', marginLeft: i === 0 ? 'auto' : undefined, whiteSpace: 'nowrap', padding: '6px 12px', borderRadius: 999,
                   border: `1px solid ${tab === t.id ? gold : line}`, background: 'transparent', color: tab === t.id ? gold : dim, fontWeight: 600, fontSize: 14 }}>
          {t.label}</button>))}
    </nav>)
}
