'use client'

import { useState } from 'react'

/** CR 1 · copies one answer. Every outcome is shown: copied, or why not (then the text is there to select by hand). */
export default function CopyAnswer({ text }: { text: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setState('copied')
    } catch {
      setState('failed')
    }
  }
  return (
    <button type="button" onClick={copy} className="ml-2 rounded border border-slate-300 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-50">
      {state === 'copied' ? 'Copied ✓' : state === 'failed' ? 'Copy blocked — select it by hand' : 'Copy'}
    </button>
  )
}
