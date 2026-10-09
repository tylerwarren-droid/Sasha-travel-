"""DIVE · THE OPERATOR CONSOLE (EU 212 surfaces.md A): Suppliers · Packages · Bookings · Activity + Proof · API & keys · the TEST
drawer (the failure beat: play a supplier's answer). Succinct statements, big buttons, a tooltip on every button, real dates; a big
✓ / ✕ ONLY for a person's or a supplier's answer — never for "nothing happened". Behind the console token (a cookie)."""
from __future__ import annotations

import hmac
import json

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import bundles as BN, config, model as M, ops as OPS, rules as R
from .model import DiveError
from .store import loads, ts


def bind(app, db, ok):
    @app.get("/console/login", response_class=HTMLResponse)
    async def login_page():
        from .app import page
        return page("Console", """<h1>Operator console</h1><form class="card" method="post"><label>Console token<input type="password" name="token"
autocomplete="current-password"></label><p><button class="go" title="Opens the console for this browser">Open the console</button></p></form>""")

    @app.post("/console/login")
    async def login(req: Request):
        f = dict((await req.form()).items())
        tok = config.CONSOLE_TOKEN or ("" if config.deployed() else "dive-local")
        if not tok or not hmac.compare_digest(str(f.get("token") or ""), tok):
            return RedirectResponse("/console/login", status_code=303)
        r = RedirectResponse("/console", status_code=303)
        r.set_cookie("dive_console", tok, httponly=True, samesite="strict", secure=config.deployed(), max_age=12 * 3600)
        return r

    @app.post("/console/api/{op}")
    async def console_op(op: str, req: Request):
        if not ok(req):
            return JSONResponse({"ok": False, "error": {"code": "unauthenticated", "message": "Open the console first."}}, 401)
        s = db()
        try:
            v = json.loads(await req.body() or b"{}")
            o = OPS.operator(s)
            if op == "bookings.list":
                out = []
                for b in s.q("select * from bundles where operator_id = ? order by created_at desc limit 20", o["id"]):
                    out.append({**await BN.sync(s, o, b["id"]), "customer": loads(b["customer"])["name"], "created_at": b["created_at"]})
                return JSONResponse({"ok": True, "result": {"bookings": out}})
            if op == "activity.list":
                return JSONResponse({"ok": True, "result": {"items": s.q("select kind, line, bundle_id, leg_id, evidence_id, at from events where operator_id = ? "
                                                                         "order by id desc limit 60", o["id"])}})
            if op == "evidence.get":
                e = s.one("select body from evidence where id = ? and operator_id = ?", v.get("evidence_id"), o["id"])
                if not e:
                    raise DiveError("not_found", "No such proof.")
                ev = loads(e["body"])
                return JSONResponse({"ok": True, "result": {"evidence": ev, "verified": M.verify_evidence(ev)}})
            if op == "captured.list":   # the test-mode "phones and inboxes": what WOULD have gone out (real ones flagged)
                return JSONResponse({"ok": True, "result": {"messages": s.q("select channel, to_, body, real, at from captured order by id desc limit 30")}})
            if op == "bookings.test_quote":   # the TEST drawer's prepared booking (the failure beat): Thursday, 4 divers
                return JSONResponse({"ok": True, "result": await _test_quote(s, o, v)})
            return JSONResponse({"ok": True, "result": await OPS.run(s, o, op, v)})
        except DiveError as e:
            return JSONResponse({"ok": False, "error": e.body()}, e.http)

    @app.get("/console", response_class=HTMLResponse)
    async def console(req: Request):
        if not ok(req):
            return RedirectResponse("/console/login", status_code=303)
        from .app import page
        o = OPS.operator(db())
        return page("Console · " + o["name"], _PAGE.replace("{name}", o["name"]).replace("{slug}", o["slug"]), footer=o["footer"] or config.FOOTER)


