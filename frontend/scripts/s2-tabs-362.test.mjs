// Sasha 362 · every S2 tab is reachable at phone width (Tyler's dry run, iPhone Safari: "My Keep" and "Group" ran off the right edge and
// couldn't be scrolled to). Read as SOURCE here — and measured live at 375 px (docs/sasha/S-362-tabs-at-phone-width.md).
//   cd frontend && npm test
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const root = new URL('..', import.meta.url).pathname
const read = (p) => readFileSync(join(root, p), 'utf8')

test('1 · S2 draws its tabs with the ONE tab bar, from ONE list that holds every tab', () => {
  const s2 = read('app/s2/S2App.tsx')
  assert.equal((s2.match(/<TabBar\b/g) || []).length, 1)
  assert.doesNotMatch(s2.slice(s2.indexOf('<header'), s2.indexOf('</header>')), /<button\b/)   // no tab drawn beside it
  const list = s2.slice(s2.indexOf('const S2_TABS'), s2.indexOf('] as const', s2.indexOf('const S2_TABS')))
  assert.deepEqual([...list.matchAll(/id: '([a-z]+)'/g)].map((m) => m[1]), ['sasha', 'trip', 'activity', 'keep', 'group'])
})

test('2 · the bar never clips a tab: it scrolls sideways, each tab keeps its size and never wraps', () => {
  const bar = read('app/s2/TabBar.tsx')
  assert.match(bar, /overflowX: 'auto'/)
  assert.match(bar, /flexWrap: 'nowrap'/)
  assert.match(bar, /minWidth: 0/)                       // the bar may be narrower than its tabs (then it scrolls)
  assert.match(bar, /flex: '0 0 auto'/)                  // a tab never shrinks to nothing
  assert.match(bar, /whiteSpace: 'nowrap'/)
  assert.match(bar, /scrollIntoView/)                    // the chosen tab is brought into view
  assert.doesNotMatch(bar, /justifyContent: 'flex-end'/) // (flex-end + overflow cuts the start off, unscrollably — margin-left:auto instead)
})
