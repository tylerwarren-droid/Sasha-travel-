import React from 'react'

// Plain-text view of markdown — used for what the avatar SPEAKS, so TTS never reads
// literal "asterisk asterisk" / "hash" / bullet characters aloud.
export function stripMarkdown(input: string): string {
  return (input || '')
    .replace(/```[\s\S]*?```/g, '')            // fenced code
    .replace(/`([^`]+)`/g, '$1')               // inline code
    .replace(/\*\*([^*]+)\*\*/g, '$1')         // **bold**
    .replace(/\*([^*\n]+)\*/g, '$1')           // *italic*
    .replace(/_([^_\n]+)_/g, '$1')             // _italic_
    .replace(/^#{1,6}\s+/gm, '')               // # headings
    .replace(/^\s*[-*•]\s+/gm, '')             // bullet markers
    .replace(/^\s*\d+\.\s+/gm, '')             // numbered markers
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')   // [text](url) -> text
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

// Inline spans: **bold**, *italic*/_italic_, `code`. Safe — builds React nodes, never
// raw HTML.
function renderInline(text: string, keyBase: string): React.ReactNode[] {
  const out: React.ReactNode[] = []
  const re = /(\*\*[^*]+\*\*|\*[^*\n]+\*|_[^_\n]+_|`[^`]+`)/g
  let last = 0
  let m: RegExpExecArray | null
  let n = 0
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const t = m[0]
    if (t.startsWith('**')) {
      out.push(<strong key={`${keyBase}-${n}`} className="font-semibold text-white">{t.slice(2, -2)}</strong>)
    } else if (t.startsWith('`')) {
      out.push(<code key={`${keyBase}-${n}`} className="px-1 rounded bg-white/10 text-[0.85em]">{t.slice(1, -1)}</code>)
    } else {
      out.push(<em key={`${keyBase}-${n}`}>{t.slice(1, -1)}</em>)
    }
    last = m.index + t.length
    n++
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

// Render a constrained subset of markdown (bold, italic, code, bullet/numbered lists,
// paragraphs) as safe React elements. Enough for concierge replies; no XSS surface.
export function renderMarkdown(content: string): React.ReactNode {
  const lines = (content || '').replace(/```[\s\S]*?```/g, '').split('\n')
  const blocks: React.ReactNode[] = []
  let list: { ordered: boolean; items: string[] } | null = null

  const flush = (key: string) => {
    if (!list) return
    const items = list.items.map((it, i) => <li key={i}>{renderInline(it, `${key}-${i}`)}</li>)
    blocks.push(
      list.ordered
        ? <ol key={key} className="list-decimal pl-5 space-y-0.5 my-1">{items}</ol>
        : <ul key={key} className="list-disc pl-5 space-y-0.5 my-1">{items}</ul>
    )
    list = null
  }

  lines.forEach((raw, i) => {
    const line = raw.trim()
    const bullet = line.match(/^[-*•]\s+(.*)/)
    const numbered = line.match(/^(\d+)\.\s+(.*)/)
    if (bullet) {
      if (list && list.ordered) flush(`l-${i}`)
      if (!list) list = { ordered: false, items: [] }
      list.items.push(bullet[1])
      return
    }
    if (numbered) {
      if (list && !list.ordered) flush(`l-${i}`)
      if (!list) list = { ordered: true, items: [] }
      list.items.push(numbered[2])
      return
    }
    flush(`l-${i}`)
    if (line === '') return
    blocks.push(<p key={`p-${i}`}>{renderInline(line, `p-${i}`)}</p>)
  })
  flush('l-end')

  return <div className="space-y-1.5">{blocks}</div>
}
