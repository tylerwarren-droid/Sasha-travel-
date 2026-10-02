# S-77 · Spanish public-health appointments for Sasha: a read-only study

*EU session, 2 Oct 2026 (EU 113). **Read-only.** Robots were read first on every host. **Nothing was submitted, no form
was opened, and no login was attempted.** Every source was read through the web-fetch tool or a web search, never
`curl` from the founder's network (the TheFork rule, 30 Sept).*

**How each fact was obtained:**
- **●** read at source (the page fetched);
- **○** from a search result's summary of the official page (not fetched).

The study says which applies wherever it matters.

---

## 0. The answer first

**What Sasha may lawfully do, on what was read:**
- **prepare** an appointment;
- tell the guest **exactly** which identifiers to have ready;
- open the official web or app **for the guest**, who **signs in and presses** themselves;
- remember the appointment in the itinerary;
- remind them;
- for a new resident, walk them through card → doctor → appointment.

**What Sasha must not do:**
- hold or use the guest's health-portal **password**, Cl@ve or certificate;
- submit bookings on a health portal herself;
- call the health centre pretending to be the patient;
- poll for free slots (**slot-hunting**);
- book more than the guest's own one appointment;
- resell or transfer an appointment.

**Why:**
1. The portals' terms make the user personally responsible for their credentials. ● La Meva Salut: *"Les persones
   usuàries són les úniques responsables de custodiar les seves claus d'accés."*
2. They require use **"for the purpose for which it was created"**. ● LMS: *"Les persones usuàries estan obligades a fer
   un ús raonable de LMS, de conformitat amb la finalitat per a la qual s'ha creat."*
3. They reserve the right to block. ● LMS: *"podrà suspendre o cancel·lar l'accés…"*; ○ Madrid: the Consejería
   *"se reserva el derecho a bloquear el acceso de cualquier usuario"* for use *"contraria a la legalidad, buena fe o
   las presentes condiciones"*, and forbids anything that could *"congestionar, afectar, interferir o paralizar"* the
   service.
4. **It's health data** (GDPR Art. 9). Sasha handling a patient's portal session is special-category processing of the
   highest sensitivity. A guest pressing the button themselves keeps Sasha out of it.

**No page read prohibits "robots" in those words.** But a general ban on interfering, a duty to keep your own
credentials, and a purpose limit together exclude an agent acting inside a patient's session. So does the obvious harm:
public-health slots are scarce, and automation competes with patients.

---

## 1. Robots, read first (2 Oct 2026, via the fetch tool)

| Host | What it is | robots.txt | Consequence |
|---|---|---|---|
| `www.comunidad.madrid` | Madrid's information pages | ● present. `User-agent: *` only (**no AI agent named**), `Crawl-delay: 10`, and it disallows admin, login and search paths | the information pages may be read, slowly |
| `www.citaprevia.sanidadmadrid.org` | **Madrid's primary-care booking web** | ● **404**, no file | no directive. **Not opened**: a booking form is not something this study fills |
| `citawebadcom.sanidadmadrid.org` | Madrid's administrative-appointment web | ● **404** | not opened |
| `citasalut.gencat.cat` | **Catalonia's appointment web** | ● **404** | not opened |
| `lamevasalut.gencat.cat` | Catalonia's patient portal | ● `User-Agent: * / Disallow:` (allows everything) | its legal notice was read (●) |
| `www.sspa.juntadeandalucia.es` | **Andalusia's SAS / ClicSalud+** | ● **403 Forbidden**: robots **unreadable** | **No SAS page was fetched.** The same rule as `ros.gov.uk`: when robots can't be read, the host stays unread. Everything below on Andalusia is ○ (search summaries only) |

---

## 2. Madrid: SERMAS

**Booking channels:**
- ○ the web at **`www.citaprevia.sanidadmadrid.org/Forms/Acceso.aspx`**;
- ○ the apps **"Cita Sanitaria Madrid"** and **"Tarjeta Sanitaria Virtual"** (Play Store, App Store, AppGallery). The app
  *"allows you to save access credentials on the device… and to manage multiple people"*;
- ○ by phone: the health centre's number on the back of the card, option 2 (voice recognition), option 9 for a person,
  Monday–Friday 08:00–21:00.

