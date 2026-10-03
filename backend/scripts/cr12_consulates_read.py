"""CR 12 · read the US Spanish consulates' own non-lucrative-visa pages, at source, and write what they say.

    cd backend && python -m scripts.cr12_consulates_read            # reads (≥ 10 s apart), writes consulates_read.json
    KANOE_READ_CACHE=/some/dir python -m scripts.cr12_consulates_read   # re-extract from pages already fetched there

robots.txt first (exteriores.gob.es: /Consulados/ and /es/ allowed; it disallows only /_layouts/, /_vti_bin/,
/_catalogs/ — kept in docs/products/reads/us/). The path to every page is the site's own: the ministry's directory of
embassies and consulates → each consulate's home page → its Demarcación page and its services catalogue → the service
"Visados Nacionales - Visado de residencia no lucrativa" through the catalogue's own parameters (scco/scd as the home
page's links carry them; scca/scs as the catalogue's <option> values publish them). Nothing is composed from memory.
Every page is saved, with its sha256, in docs/products/reads/us/. Read-only: no form is submitted, nothing is booked.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "KanoeBot/1.0 (+https://kanoe.ai; reads public consular pages)"
BASE = "https://www.exteriores.gob.es"
DIRECTORY = BASE + "/es/EmbajadasConsulados"
SERVICE = "Visados Nacionales - Visado de residencia no lucrativa"
WANT = {"NuevaYork": "newyork", "Washington": "washington", "LosAngeles": "losangeles", "Miami": "miami",
        "Chicago": "chicago", "Houston": "houston", "Boston": "boston", "SanFrancisco": "sanfrancisco"}
HERE = Path(__file__).resolve().parents[1]
OUT_JSON = HERE / "products" / "relocation" / "consulates_read.json"
READS = HERE.parent / "docs" / "products" / "reads" / "us"
CACHE = Path(os.getenv("KANOE_READ_CACHE") or (READS / ".cache"))
GAP = 10.0


def get(url: str):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / hashlib.sha256(url.encode()).hexdigest()[:24]
    if p.with_suffix(".meta").exists():
        m = json.loads(p.with_suffix(".meta").read_text())
        if m["status"] < 500 or m.get("retried"):
            return m, p.read_bytes()
        retry = True   # a 5xx is the server's moment, not its answer: asked once more, ≥ GAP later, then kept as it is
    else:
        retry = False
    last = CACHE / ".last"
    wait = GAP - (time.time() - (float(last.read_text()) if last.exists() else 0))
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            body, status, final, ctype = r.read(), r.status, r.geturl(), r.headers.get("content-type", "")
    except urllib.error.HTTPError as e:
        body, status, final, ctype = e.read(), e.code, url, e.headers.get("content-type", "")
    last.write_text(str(time.time()))
    m = {"url": url, "final": final, "status": status, "ctype": ctype, "sha256": hashlib.sha256(body).hexdigest(),
         "at": time.strftime("%Y-%m-%d %H:%M:%S"), "retried": retry}
    p.write_bytes(body)
    p.with_suffix(".meta").write_text(json.dumps(m))
    return m, body


def links(base: str, body: bytes):
    s = body.decode("utf-8", "replace")
    out = []
    for m in re.finditer(r"""<a\b[^>]*?href=(?:"([^"#]*)"|'([^'#]*)'|([^\s>"'#]+))[^>]*>(.*?)</a>""", s, re.S | re.I):
        href = m.group(1) or m.group(2) or m.group(3) or ""
        if href:
            t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(4)))).replace("​", "").strip()
            out.append((urllib.parse.urljoin(base, html.unescape(href)), t))
    return out


def clean(x: str) -> str:
    x = re.sub(r"(?i)<br\s*/?>|</p>|</li>", "\n", x)
    x = html.unescape(re.sub(r"<[^>]+>", "", x)).replace("​", "").replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*", "\n", x)).strip()


