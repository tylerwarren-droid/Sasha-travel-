import type { Status } from '../../(site)/content/types'
import s from './site.module.css'

const GLYPH: Record<Status, string> = { proven: '✅', reported: '◐', concept: '○' }
const WORD: Record<Status, string> = { proven: 'Proven', reported: 'Founder-reported', concept: 'Concept: designed, not built' }

/** Sasha 123 · every claim line carries one: ✅ proven · ◐ founder-reported · ○ concept — and names its evidence. */
export function Mark({ status, evidence }: { status: Status; evidence: string }) {
  return <span className={s.mark} title={`${WORD[status]} — ${evidence}`} aria-label={WORD[status]}>{GLYPH[status]}</span>
}
