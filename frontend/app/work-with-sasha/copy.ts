/**
 * S-55 · The Work-with-Sasha page's words, EN and ES (S-50 §3, with S-52's "AI concierge").
 *
 * ⚠ The three CONSENT wordings are not here: the page fetches them from the server (wordings.py, v2), so the text a
 * venue sees is the text its row stores, byte for byte, and the server refuses a submission whose hashes differ.
 *
 * ⛔ Nothing here claims what Sasha cannot do today (standing rule 4): her own WhatsApp number and form submission do
 * not exist yet, so the page says a permission is recorded now and used only once each starts.
 */
export type Lang = 'en' | 'es'
export const langOf = (v: unknown): Lang => (v === 'es' ? 'es' : 'en')

export const COPY = {
  en: {
    title: 'Work with Sasha',
    lead: 'Sasha is an AI concierge. She books tables for her guests, and she tells you so.',
    pitch: 'When a guest asks Sasha for a table, she reads the booking back to them (the day, the time, how many people, and the name) and they approve it before anything reaches you. Every message says who it is on behalf of, and that Sasha is an AI concierge. She never agrees to a deposit, a card guarantee or a fee: if you ask for one, she goes back to the guest first.',
    notYet: 'Sasha’s own WhatsApp number isn’t live yet, and she doesn’t submit booking forms yet. What you allow here is recorded now and used only once each of those starts.',
    choose: 'Choose what you allow.',
    noneTicked: 'Nothing is ticked for you.',
    channel: { whatsapp: 'WhatsApp', web_submit: 'Our booking form', email_confirm: 'Email confirmation' },
    number: 'WhatsApp number (international form, e.g. +34 600 111 222)',
    formUrl: 'Booking form address (https://…)',
    urlPlaceholder: '[your booking form’s address]',
    emailScope: 'At the email address below.',
    venue: 'Venue name',
    website: 'Venue website (helps Sasha recognise you)',
    country: 'Country (two letters)',
    name: 'Your name',
    role: 'Your role (e.g. owner, manager)',
    email: 'Your email: we send the confirmation link here',
    authorised: 'I am authorised to agree to this on behalf of the venue.',
    confirmNote: 'We’ll email you a link. Nothing starts until you open it and press Confirm. You can withdraw at any time with the link in that email, and every one of Sasha’s channels to your venue stops.',
    privacy: 'How we use your details: Privacy notice',
    draft: '(draft, under legal review)',
    submit: 'Send me the confirmation link',
    needs: 'Waiting for',
    need: { channel: 'a ticked channel', number: 'the WhatsApp number', url: 'the form address', venue: 'the venue name', name: 'your name', role: 'your role', email: 'your email', authorised: 'the authorisation tick' },
    sending: 'Sending…',
    sent: (e: string) => `We’ve emailed a link to ${e}. Nothing starts until you open it and press Confirm. The link works for 48 hours.`,
    closed: 'Sign-up isn’t open yet.',
    unreachable: 'This page couldn’t reach Sasha’s server just now. Please try again later.',
    refused: 'Not sent:',
    operated: 'Operated by Kanoe Technologies SL · tyler@kanoe.ai',
    // the confirm / withdraw pages
    loading: 'Loading…',
    confirmTitle: 'Confirm: Sasha for',
    withdrawTitle: 'Withdraw: Sasha and',
    agreedBy: (n: string, r: string, e: string) => `Asked by ${n} (${r}), ${e}.`,
    confirmBtn: 'Confirm',
    withdrawBtn: 'Withdraw every channel',
    confirmed: 'Recorded. Thank you: these permissions are now on file for your venue, exactly as worded above.',
    alreadyConfirmed: 'This was already confirmed. Nothing new was recorded.',
    withdrawn: (v: string) => `Recorded: Sasha won’t contact ${v} on any channel, including phone and email. To allow her again, ask on the page.`,
    withdrawIntro: 'This stops every one of Sasha’s channels to your venue: WhatsApp, your booking form, email, and phone calls.',
    link: 'Not done:',
    back: 'Back to Work with Sasha',
  },
  es: {
    title: 'Trabaja con Sasha',
    lead: 'Sasha es una concierge de inteligencia artificial. Reserva mesa para sus clientes, y os lo dice.',
    pitch: 'Cuando un cliente le pide una mesa, Sasha le lee la reserva (día, hora, número de personas y nombre) y el cliente la confirma antes de que os llegue nada. Todos sus mensajes dicen en nombre de quién escribe y que Sasha es una concierge de inteligencia artificial. Nunca acepta un depósito, una garantía con tarjeta ni un cargo: si lo pedís, vuelve antes al cliente.',
    notYet: 'El número de WhatsApp propio de Sasha aún no está activo, y todavía no envía formularios de reserva. Lo que permitáis aquí queda registrado ya y solo se usará cuando cada uno empiece.',
    choose: 'Elegid qué permitís.',
    noneTicked: 'No hay nada marcado de antemano.',
    channel: { whatsapp: 'WhatsApp', web_submit: 'Nuestro formulario de reservas', email_confirm: 'Confirmación por email' },
    number: 'Número de WhatsApp (formato internacional, p. ej. +34 600 111 222)',
    formUrl: 'Dirección del formulario de reservas (https://…)',
    urlPlaceholder: '[la dirección de vuestro formulario]',
    emailScope: 'En la dirección de email de abajo.',
    venue: 'Restaurante',
    website: 'Web del restaurante (ayuda a Sasha a reconoceros)',
    country: 'País (dos letras)',
    name: 'Vuestro nombre',
    role: 'Cargo (p. ej. propietario/a, encargado/a)',
    email: 'Vuestro email: aquí enviamos el enlace de confirmación',
    authorised: 'Estoy autorizado/a para aceptar esto en nombre del restaurante.',
    confirmNote: 'Os enviaremos un enlace por email. Nada empieza hasta que lo abráis y pulséis Confirmar. Podéis retirarlo cuando queráis con el enlace de ese email, y se paran todos los canales de Sasha con vuestro restaurante.',
    privacy: 'Cómo usamos vuestros datos: Aviso de privacidad',
    draft: '(borrador, pendiente de revisión legal)',
    submit: 'Enviadme el enlace de confirmación',
    needs: 'Falta',
    need: { channel: 'marcar un canal', number: 'el número de WhatsApp', url: 'la dirección del formulario', venue: 'el nombre del restaurante', name: 'vuestro nombre', role: 'vuestro cargo', email: 'vuestro email', authorised: 'la casilla de autorización' },
    sending: 'Enviando…',
    sent: (e: string) => `Hemos enviado un enlace a ${e}. Nada empieza hasta que lo abráis y pulséis Confirmar. El enlace vale 48 horas.`,
    closed: 'El registro aún no está abierto.',
    unreachable: 'Esta página no ha podido conectar con el servidor de Sasha. Probad más tarde.',
    refused: 'No enviado:',
    operated: 'Operado por Kanoe Technologies SL · tyler@kanoe.ai',
    loading: 'Cargando…',
    confirmTitle: 'Confirmad: Sasha para',
    withdrawTitle: 'Retirar: Sasha y',
    agreedBy: (n: string, r: string, e: string) => `Pedido por ${n} (${r}), ${e}.`,
    confirmBtn: 'Confirmar',
    withdrawBtn: 'Retirar todos los canales',
    confirmed: 'Registrado. Gracias: estos permisos quedan registrados para vuestro restaurante, exactamente con el texto de arriba.',
    alreadyConfirmed: 'Esto ya estaba confirmado. No se ha registrado nada nuevo.',
    withdrawn: (v: string) => `Registrado: Sasha no contactará con ${v} por ningún canal, tampoco por teléfono ni email. Para volver a permitirlo, pedidlo en la página.`,
    withdrawIntro: 'Esto para todos los canales de Sasha con vuestro restaurante: WhatsApp, vuestro formulario, email y llamadas.',
    link: 'No hecho:',
    back: 'Volver a Trabaja con Sasha',
  },
} as const

export type Channel = 'whatsapp' | 'web_submit' | 'email_confirm'
export const CHANNELS: Channel[] = ['whatsapp', 'web_submit', 'email_confirm']

export async function sha256hex(text: string): Promise<string> {
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return Array.from(new Uint8Array(d)).map((b) => b.toString(16).padStart(2, '0')).join('')
}

export async function call(action: string, body?: unknown, lang?: Lang): Promise<{ ok: boolean; status: number; json: Record<string, unknown> }> {
  const url = `/api/work-with-sasha/${action}${lang ? `?lang=${lang}` : ''}`
  const r = await fetch(url, body === undefined ? { cache: 'no-store' } : { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
  let json: Record<string, unknown> = {}
  try { json = await r.json() } catch { /* reported by status */ }
  return { ok: r.ok, status: r.status, json }
}