async def _test_quote(s, o, v):
    from datetime import date, timedelta
    d = date.today() + timedelta(days=2)
    while d.weekday() != 3:
        d += timedelta(days=1)
    pkg = s.one("select * from packages where operator_id = ? and published = 1", o["id"])
    if not pkg:
        raise DiveError("package_not_published", "Publish a package first.")
    b = await BN.quote(s, o, pkg["id"], v.get("date") or d.isoformat(), "09:00", 4, {"name": "Test drawer (Thursday group)", "phone": "+15005550199"}, None)
    aid = BN.approve(s, s.one("select * from bundles where id = ?", b["bundle_id"]), method="tap")   # test: stands in for the customer's tap
    return await BN.confirm(s, o, b["bundle_id"], aid)


_PAGE = r"""<style>.rail{display:flex;gap:.4rem;flex-wrap:wrap;margin:.5rem 0 1rem}.rail button.on{background:var(--acc);color:#fff}
.row{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap}.legs p{margin:.35rem 0}.k{font-family:ui-monospace,monospace;font-size:.85rem;overflow-wrap:anywhere}
.badge{border:1px solid var(--line);border-radius:99px;padding:.1rem .6rem;font-size:.75rem;letter-spacing:.06em}</style>
<div class="row" style="justify-content:space-between"><h1 style="margin:.2rem 0">{name}</h1><span class="badge">TEST</span></div>
<div class="rail" id="rail"></div><div id="view"></div><div id="msg" class="mut"></div>
<script>
const TABS=[["suppliers","Suppliers"],["packages","Packages"],["bookings","Bookings"],["activity","Activity"],["api","API & keys"],["drawer","Test drawer"]];
let tab="suppliers",timer=null;const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"})[c]);
async function api(op,body){const r=await fetch("/console/api/"+op,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body||{})});
const j=await r.json();if(!j.ok){$("msg").textContent=j.error.message;throw new Error(j.error.code)}$("msg").textContent="";return j.result}
function rail(){$("rail").innerHTML=TABS.map(([k,l])=>`<button class="${k===tab?'on':''}" onclick="go('${k}')" title="${l}">${l}</button>`).join("")}
function go(k){tab=k;rail();clearTimeout(timer);VIEWS[k]().catch(e=>{})}
const when=s=>s?new Date(s).toLocaleString([], {day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit"}).toUpperCase():"";
const VIEWS={
async suppliers(){const r=await api("suppliers.list");const conf=r.suppliers.filter(s=>s.status==="confirmed"),dr=r.suppliers.filter(s=>s.status==="draft");
$("view").innerHTML=`<div class="card row"><b>Suppliers · ${conf.length} confirmed · ${dr.length} drafts</b>
<button class="go" title="Reads your website and lists the businesses it mentions. You confirm each one." onclick="find()">Find suppliers on my site</button></div>`+
dr.map(s=>`<div class="card"><b>${esc(s.name)}</b> · ${esc(s.kind.replace("_"," "))} <span class="mut">(${s.confidence}%)</span>
<p class="q">Found on ${esc(s.evidence_of_source.source.replace("site:",""))}: “${esc(s.evidence_of_source.text)}”${s.evidence_of_source.instruction_like?' <span class="chip no" title="This text tries to instruct an AI. It was not acted on.">instruction-like: ignored</span>':''}</p>
<div class="row"><button class="go" title="Adds this business as a supplier. Nothing is sent to them yet." onclick="setSup('${s.supplier_id}','confirmed')">Confirm</button>
<button title="Removes this draft." onclick="setSup('${s.supplier_id}','rejected')">Not ours</button></div></div>`).join("")+
conf.map(s=>`<div class="card"><b>${esc(s.name)}</b> · ${esc(s.kind.replace("_"," "))}<div class="legs">`+(s.channels.length?s.channels.map(c=>`<p>
<span class="chip ${c.verified?'ok':'amb'}">${esc(c.kind.replace("_"," "))} ${c.verified?'✓ verified '+when(c.verified_at):'· not verified'}</span> <span class="k">${esc(c.address)}</span>
${c.verified?'':`<button title="Sends one message asking them to reply YES to receive your booking requests." onclick="verify('${c.channel_id}')">Send verification</button>`}</p>`).join(""):
`<p class="mut">No channel yet.</p>`)+`</div><div class="row">${chanForm(s)}</div></div>`).join("")},
async packages(){const r=await api("packages.list");$("view").innerHTML=(r.packages.length?"":`<div class="card row"><span>No package yet.</span>
<button class="go" title="Builds Discover Mykonos from your confirmed suppliers (dive + boat, gear, lunch, hotel)." onclick="fixture()">Create “Discover Mykonos”</button></div>`)+
r.packages.map(p=>`<div class="card"><b>${esc(p.title)}</b> · €${p.price.amount_minor/100} per diver · <span class="chip ${p.published?'ok':'amb'}">${p.published?'Published':'Draft'}</span>
<p class="mut">${esc(p.description||"")}</p><p class="mut">${p.components.map(c=>esc(c.label)+(c.required?"":" (optional)")).join(" · ")}</p>
${p.published?'':`<button class="go" title="Publishes your API and its docs page with this package." onclick="publish()">Publish</button>`}</div>`).join("")},
async bookings(){const r=await api("bookings.list");$("view").innerHTML=r.bookings.map(b=>{const st=b.state;
const chip=st==="confirmed"?'<span class="chip ok big">✓ Confirmed</span>':st==="failed"?'<span class="chip no big">✕ Couldn’t confirm</span>':
`<span class="chip amb">${b.legs.filter(l=>["requested","pending","unreachable"].includes(l.state)).length?"Waiting for "+b.legs.filter(l=>["requested","pending","unreachable"].includes(l.state)).length+" supplier(s)":esc(st.replace("_"," "))}</span>`;
return `<div class="card"><div class="row" style="justify-content:space-between"><b>${esc(b.customer)} · ${when(b.starts_at)} · ${b.party}</b>${chip}</div>
<p class="mut">${esc(b.customer_sentence)}</p><div class="legs">`+b.legs.map(l=>{const ans=l.parse==="yes"?'<span class="chip ok">✓ their yes</span>':l.parse==="no"?'<span class="chip no">✕ their no</span>':l.parse==="unclear"?'<span class="chip amb">unclear — yours to decide</span>':"";
const cd=l.state==="requested"&&l.answer_by?` · answer by ${when(l.answer_by)}`:"";
return `<p><b>${esc(l.title)}</b> · ${esc(l.supplier)} · ${esc(l.channel_kind.replace("_"," "))} · ${esc(l.state.replace("_"," "))}${cd} ${ans}
${l.reply?` <span class="q">“${esc(l.reply.text)}”</span>`:""} ${l.evidence_id?`<button title="What we sent, what they answered, when — and a check that the record matches." onclick="proof('${l.evidence_id}')">Proof</button>`:""}</p>`}).join("")+
`</div>${b.evidence_id?`<button title="The whole booking's record." onclick="proof('${b.evidence_id}')">Booking proof</button>`:""}</div>`}).join("")||'<p class="mut">No bookings yet.</p>';
timer=setTimeout(()=>tab==="bookings"&&VIEWS.bookings().catch(()=>{}),3000)},
async activity(){const r=await api("activity.list");$("view").innerHTML='<div class="card">'+r.items.map(i=>`<p>${when(i.at)} · ${esc(i.line)}
${i.evidence_id?`<button title="Opens the record and checks it." onclick="proof('${i.evidence_id}')">Proof</button>`:""}</p>`).join("")+'</div>';timer=setTimeout(()=>tab==="activity"&&VIEWS.activity().catch(()=>{}),4000)},
async api(){$("view").innerHTML=`<div class="card"><p>Your API: <span class="k">${location.origin}/o/{slug}/v1</span> · Docs: <span class="k">${location.origin}/o/{slug}/docs</span></p>
<div class="row"><a class="btn" href="/o/{slug}/docs" target="_blank" title="Your API's documentation, under your name">Open my docs</a>
<a class="btn" href="/o/{slug}/book" target="_blank" title="Your customers' booking page">Open my booking page</a>
<button title="Creates a key for a partner or your own website. Shown once." onclick="issue()">Issue a key</button></div><p id="key" class="k"></p></div>`},
async drawer(){const r=await api("bookings.list");const open=r.bookings.flatMap(b=>b.legs.filter(l=>l.state==="requested").map(l=>({...l,b})));
const cap=await api("captured.list");
$("view").innerHTML=`<div class="card"><p class="mut">Test mode: in test we can play the supplier. Nothing here reaches a real phone.</p>
<button class="go" title="Prepares the Thursday booking for the failure beat and sends its requests." onclick="testQuote()">Prepare the Thursday booking</button></div>`+
open.map(l=>`<div class="card"><b>${esc(l.supplier)}</b> · ${esc(l.title)} · ${esc(l.b.customer)} ${when(l.b.starts_at)}<div class="row">
<button title="Plays the supplier answering YES" onclick="reply('${l.leg_id}','YES')">Supplier: YES</button><button title="Plays the supplier answering ΝΑΙ (Greek yes)" onclick="reply('${l.leg_id}','ΝΑΙ')">ΝΑΙ</button>
<button title="Plays the supplier answering NO, full" onclick="reply('${l.leg_id}','NO, full')">Supplier: NO, full</button>
<button title="Plays an unclear answer — it goes to you, never guessed" onclick="reply('${l.leg_id}','yes but only 3 seats')">“yes but only 3”</button></div></div>`).join("")+
`<div class="card"><b>What would have gone out (captured)</b>`+cap.messages.map(m=>`<p class="mut">${when(m.at)} · ${esc(m.channel)} → ${esc(m.to_)} ${m.real?'<span class="chip no">REAL</span>':''}<br>${esc(m.body)}</p>`).join("")+`</div>`}};
async function find(){$("view").innerHTML='<p class="big">Reading the site…</p>';try{await api("suppliers.draft_from_site")}catch(e){}VIEWS.suppliers()}
async function setSup(id,st){await api("suppliers.put",{supplier_id:id,status:st});VIEWS.suppliers()}
function chanForm(s){const c=s.contacts||{};const opts=[c.whatsapp?["whatsapp",c.whatsapp]:null,c.email?["email",c.email]:null,c.web_form?["web_form",c.web_form]:null,
s.kind==="hotel_feed"?["feed","feed:sandbox-hotels#Hotel Kyma View"]:null].filter(Boolean);
return opts.filter(([k])=>!s.channels.some(x=>x.kind===k)).map(([k,a])=>`<button title="Adds ${k.replace("_"," ")} (${esc(a)}) as how bookings reach them." onclick="addChan('${s.supplier_id}','${k}','${esc(a)}')">Use ${k.replace("_"," ")}</button>`).join("")}
async function addChan(id,k,a){await api("channels.put",{supplier_id:id,kind:k,address:a});VIEWS.suppliers()}
async function verify(id){const r=await api("channels.verify",{channel_id:id});$("msg").textContent=r.say;VIEWS.suppliers()}
async function fixture(){await api("packages.from_fixture");VIEWS.packages()}
async function publish(){const r=await api("operator_api.publish");$("msg").textContent="Published: "+r.base_url;VIEWS.packages()}
async function issue(){const r=await api("operator_keys.issue",{label:"Partner key"});$("key").textContent="Shown once: "+r.key}
async function testQuote(){await api("bookings.test_quote");go("bookings")}
async function reply(id,t){await api("sandbox.supplier_reply",{leg_id:id,text:t});VIEWS.drawer()}
async function proof(id){const r=await api("evidence.get",{evidence_id:id});const e=r.evidence;
alert((r.verified?"✓ The record matches.":"✕ Doesn't match.")+"\n\n"+e.operation+" · "+e.produced_at+"\n"+e.sources.map(s=>s.service+" · "+(s.snippet?s.snippet.text:"")+" · "+s.sha256.slice(0,23)+"…").join("\n")+(e.approval?"\nApproved by the customer: "+e.approval.method+" at "+e.approval.approved_at:""))}
rail();go("suppliers");
</script>"""