def keep(name: str, m: dict, body: bytes) -> str:
    READS.mkdir(parents=True, exist_ok=True)
    ext = ".pdf" if "pdf" in m["ctype"] else ".html"
    f = READS / f"2026-10-03-{name}{ext}"
    f.write_bytes(body)
    return f.name


def section(seg: str, label: str):
    """The text after '<strong>Label</strong>:' up to the next bold label — the page's own paragraph(s)."""
    j = seg.find(label)
    if j < 0:
        return None, []
    k = re.search(r"<p>\s*<strong>[^<]{3,60}</strong>\s*:", seg[j + len(label):])
    part = seg[j:j + len(label) + (k.start() if k else 3000)]
    return clean(part), [(t, u) for u, t in links(BASE, part.encode())]   # (text, url), like the items' links


def territory_of(body: bytes) -> dict:
    """The page's own words under its 'Demarcación' heading, cut where it moves on (honorary consulates, the network list,
    'if you live elsewhere'); the date printed under the heading, if any. Never rephrased."""
    t = re.sub(r"\s+", " ", clean(body.decode("utf-8", "replace"))).replace("\u200b", "")
    m = re.search(r"Buscar Consulados Bienvenido Consulado (Demarcación(?: y red de Oficinas Consulares en EE\.UU\.)?)\s*", t)
    if not m:
        return {"dated": None, "text": None}
    rest = t[m.end():]
    stops = [k for k in (rest.find(w) for w in ("CONSULADOS HONORARIOS", "Consulados Honorarios", "Consulados honorarios",
                                                 "Si se encuentra", "Pese a", "Red de Ofic", "En nuestra", "Vicec",
                                                 "Más información")) if k > 0]
    seg = rest[:min(stops + [600])].strip()
    d = re.match(r"(\d{1,2} de [a-záéíóú]+ de 20\d\d)?\s*(.*)", seg)
    return {"dated": d.group(1), "text": d.group(2).strip() or None}


