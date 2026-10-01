/**
 * S-52 · WhatsApp Mode A's pre-filled message: S-48 §3's first-contact text, v2 ("an AI concierge operated by
 * Kanoe Technologies SL", the disclosure first). ⚠ A COPY of backend/booking_signer/wordings.py WHATSAPP_TEMPLATE_V2,
 * held byte-identical by backend/tests/test_wordings.py — change both, or the test fails.
 */
export const WHATSAPP_TEMPLATE_V2: Record<string, string> = {
  en: "Hello, this is Sasha, an AI concierge operated by Kanoe Technologies SL, writing on behalf of {who} to ask for a table for {n} people on {date} at {time}. Could you tell us whether that is possible? We will not agree to a deposit or fee without asking {who} first. Thank you.",
  es: "Hola, soy Sasha, una concierge de inteligencia artificial operada por Kanoe Technologies SL, y escribo en nombre de {who} para pedir una mesa para {n} personas el {date} a las {time}. ¿Nos puede decir si es posible? No aceptaremos ningún depósito ni cargo sin consultarlo antes con {who}. Gracias.",
  pt: "Olá, sou a Sasha, uma concierge de inteligência artificial operada pela Kanoe Technologies SL, e escrevo em nome de {who} para pedir uma mesa para {n} pessoas no dia {date} às {time}. Pode dizer-nos se é possível? Não aceitaremos qualquer depósito ou taxa sem consultar primeiro {who}. Obrigada.",
  tr: "Merhaba, ben Sasha; Kanoe Technologies SL tarafından işletilen bir yapay zekâ konsiyerjiyim. {who} adına {date} tarihinde saat {time} için {n} kişilik bir masa rica etmek üzere yazıyorum. Bunun mümkün olup olmadığını bize bildirebilir misiniz? {who} ile önceden görüşmeden hiçbir depozito veya ücreti kabul etmeyeceğiz. Teşekkürler.",
}

/** S-64 · a party of ONE: the template's "{n} people" becomes "1 person". ⚠ A copy of backend wordings.py WHATSAPP_ONE. */
export const WHATSAPP_ONE: Record<string, [string, string]> = {
  en: ["{n} people", "{n} person"], es: ["{n} personas", "{n} persona"], pt: ["{n} pessoas", "{n} pessoa"],
}

/** country → the template's language (only these four exist; anything else is English) */
export const WA_LANG: Record<string, string> = { ES: 'es', PT: 'pt', TR: 'tr' }
const LOCALE: Record<string, string> = { en: 'en-GB', es: 'es-ES', pt: 'pt-PT', tr: 'tr-TR' }
const FAMILY: Record<string, (s: string) => string> = { en: (s) => `the ${s} family`, es: (s) => `la familia ${s}`, pt: (s) => `a família ${s}`, tr: (s) => `${s} ailesi` }

/** The message, in the venue's language: {who} the guest's name as approved, {date} written out (never "Thursday" alone), {time} HH:MM. */
export function whatsappText(country: string | null, name: string, party: number, dateIso: string, time: string): string {
  const lang = WA_LANG[(country ?? '').toUpperCase()] ?? 'en'
  const surname = name.trim().split(/\s+/).pop() ?? name
  const who = party > 1 ? FAMILY[lang](surname) : name.trim()
  const date = dateIso ? new Date(`${dateIso}T12:00:00Z`).toLocaleDateString(LOCALE[lang], { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }) : '[date]'
  const one = party === 1 ? WHATSAPP_ONE[lang] : undefined
  const template = one ? WHATSAPP_TEMPLATE_V2[lang].split(one[0]).join(one[1]) : WHATSAPP_TEMPLATE_V2[lang]
  const text = template.split('{who}').join(who).split('{n}').join(String(party)).split('{date}').join(date).split('{time}').join(time)
  // S-64 · Portuguese contracts "de a" → "da": "em nome da família Warren" (the backend renders the same)
  return lang === 'pt' ? text.split('em nome de a ').join('em nome da ') : text
}
