'use client'
/** Sasha 327 · TRAINS ARE TRAINS — a train row on the trip, drawn from the server's `train` (backend booking_signer/trains.py: AgAPI's
 *  booking record, read when shown): operator + train number, from → to, departs–arrives, coach / seat, the reference, the fare and its
 *  price, and one "Manage your ticket" button to the operator's own page (nothing is changed from here). */

export type Train = {
  operator?: string | null; number?: string | null; origin?: string | null; destination?: string | null; date?: string | null
  departs?: string | null; arrives?: string | null; coach?: string | null; seat?: string | null; reference?: string | null
  passengers?: number | null; fare?: string | null; price_eur?: number | null
  manage?: { page: string; label: string; how?: string | null; options?: { action?: string; say?: string; open_now?: boolean }[] } | null
}

const eur = (n: number) => `€${n.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export default function TrainLine({ t, status }: { t: Train; status?: string }) {
  const leg = t.origin && t.destination ? `${t.origin} → ${t.destination}` : ''
  const times = [t.departs, t.arrives].filter(Boolean).join('–')
  const seat = [t.coach ? `coach ${t.coach}` : '', t.seat ? `seat ${t.seat}` : ''].filter(Boolean).join(', ')
  const fare = [t.fare ? `fare ${t.fare}` : '', t.price_eur != null ? eur(t.price_eur) : ''].filter(Boolean).join(' · ')
  return (
    <div data-train>
      <div>🚆 {[t.operator, t.number].filter(Boolean).join(' ')}{leg ? ` · ${leg}` : ''}</div>
      <div className="lw-note-s">
        {[times, seat, t.reference ? `ref ${t.reference}` : '', t.passengers ? `${t.passengers} ${t.passengers === 1 ? 'passenger' : 'passengers'}` : '', fare, status ?? '']
          .filter(Boolean).join(' · ')}
      </div>
      {(t.manage?.options ?? []).map((o, k) => o.say ? <div key={k} className="lw-note-s">{o.say}</div> : null)}
      {t.manage?.page ? (
        <a className="lw-chip" data-manage-ticket href={t.manage.page} target="_blank" rel="noopener noreferrer">{t.manage.label || 'Manage your ticket'}</a>
      ) : null}
    </div>
  )
}