def read_one(key: str, path: str, office_title: str, read_on: str, list_id: str) -> dict:
    cid = WANT[key]
    r = {"office": None, "read": read_on, "items": [], "route": None, "territory": None, "visa_page": None, "pages": []}
    m, b = get(BASE + path)
    home, raw = m["final"], html.unescape(b.decode("utf-8", "replace"))
    r["pages"].append({"what": "home", "url": home, "sha256": m["sha256"], "file": keep(f"{cid}-home", m, b)})
    t = re.search(r"<title>\s*(.*?)\s*</title>", raw, re.S)
    title = (t.group(1).split(" - ")[-1].strip() if t else "")
    r["office"] = title if re.match(r"(Consulado General|Sección Consular) de", title) else None   # else: the network's name
    root = home.split("/es/")[0]
    hl = links(home, b)
    if m["status"] != 200:
        r["error"] = f"its home page answered HTTP {m['status']} (asked twice, {GAP:.0f} s+ apart)"
        return r
    dem = next((u[len(BASE):] for u, _ in hl if re.search(r"(?i)/es/Consulado/Paginas/Demarcaci(o|%c3%b3|ó)n\.aspx$", u)), None)
    if dem:
        md, bd = get(BASE + dem)
        r["pages"].append({"what": "demarcacion", "url": BASE + dem, "sha256": md["sha256"], "file": keep(f"{cid}-demarcacion", md, bd)})
        r["territory"] = {"url": BASE + dem, "sha256": md["sha256"], **territory_of(bd)}
    else:
        r["territory"] = {"url": None, "dated": None, "text": None, "why": "its home page links no Demarcación page"}
    cat = next((u for u, t in hl if re.search(r"(?i)/es/ServiciosConsulares(/Paginas/index\.aspx)?$", u)), None)
    if not cat:
        r["error"] = "its home page links no services catalogue"
        return r
    mc, bc = get(cat)
    if mc["status"] != 200:
        r["error"] = f"its services catalogue answered HTTP {mc['status']} (asked twice, {GAP:.0f} s+ apart)"
        return r
    craw = html.unescape(bc.decode("utf-8", "replace"))
    sc = re.search(r"scco=([^&\"]+)&scd=(\d+)", raw) or re.search(r"scco=([^&\"]+)&scd=(\d+)", craw)
    if sc:
        scco, scd = urllib.parse.unquote_plus(sc.group(1)), sc.group(2)
        r["code"] = {"scd": scd, "from": "its own links", "directory_id": list_id, "agrees": scd == list_id}
    else:
        # the ministry's directory gives each office an id; on every consulate whose links carry its catalogue code, the
        # two are the same number (checked in main and recorded) — so the directory's id IS the code, not a guess
        scco, scd = "Estados Unidos", list_id
        r["code"] = {"scd": scd, "from": "the ministry's directory (ListItemID) — its own pages carry no code"}
    cat = mc["final"].split("?")[0]
    if SERVICE not in craw:
        r["error"] = "its services catalogue doesn't list the non-lucrative residence visa"
        return r
    q = urllib.parse.urlencode({"scco": scco, "scd": scd, "scca": "Visados", "scs": SERVICE})
    url = cat + "?" + q
    mv, bv = get(url)
    r["visa_page"] = {"url": url, "status": mv["status"], "sha256": mv["sha256"], "file": keep(f"{cid}-no-lucrativa", mv, bv)}
    if mv["status"] != 200:
        r["error"] = f"its non-lucrative visa page answered HTTP {mv['status']}"
        return r
    s = bv.decode("utf-8", "replace")
    h = re.search(r"section__header-title>\s*" + re.escape(SERVICE), s)   # the service's own title on its page
    t0 = h.start() if h else -1
    k = s.find("Documentos necesarios", max(t0, 0))
    if t0 < 0 or k < 0:
        r["error"] = "its non-lucrative visa page publishes no 'Documentos necesarios' list"
        return r
    seg = s[k:]
    dated = re.search(r"(\d{1,2} de [a-záéíóú]+ de 20\d\d)", s[t0 - 2000:t0 + 400]) if t0 > 2000 else None
    r["dated"] = dated.group(1) if dated else None
    gen = re.search(r"Documentos necesarios</h2>\s*<p>(.*?)</p>", seg, re.S)
    r["general"] = clean(gen.group(1)) if gen else None
    ol = re.search(r"<ol\b[^>]*>(.*?)</ol>", seg, re.S)
    for i, li in enumerate(re.findall(r"<li\b[^>]*>(.*?)</li>", ol.group(1), re.S) if ol else [], 1):
        st = re.search(r"<strong>(.*?)</strong>", li, re.S)
        r["items"].append({"n": i, "title": clean(st.group(1)).rstrip(" .:") if st else None, "text": clean(li),
                           "links": [(tx, u) for u, tx in links(mv["final"], li.encode())]})
    if not r["items"]:
        r["error"] = "its 'Documentos necesarios' has no numbered list"
    rt, rl = section(seg, "Lugar de presentaci")
    body_only = re.sub(r"^Lugar de presentaci[oó]n\s*:?\s*", "", rt or "").strip()
    r["route"] = {"text": body_only or None, "links": rl}
    if not body_only:
        r["route_missing"] = "its page has the heading 'Lugar de presentación' with nothing under it"
    asks = re.findall(r"\n\s*([A-F])\)\s*([^\n]+)", "\n" + (rt or ""))
    r["route_asks_raw"] = asks
    val, _ = section(seg, "Validez del visado")
    r["validity"] = re.sub(r"\s+", " ", re.split(r"\n\s*Más información", val or "")[0]).strip() or None
    mt = re.search(r"(?i)\b(\d+|un) mes(es)? desde la entrada en España", r["validity"] or "")
    r["tie_within_months"] = (1 if mt.group(1).lower() == "un" else int(mt.group(1))) if mt else None
    fam, _ = section(seg, "Documentos necesarios para los familiares")
    r["family"] = fam
    return r


