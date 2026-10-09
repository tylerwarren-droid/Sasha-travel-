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
            if op == "bookings.cancel":       # CR 65 · from the console: the cancellation read-back goes to the CUSTOMER to approve
                try:
                    return JSONResponse({"ok": True, "result": await OPS.run(s, o, op, v)})
                except DiveError as e:
                    if e.code != "approval_required":
                        raise
                    return JSONResponse({"ok": True, "result": {"state": "sent_to_customer", "read_back": e.details["read_back"]}})
            if op == "drawer.state":          # CR 65 · the test drawer: verifications waiting + the customer's phone (captured links)
                waiting = [{"channel_id": c["id"], "supplier": c["name"], "kind": c["kind"]} for c in s.q(
                    "select c.id, c.kind, x.name from channels c join suppliers x on x.id = c.supplier_id where x.operator_id = ? and c.verified = 0 "
                    "and c.verify_state like '%\"sent\"%'", o["id"])]
                phone = [{"text": m["body"].rsplit(":", 1)[0] if "http" in m["body"] else m["body"], "link": m["body"].rsplit(" ", 1)[-1], "at": m["at"]}
                         for m in s.q("select body, at from captured where channel = 'sms' order by id desc limit 6")]
                return JSONResponse({"ok": True, "result": {"verifications": waiting, "phone": phone}})
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
.badge{border:1px solid var(--line);border-radius:99px;padding:.1rem .6rem;font-size:.75rem;letter-spacing:.06em}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.45);display:grid;place-items:center;padding:1rem;z-index:9}
.sheet{background:var(--card);border-radius:16px;max-width:42rem;width:100%;max-height:85vh;overflow:auto;padding:1rem 1.2rem}
.sheet dl{display:grid;grid-template-columns:auto 1fr;gap:.25rem .8rem;font-size:.92rem}.sheet dt{color:var(--mut)}.sheet dd{margin:0;overflow-wrap:anywhere}
.mini{display:flex;gap:.4rem;flex-wrap:wrap;align-items:center;margin:.3rem 0 .6rem}.mini input,.mini select{width:auto}</style>
<div class="row" style="justify-content:space-between"><h1 style="margin:.2rem 0">{name}</h1><span class="badge">TEST</span></div>
<div class="rail" id="rail"></div><div id="msg" class="mut" data-testid="msg"></div><div id="view"></div>
<div id="proof" class="overlay" hidden data-testid="proof-panel"><div class="sheet"><div class="row" style="justify-content:space-between"><b>Proof</b>
<button title="Close the proof" onclick="proofOpen=null;$('proof').hidden=true" data-testid="proof-close">Close</button></div><div id="proofbody"></div></div></div>
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
async suppliers(){const my="suppliers";const r=await api("suppliers.list");const conf=r.suppliers.filter(s=>s.status==="confirmed"),dr=r.suppliers.filter(s=>s.status==="draft");
if(tab===my)$("view").innerHTML=`<div class="card row"><b>Suppliers · ${conf.length} confirmed · ${dr.length} drafts</b>
<button class="go" title="Reads your website and lists the businesses it mentions. You confirm each one." onclick="find()">Find suppliers on my site</button></div>`+
dr.map(s=>`<div class="card"><b>${esc(s.name)}</b> · ${esc(s.kind.replace("_"," "))} <span class="mut">(${s.confidence}%)</span>
<p class="q">Found on ${esc(s.evidence_of_source.source.replace("site:",""))}: “${esc(s.evidence_of_source.text)}”${s.evidence_of_source.instruction_like?' <span class="chip no" title="This text tries to instruct an AI. It was not acted on.">instruction-like: ignored</span>':''}</p>
<div class="row"><button class="go" title="Adds this business as a supplier. Nothing is sent to them yet." onclick="setSup('${s.supplier_id}','confirmed')">Confirm</button>
<button title="Removes this draft." onclick="setSup('${s.supplier_id}','rejected')">Not ours</button></div></div>`).join("")+
conf.map(s=>`<div class="card"><b>${esc(s.name)}</b> · ${esc(s.kind.replace("_"," "))}<div class="legs">`+(s.channels.length?s.channels.map(c=>`<p>
<span class="chip ${c.verified?'ok':'amb'}">${esc(c.kind.replace("_"," "))} ${c.verified?'✓ verified '+when(c.verified_at):'· not verified'}</span> <span class="k">${esc(c.address)}</span>
${c.verified?'':`<button title="Sends one message asking them to reply YES to receive your booking requests." onclick="verify('${c.channel_id}')">Send verification</button>`}</p>`).join(""):
`<p class="mut">No channel yet.</p>`)+`</div><div class="row">${chanForm(s)}</div></div>`).join("")},
async packages(){const my="packages";const r=await api("packages.list");if(tab===my)$("view").innerHTML=(r.packages.length?"":`<div class="card row"><span>No package yet.</span>
<button class="go" title="Builds Discover Mykonos from your confirmed suppliers (dive + boat, gear, lunch, hotel)." onclick="fixture()">Create “Discover Mykonos”</button></div>`)+
r.packages.map(p=>`<div class="card"><b>${esc(p.title)}</b> · €${p.price.amount_minor/100} per diver · <span class="chip ${p.published?'ok':'amb'}">${p.published?'Published':'Draft'}</span>
<p class="mut">${esc(p.description||"")}</p><p class="mut">${p.components.map(c=>esc(c.label)+(c.required?"":" (optional)")).join(" · ")}</p>
${p.published?'':`<button class="go" title="Publishes your API and its docs page with this package." onclick="publish()">Publish</button>`}</div>`).join("")},
async bookings(){const my="bookings";const r=await api("bookings.list");if(tab===my)$("view").innerHTML=r.bookings.map(b=>{const st=b.state;
const waiting=b.legs.filter(l=>["requested","pending","unreachable"].includes(l.state)).length;
const chip=st==="confirmed"?'<span class="chip ok big">✓ Confirmed</span>':st==="failed"?'<span class="chip no big">✕ Couldn’t confirm</span>':
st==="cancelled"?'<span class="chip amb">Cancelled</span>':st==="replaced"?'<span class="chip amb">Replaced — new read-back sent</span>':
`<span class="chip amb">${waiting?"Waiting for "+waiting+" supplier(s)":esc(st.replace("_"," "))}</span>`;
const todo=((b.notes||{}).todo||[]).map(t=>`<p class="chip amb">To do: ${esc(t)}</p>`).join("");
const act=["confirmed","in_progress"].includes(st)?`<button data-testid="cancel-${b.bundle_id}" title="Sends the customer a cancellation to approve, then cancels with each supplier." onclick="cancelB('${b.bundle_id}')">Cancel booking</button>`:
["failed","replaced","cancelled"].includes(st)?`<span class="mini"><input type="date" id="d-${b.bundle_id}"><select id="t-${b.bundle_id}"><option>09:00</option><option>10:00</option></select>
<button data-testid="offer-${b.bundle_id}" title="Builds a new quote for the customer. They approve it on their phone." onclick="offer('${b.bundle_id}')">Offer another time</button></span>`:"";
return `<div class="card" data-testid="booking" data-state="${st}"><div class="row" style="justify-content:space-between"><b>${esc(b.customer)} · ${when(b.starts_at)} · ${b.party}</b>${chip}</div>
<p class="mut" data-testid="sentence">${esc(b.customer_sentence)}</p>${todo}<div class="legs">`+b.legs.map(l=>legRow(b,l)).join("")+
`</div><div class="row">${b.evidence_id?`<button title="The whole booking's record." onclick="proof('${b.evidence_id}')" data-testid="booking-proof">Booking proof</button>`:""}${act}</div></div>`}).join("")||'<p class="mut">No bookings yet.</p>';
timer=setTimeout(()=>tab==="bookings"&&!document.querySelector("#view input:focus,#view select:focus")&&VIEWS.bookings().catch(()=>{}),3000)},
async activity(){const my="activity";const r=await api("activity.list");if(tab===my)$("view").innerHTML='<div class="card">'+r.items.map(i=>`<p>${when(i.at)} · ${esc(i.line)}
${i.evidence_id?`<button title="Opens the record and checks it." onclick="proof('${i.evidence_id}')">Proof</button>`:""}</p>`).join("")+'</div>';timer=setTimeout(()=>tab==="activity"&&VIEWS.activity().catch(()=>{}),4000)},
async api(){const my="api";if(tab===my)$("view").innerHTML=`<div class="card"><p>Your API: <span class="k">${location.origin}/o/{slug}/v1</span> · Docs: <span class="k">${location.origin}/o/{slug}/docs</span></p>
<div class="row"><a class="btn" href="/o/{slug}/docs" target="_blank" title="Your API's documentation, under your name">Open my docs</a>
<a class="btn" href="/o/{slug}/book" target="_blank" title="Your customers' booking page">Open my booking page</a>
<button title="Creates a key for a partner or your own website. Shown once." onclick="issue()">Issue a key</button></div><p id="key" class="k"></p></div>`},
async drawer(){const my="drawer";const r=await api("bookings.list");const open=r.bookings.flatMap(b=>b.legs.filter(l=>l.state==="requested").map(l=>({...l,b})));
const ds=await api("drawer.state");const cap=await api("captured.list");
if(tab===my)$("view").innerHTML=`<div class="card"><p class="mut">Test mode: in test we can play the supplier. Nothing here reaches a real phone.</p>
<button class="go" data-testid="test-quote" title="Prepares the Thursday booking for the failure beat and sends its requests." onclick="testQuote()">Prepare the Thursday booking</button></div>`+
ds.verifications.map(v=>`<div class="card"><b>${esc(v.supplier)}</b> · verification sent by ${esc(v.kind)}<div class="row">
<button data-testid="verify-yes-${v.channel_id}" title="Plays the supplier answering YES to the verification" onclick="vreply('${v.channel_id}','YES')">Supplier: YES</button></div></div>`).join("")+
open.map(l=>`<div class="card" data-testid="drawer-leg" data-supplier="${esc(l.supplier)}"><b>${esc(l.supplier)}</b> · ${esc(l.title)} · ${esc(l.b.customer)} ${when(l.b.starts_at)}<div class="row">
<button data-testid="yes-${l.leg_id}" title="Plays the supplier answering YES" onclick="reply('${l.leg_id}','YES')">Supplier: YES</button><button data-testid="nai-${l.leg_id}" title="Plays the supplier answering ΝΑΙ (Greek yes)" onclick="reply('${l.leg_id}','ΝΑΙ')">ΝΑΙ</button>
<button data-testid="no-${l.leg_id}" title="Plays the supplier answering NO, full" onclick="reply('${l.leg_id}','NO, full')">Supplier: NO, full</button>
<button data-testid="unclear-${l.leg_id}" title="Plays an unclear answer — it goes to you, never guessed" onclick="reply('${l.leg_id}','yes but only 3 seats')">“yes but only 3”</button></div></div>`).join("")+
`<div class="card"><b>The customer's phone</b>`+ds.phone.map((m,i)=>`<p><a data-testid="phone-link-${i}" href="${esc(m.link)}" target="_blank" title="Opens the customer's phone screen">${esc(m.text)}</a> <span class="mut">${when(m.at)}</span></p>`).join("")+`</div>`+
`<div class="card"><b>What would have gone out (captured)</b>`+cap.messages.map(m=>`<p class="mut">${when(m.at)} · ${esc(m.channel)} → ${esc(m.to_)} ${m.real?'<span class="chip no">REAL</span>':''}<br>${esc(m.body)}</p>`).join("")+`</div>`}};
function legRow(b,l){const ans=l.parse==="yes"?'<span class="chip ok">✓ their yes</span>':l.parse==="no"?'<span class="chip no">✕ their no</span>':l.parse==="unclear"?'<span class="chip amb">unclear — yours to decide</span>':"";
const cd=l.state==="requested"&&l.answer_by?` · answer by ${when(l.answer_by)}`:"";
let tools="";if(l.parse==="unclear"&&l.state==="requested"){const m=(l.reply&&l.reply.text||"").match(/\b(\d{1,2})\b/);const n=m&&+m[1]<b.party?+m[1]:b.party-1;
tools=`<span class="mini"><button class="go" data-testid="accept-${l.leg_id}" title="Re-quotes for ${n} and asks the customer" onclick="act('legs.accept_partial',{leg_id:'${l.leg_id}',party:${n}})">Accept ${n}</button>
<button data-testid="treatno-${l.leg_id}" title="Records a no" onclick="act('legs.treat_as_no',{leg_id:'${l.leg_id}',by:'the operator'})">Treat as no</button>
<button data-testid="askagain-${l.leg_id}" title="Sends the question again" onclick="act('legs.ask_again',{leg_id:'${l.leg_id}'})">Ask again</button></span>`}
else if(["requested","no_answer","unreachable"].includes(l.state)){tools=`<span class="mini"><button data-testid="phone-${l.leg_id}" title="Mark that you'll call them; record their answer here afterwards." onclick="act('legs.ask_by_phone',{leg_id:'${l.leg_id}',by:'the operator'})">Ask again by phone</button>
<select id="ra-${l.leg_id}"><option value="yes">They said yes</option><option value="no">They said no</option></select><input id="rn-${l.leg_id}" placeholder="Note (who, when)" maxlength="300">
<button data-testid="record-${l.leg_id}" title="Enter what the supplier told you by phone. It's saved as your record, with your name." onclick="record('${l.leg_id}')">Record answer</button></span>`}
return `<p data-testid="leg" data-supplier="${esc(l.supplier)}" data-state="${l.state}"><b>${esc(l.title)}</b> · ${esc(l.supplier)} · ${esc(l.channel_kind.replace("_"," "))} · ${esc(l.state.replace("_"," "))}${cd} ${ans}
${l.reply?` <span class="q">“${esc(l.reply.text)}”</span>`:""} ${l.evidence_id?`<button data-testid="proof-${l.leg_id}" title="What we sent, what they answered, when — and a check that the record matches." onclick="proof('${l.evidence_id}')">Proof</button>`:""}</p>${tools}`}
async function act(op,body){await api(op,body);VIEWS.bookings()}
async function record(id){await api("legs.record_answer",{leg_id:id,answer:$("ra-"+id).value,note:$("rn-"+id).value,by:"the operator"});VIEWS.bookings()}
async function offer(id){const d=$("d-"+id).value;if(!d){$("msg").textContent="Choose a date to offer.";return}const r=await api("bookings.offer_another_time",{bundle_id:id,date:d,start_time:$("t-"+id).value});
await VIEWS.bookings();$("msg").textContent="A new read-back went to the customer."}
async function cancelB(id){const r=await api("bookings.cancel",{bundle_id:id});await VIEWS.bookings();$("msg").textContent=r.state==="sent_to_customer"?"The cancellation went to the customer to approve.":"Cancelled."}
async function find(){$("view").innerHTML='<p class="big">Reading the site…</p>';try{await api("suppliers.draft_from_site")}catch(e){}VIEWS.suppliers()}
async function setSup(id,st){await api("suppliers.put",{supplier_id:id,status:st});VIEWS.suppliers()}
function chanForm(s){const c=s.contacts||{};const opts=[c.whatsapp?["whatsapp",c.whatsapp]:null,c.email?["email",c.email]:null,c.web_form?["web_form",c.web_form]:null,
s.kind==="hotel_feed"?["feed","feed:sandbox-hotels#Hotel Kyma View"]:null].filter(Boolean);
return opts.filter(([k])=>!s.channels.some(x=>x.kind===k)).map(([k,a])=>`<button title="Adds ${k.replace("_"," ")} (${esc(a)}) as how bookings reach them." onclick="addChan('${s.supplier_id}','${k}','${esc(a)}')">Use ${k.replace("_"," ")}</button>`).join("")}
async function addChan(id,k,a){await api("channels.put",{supplier_id:id,kind:k,address:a});VIEWS.suppliers()}
async function verify(id){const r=await api("channels.verify",{channel_id:id});await VIEWS.suppliers();$("msg").textContent=r.say}
async function fixture(){await api("packages.from_fixture");VIEWS.packages()}
async function publish(){const r=await api("operator_api.publish");await VIEWS.packages();$("msg").textContent="Published: "+r.base_url}
async function issue(){const r=await api("operator_keys.issue",{label:"Partner key"});$("key").textContent="Shown once: "+r.key}
async function testQuote(){await api("bookings.test_quote");go("bookings")}
async function reply(id,t){await api("sandbox.supplier_reply",{leg_id:id,text:t});VIEWS.drawer()}
async function vreply(id,t){await api("sandbox.supplier_reply",{channel_id:id,text:t});VIEWS.drawer()}
async function proof(id){const r=await api("evidence.get",{evidence_id:id});const e=r.evidence;
const src=e.sources.map(x=>`<dt>${esc(x.service)}</dt><dd>${x.snippet?"“"+esc(x.snippet.text)+"”"+(x.snippet.instruction_like?' <span class="chip no">instruction-like: not acted on</span>':""):""}<br><span class="k">${esc(x.sha256)}</span></dd>`).join("");
const ap=e.approval?`<dt>Approved</dt><dd>by the customer (${esc(e.approval.method)}) at ${when(e.approval.approved_at)}${e.approval.said?" — “"+esc(e.approval.said)+"”":""}<br><span class="k">read-back ${esc(e.approval.read_back_sha256)}</span></dd>`:"";
$("proofbody").innerHTML=`<p class="big ${r.verified?'':'no'}" data-testid="proof-verdict">${r.verified?"✓ The record matches.":"✕ Doesn't match."}</p>
<dl><dt>What</dt><dd>${esc(e.operation)}${e.outcome?" · "+esc(e.outcome.kind)+(e.outcome.reference?" · "+esc(e.outcome.reference):""):""}</dd><dt>When</dt><dd>${when(e.produced_at)}</dd>${ap}${src}
<dt>Fingerprint</dt><dd class="k">${esc(e.body_sha256)}</dd></dl><p><button class="go" data-testid="proof-verify" title="Recomputes the record's fingerprint now" onclick="verifyAgain('${id}')">Verify</button></p>`;
proofOpen=id;$("proof").hidden=false}
let proofOpen=null;
async function verifyAgain(id){const v=document.querySelector("[data-testid=proof-verdict]");v.textContent="Checking…";v.className="big";
const r=await api("evidence.get",{evidence_id:id});if(proofOpen!==id||$("proof").hidden)return;   // closed meanwhile: a late answer never reopens it
v.textContent=r.verified?"✓ The record matches.":"✕ Doesn't match.";v.className="big"+(r.verified?"":" no")}
rail();go("suppliers");
</script>"""
