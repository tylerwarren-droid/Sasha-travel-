import type { Metadata } from 'next'
import type { ReactNode } from 'react'

export const metadata: Metadata = { title: 'Sasha privacy notice (draft)', robots: { index: false } }

/**
 * S-55 · S-51's privacy notice, EN and ES — ⛔ A DRAFT until counsel signs it off, and marked so on the page.
 *
 * Where S-51's text states something the code does not do today, this page says what the code does (standing rule 4):
 *   · "AI assistant" → "AI concierge" (S-52);
 *   · retention: the daily job (retention.py, S-53) enforces bookings 24 months, bodies 12 months (counted from when
 *     they were recorded, which is how the job counts), consent 3 years after withdrawal; published venue contact
 *     details are NOT yet deleted by anything, and the page says so;
 *   · stopping: no STOP-reply handler exists yet, so the page names the two ways that work today — the withdraw link
 *     in the opt-in email, and writing to tyler@kanoe.ai.
 * Bracketed items are counsel's (S-51 ⚑) and are shown as brackets, never filled in by guess.
 */
type Lang = 'en' | 'es'

function T({ head, rows }: { head: [string, string, string?]; rows: Array<[ReactNode, ReactNode, ReactNode?]> }) {
  return (
    <table className="mt-2 w-full border-collapse text-sm">
      <thead><tr>{head.filter(Boolean).map((h) => <th key={h} className="border-b py-1 pr-3 text-left">{h}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{r.filter((c) => c !== undefined).map((c, j) => <td key={j} className="border-b py-1 pr-3 align-top">{c}</td>)}</tr>)}</tbody>
    </table>
  )
}

const H = ({ children }: { children: ReactNode }) => <h2 className="mt-8 text-lg font-semibold">{children}</h2>