**What's needed to book** (○ `comunidad.madrid/salud/cita-sanitaria`):
- the **tarjeta sanitaria code**;
- **date of birth**;
- **DNI or NIE**. *"No es válido el número de Pasaporte."*
- For under-16s, the responsible adult's DNI/NIE.
- **The guest must already have an assigned professional at that centre** (○: *"tener… asignado su profesional
  sanitario en el centro"*).

**Rules:**
- ○ multiple appointments with the same professional are allowed only on dates **before** the first one booked;
- ○ each person is booked in a **separate session** (*"en sesiones sucesivas"*);
- ○ consult, cancel and change are online.

**CAPTCHA:** none mentioned on the information page. The booking form itself wasn't opened.

**What Sasha does in Madrid:**
1. Asks once which three identifiers the guest has. They're stored only with S-78 (Vault) **as an `identifier`, a
   special-category item, with Art. 9 consent**, and **only if the guest asks** Sasha to remember them.
2. Shows them for **copy**.
3. Opens the official app or web link.
4. The guest books.
5. The guest tells Sasha (or forwards the confirmation), and Sasha adds it to the itinerary with a reminder.

---

## 3. Catalonia: CatSalut

**Booking channels:**
- ○ **La Meva Salut** (web and app): "Cites i agenda" → "Sol·licitud de cites i consultes" → "Cites i consultes
  d'atenció primària";
- ○ **citasalut.gencat.cat**, entered with the **CIP** ("Programació per motius": the guest picks a **reason**, and
  the system routes them).

**Identification:** ○ the **CIP** (on the TSI), or DNI/NIE/passport **with a password** (LMS registration is its own
procedure, ○ `tramits.gencat.cat` 20277).

**Terms (● the La Meva Salut legal notice):**
- reasonable use for its purpose;
- **the user alone safeguards their access keys**;
- **parents and legal guardians may act for minors and dependants**, after requesting that access individually (*"es
  pot accedir a LMS de fills i filles menors de 18 anys i de les persones de les quals se sigui responsable legal"*);
- the Department may suspend access.

**No clause names automated access**, and **no other representation** (a concierge) is provided for.

**What Sasha does in Catalonia:** the same shape as Madrid. Note that **the system asks for the reason**: Sasha can
help the guest choose the right one in plain words, **without** recording a clinical reason anywhere but the guest's
own screen.

---

## 4. Andalusia: SAS (○ only: robots unreadable, nothing fetched)

**Booking channels:**
- **ClicSalud+** on the web: identify with **personal data**, or with **certificate, DNIe or Cl@ve**. With personal data,
  only primary-care appointments show; with a certificate, all of them do.
- **The Salud Responde app.**
- **Phone 955 545 060** (24/7).

**Identifier:** the **NUHSA**, on the card (○ the search summaries; not confirmed at source).

**What Sasha does:** the same shape, and **SAS is to be confirmed at source before any guest-facing copy names its
steps.** Founder decision H-3: re-read by a person in a browser, the agent lane, since robots couldn't be read.

---

## 5. A new resident (all three regions; the shape is the same)

| Step | Madrid (○) | Catalonia (○) | Andalusia (○) | What Sasha can do |
|---|---|---|---|---|
| 1. **Empadronamiento** (town-hall registration) | the *volante*, **issued within 90 days** | the certificate, **under 3 months old** | the *certificado de empadronamiento* | tell them which town hall, what to bring, and how to get its own *cita previa*. **Never hunt for padrón slots** (Madrid city's are scarce; polling is the harm this forbids) |
| 2. **The right to public healthcare** | the **INSS** *Documento Acreditativo de Derecho* (as worker, pensioner or beneficiary) | through the TSI request | the INSS document of insured or beneficiary status | explain which INSS document, and that the employer's Social Security registration usually triggers it |
| 3. **Apply for the card** | at the **assigned health centre** (08:30–20:30), or online with DNIe or certificate. ID: **DNI, or TIE for foreigners** | at the CAP for their address (or one chosen), or online first; the definitive card needs the padrón | **in person** at a primary-care centre (registers them in the BDU and the SNS) | a checklist and the address of the right centre; **the guest goes or submits** |
| 4. **Family doctor** | assigned with the card; **card issued in ~3–4 weeks** | the CAP assigned by address | **assigned when the card is requested** | add "card ready ~{date}" to the itinerary; remind them |
| 5. **First appointment** | §2 (needs the assigned professional, so only after step 4) | §3 | §4 | §2–§4 shape |

- **Free choice of doctor or centre** exists in Madrid (○ *"Libre elección sanitaria"*). Sasha explains it; the guest
  applies.
- **People without INSS coverage** (○ DASE in Madrid, ○ CatSalut's "no assegurades" route) have a separate route.
  Sasha points to it and doesn't assess eligibility (that's a legal determination).

---

## 6. What Sasha may do: the lawful shape

| May | Must not |
|---|---|
| explain the route and the documents in plain words, per region | hold or type the guest's **portal password, Cl@ve PIN or certificate** |
| store the guest's **card number / DNI / DOB** in S-78 (Vault) as an `identifier`, **only on request, with Art. 9 explicit consent**, and show it for copying | **submit** a booking on any health portal, or drive the app |
| open the official link or app on the guest's device; **the guest signs in and presses** | **call the health centre as the patient** (the Madrid voice line asks for the patient's own data; Sasha's phone rung must refuse a health centre) |
| record the guest's own appointment in the itinerary, with a reminder | **slot-hunt**: poll for cancellations or earlier slots, on the web, the app or the phone |
| help pick the **reason** (CatSalut) in plain words, on the guest's screen only | book **more than one** appointment for the person, or book for anyone **except** a minor or dependant the guest is the legal guardian of, through the portal's own guardian access |
| book a **private** clinic through the normal ladder (a different S-ticket and that clinic's own terms) | **resell, transfer** or hold appointments |

**In code, these become guards** (for the Sasha tab):
- **Every health host goes on a block list for the executors:** `*.sanidadmadrid.org`, `citasalut.gencat.cat`,
  `lamevasalut.gencat.cat`, `*.sspa.juntadeandalucia.es`, and any `salud`/`salut`/`sas`/`sergas`/`osakidetza`
  regional host as added. No form fill, email or slot link may target them.
- **The phone rung refuses a number** that belongs to a public health centre (a list per region from the official
  directories, kept as data).
- The model's capability facts (`conductor.py` `CAPABILITY_FACTS`) gain: *"Public-health appointments in Spain: Sasha
  prepares and the guest books. She never books, calls or signs in for them."*

---

## 7. Open, for the founder

- **H-1:** **counsel on the health line.** Sasha storing a card number or DNI for a patient is Art. 9 processing even
  when it's only displayed. A DPIA should precede it (S-78 (Vault) V-4). The alternative: never store, and only explain.
- **H-2:** private clinics (Sanitas, Quirón, HM…) are where Sasha could actually book. That's a separate study (their
  terms; most use online booking platforms, and **never probe a booking platform from the founder's network**).
- **H-3:** Andalusia confirmed at source by a person in a browser, since robots returned 403.
- **H-4:** other regions (Galicia SERGAS, Basque Osakidetza, Valencia GVA…), the same method, if wanted.

---

## Sources

- **●**
  - `www.comunidad.madrid/robots.txt`
  - `lamevasalut.gencat.cat/robots.txt`
  - `lamevasalut.gencat.cat/en/web/cps/avis-legal`
  - `www.comunidad.madrid/salud/cita-sanitaria` (Madrid's identifiers, channels and rules: read through the fetch tool's
    summary)
  - the 404s and the 403 listed in §1
- **○** (search summaries of official pages):
  - `comunidad.madrid/salud/tarjeta-sanitaria`, `…/libre-eleccion-sanitaria`, and Madrid's legal and
    data-protection notices for the health portals
  - `catsalut.gencat.cat` (on-line appointments, obtaining the TSI), `tramits.gencat.cat` 8144 and 20277
  - `sspa.juntadeandalucia.es`: ClicSalud+, Salud Responde, the Andalusian health card, cobertura
  - `juntadeandalucia.es/temas/salud/servicios/cita.html`
- **Not saved raw.** These are terms read for a study, not a licence (the AD licence-saving rule doesn't apply). If any
  becomes a reliance point for a build, save it raw then.
