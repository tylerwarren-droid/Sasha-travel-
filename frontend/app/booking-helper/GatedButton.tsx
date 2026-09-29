'use client'

/**
 * P807mt · A button that CANNOT be greyed out without saying why.
 *
 * There is deliberately no `disabled` prop. A GatedButton is disabled exactly when `needs` is non-empty, and
 * whenever it is disabled it renders those needs beneath itself. So "a silent grey button" is not a mistake
 * someone has to remember to avoid; it cannot be written. (The rule used to live in a comment on the page,
 * and was applied to one button of four.)
 *
 * `done` is for a button that is off because its work is complete ("already paired"): that is a state to
 * state, not a need to meet.
 *
 * scripts/check-outcome-surfaces.mjs fails the build if an outcome surface uses `disabled=` anywhere else.
 */

type Props = {
  label: string
  onClick: () => void
  /** What this button is waiting for. Empty means enabled. Falsy entries are ignored. */
  needs: Array<string | false | null | undefined>
  /** Set when the button is off because its work is already done — shown instead of needs. */
  done?: string | false | null
  className?: string
}

export function GatedButton({ label, onClick, needs, done, className }: Props) {
  const waiting = needs.filter((n): n is string => typeof n === 'string' && n.length > 0)
  const off = !!done || waiting.length > 0
  return (
    <span className="inline-flex flex-col items-start gap-0.5">
      <button className={`rounded border px-3 py-1 disabled:opacity-40 ${className ?? ''}`} disabled={off} onClick={onClick}>
        {label}
      </button>
      {done
        ? <span className="text-xs opacity-70">{done}</span>
        : waiting.length > 0 && <span className="text-xs opacity-70">Waiting for: {waiting.join(', ')}.</span>}
    </span>
  )
}