function En() {
  return (
    <>
      <h1 className="text-2xl font-semibold">How Sasha uses your information</h1>
      <p className="mt-4"><b>Who we are.</b> Sasha is an AI concierge operated by <b>Kanoe Technologies SL</b>, [CIF], Calle del Padre Damián 41, 28036 Madrid, Spain. Contact: <b>tyler@kanoe.ai</b>. [Data protection officer: to be confirmed.]</p>
      <p className="mt-3"><b>What Sasha does.</b> She books tables and appointments for her guests at restaurants and other venues, by phone, by email, by WhatsApp, or through a venue’s own booking form. <b>She always says she is an AI concierge, and on whose behalf she is writing or calling.</b></p>

      <H>If you are a guest</H>
      <ul className="ml-5 mt-2 list-disc space-y-2">
        <li><b>What we pass to the venue:</b> your <b>name</b>, the <b>number of people</b>, and the <b>date and time</b>. <b>Your phone number only if the venue asks for a contact number, and only if you gave it to us.</b> <b>If Sasha books by email, you get a private copy (BCC): the venue does not see your email address.</b> Sasha tells you this before you approve.</li>
        <li><b>Why:</b> to make the booking you asked for. <b>Lawful basis: performing our agreement with you</b> (GDPR Art. 6(1)(b)).</li>
        <li><b>Nothing is sent before you approve.</b> Sasha reads the booking back to you and waits for your yes.</li>
      </ul>

      <H>Your saved accesses (the vault)</H>
      <ul className="ml-5 mt-2 list-disc space-y-2">
        <li><b>Only if you add one.</b> You may save a login, an app password or a membership number Sasha may need to book for you. Each is <b>encrypted on its own</b>, with a key held in <b>Google Cloud’s key service</b>, outside our database.</li>
        <li><b>The AI model never sees it.</b> It is opened only inside the booking you approved, at the moment of use, and <b>only if the read-back you said yes to names it</b>. One yes, one use. Every use is logged and shown to you. <b>No booking uses a saved access yet</b>; the vault is ready before anything may use it.</li>
        <li><b>Never card numbers.</b> Payments go through Stripe, which never shows us your card.</li>
        <li><b>Health-related accesses</b> (a clinic portal, a health-card number) are <b>not accepted</b> until a data-protection impact assessment is done; then only with your explicit consent (Art. 9(2)(a)).</li>
        <li><b>One tap deletes it</b>: its key and its encrypted copy are destroyed. For a password, change it at the site too; we can’t revoke a password there for you. <b>Lawful basis:</b> performing our agreement with you (6(1)(b)).</li>
      </ul>

      <H>If you are a venue</H>
      <ul className="ml-5 mt-2 list-disc space-y-2">
        <li><b>Your published contact details.</b> Sasha reads the phone number, email address and WhatsApp link <b>your own website or Google listing publishes</b>, and records where and when she read them. <b>Lawful basis: our legitimate interest in contacting a business about a booking it offers publicly</b> (Art. 6(1)(f)). This notice is our information to you under Art. 14.</li>
        <li><b>If you opt in</b> (to receive Sasha’s WhatsApp messages, to let Sasha submit your booking form, or to confirm by email), we store: <b>who agreed</b> (the name and role you give), <b>when</b>, <b>how</b>, <b>the exact wording you agreed to</b>, and <b>the evidence</b> (the form and its confirmation click). <b>Why:</b> to prove your consent and to keep to it. <b>Lawful basis: your consent</b> for the messages (Art. 6(1)(a)), and <b>our legal obligation to be able to demonstrate consent</b> for keeping the record (Art. 7(1)).</li>
        <li><b>Stopping.</b> Use the <b>withdraw link</b> in the email we sent when you opted in, or write to <b>tyler@kanoe.ai</b>. <b>Every</b> one of Sasha’s channels to your venue stops, phone and email included. We record the withdrawal and keep the record of it.</li>
      </ul>

      <H>Phone calls</H>
      <ul className="ml-5 mt-2 list-disc space-y-2">
        <li>Sasha opens every call by saying she is <b>an AI concierge calling on behalf of</b> the guest.</li>
        <li><b>Calls are not recorded.</b> Our calling provider produces a <b>text transcript</b>, which an AI model reads to note whether the booking was accepted, <b>always keeping the venue’s own words.</b></li>
        <li><b>Transcripts are deleted 12 months after they were recorded.</b></li>
        <li><b>Lawful basis:</b> performing the guest’s booking (6(1)(b)), and our legitimate interest in having an accurate record of what was agreed (6(1)(f)).</li>
      </ul>

      <H>Who processes the data for us</H>
      <T head={['Provider', 'For', 'Where']} rows={[
        [<b key="b">Bland AI</b>, 'phone calls, and their transcripts', 'USA'],
        [<b key="r">Resend</b>, 'sending and receiving email', 'USA'],
        [<b key="m">Meta (WhatsApp Business)</b>, <>WhatsApp messages from Sasha’s own number, <b>once that service starts</b></>, 'EU/USA'],
        [<b key="a">Anthropic</b>, 'an AI model reading call transcripts and replies', 'USA'],
        [<b key="k">Google Cloud (Key Management)</b>, <>holding the key that locks your saved accesses; <b>it never sees them</b></>, '[region]'],
        [<b key="rw">Railway</b>, 'hosting Sasha’s server', '[region]'],
        [<b key="d">[database host]</b>, 'storing bookings and records', '[region]'],
        [<b key="g">Google (Places)</b>, <>reading venues’ published listings; <b>no guest data is sent</b></>, 'USA'],
      ]} />
      <p className="mt-2 text-sm"><b>Transfers outside the EEA</b> rely on [the EU–US Data Privacy Framework / Standard Contractual Clauses, per provider].</p>

      <H>How long we keep it</H>
      <T head={['Data', 'Kept']} rows={[
        ['Booking details (venue, date, time, party, status, the venue’s words)', '24 months after the booking date'],
        ['Call transcripts, and email and WhatsApp message bodies', '12 months after they were recorded'],
        ['Venue opt-in records, including withdrawals', 'while active, then 3 years after withdrawal (to prove consent)'],
        ['Published venue contact details', '[12 months after last use] — not yet enforced'],
      ]} />

      <H>Your rights</H>
      <p className="mt-2">You may ask for <b>access</b> to your data, <b>correction</b>, <b>deletion</b>, <b>restriction</b>, <b>portability</b>, and <b>object</b> to our use based on legitimate interest. <b>You may withdraw consent at any time</b>; for venues, the withdraw link or an email to us does it. Write to <b>tyler@kanoe.ai</b>. We reply within one month. <b>Signed in, you can delete your saved accesses, WhatsApp link and saved details yourself, and download a copy of what we hold</b> (saved accesses as names and history only, never their contents).</p>
      <p className="mt-3"><b>You can complain to the Spanish data protection authority</b>: <b>Agencia Española de Protección de Datos (AEPD)</b>, C/ Jorge Juan 6, 28001 Madrid, <b>www.aepd.es</b>.</p>
      <p className="mt-6 text-sm italic">Last updated: [date].</p>
    </>
  )
}

