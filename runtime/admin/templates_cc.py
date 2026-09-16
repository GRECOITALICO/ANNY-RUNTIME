def control_center_page(csrf_token: str) -> str:
    """Evidence-first ANNY Runtime control center.

    The page intentionally derives trust indicators from the bootstrap gate report
    rather than from optimistic client-side assumptions. Runtime state remains the
    process state; readiness, continuity, admission and Repository Fabric status
    are shown only from their corresponding gates.
    """
    html = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ANNY Runtime — Trust Center</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg:#080b12; --panel:#0f141d; --panel2:#121a25; --line:#253041;
  --text:#edf2f7; --muted:#8b98aa; --dim:#627084;
  --good:#31c48d; --warn:#e6b84a; --bad:#f06a6a; --info:#73a7ff;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,sans-serif;min-height:100vh}
header{position:sticky;top:0;z-index:10;background:rgba(8,11,18,.97);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:16px 22px;display:flex;justify-content:space-between;gap:18px;align-items:center}
.brand{display:flex;align-items:center;gap:12px}.mark{width:34px;height:34px;border:1px solid var(--line);display:grid;place-items:center;font-size:17px;background:var(--panel2)}
.brand h1{font-size:15px;letter-spacing:.1em;margin:0;font-weight:700}.brand p{margin:3px 0 0;color:var(--muted);font-size:11px}
.header-right{display:flex;align-items:center;gap:10px}.poll{font-size:11px;color:var(--muted)}
button{border:1px solid var(--line);background:var(--panel2);color:var(--text);padding:8px 12px;font-weight:600;font-size:12px;cursor:pointer}button:hover{border-color:#3c4d64}button:disabled{opacity:.5;cursor:wait}
main{max-width:1500px;margin:0 auto;padding:20px;display:grid;gap:14px}
.grid4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.panel{background:var(--panel);border:1px solid var(--line);padding:16px;min-width:0}.panel h2{font-size:11px;letter-spacing:.11em;text-transform:uppercase;margin:0 0 13px;color:var(--muted)}
.card{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;min-height:74px}.label{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}.value{font-family:'JetBrains Mono',monospace;font-size:14px;font-weight:600;margin-top:6px;word-break:break-word}
.badge{display:inline-flex;align-items:center;justify-content:center;border:1px solid var(--line);padding:4px 7px;font:600 10px 'JetBrains Mono',monospace;letter-spacing:.04em}.badge.good{color:var(--good);border-color:rgba(49,196,141,.35);background:rgba(49,196,141,.08)}.badge.warn{color:var(--warn);border-color:rgba(230,184,74,.35);background:rgba(230,184,74,.07)}.badge.bad{color:var(--bad);border-color:rgba(240,106,106,.35);background:rgba(240,106,106,.07)}.badge.info{color:var(--info);border-color:rgba(115,167,255,.35);background:rgba(115,167,255,.07)}.badge.unknown{color:var(--muted)}
.trust{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}.trust-item{background:var(--panel2);border:1px solid var(--line);padding:12px}.trust-item .t{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em}.trust-item .s{margin-top:8px}
.kv{display:grid;grid-template-columns:160px 1fr;gap:10px 16px;font-size:12px}.kv .k{color:var(--muted)}.mono{font-family:'JetBrains Mono',monospace}
.table-wrap{overflow:auto;border:1px solid var(--line)}table{width:100%;border-collapse:collapse;font-size:11px}th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600;font-size:10px;text-transform:uppercase;letter-spacing:.07em;white-space:nowrap}td{color:#dfe6ee}tr:last-child td{border-bottom:none}
.reason{color:var(--muted);font-size:11px;line-height:1.45}.empty{color:var(--dim);padding:10px 0;font-size:12px}.okline{display:flex;align-items:center;gap:8px}.dot{width:8px;height:8px;border-radius:50%;background:var(--dim);display:inline-block}.dot.good{background:var(--good)}.dot.warn{background:var(--warn)}.dot.bad{background:var(--bad)}
.notice{padding:11px 12px;border:1px solid var(--line);background:var(--panel2);font-size:11px;line-height:1.5;color:var(--muted)}
.gate-pass{color:var(--good)}.gate-fail{color:var(--bad)}.gate-block{color:var(--warn)}
@media(max-width:1100px){.grid4,.trust{grid-template-columns:repeat(2,minmax(0,1fr))}.grid2{grid-template-columns:1fr}}
@media(max-width:650px){header{padding:13px 14px}.header-right{flex-direction:column;align-items:flex-end}.grid4,.trust{grid-template-columns:1fr}main{padding:12px}.kv{grid-template-columns:1fr;gap:3px}.panel{padding:13px}}
</style>
</head>
<body>
<header>
  <div class="brand"><div class="mark">⬡</div><div><h1>ANNY RUNTIME · TRUST CENTER</h1><p>Live runtime state, deterministic bootstrap evidence, operational continuity and Repository Fabric binding.</p></div></div>
  <div class="header-right"><span id="poll" class="poll">LIVE CHECK: —</span><button id="verify" onclick="verifyNow()">VERIFY NOW</button></div>
</header>
<main>
  <div id="notice" class="notice">Waiting for the runtime status endpoint.</div>

  <section class="grid4">
    <div class="panel card"><div><div class="label">Runtime process</div><div id="runtime-state" class="value">UNKNOWN</div></div><div id="runtime-badge"></div></div>
    <div class="panel card"><div><div class="label">Bootstrap verdict</div><div id="ready-value" class="value">UNKNOWN</div></div><div id="ready-badge"></div></div>
    <div class="panel card"><div><div class="label">Continuity gate</div><div id="continuity-value" class="value">UNKNOWN</div></div><div id="continuity-badge"></div></div>
    <div class="panel card"><div><div class="label">Repository Fabric</div><div id="fabric-value" class="value">UNKNOWN</div></div><div id="fabric-badge"></div></div>
  </section>

  <section class="panel">
    <h2>Trust basis</h2>
    <div class="trust" id="trust-grid"></div>
  </section>

  <section class="grid2">
    <div class="panel">
      <h2>Runtime identity & binding</h2>
      <div class="kv">
        <div class="k">Runtime ID</div><div id="runtime-id" class="mono">—</div>
        <div class="k">Runtime version</div><div id="runtime-version" class="mono">—</div>
        <div class="k">GitHub</div><div id="github" class="mono">—</div>
        <div class="k">GitHub org</div><div id="github-org" class="mono">—</div>
        <div class="k">Fabric org</div><div id="fabric-org" class="mono">—</div>
        <div class="k">Fabric repo</div><div id="fabric-repo" class="mono">—</div>
        <div class="k">Fabric node</div><div id="fabric-node" class="mono">—</div>
      </div>
    </div>
    <div class="panel">
      <h2>Operational continuity</h2>
      <div class="kv">
        <div class="k">Status</div><div id="cont-status">—</div>
        <div class="k">Current mission</div><div id="mission" class="mono">—</div>
        <div class="k">Current task</div><div id="task" class="mono">—</div>
        <div class="k">Current step</div><div id="step" class="mono">—</div>
        <div class="k">Next action</div><div id="action" class="mono">—</div>
        <div class="k">Blockers</div><div id="blockers" class="mono">—</div>
      </div>
      <div id="continuity-note" class="reason" style="margin-top:14px">Continuity context will be shown only when the runtime exposes it.</div>
    </div>
  </section>

  <section class="panel">
    <h2>Repository Fabric evidence</h2>
    <div class="table-wrap"><table><thead><tr><th>Gate</th><th>Result</th><th>Evidence</th><th>Detail</th></tr></thead><tbody id="fabric-gates"></tbody></table></div>
  </section>

  <section class="panel">
    <h2>Deterministic bootstrap gates</h2>
    <div class="table-wrap"><table><thead><tr><th>#</th><th>Gate</th><th>Result</th><th>Evidence</th><th>Detail</th></tr></thead><tbody id="gates"></tbody></table></div>
  </section>

  <section class="grid2">
    <div class="panel">
      <h2>Runtime health</h2>
      <div id="health"></div>
    </div>
    <div class="panel">
      <h2>Inventory visibility</h2>
      <div id="inventory"></div>
    </div>
  </section>
</main>
<script>
const CSRF_TOKEN = "__CSRF__";
const FABRIC_GATE_NAMES = new Set([
  'FABRIC_REACHABLE','FABRIC_IDENTITY_VERIFIED','FABRIC_NODE_AT_REMOTE_HEAD',
  'FABRIC_TRUST_VERIFIED','FABRIC_TENANT_BOUND','FABRIC_STATE_READABLE','FABRIC_PROVENANCE_VALID',
  'RUNTIME_BINDING_VERIFIED','RUNTIME_ADMITTED'
]);
const TRUST_NAMES = [
  ['Runtime reachable','RUNTIME_REACHABLE'],
  ['Runtime health','RUNTIME_HEALTH_VERIFIED'],
  ['GitHub connected','GITHUB_CONNECTED'],
  ['Fabric reachable','FABRIC_REACHABLE'],
  ['Fabric node @ remote HEAD','FABRIC_NODE_AT_REMOTE_HEAD'],
  ['Fabric trust','FABRIC_TRUST_VERIFIED'],
  ['Fabric tenant','FABRIC_TENANT_BOUND'],
  ['Runtime binding','RUNTIME_BINDING_VERIFIED'],
  ['Runtime admitted','RUNTIME_ADMITTED'],
  ['Continuity coherent','CONTINUITY_COHERENT']
];
function safe(v){ return v === null || v === undefined || v === '' ? '—' : String(v); }
function escapeHtml(v){ return safe(v).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
function cls(status){
  const s=String(status||'UNKNOWN').toUpperCase();
  if(['PASS','READY','CONNECTED','ADMITTED','COHERENT','OK','AUTHORIZED'].includes(s)) return 'good';
  if(['FAIL','BLOCKED','ERROR','DENIED','UNAUTHORIZED'].includes(s)) return 'bad';
  if(['VERIFYING','STARTING','PENDING','STALE','NOT_CONFIGURED','UNAVAILABLE'].includes(s)) return 'warn';
  return 'unknown';
}
function badge(status){ return '<span class="badge '+cls(status)+'">'+escapeHtml(status||'UNKNOWN')+'</span>'; }
function gateMap(gates){ const m={}; (gates||[]).forEach(g=>{ const n=safe(g.gate); m[n]=g; }); return m; }
function gateState(g){ return g ? (g.status || (g.passed ? 'PASS':'FAIL')) : 'UNVERIFIED'; }
function set(id, html){ const el=document.getElementById(id); if(el) el.innerHTML=html; }
function text(id, val){ const el=document.getElementById(id); if(el) el.textContent=safe(val); }
function renderTrust(map){
  set('trust-grid', TRUST_NAMES.map(([label,name])=>{
    const g=map[name]; const s=gateState(g); const c=cls(s);
    return '<div class="trust-item"><div class="t">'+label+'</div><div class="s okline"><span class="dot '+c+'"></span>'+badge(s)+'</div></div>';
  }).join(''));
}
function renderGates(gates){
  if(!gates || !gates.length){ set('gates','<tr><td colspan="5" class="empty">No bootstrap report is currently exposed.</td></tr>'); return; }
  set('gates', gates.map((g,i)=>'<tr><td class="mono">'+(i+1)+'</td><td class="mono">'+escapeHtml(g.gate)+'</td><td>'+badge(g.status)+'</td><td class="mono">'+escapeHtml(g.evidence)+'</td><td>'+escapeHtml(g.detail)+'</td></tr>').join(''));
}
function renderFabricGates(gates){
  const rows=(gates||[]).filter(g=>FABRIC_GATE_NAMES.has(String(g.gate)));
  if(!rows.length){ set('fabric-gates','<tr><td colspan="4" class="empty">Fabric evidence unavailable.</td></tr>'); return; }
  set('fabric-gates', rows.map(g=>'<tr><td class="mono">'+escapeHtml(g.gate)+'</td><td>'+badge(g.status)+'</td><td class="mono">'+escapeHtml(g.evidence)+'</td><td>'+escapeHtml(g.detail)+'</td></tr>').join(''));
}
function renderHealth(d,map){
  const rows=[
    ['Process state',safe(d.runtime_state)],
    ['Runtime reachable',gateState(map.RUNTIME_REACHABLE)],
    ['Runtime health gate',gateState(map.RUNTIME_HEALTH_VERIFIED)],
    ['Runtime binding',gateState(map.RUNTIME_BINDING_VERIFIED)],
    ['Generation', d.health && d.health.generation !== undefined ? d.health.generation : 'not exposed']
  ];
  set('health', rows.map(r=>'<div class="okline" style="justify-content:space-between;border-bottom:1px solid var(--line);padding:8px 0"><span class="label">'+escapeHtml(r[0])+'</span><span class="mono">'+escapeHtml(r[1])+'</span></div>').join(''));
}
function renderInventory(d){
  const names=['capabilities','tools','models','workers','connectors'];
  set('inventory', names.map(n=>{
    const arr=d[n]||[]; return '<div class="okline" style="justify-content:space-between;border-bottom:1px solid var(--line);padding:8px 0"><span class="label">'+n+'</span><span class="mono">'+arr.length+'</span></div>';
  }).join(''));
}
function update(d, c){
  const gates=d.gates||[]; const map=gateMap(gates);
  const continuity=gateState(map.CONTINUITY_COHERENT); const fabric=gateState(map.FABRIC_REACHABLE); const ready=d.anny_ready ? 'READY':'BLOCKED';
  text('runtime-state', d.runtime_state); set('runtime-badge',badge(d.runtime_state));
  text('ready-value',ready); set('ready-badge',badge(ready));
  text('continuity-value',continuity); set('continuity-badge',badge(continuity));
  text('fabric-value',fabric); set('fabric-badge',badge(fabric));
  text('runtime-id',d.runtime_id); text('runtime-version',d.runtime_version); text('github',d.github_status); text('github-org',d.github_org);
  text('fabric-org',d.fabric_org); text('fabric-repo',d.fabric_repo); text('fabric-node',d.fabric_node);
  renderTrust(map); renderGates(gates); renderFabricGates(gates); renderHealth(d,map); renderInventory(d);
  const cont=d.continuity||{};
  set('cont-status', badge(cont.status || continuity)); text('mission',cont.mission); text('task',cont.task); text('step',cont.step); text('action',cont.action); text('blockers',cont.blockers);
  const contKnown=[cont.mission,cont.task,cont.step,cont.action].some(Boolean);
  text('continuity-note', contKnown ? 'Context is exposed by the current runtime status projection.' : 'The current status projection does not expose a canonical mission/task record. Continuity trust is therefore shown from the deterministic CONTINUITY_COHERENT gate, not inferred from UI state.');
  const failed=gates.filter(g=>String(g.status).toUpperCase()!=='PASS');
  if(d.anny_ready) {
    set('notice','ANNY reports READY because the mandatory bootstrap gates passed. Keep this distinction: process state, bootstrap readiness, continuity coherence and Fabric connectivity are separate proofs.');
  } else if(failed.length) {
    const names=failed.slice(0,4).map(g=>escapeHtml(g.gate)).join(', '); const more=failed.length>4?' …':'';
    set('notice','ANNY is BLOCKED. The control center is showing the actual failed/unverified gates instead of converting them into a generic degraded state: '+names+more);
  } else {
    set('notice','Runtime is up, but the bootstrap report has not yet provided enough evidence to establish readiness.');
  }
}
async function fetchStatus(){
  try{
    const r=await fetch('/api/status',{cache:'no-store'}); if(!r.ok) throw new Error('HTTP '+r.status);
    const d=await r.json(); update(d, gateMap(d.gates||[]));
    text('poll','LIVE CHECK: '+new Date().toISOString().replace('T',' ').replace('Z',' UTC'));
  }catch(e){
    set('notice','CONTROL PLANE UNREACHABLE: '+escapeHtml(e.message)+'. The UI does not mark the runtime healthy when it cannot poll the status endpoint.');
    text('runtime-state','UNREACHABLE'); set('runtime-badge',badge('UNAVAILABLE'));
    text('ready-value','UNVERIFIED'); set('ready-badge',badge('UNVERIFIED'));
    text('continuity-value','UNVERIFIED'); set('continuity-badge',badge('UNVERIFIED'));
    text('fabric-value','UNVERIFIED'); set('fabric-badge',badge('UNVERIFIED'));
  }
}
async function verifyNow(){
  const b=document.getElementById('verify'); b.disabled=true; b.textContent='VERIFYING…';
  try{
    await fetch('/api/bootstrap/verify',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'csrf_token='+encodeURIComponent(CSRF_TOKEN),cache:'no-store'});
  }catch(e){} finally{ setTimeout(()=>{ fetchStatus(); b.disabled=false; b.textContent='VERIFY NOW'; },450); }
}
fetchStatus(); setInterval(fetchStatus,2000);
</script>
</body>
</html>'''
    return html.replace("__CSRF__", csrf_token)
