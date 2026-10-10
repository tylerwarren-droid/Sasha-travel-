"""CR 73 · /registry — the registry survey's first demo page on the sandbox (EU 214 build-plan step 8, read-only):
pick a country → its registers → their documents → "how do I get it?" (registry.obtain_plan) — every value with its source link, the
sentence quoted from it and the date it was read; "unknown" where nothing says. "Check now" re-reads one source (registry.verify).

No key is shown or needed: the page calls the same operation functions as /v1/registry.* on public, read-only facts. Check now is
budgeted (per host, and 60 an hour for the page), and registry.obtain stays off: nothing is ever obtained from here."""
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, Callable, Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ..registry import AgapiError
from . import ops

router = APIRouter()
_get_store: Callable[[], Any] = lambda: None
_CHECKS: List[float] = []
PAGE_CHECKS_PER_HOUR = 60


def bind(get_store: Callable[[], Any]) -> None:
    global _get_store
    _get_store = get_store


async def _run(fn, inp: dict, status_ok: int = 200):
    try:
        out, _, _ = await fn(SimpleNamespace(store=_get_store()), inp)
        return JSONResponse({"ok": True, "result": out}, headers={"Cache-Control": "no-store"})
    except AgapiError as e:
        return JSONResponse({"ok": False, "error": e.body()}, status_code=e.http)


@router.get("/registry/api/countries")
async def api_countries():
    return await _run(ops.countries, {})


@router.get("/registry/api/country/{code}")
async def api_country(code: str):
    try:
        g, _, _ = await ops.get(SimpleNamespace(store=_get_store()), {"jurisdiction": code})
        d, _, _ = await ops.documents(SimpleNamespace(store=_get_store()), {"jurisdiction": code})
    except AgapiError as e:
        return JSONResponse({"ok": False, "error": e.body()}, status_code=e.http)
    return JSONResponse({"ok": True, "result": {**g, "documents": d["documents"]}}, headers={"Cache-Control": "no-store"})


@router.get("/registry/api/plan/{code}/{document_id}")
async def api_plan(code: str, document_id: str, actor: str = "agapi"):
    return await _run(ops.obtain_plan, {"jurisdiction": code, "document_id": document_id, "actor": actor if actor in ("agapi", "person", "subject") else "agapi"})


@router.post("/registry/api/verify")
async def api_verify(req: Request):
    body = await req.json()
    now = time.time()
    _CHECKS[:] = [t for t in _CHECKS if now - t < 3600]
    if len(_CHECKS) >= PAGE_CHECKS_PER_HOUR:
        return JSONResponse({"ok": False, "error": {"code": "rate_limited", "message": "This page's checks for the hour are used up."}}, status_code=429)
    _CHECKS.append(now)
    return await _run(ops.verify, {"claim_id": str(body.get("claim_id") or "")[:40]})


