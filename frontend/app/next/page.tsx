import S2App from '../s2/S2App'

// Sasha 396 · /next = S2's desktop layout (EU 288 §5.2; KANOE "THREE DOORS, ONE PRODUCT"): ONE engine — the same turn route (/api/s2-agent),
// memory, cards and taps as /s2 on the phone; desktop adds layout only (the conversation beside a permanent trip pane). The old /next
// (SashaChat in agent mode → /api/sasha-agent → surface "s1") is gone; its own features are named in row 2080 (kept or why they went).
export default function NextPage() {
  return <S2App layout="desktop" />
}
