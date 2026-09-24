"""First-level Control Center SYNC controls.

The UI is deliberately injected around the existing Control Center so the SYNC
surface remains first-class without coupling its rendering to bootstrap HTML.
"""

from __future__ import annotations

import html
import json


def inject_sync_controls(page: str, csrf_token: str) -> str:
    """Add the first-level governed SYNC control to the Control Center page."""
    token = json.dumps(csrf_token or "")
    css = """
<style id="anny-sync-ui-css">
#anny-sync-header-btn, #anny-sync-panel-btn{background:linear-gradient(135deg,#7c3aed,#9333ea);color:#fff;border:none;padding:.45rem 1.1rem;border-radius:6px;font-weight:700;font-size:.85rem;cursor:pointer}
#anny-sync-header-btn:disabled, #anny-sync-panel-btn:disabled{opacity:.45;cursor:not-allowed}
#anny-sync-panel{grid-column:1/-1;border:1px solid #4c1d95;background:linear-gradient(180deg,rgba(76,29,149,.18),rgba(17,24,39,.95));border-radius:10px;padding:1rem 1.25rem;box-shadow:0 4px 12px rgba(0,0,0,.18)}
#anny-sync-grid{display:grid;grid-template-columns:repeat(6,minmax(120px,1fr));gap:.8rem}
.anny-sync-k{display:flex;flex-direction:column}.anny-sync-k small{font-size:.62rem;color:#9ca3af;text-transform:uppercase}.anny-sync-k strong{font-family:'JetBrains Mono',monospace;font-size:.78rem;margin-top:.2rem;overflow-wrap:anywhere}
#anny-sync-message{margin-top:.7rem;color:#c4b5fd;font-size:.72rem}.anny-sync-actions{display:flex;gap:.5rem;margin-top:.8rem;flex-wrap:wrap}.anny-sync-actions button{background:#1f2937;color:#fff;border:1px solid #374151;padding:.35rem .7rem;border-radius:5px;font-size:.72rem;cursor:pointer}.anny-sync-actions button:disabled{opacity:.4;cursor:not-allowed}
@media(max-width:900px){#anny-sync-grid{grid-template-columns:repeat(2,minmax(120px,1fr))}}
</style>
"""
    panel = """
<div id="anny-sync-panel" data-projection-id="distribution.sync">
  <div style="display:flex;justify-content:space-between;align-items:center;gap:.75rem;flex-wrap:wrap">
    <div>
      <div style="font-size:.75rem;text-transform:uppercase;letter-spacing:.08em;color:#c4b5fd;font-weight:700">Governed SYNC</div>
      <div style="font-size:.68rem;color:#9ca3af;margin-top:.15rem">SYNC is separate from VERIFY, STAGE and ACTIVATE.</div>
    </div>
    <button id="anny-sync-panel-btn" onclick="annySyncNow()">⟳ SYNC NOW</button>
  </div>
  <div id="anny-sync-grid" style="margin-top:.9rem">
    <div class="anny-sync-k"><small>State</small><strong id="anny-sync-state">UNKNOWN</strong></div>
    <div class="anny-sync-k"><small>Stage</small><strong id="anny-sync-stage">NONE</strong></div>
    <div class="anny-sync-k"><small>Local version</small><strong id="anny-sync-local">UNKNOWN</strong></div>
    <div class="anny-sync-k"><small>Candidate</small><strong id="anny-sync-candidate">—</strong></div>
    <div class="anny-sync-k"><small>Trace</small><strong id="anny-sync-trace">—</strong></div>
    <div class="anny-sync-k"><small>Activation</small><strong id="anny-sync-activation">FALSE</strong></div>
  </div>
  <div class="anny-sync-actions">
    <button id="anny-sync-refresh" onclick="annySyncPoll()">REFRESH SYNC STATUS</button>
    <button id="anny-sync-stage-btn" onclick="annySyncStage()" disabled title="Blocked until physical staging is implemented and verified">STAGE</button>
    <button id="anny-sync-activate-btn" onclick="annySyncActivate()" disabled title="Blocked until activation is physically implemented and authorized">ACTIVATE</button>
    <button id="anny-sync-rollback-btn" onclick="annySyncRollback()" disabled title="Blocked until physical activation/rollback is implemented and verified">ROLLBACK</button>
  </div>
  <div id="anny-sync-message">SYNC status has not been read yet.</div>
</div>
"""
    js = f"""
<script id="anny-sync-ui-js">
(function(){{
  const ANNY_SYNC_CSRF = {token};
  const stateColors = {{VERIFIED:'#10b981',SYNCING:'#8b5cf6',BLOCKED:'#ef4444',FAILED:'#ef4444',UNKNOWN:'#9ca3af',IDLE:'#9ca3af'}};
  function text(id, value){{const el=document.getElementById(id);if(el)el.textContent=(value===null||value===undefined||value==='')?'—':String(value);}}
  function render(d){{
    const state=String(d.sync_state||'UNKNOWN').toUpperCase();
    text('anny-sync-state', state);
    text('anny-sync-stage', d.stage||'NONE');
    text('anny-sync-local', d.local_version||'UNKNOWN');
    text('anny-sync-candidate', d.candidate_version||'—');
    text('anny-sync-trace', d.trace_id||'—');
    text('anny-sync-activation', d.activation_performed ? 'TRUE' : 'FALSE');
    const stateEl=document.getElementById('anny-sync-state');if(stateEl)stateEl.style.color=stateColors[state]||'#9ca3af';
    [document.getElementById('anny-sync-header-btn'), document.getElementById('anny-sync-panel-btn')].forEach(function(btn){{if(btn)btn.disabled=(state==='SYNCING' || state==='STAGING' || state==='ACTIVATING' || state==='ROLLING_BACK');}});
    // The backend lifecycle is not physically implemented. Keep all mutating
    // lifecycle controls blocked even when a candidate reaches VERIFIED/STAGED.
    const stageBtn = document.getElementById('anny-sync-stage-btn');
    if(stageBtn) stageBtn.disabled = true;
    const activateBtn = document.getElementById('anny-sync-activate-btn');
    if(activateBtn) activateBtn.disabled = true;
    const rollbackBtn = document.getElementById('anny-sync-rollback-btn');
    if(rollbackBtn) rollbackBtn.disabled = true;
    const msg=document.getElementById('anny-sync-message');
    if(msg){{
      const err=d.error_classification?(' — '+d.error_classification):'';
      msg.textContent='SYNC '+state+' / stage '+String(d.stage||'NONE')+err;
    }}
  }}
  window.annySyncPoll=function(){{
    fetch('/api/sync/status',{{credentials:'same-origin',cache:'no-store'}})
      .then(r=>r.json()).then(render).catch(()=>render({{sync_state:'UNKNOWN',error_classification:'STATUS_UNAVAILABLE'}}));
  }};
  window.annySyncNow=function(){{
    [document.getElementById('anny-sync-header-btn'), document.getElementById('anny-sync-panel-btn')].forEach(function(btn){{if(btn)btn.disabled=true;}});
    const body=new URLSearchParams();body.set('csrf_token',ANNY_SYNC_CSRF);
    fetch('/api/sync',{{method:'POST',credentials:'same-origin',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body}})
      .then(r=>r.json()).then(d=>{{
        text('anny-sync-trace',d.trace_id||'—');
        const msg=document.getElementById('anny-sync-message');if(msg)msg.textContent='SYNC requested; reading durable result…';
        annySyncPoll();
      }})
      .catch(()=>render({{sync_state:'FAILED',error_classification:'SYNC_REQUEST_FAILED'}}))
      .finally(()=>setTimeout(annySyncPoll,250));
  }};
  window.addEventListener('load',function(){{annySyncPoll();setInterval(annySyncPoll,3000);}});
}})();
</script>
"""

    injected_header = '<button id="anny-sync-header-btn" onclick="annySyncNow()">⟳ SYNC NOW</button>'
    if 'id="anny-sync-header-btn"' not in page:
        page = page.replace('</div>\n</header>', f'</div>{injected_header}\n</header>', 1)
    if 'id="anny-sync-panel"' not in page:
        if '<main>\n' in page:
            page = page.replace('<main>\n', '<main>\n' + panel + '\n', 1)
        elif '<main>' in page:
            page = page.replace('<main>', '<main>\n' + panel + '\n', 1)
    if 'id="anny-sync-ui-css"' not in page:
        page = page.replace('</head>', css + '\n</head>', 1)
    if 'id="anny-sync-ui-js"' not in page:
        page = page.replace('</body>', js + '\n</body>', 1)
    return page
