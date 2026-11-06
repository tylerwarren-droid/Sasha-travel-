/** Sasha 349 · ONE way to say money: in the record's own currency (€), to the cent when it has cents — never rounded on one card
 *  and exact on the next ("€59 all in" beside "€58.55", found live). */
export const eur = (n: unknown): string =>
  typeof n === 'number' && Number.isFinite(n) ? `€${n.toLocaleString('en-GB', { minimumFractionDigits: Number.isInteger(n) ? 0 : 2, maximumFractionDigits: 2 })}` : '—'
