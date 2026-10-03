import type { DemoKind } from '../../(site)/content/types'
import s from './site.module.css'

/** Sasha 123 · every demo carries one (kanoe-site-scope.md §9.3): the chip, then the tab's own sentence. */
const CHIP: Record<DemoKind, { text: string; cls: string }> = {
  live: { text: 'LIVE', cls: s.chip_live },
  'click-through': { text: 'CLICK-THROUGH', cls: s.chip_clickthrough },
  concept: { text: 'CONCEPT', cls: s.chip_concept },
}

export function DemoLabel({ kind, sentence }: { kind: DemoKind; sentence: string }) {
  return <p className={s.demoSentence}><span className={`${s.chip} ${CHIP[kind].cls}`}>{CHIP[kind].text}</span>{sentence}</p>
}
