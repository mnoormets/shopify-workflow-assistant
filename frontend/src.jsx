import React,{useEffect,useState} from 'react';

import {createRoot} from 'react-dom/client';

import './style.css';

const names={PAID_NOT_FULFILLED:'Makstud, kuid saatmata',PAYMENT_PENDING:'Makse on ootel',REFUNDED_FULFILLED:'Tagastus ja tarne',PAYMENT_MISMATCH:'Makseolekute vastuolu',TRACKING_MISSING:'Jälgimiskood puudub',STOCK_SHORTAGE:'Laoseisu puudujääk',SHIPMENT_MISMATCH:'Tarneolekute vastuolu'};

const priorities={high:'Kõrge',medium:'Keskmine',low:'Madal'};

async function api(path,options={}){const r=await fetch('/api'+path,options);let body;try{body=await r.json()}catch{throw new Error('Server ei vastanud ootuspäraselt.')}if(!r.ok)throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail));return body}

function App(){

 const [report,setReport]=useState(null),[q,setQ]=useState(''),[severity,setSeverity]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[selected,setSelected]=useState(null),[explanation,setExplanation]=useState(null),[ai,setAi]=useState(false);

 const [explaining,setExplaining]=useState(false),[message,setMessage]=useState('');

 const [policy,setPolicy]=useState(null),[saving,setSaving]=useState(false);
 const [events,setEvents]=useState(null),[eventBusy,setEventBusy]=useState(false),[audit,setAudit]=useState(null);
 async function loadEvents(){try{setEvents(await api('/events'))}catch(e){setError(e.message)}}
 async function eventAction(path){setEventBusy(true);setAudit(null);try{await api(path,{method:'POST'});await loadEvents();await load();setMessage('Sündmuste töötlemine kontrollitud. Tellimusi Shopify poes ei muudetud.')}catch(e){setError(e.message)}finally{setEventBusy(false)}}
 async function showAudit(id){try{setAudit(await api('/events/'+id+'/audit'))}catch(e){setError(e.message)}}
 useEffect(()=>{loadEvents()},[]);

 async function load(){try{const r=await api('/findings?q='+encodeURIComponent(q)+'&severity='+severity);setReport(r);setError('')}catch(e){setError(e.message)}}

 useEffect(()=>{let active=true;const timer=setTimeout(async()=>{try{const r=await api('/findings?q='+encodeURIComponent(q)+'&severity='+severity);if(active){setReport(r);setError('')}}catch(e){if(active)setError(e.message)}},150);return()=>{active=false;clearTimeout(timer)}},[q,severity]);

 useEffect(()=>{api('/policy').then(setPolicy).catch(e=>setError(e.message))},[]);

 useEffect(()=>{api('/health').then(r=>setAi(r.ai_enabled)).catch(()=>{})},[]);

 async function savePolicy(event){event.preventDefault();setSaving(true);try{const saved=await api('/policy',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({paid_unfulfilled_hours:Number(policy.paid_unfulfilled_hours),pending_payment_hours:Number(policy.pending_payment_hours)})});setPolicy(saved);setSelected(null);setExplanation(null);setMessage('Kontrollipiirid salvestatud. Tellimused hinnati uuesti.');await load()}catch(e){setError(e.message)}finally{setSaving(false)}}

 async function demo(){setBusy(true);try{const r=await api('/demo',{method:'POST'});setMessage(r.replayed?'Näidisandmed olid juba imporditud.':'Näidistellimused imporditud.');await load()}catch(e){setError(e.message)}finally{setBusy(false)}}

 async function importFile(event){const file=event.target.files[0];if(!file)return;setBusy(true);try{if(file.size>1024*1024)throw new Error('Fail on suurem kui 1 MB.');const payload=JSON.parse(await file.text());const bytes=new TextEncoder().encode(JSON.stringify(payload));const digest=await crypto.subtle.digest('SHA-256',bytes);const key=Array.from(new Uint8Array(digest)).map(b=>b.toString(16).padStart(2,'0')).join('');const r=await api('/import',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify(payload)});setMessage(r.replayed?'Sama import oli juba tehtud.':r.imported+' tellimust imporditud.');await load()}catch(e){setError(e.message)}finally{setBusy(false);event.target.value=''}}

 async function explain(f){setSelected(f);setExplanation(null);setExplaining(true);try{setExplanation(await api('/explain/'+encodeURIComponent(f.order_id)+'/'+f.code,{method:'POST'}))}catch(e){setError(e.message)}finally{setExplaining(false)}}

 return <main><header><div className="brand">WORKFLOW / LAB</div><span className="pill">Näidisandmete demo</span></header>

 <section className="intro"><p className="eyebrow">SHOPIFY TÖÖVOOGUDE ASSISTENT</p><h1>Leia vastuolud.<br/><span>Tea, mida kontrollida.</span></h1><p className="lede">Maksed, laoseis ja tarne ühes ülevaates. Iga leid näitab tõendeid ja järgmist kontrollsammu.</p><div className="actions"><button onClick={demo} disabled={busy}>{busy?'Laadin…':'Laadi näidistellimused'}</button><label className="file">Impordi JSON<input type="file" accept=".json,application/json" onChange={importFile} disabled={busy}/></label><a href="/docs" target="_blank" rel="noreferrer">API dokumentatsioon ↗</a></div></section>

 {error&&<div className="error" role="alert">{error}</div>}{message&&<div className="notice" role="status">{message}</div>}

 <section className="metrics"><article><span>Kontrollitud tellimusi</span><strong>{report?.orders_scanned??'—'}</strong></article><article><span>Kontrollimist vajavaid leide</span><strong>{report?.total_findings??'—'}</strong></article><article><span>Selgituste allikas</span><strong className="small">{ai?'Kohalik AI + reeglid':'Kontrollitavad reeglid'}</strong><small>{ai?'AI tekst on kontrollimist vajav mustand.':'AI mudel pole veel ühendatud.'}</small></article></section>

 {policy&&<section className="policy"><h2>Kontrollipiirid</h2><p>Vali, mitme tunni möödudes tellimus kontrollijärjekorda lisada. Muutus ei muuda tellimusi ega makseid.</p><form onSubmit={savePolicy}><label>Makstud, kuid saatmata (tundi)<input type="number" min="1" max="720" step="1" required value={policy.paid_unfulfilled_hours} onChange={e=>setPolicy({...policy,paid_unfulfilled_hours:e.target.value})}/></label><label>Makse ootel (tundi)<input type="number" min="1" max="720" step="1" required value={policy.pending_payment_hours} onChange={e=>setPolicy({...policy,pending_payment_hours:e.target.value})}/></label><button disabled={saving}>{saving?'Salvestan…':'Salvesta piirid'}</button></form></section>}

 <section className="review"><div className="section-title"><h2>Kontrollijärjekord</h2><span>{report?.findings.length??0} nähtavat leidu</span></div><div className="filters"><input aria-label="Otsi tellimust või probleemi" placeholder="Otsi tellimuse ID või probleemi järgi…" value={q} onChange={e=>setQ(e.target.value)}/><select aria-label="Prioriteet" value={severity} onChange={e=>setSeverity(e.target.value)}><option value="">Kõik prioriteedid</option><option value="high">Kõrge</option><option value="medium">Keskmine</option><option value="low">Madal</option></select></div>

 {!report?<p className="empty">Laadin ülevaadet…</p>:report.orders_scanned===0?<p className="empty">Alusta näidistellimuste laadimisest.</p>:report.findings.length===0?<p className="empty">Nende filtritega leide ei ole.</p>:<div className="table-wrap"><table><thead><tr><th>Tellimus</th><th>Prioriteet</th><th>Probleem</th><th></th></tr></thead><tbody>{report.findings.map(f=><tr key={f.order_id+f.code}><td className="order">{f.order_id}</td><td><span className={'severity '+f.severity}>{priorities[f.severity]}</span></td><td><b>{names[f.code]??f.code}</b><small>{f.reason}</small></td><td><button className="secondary" onClick={()=>explain(f)} disabled={explaining}>Vaata tõendeid →</button></td></tr>)}</tbody></table></div>}

 </section>{selected&&<section className="detail" aria-live="polite"><div className="section-title"><h2>{selected.order_id} / {names[selected.code]}</h2><button className="secondary" onClick={()=>setSelected(null)}>Sulge</button></div><div className="evidence">{Object.entries(selected.evidence).map(([k,v])=><div key={k}><small>{k}</small><b>{v}</b></div>)}</div>{explaining?<p>Koostan selgitust…</p>:explanation&&<><span className="pill">{explanation.source==='local_ai'?'AI mustand':'Reeglipõhine selgitus'}</span><p>{explanation.explanation}</p><ul>{explanation.checks.map((c,i)=><li key={i}>{c}</li>)}</ul><small>{explanation.notice}</small></>}</section>}

 <section className="event-section"><div className="section-title"><h2>Integratsiooni sündmused</h2><span>{events?.receiver_configured?'Shopify vastuvõtja seadistatud':'Kohalik simulaator'}</span></div><p className="event-note">Sündmus salvestatakse enne töötlemist. Korduv teade ei tekita uut muudatust ja vana olek ei kirjuta uuemat üle.</p><div className="event-actions">{!events?.receiver_configured&&<button onClick={()=>eventAction('/integration-demo')} disabled={eventBusy}>Käivita sündmuste katse</button>}<button className="secondary" onClick={()=>eventAction('/events/process')} disabled={eventBusy}>Töötle ootel sündmused</button><button className="secondary" onClick={loadEvents}>Värskenda</button></div><div className="event-counts">{Object.entries(events?.counts??{}).map(([status,count])=><span className="pill" key={status}>{status}: {count}</span>)}</div>{events?.events.length>0?<div className="table-wrap"><table><thead><tr><th>Tellimus</th><th>Sündmus</th><th>Tulemus</th><th></th></tr></thead><tbody>{events.events.map(e=><tr key={e.event_id}><td className="order">{e.order_id||'—'}</td><td><b>{e.topic}</b><small>{e.source_updated_at}</small></td><td>{e.status}{e.error&&<small>{e.error}</small>}</td><td>{!['pending','failed'].includes(e.status)&&<button className="secondary" onClick={()=>showAudit(e.event_id)}>Enne / pärast</button>}</td></tr>)}</tbody></table></div>:<p className="empty">Sündmusi pole veel. Katse näitab makstud, hilinenud ja korduvat teadet.</p>}{audit&&<div className="audit"><h3>{audit.order_id} · {audit.outcome}</h3><div><article><h4>Enne</h4><pre>{JSON.stringify(audit.before,null,2)}</pre></article><article><h4>Pärast</h4><pre>{JSON.stringify(audit.after,null,2)}</pre></article></div></div>}</section>
 <footer>Tellimusi ega makseid ei muudeta. Aktiivsed piirid: saatmine {report?.policy?.paid_unfulfilled_hours??48} h, makse {report?.policy?.pending_payment_hours??24} h. Need pole poe kinnitatud teenindustähtajad. <span>Reeglistik {report?.rule_version??'1.1.0'}</span></footer></main>

}

createRoot(document.getElementById('root')).render(<App/>);