function Es() {
  return (
    <>
      <h1 className="text-2xl font-semibold">Cómo usa Sasha tu información</h1>
      <p className="mt-4"><b>Quiénes somos.</b> Sasha es una concierge de inteligencia artificial operada por <b>Kanoe Technologies SL</b>, [CIF], Calle del Padre Damián 41, 28036 Madrid (España). Contacto: <b>tyler@kanoe.ai</b>. [Delegado de protección de datos: por confirmar.]</p>
      <p className="mt-3"><b>Qué hace Sasha.</b> Reserva mesas y citas para sus clientes en restaurantes y otros establecimientos, por teléfono, email, WhatsApp o mediante el propio formulario de reservas del establecimiento. <b>Siempre dice que es una concierge de inteligencia artificial y en nombre de quién escribe o llama.</b></p>

      <H>Si eres cliente</H>
      <ul className="ml-5 mt-2 list-disc space-y-2">
        <li><b>Qué enviamos al establecimiento:</b> tu <b>nombre</b>, el <b>número de personas</b>, y la <b>fecha y hora</b>. <b>Tu teléfono solo si el establecimiento pide un número de contacto y nos lo has dado.</b> <b>Si Sasha reserva por email, recibes una copia oculta (CCO): el establecimiento no ve tu dirección de email.</b> Sasha te lo dice antes de que lo apruebes.</li>
        <li><b>Para qué:</b> para hacer la reserva que pediste. <b>Base legal: la ejecución de nuestro acuerdo contigo</b> (RGPD art. 6.1.b).</li>
        <li><b>No se envía nada sin tu aprobación.</b> Sasha te lee la reserva y espera tu «sí».</li>
      </ul>

      <H>Tus accesos guardados (la bóveda)</H>
      <ul className="ml-5 mt-2 list-disc space-y-2">
        <li><b>Solo si añades uno.</b> Puedes guardar un acceso, una contraseña de aplicación o un número de socio que Sasha necesite para reservar por ti. Cada uno se <b>cifra por separado</b>, con una clave custodiada en el <b>servicio de claves de Google Cloud</b>, fuera de nuestra base de datos.</li>
        <li><b>El modelo de IA nunca lo ve.</b> Solo se abre dentro de la reserva que aprobaste, en el momento de usarlo, y <b>solo si la lectura a la que dijiste sí lo nombra</b>. Un sí, un uso. Cada uso queda registrado y se te muestra. <b>Ninguna reserva usa todavía un acceso guardado</b>.</li>
        <li><b>Nunca números de tarjeta.</b> Los pagos van por Stripe, que nunca nos muestra tu tarjeta.</li>
        <li><b>Accesos de salud</b> (un portal clínico, una tarjeta sanitaria) <b>no se aceptan</b> hasta hacer una evaluación de impacto; después, solo con tu consentimiento explícito (art. 9.2.a).</li>
        <li><b>Un toque lo borra</b>: su clave y su copia cifrada se destruyen. Si es una contraseña, cámbiala también en el sitio; nosotros no podemos revocarla allí. <b>Base legal:</b> la ejecución de nuestro acuerdo contigo (6.1.b).</li>
      </ul>

      <H>Si eres un establecimiento</H>
      <ul className="ml-5 mt-2 list-disc space-y-2">
        <li><b>Tus datos de contacto publicados.</b> Sasha lee el teléfono, el email y el enlace de WhatsApp que <b>publica tu propia web o tu ficha de Google</b>, y registra dónde y cuándo los leyó. <b>Base legal: nuestro interés legítimo en contactar con un negocio sobre una reserva que ofrece públicamente</b> (art. 6.1.f). Este aviso es nuestra información conforme al art. 14.</li>
        <li><b>Si das tu consentimiento</b> (a recibir WhatsApp de Sasha, a que Sasha envíe vuestro formulario de reservas, o a confirmar por email), guardamos: <b>quién lo dio</b> (nombre y cargo), <b>cuándo</b>, <b>cómo</b>, <b>el texto exacto que aceptaste</b>, y <b>la prueba</b> (el formulario y su clic de confirmación). <b>Para qué:</b> para poder demostrar tu consentimiento y respetarlo. <b>Base legal: tu consentimiento</b> para los mensajes (art. 6.1.a), y <b>la obligación de poder demostrarlo</b> para conservar el registro (art. 7.1).</li>
        <li><b>Para parar:</b> usa el <b>enlace de retirada</b> del email que te enviamos al dar tu consentimiento, o escribe a <b>tyler@kanoe.ai</b>. Se paran <b>todos</b> los canales de Sasha con tu establecimiento, también teléfono y email. Registramos la retirada y conservamos ese registro.</li>
      </ul>

      <H>Llamadas</H>
      <ul className="ml-5 mt-2 list-disc space-y-2">
        <li>Sasha empieza cada llamada diciendo que es <b>una concierge de inteligencia artificial que llama en nombre</b> del cliente.</li>
        <li><b>Las llamadas no se graban.</b> Nuestro proveedor de llamadas genera una <b>transcripción de texto</b>, que lee un modelo de IA para anotar si la reserva se aceptó, <b>conservando siempre las palabras del establecimiento.</b></li>
        <li><b>Las transcripciones se borran 12 meses después de registrarse.</b></li>
        <li><b>Base legal:</b> la ejecución de la reserva del cliente (6.1.b) y nuestro interés legítimo en tener un registro fiel de lo acordado (6.1.f).</li>
      </ul>

      <H>Quién trata los datos por nosotros</H>
      <T head={['Proveedor', 'Para', 'Dónde']} rows={[
        [<b key="b">Bland AI</b>, 'llamadas y sus transcripciones', 'EE. UU.'],
        [<b key="r">Resend</b>, 'envío y recepción de emails', 'EE. UU.'],
        [<b key="m">Meta (WhatsApp Business)</b>, <>mensajes de WhatsApp desde el número de Sasha, <b>cuando ese servicio empiece</b></>, 'UE/EE. UU.'],
        [<b key="a">Anthropic</b>, 'un modelo de IA que lee transcripciones y respuestas', 'EE. UU.'],
        [<b key="k">Google Cloud (Key Management)</b>, <>custodia de la clave que protege tus accesos guardados; <b>nunca los ve</b></>, '[región]'],
        [<b key="rw">Railway</b>, 'alojamiento del servidor de Sasha', '[región]'],
        [<b key="d">[proveedor de base de datos]</b>, 'almacenamiento de reservas y registros', '[región]'],
        [<b key="g">Google (Places)</b>, <>lectura de fichas publicadas de establecimientos; <b>no se envían datos de clientes</b></>, 'EE. UU.'],
      ]} />
      <p className="mt-2 text-sm"><b>Las transferencias fuera del EEE</b> se basan en [el Marco de Privacidad de Datos UE-EE. UU. / Cláusulas Contractuales Tipo, según el proveedor].</p>

      <H>Cuánto tiempo lo guardamos</H>
      <T head={['Datos', 'Plazo']} rows={[
        ['Datos de la reserva (establecimiento, fecha, hora, personas, estado, palabras del establecimiento)', '24 meses desde la fecha de la reserva'],
        ['Transcripciones y textos de emails y WhatsApp', '12 meses desde que se registraron'],
        ['Registros de consentimiento de establecimientos, incluidas las retiradas', 'mientras esté activo y 3 años tras la retirada (para poder demostrarlo)'],
        ['Datos de contacto publicados de establecimientos', '[12 meses tras el último uso] — aún no se aplica'],
      ]} />

      <H>Tus derechos</H>
      <p className="mt-2">Puedes pedir <b>acceso</b> a tus datos, su <b>rectificación</b>, <b>supresión</b>, <b>limitación</b> y <b>portabilidad</b>, y <b>oponerte</b> al uso basado en interés legítimo. <b>Puedes retirar tu consentimiento cuando quieras</b>; si eres un establecimiento, basta con el enlace de retirada o un email. Escribe a <b>tyler@kanoe.ai</b>. Respondemos en un plazo de un mes. <b>Con tu sesión iniciada, puedes borrar tú mismo tus accesos guardados, tu enlace de WhatsApp y tus datos guardados, y descargar una copia de lo que tenemos</b> (los accesos, solo como nombres e historial, nunca su contenido).</p>
      <p className="mt-3"><b>Puedes reclamar ante la Agencia Española de Protección de Datos (AEPD)</b>, C/ Jorge Juan 6, 28001 Madrid, <b>www.aepd.es</b>.</p>
      <p className="mt-6 text-sm italic">Última actualización: [fecha].</p>
    </>
  )
}

export default async function Page({ searchParams }: { searchParams: Promise<{ [k: string]: string | string[] | undefined }> }) {
  const lang: Lang = (await searchParams).lang === 'es' ? 'es' : 'en'
  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-10 text-[15px] leading-relaxed">
      <p className="mb-6 rounded border border-amber-400 bg-amber-50 p-3 text-sm font-medium text-amber-900">
        {lang === 'es'
          ? 'BORRADOR — pendiente de revisión legal. Aún no es el aviso definitivo; lo que va entre corchetes está por confirmar.'
          : 'DRAFT — under legal review. This is not yet the final notice; bracketed items are still to be confirmed.'}
      </p>
      <p className="mb-6 text-sm"><a className="underline" href={`?lang=${lang === 'en' ? 'es' : 'en'}`}>{lang === 'en' ? 'Español' : 'English'}</a></p>
      {lang === 'es' ? <Es /> : <En />}
    </main>
  )
}