CITY = {"Boston": "boston", "Chicago": "chicago", "Houston": "houston", "Los Ángeles": "losangeles", "Miami": "miami",
        "Nueva York": "newyork", "San Francisco": "sanfrancisco", "Washington DC": "washington", "Washington": "washington"}


def read_network(out: dict) -> dict:
    """The 'Red de Oficinas Consulares en EE.UU.' list a consulate publishes on its Demarcación page: every US office with
    its 'Jurisdicción:' line, in its own words."""
    for cid, v in out.items():
        pg = next((p for p in v.get("pages", []) if p["what"] == "demarcacion"), None)
        if not pg:
            continue
        t = re.sub(r"\s+", " ", clean((READS / pg["file"]).read_text(encoding="utf-8", errors="replace"))).replace("\u200b", "")
        i = t.find("Red de Ofic")
        if i < 0:
            continue
        offices = {}
        for m in re.finditer(r"Consulado General de España en ([A-ZÁ][\wÁá ]+?)\s+\d.*?Jurisdicción:\s*(.*?)(?= Consulado General de España en | Más información|$)", t[i:]):
            c = CITY.get(m.group(1).strip())
            if c:
                offices[c] = {"office": f"Consulado General de España en {m.group(1).strip()}", "text": m.group(2).strip()}
        if offices:
            return {"from": out[cid]["office"], "url": pg["url"], "sha256": pg["sha256"], "file": pg["file"], "offices": offices}
    return {}


def main() -> None:
    read_on = time.strftime("%-d %b %Y")
    rb_m, rb = get(BASE + "/robots.txt")
    (READS / "robots-www.exteriores.gob.es.txt").parent.mkdir(parents=True, exist_ok=True)
    (READS / "robots-www.exteriores.gob.es.txt").write_bytes(rb)
    if re.search(r"(?im)^Disallow:\s*/(Consulados|es)?/?\s*$", rb.decode("utf-8", "replace")):
        sys.exit("⛔ robots.txt now disallows the consulate pages — nothing read")
    m, b = get(DIRECTORY)
    raw = html.unescape(b.decode("utf-8", "replace"))
    keep("directorio-embajadas-consulados", m, b)
    found = {p.split("/")[-1]: (t, p, i) for t, i, p in re.findall(
        r'"Title":"([^"]+)","ListItemID":(\d+),"SPCPaisLookup":"Estados Unidos","SPCTipoOrganismo":"Consulado","SPCEnlacePagina":"([^"]+)"', raw)}
    out = {}
    for key in WANT:
        if key not in found:
            out[WANT[key]] = {"error": "not in the ministry's directory", "items": []}
            continue
        title, path, list_id = found[key]
        print(f"· {title} {path}", flush=True)
        out[WANT[key]] = read_one(key, path, title.title(), read_on, list_id)
    codes = [v["code"] for v in out.values() if (v.get("code") or {}).get("from") == "its own links"]
    if codes and not all(c["agrees"] for c in codes):
        sys.exit("⛔ a consulate's own catalogue code differs from its directory id — the directory fallback isn't safe")
    network = read_network(out)
    for cid, v in out.items():   # an office whose page title isn't its full name: the network list's own name for it
        if not v.get("office"):
            v["office"] = ((network.get("offices") or {}).get(cid) or {}).get("office") or v.get("office")
    OUT_JSON.write_text(json.dumps({"read": read_on, "codes_checked": len(codes), "network": network, "consulates": out},
                                   indent=1, ensure_ascii=False) + "\n")
    for k, v in out.items():
        print(f"{k:13} items {len(v.get('items') or [])} · route {'yes' if (v.get('route') or {}).get('text') else 'NONE'} · "
              f"territory {'yes' if (v.get('territory') or {}).get('text') else 'NONE'} · {v.get('error') or ''}")


if __name__ == "__main__":
    main()
