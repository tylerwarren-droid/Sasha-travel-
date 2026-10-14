'use client'
/**
 * Sasha 246 item 2 · THE PAUSE / SLEEP BUTTON — one control, used on /s2 and /next, always visible.
 * One tap: she stops mid-word, the mic goes off, her face dims (asleep, not listening). Tap again: she wakes ("I'm here").
 * The rule is lib/sleep-rule.mjs; each surface carries out its effects (its speaker / avatar, its VoiceButton, its face).
 */
import type { CSSProperties } from 'react'
import { Moon, Sun } from 'lucide-react'
import { buttonLabel } from '@/lib/sleep-rule.mjs'

export default function SleepButton({ asleep, onToggle, size = 44, showLabel = true, className, style, tone = 'dark' }: {
  asleep: boolean
  onToggle: () => void
  size?: number
  showLabel?: boolean       // the words beside the icon — Sasha 268 · item 8: always, unless a surface has no room (/next's picture-in-picture)
  className?: string
  style?: CSSProperties
  tone?: 'dark' | 'glass'   // /s2's card look, or /next's glass pills over her face
}) {
  const gold = '#e8b931'
  const label = buttonLabel(asleep)
  const base: CSSProperties = tone === 'glass'
    ? { background: asleep ? 'rgba(232,185,49,.22)' : 'rgba(0,0,0,.4)', border: `1px solid ${asleep ? 'rgba(232,185,49,.7)' : 'rgba(255,255,255,.18)'}`, backdropFilter: 'blur(8px)' }
    : { background: asleep ? 'rgba(232,185,49,.16)' : '#16161f', border: `1px solid ${asleep ? gold : 'rgba(255,255,255,.12)'}` }
  return (
    <button type="button" className={className} aria-pressed={asleep} aria-label={asleep ? 'Sasha is paused — tap to wake her' : 'Pause Sasha — she stops talking and listening'} data-sasha-pause={asleep ? 'paused' : 'awake'}
      title={label}
      onClick={e => { e.stopPropagation(); onToggle() }}
      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 7, height: size, minWidth: size, padding: showLabel ? '0 12px' : 0,
        borderRadius: 999, color: asleep ? gold : '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap', transition: 'background .3s, border-color .3s, color .3s', ...base, ...style }}>
      {asleep ? <Sun size={Math.round(size * 0.42)} strokeWidth={2} /> : <Moon size={Math.round(size * 0.42)} strokeWidth={2} />}
      {showLabel ? <span>{label}</span> : null}
    </button>
  )
}