@router.get("/registry", response_class=HTMLResponse)
async def page():
    return HTMLResponse(PAGE, headers={"Cache-Control": "no-store"})


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Registry survey</title><meta name="robots" content="noindex"><style>
:root{--bg:#f6f4ef;--fg:#1c1a16;--mut:#6d675c;--card:#fff;--line:#e3ded3;--ok:#18794e;--okbg:#e7f5ee;--no:#b42318;--nobg:#fdecea;
--amb:#8a5a00;--ambbg:#fff4dd;--acc:#1f4fd1;--accbg:#e9efff}
@media (prefers-color-scheme:dark){:root{--bg:#121110;--fg:#f2efe8;--mut:#a59f93;--card:#1b1a17;--line:#2d2b27;--ok:#4ade80;--okbg:#10291c;
--no:#f87171;--nobg:#2c1414;--amb:#fbbf24;--ambbg:#2a210b;--acc:#8fb0ff;--accbg:#18213a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1080px;margin:0 auto;padding:20px 16px 60px}h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:24px 0 8px}
.sub{color:var(--mut);margin:0 0 16px;max-width:760px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}.chip{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:999px;
padding:6px 11px;cursor:pointer;font:inherit;font-size:13px}.chip[aria-pressed=true]{background:var(--fg);color:var(--bg);border-color:var(--fg)}
.chip small{color:var(--mut);margin-left:4px}.chip[aria-pressed=true] small{color:inherit;opacity:.7}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:10px 0}
.row{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}.k{color:var(--mut);font-size:12px;min-width:118px}
.v{flex:1;min-width:0;overflow-wrap:anywhere}.unk{color:var(--mut);font-style:italic}
.src{font-size:12px;color:var(--acc);background:none;border:0;padding:0;cursor:pointer;text-decoration:underline;font:inherit;font-size:12px}
.q{margin:6px 0 2px;padding:8px 10px;border-left:3px solid var(--line);background:var(--bg);font-size:13px;border-radius:0 6px 6px 0;overflow-wrap:anywhere}
.meta{font-size:12px;color:var(--mut)}.tag{display:inline-block;font-size:11px;padding:2px 7px;border-radius:999px;background:var(--bg);border:1px solid var(--line);color:var(--mut)}
.t1{background:var(--okbg);color:var(--ok);border-color:transparent}.t2{background:var(--accbg);color:var(--acc);border-color:transparent}
.t3{background:var(--ambbg);color:var(--amb);border-color:transparent}.t4{background:var(--bg)}
.yes{color:var(--ok)}.with_human{color:var(--amb)}.no{color:var(--no)}
button.go{background:var(--fg);color:var(--bg);border:0;border-radius:8px;padding:7px 12px;font:inherit;font-size:13px;cursor:pointer}
.plan{margin-top:10px;border-top:1px dashed var(--line);padding-top:10px}.route{padding:8px 0;border-bottom:1px solid var(--line)}.route:last-child{border:0}
.off{margin-top:8px;font-size:12px;color:var(--mut)}.stats{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--mut)}
.chk{font-size:12px;margin-left:6px}.ok{color:var(--ok)}.bad{color:var(--no)}.warn{color:var(--amb)}
details summary{cursor:pointer}footer{margin-top:30px;font-size:12px;color:var(--mut)}
</style></head><body><main>
<h1>Registry survey · wave 0</h1>
<p class="sub">The official registers of the 19 jurisdictions where Applied Diligence has a certified rail. Pick a country: its registers, what you can get from them, and how. Every value links to its source — the sentence, quoted word for word, and the date it was read. <b>Unknown</b> means no source says.</p>
<div id="chips" class="chips" role="group" aria-label="Country"></div>
<div id="out"><p class="meta">Loading…</p></div>
<footer>AgAPI sandbox · registry.* (Kanoe extensions, EU 214) · read-only: registry.obtain is off — plans only; nothing is bought, no account is used, no CAPTCHA is solved. Sources were read by Magellan from the sandbox server, robots.txt first.</footer>
</main><script>
const $=s=>document.querySelector(s), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const LABEL={name_local:'Name',name_en:'Name (English)',authority:'Authority',kind:'Kind',official_url:'Official site',governing_law:'Law',status:'Status',
 subject:'About',identifier_needed:'You need',who_may_obtain:'Who may obtain it',certified_form_available:'Certified form',channel:'How',actor:'Who can use it',
 cost:'Cost',turnaround:'Turnaround',entry_url:'Where',robots_verdict:'robots.txt',certified_rail:'Certified rail',catalogue_availability:'In AD’s catalogue',
 terms_url:'Terms',apostille_available:'Apostille'};
const SAY={free_web:'free on the web',paid_web:'paid, on the web',account:'with an account',eid:'with an eID',api:'an API',bulk_download:'a bulk download',
 intermediary:'through an intermediary',post:'by post',in_person:'in person',anyone:'anyone',account_holder:'an account holder',resident_eid:'a resident with an eID',
 subject:'the subject only',legitimate_interest:'someone with a legitimate interest',subject_only:'the subject only',authority_only:'authorities only',
 obliged_entity:'obliged entities (AML)',extract_current:'current extract',extract_historical:'historical extract',certificate:'certificate',search_result:'search result',
 filing_copy:'filed document',ubo_extract:'UBO extract',dataset:'dataset',company:'company',person:'person',property:'property',registration_number:'the registration number',
 national_id:'a national ID',name:'a name',none:'nothing',exists:'exists',does_not_exist:'does not exist',instant:'instant',minutes:'minutes',allowed:'allows us',
 disallowed:'disallows automated readers',unreadable:'unreadable (a web page, not a robots file)',never_fetch:'on AD’s never-fetch list',not_applicable:'not applicable (a person downloads the file)',
 available:'available',withdrawn:'withdrawn',true:'yes',false:'no'};
const OBT={yes:'AgAPI can obtain it',with_human:'with a person',no:'AgAPI can\u2019t: only the subject or an authority',unknown:'unknown: no source states a route yet'};
function val(v){if(v==='unknown'||v==null)return '<span class="unk">unknown</span>';
 if(typeof v==='object'){if('amount_minor' in v)return v.basis==='free'?'free':esc((v.amount_minor/100).toFixed(2)+' '+(v.currency||'')+' '+(v.basis||'').replace('_',' '));
  if(v.config_hash)return 'suite '+esc(v.suite)+' passed '+esc((v.executed_at||'').slice(0,10))+' · config '+esc(v.config_hash.slice(0,12))+'…';return esc(JSON.stringify(v))}
 if(typeof v==='string'&&/^https?:\/\//.test(v))return '<a href="'+esc(v)+'" rel="noopener noreferrer" target="_blank">'+esc(v.replace(/^https?:\/\//,'').slice(0,70))+'</a>';
 if(typeof v==='string'&&v.startsWith('days:'))return esc(v.slice(5))+' days';return esc(SAY[String(v)]??v)}
let uid=0;
function field(name,c){const id='s'+(++uid);if(!c||c.value==='unknown')return '<div class="row"><span class="k">'+esc(LABEL[name]||name)+'</span><span class="v"><span class="unk">unknown</span> <span class="meta">no claim behind it</span></span></div>';
 const web=/^https?:/.test(c.source_url||'');
 return '<div class="row"><span class="k">'+esc(LABEL[name]||name)+'</span><span class="v">'+val(c.value)+' <button class="src" aria-expanded="false" data-t="'+id+'">source</button>'
  +'<div id="'+id+'" hidden>'+(c.quote&&c.quote.text?'<div class="q">“'+esc(c.quote.text)+'”</div>':'')
  +'<div class="meta">'+(web?'<a href="'+esc(c.source_url)+'" target="_blank" rel="noopener noreferrer">'+esc(c.source_url.slice(0,90))+'</a>':esc(c.source_url))
  +' · read '+esc((c.read_at||'').slice(0,10))+' · '+esc(c.method)+' · '+esc(c.confidence)+(c.note?' · '+esc(c.note):'')
  +(web&&c.method!=='magellan_robots'?' <button class="src chk" data-claim="'+esc(c.claim_id)+'">check now</button><span class="chk" id="v'+esc(c.claim_id)+'"></span>':'')+'</div></div></span></div>'}
function fields(f,order){const ks=order.concat(Object.keys(f).filter(k=>!order.includes(k)));return ks.filter(k=>f[k]).map(k=>field(k,f[k])).join('')}
async function j(u,o){const r=await fetch(u,o);return r.json()}
async function countries(){const r=await j('/registry/api/countries');if(!r.ok){$('#out').innerHTML='<p>Couldn’t load.</p>';return}
 $('#chips').innerHTML=r.result.jurisdictions.map(c=>'<button class="chip" aria-pressed="false" data-c="'+esc(c.code)+'">'+esc(c.name)+'<small>'+c.registers+'·'+c.documents+'·'+c.routes+'</small></button>').join('');
 const want=(location.hash||'#AT').slice(1);show(r.result.jurisdictions.some(c=>c.code===want)?want:'AT')}
async function show(code){document.querySelectorAll('.chip').forEach(b=>b.setAttribute('aria-pressed',b.dataset.c===code));history.replaceState(null,'','#'+code);
 $('#out').innerHTML='<p class="meta">Loading…</p>';const r=await j('/registry/api/country/'+encodeURIComponent(code));
 if(!r.ok){$('#out').innerHTML='<p>'+esc(r.error.message)+'</p>';return}const g=r.result,s=g.sources||{};
 let h='<div class="stats"><span>'+g.registers.length+' register'+(g.registers.length===1?'':'s')+'</span><span>'+g.documents.length+' documents</span>'
  +(s.read_at?'<span>sources read '+esc(s.read_at.slice(0,10))+' ('+(s.pages||[]).length+' pages)</span>':'<span>no official page read yet</span>')+'</div>';
 if((s.unread||[]).length)h+='<details class="card"><summary>'+s.unread.length+' official page'+(s.unread.length===1?'':'s')+' not read — why</summary>'+s.unread.map(u=>'<div class="meta">'+esc(u.url)+' — '+esc(u.why)+'</div>').join('')+'</details>';
 h+='<h2>Registers</h2>'+g.registers.map(x=>'<div class="card"><b>'+esc(x.name==='unknown'?'Register (name not stated by a source)':x.name)+'</b> <span class="tag">'+esc(x.confidence)+'</span>'+fields(x.fields,['name_local','name_en','authority','kind','status','official_url','governing_law'])+'</div>').join('');
 h+='<h2>What you can get, and how</h2>'+g.documents.map(d=>'<div class="card"><div class="row"><b style="flex:1">'+esc(d.name==='unknown'?'Document (name not stated)':d.name)+'</b><span class="meta">'+esc(d.register)+'</span></div>'
  +fields(d.fields,['kind','subject','who_may_obtain','identifier_needed','certified_form_available'])
  +'<div class="row" style="margin-top:8px"><button class="go" data-plan="'+esc(d.document_id)+'">How do I get it?</button><span class="meta">'+d.routes.length+' route'+(d.routes.length===1?'':'s')+'</span></div><div class="plan" id="p'+esc(d.document_id)+'" hidden></div></div>').join('');
 $('#out').innerHTML=h}
async function plan(doc){const box=$('#p'+doc);box.hidden=false;box.innerHTML='<p class="meta">Planning…</p>';const code=location.hash.slice(1);
 const r=await j('/registry/api/plan/'+encodeURIComponent(code)+'/'+encodeURIComponent(doc));if(!r.ok){box.innerHTML='<p>'+esc(r.error.message)+'</p>';return}const p=r.result;
 box.innerHTML='<div class="row"><b>'+esc(OBT[p.obtainable_by_agapi])+'</b></div>'+p.routes.map(x=>'<div class="route"><div class="row"><span class="tag t'+x.tier+'">'+x.rank+' · '+esc(x.tier_says)+'</span><span class="'+x.obtainable_by_agapi+'">'+esc(OBT[x.obtainable_by_agapi])+'</span>'
  +(x.requires.length?'<span class="meta">needs: '+esc(x.requires.join(', ').replace(/_/g,' '))+'</span>':'')+'</div>'+(x.notes.length?'<div class="meta">'+x.notes.map(esc).join(' · ')+'</div>':'')
  +fields(x.fields,['channel','actor','cost','turnaround','entry_url','robots_verdict','certified_rail','catalogue_availability'])+'</div>').join('')
  +(p.excluded.length?'<div class="meta">Not for AgAPI: '+p.excluded.map(e=>esc(e.why)).join(' · ')+'</div>':'')+'<div class="off">'+esc(p.obtain)+'</div>'}
async function check(id,el){const o=$('#v'+id);o.textContent=' checking…';o.className='chk';const r=await j('/registry/api/verify',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({claim_id:id})});
 if(!r.ok){o.textContent=' '+(r.error.message||r.error.code);o.className='chk warn';return}const v=r.result;
 o.textContent=v.state==='fresh'?' ✓ the quoted sentence is still on the page, read now':v.state==='drifted'?' ✗ the sentence is no longer on the page (drifted)':' ✗ the page can’t be read now ('+(v.failure_layer||'')+')';o.className='chk '+(v.state==='fresh'?'ok':'bad');el.remove()}
document.addEventListener('click',e=>{const t=e.target;if(t.dataset.c)show(t.dataset.c);else if(t.dataset.t){const d=document.getElementById(t.dataset.t);d.hidden=!d.hidden;t.setAttribute('aria-expanded',!d.hidden)}
 else if(t.dataset.plan)plan(t.dataset.plan);else if(t.dataset.claim)check(t.dataset.claim,t)});
countries();
</script></body></html>"""
