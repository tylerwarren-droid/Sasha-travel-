"""CR 4 · every link and every step the health product shows, with the page it was READ from and how.

  ● raw  — fetched from this machine (robots read first, ≥ 10 s apart), saved with its sha256 in docs/products/reads/health/
  ● tool — read through the fetch tool (the host refuses plain requests from here), its words quoted in READS.md there
Never a URL composed from memory (AD P807id:23). A host whose robots couldn't be read stays unread (sede.madrid.es: 403).
"""
from __future__ import annotations

READ_ON = "3 Oct 2026"

SERMAS = {
    "name": "Cita sanitaria — Comunidad de Madrid (SERMAS)",
    "page": "https://www.comunidad.madrid/salud/cita-sanitaria", "how": "● tool",
    # the page's own link for primary care ("Atención Primaria")
    "primary_care_url": "https://www.citaprevia.sanidadmadrid.org/Forms/Acceso.aspx",
    "app": "the “Cita Sanitaria Madrid” app (Play Store, App Store, AppGallery)",
    "phone": "the health centre's number on the back of your card, option 2 (option 9 for a person)",
    "needs": ["the code of your tarjeta sanitaria", "your date of birth", "your DNI or NIE"],
    "not_valid": "No es válido el número de Pasaporte.",      # the page's own words
    "minors": "for under-16s, the DNI/NIE of the adult responsible for the appointment",
}

PADRON = {
    "name": "Trámites de Padrón y censo electoral con cita previa — Ayuntamiento de Madrid",
    "page": ("https://www.madrid.es/portales/munimadrid/es/Inicio/Sistema-municipal-de-cita-previa/"
             "Informacion-sobre-cita-previa-tramites-y-oficinas-/Informacion-sobre-los-ambitos-municipales-con-cita-previa-/"
             "Tramites-de-Padron-y-censo-electoral-con-cita-previa/?vgnextfmt=default&vgnextoid=3da7968042610810VgnVCM1000001d4a900aRCRD"
             "&vgnextchannel=6fdb006746c30810VgnVCM1000001d4a900aRCRD"),
    "how": "● raw", "sha256": "62d6b13587e2dd23e550aa3a4c5816e28be4045c10ca5f3807ace97b3d5942f2",
    "appointment_url": "https://servpub.madrid.es/GNSIS_WBCIUDADANO/tramitePorCodigoWeb.do?codTramite=PAD",
    "bring": ["the application, signed by the adults", "your identity documents, in force",
              "documents showing you use the home (and any authorisations)"],
    "rules": ["the appointment is in the name of the adult who goes", "1 appointment per person every 30 days",
              "one address per appointment"],
}

INSS = {
    "name": "Asistencia Sanitaria — Seguridad Social",
    "page": "https://www.seg-social.es/wps/portal/wss/internet/InformacionUtil/44539/45195",
    "how": "● raw", "sha256": "1ab94a273a64d0d59bf6f9c94dd3c5a90b1c4a8e2e940be3449b8c7a7616d26a",
    "who": ("everyone of Spanish nationality and foreigners who have established their residence in Spain "
            "(Ley 16/2003, art. 3.1)"),
    "document": "the Documento Acreditativo del Derecho a la asistencia sanitaria (DAD)",
    "request_url": ("https://sede.seg-social.gob.es/wps/portal/sede/sede/Ciudadanos/CiudadanoDetalle/!ut/p/z1/rVPBbuIwEP2VvXC0PBM7sX0MFUphSRGlKSQX5I0DuFsSSrJ0269fp1upUreEVal98njmvdGbNzSjC5qV-mDXurFVqe_dO82CJcOAowIcRzAcQJjE3xPFpiwaIp2_JMCREwLNuutvaUazvGx2zYamdWGKZV6VTVFaU9U9aAM9yO0vo40u24iube2-c6u_1bq0jd5b3QPPXc5bqF1uDU2h8HOFQpEVgk84DwxRhZLE_BBGFBo50_lr60d6A3Wy9XnLdwLhJaFLnU4SL6Cpa1K8JQBEri7pw-wWPISI0fnBFo80Kav91s1r9qYBFwI5epIIVgjCGVdEBgKJx4AZzZhvBNJLeM8Q4dRvGSZyeD1FkOJMhr_w_kQCjsAbQxBLCNV0loyvkIHgZ8KPTgnoHOzt44t47WB1syG2XFV08ZGN6AKCj-M0tXcPD1nonNqa83dDF5-26hGOf6bQ5xDi5CbwLgcIkw6Z_svrnVOIAM-EH53alS-V8HXbd9tkK9kT-XktH29Wm_V2GQ-Yf3_3xJ77VyQdHZ7H4R-3mLUK/dz/d5/L2dBISEvZ0FBIS9nQSEh/"),
    "request_words": "Asistencia Sanitaria: consulta del derecho y emisión del documento acreditativo del derecho",
}

TARJETA = {
    "name": "Tarjeta Sanitaria — Comunidad de Madrid",
    "page": "https://www.comunidad.madrid/servicios/salud/tarjeta-sanitaria", "how": "● tool",
    "bring": ["your DNI — for foreigners, your residence permit (TIE) in force",
              "the volante de empadronamiento from your town hall, issued in the last 90 days",
              "the DAD from the INSS"],
    "where": "at the health centre assigned to you, 8.30–20.30, or online",
    "online_url": "https://sede.comunidad.madrid/prestacion-social/tarjeta-sanitaria",
    "delivery": "the card is sent to the health centre where you asked for it, and collected there in person",
}

# hosts the products NEVER fetch, fill, email or dial (S-77 §6 "in code, these become guards")
PUBLIC_HEALTH_HOSTS = ("sanidadmadrid.org", "citasalut.gencat.cat", "lamevasalut.gencat.cat", "sspa.juntadeandalucia.es",
                       "sergas", "osakidetza", "gva.es/sanitat")
PUBLIC_HEALTH_WORDS = ("centro de salud", "sermas", "consultorio local", "servicio madrileño de salud", "cap ", "ambulatorio")
