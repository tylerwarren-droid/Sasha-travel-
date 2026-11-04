/**
 * Sasha 336 · ONE palette for the group pages (/group, /vault/<token>) on Sasha's dark theme (globals.css: #0a0a0f). Tailwind's base reset
 * strips buttons to plain text, so every button here gets its own real button style. Every text-on-background pair below is WCAG AA
 * (≥ 4.5:1) — backend/tests/test_s336_group_fixes.py computes each ratio from THIS file.
 */
import type { CSSProperties } from 'react'

export const T = {
  bg: '#0a0a0f', surface: '#16161f', field: '#1f1f2b', border: '#5c5c70',
  text: '#f0ede8', muted: '#b9b4ad', link: '#9cc2ff',
  gold: '#e8b931', onGold: '#16120a', second: '#2b2b3a',
  over: '#ff8f85', vault: '#ffbe5c', planned: '#9cc2ff', booked: '#6ad99a', idle: '#b9b4ad',
} as const

/** [foreground, background] — the pairs the pages draw; each must be ≥ 4.5:1 */
export const PAIRS: [keyof typeof T, keyof typeof T][] = [
  ['text', 'bg'], ['text', 'surface'], ['text', 'field'], ['muted', 'bg'], ['muted', 'surface'], ['link', 'surface'], ['link', 'bg'],
  ['onGold', 'gold'], ['text', 'second'], ['over', 'bg'], ['vault', 'bg'], ['planned', 'bg'], ['booked', 'bg'], ['idle', 'bg'],
]

export const TONE: Record<string, string> = { 'over limit': T.over, 'needs vault': T.vault, planned: T.planned, booked: T.booked,
  cancelled: T.idle, 'not planned': T.idle }

export const page: CSSProperties = { color: T.text, background: T.bg, fontFamily: 'system-ui, sans-serif' }
export const card: CSSProperties = { background: T.surface, border: `1px solid ${T.border}`, borderRadius: 12, padding: 14 }
export const field: CSSProperties = { background: T.field, color: T.text, border: `1px solid ${T.border}`, borderRadius: 8, padding: '8px 10px',
  fontSize: 15, boxSizing: 'border-box' }
const base: CSSProperties = { borderRadius: 999, padding: '8px 16px', fontSize: 14, fontWeight: 600, cursor: 'pointer', lineHeight: 1.2 }
export const btn: CSSProperties = { ...base, background: T.gold, color: T.onGold, border: `1px solid ${T.gold}` }
export const btn2: CSSProperties = { ...base, background: T.second, color: T.text, border: `1px solid ${T.border}` }
export const small: CSSProperties = { ...btn2, padding: '4px 10px', fontSize: 13 }
/** a disabled button is still a button — dimmed, never invisible */
export const off = (s: CSSProperties, disabled: boolean): CSSProperties => (disabled ? { ...s, opacity: 0.55, cursor: 'not-allowed' } : s)
