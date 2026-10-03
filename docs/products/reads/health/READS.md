# CR 4 · health: what was read, and how (3 Oct 2026)

**Robots first, per host:**

| Host | robots.txt | So |
|---|---|---|
| www.madrid.es | 200, `*` allowed (except listed admin paths) | read raw |
| www.seg-social.es | 200, `Allow: /` | read raw |
| www.comunidad.madrid | answers 404 to plain requests from here, for robots and pages alike (the same 404 page byte for byte). It looks like bot protection | read **through the fetch tool** only, as S-77 did. Never again from this machine |
| sede.madrid.es | **403** (Akamai) | **unread** (S-77 §1's rule). Its links appear only as madrid.es gives them |
| *.sanidadmadrid.org | not fetched: a public health booking host (S-77 §6 block list) | linked only, never opened by code |

**Raw (saved here, sha256):**
- `2026-10-03-madrides-padron-cita-previa.html`, sha256 `62d6b135…42f2`. Read with a 10 s gap between requests. The
  padrón appointment system link (`servpub.madrid.es/…codTramite=PAD`), what to bring, and the page's warnings:
  - one appointment per person every 30 days;
  - the appointment is in the name of the adult;
  - one address per appointment.
- `2026-10-03-segsocial-info-45195.html`, sha256 `1ab94a27…26a`. Who is entitled to public healthcare (Ley 16/2003 art.
  3.1, foreigners resident in Spain included), and the e-office link "Asistencia Sanitaria: consulta del derecho y
  emisión del documento acreditativo del derecho".

**Through the fetch tool (the words quoted are the page's own):**
- `https://www.comunidad.madrid/salud/cita-sanitaria`:
  - what is needed: "el código de su tarjeta sanitaria, su fecha de nacimiento y el DNI o NIE"; "No es válido el número
    de Pasaporte";
  - the Atención Primaria link: `https://www.citaprevia.sanidadmadrid.org/Forms/Acceso.aspx`;
  - the app "Cita Sanitaria Madrid";
  - phone: the number on the back of the card, option 2 (option 9 for a person).
- `https://www.comunidad.madrid/servicios/salud/tarjeta-sanitaria`:
  - documents: "El DNI. En caso de extranjeros: el Permiso de Residencia (TIE) en vigor… El Volante de Empadronamiento…
    en los últimos noventa días… el documento Acreditativo de Derecho a Asistencia Sanitaria (DAD) emitido por el
    INSS";
  - where: at the assigned health centre, 8.30–20.30, or online (`sede.comunidad.madrid/prestacion-social/tarjeta-sanitaria`);
  - the card is sent to that centre and collected in person.
  - **The page gives no time to delivery and no rule on when the doctor is assigned, so the product states neither.**
    S-77's "~3–4 weeks" was a search summary.
