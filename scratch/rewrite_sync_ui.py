import os

with open("/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME/runtime/admin/sync_ui.py", "r") as f:
    code = f.read()

# Replace actions block
old_actions = """  <div class="anny-sync-actions">
    <button id="anny-sync-refresh" onclick="annySyncPoll()">REFRESH SYNC STATUS</button>
  </div>"""

new_actions = """  <div class="anny-sync-actions">
    <button id="anny-sync-refresh" onclick="annySyncPoll()">REFRESH SYNC STATUS</button>
    <button id="anny-sync-stage-btn" onclick="annySyncStage()" disabled>STAGE</button>
    <button id="anny-sync-activate-btn" onclick="annySyncActivate()" disabled>ACTIVATE</button>
    <button id="anny-sync-rollback-btn" onclick="annySyncRollback()" disabled>ROLLBACK</button>
  </div>"""

code = code.replace(old_actions, new_actions)

# Update render function
old_render = """    const btn=document.getElementById('anny-sync-btn');if(btn)btn.disabled=(state==='SYNCING');"""
new_render = """    const btn=document.getElementById('anny-sync-btn');if(btn)btn.disabled=(state==='SYNCING' || state==='STAGING' || state==='ACTIVATING' || state==='ROLLING_BACK');
    const stageBtn = document.getElementById('anny-sync-stage-btn');
    if(stageBtn) stageBtn.disabled = (state !== 'VERIFIED');
    const activateBtn = document.getElementById('anny-sync-activate-btn');
    if(activateBtn) activateBtn.disabled = (state !== 'STAGED');
    const rollbackBtn = document.getElementById('anny-sync-rollback-btn');
    if(rollbackBtn) rollbackBtn.disabled = (!d.activation_performed || state==='ROLLING_BACK');"""

code = code.replace(old_render, new_render)

# Add stage/activate/rollback JS functions
old_sync_now = """  window.annySyncNow=function(){
    const btn=document.getElementById('anny-sync-btn');if(btn)btn.disabled=true;
    const body=new URLSearchParams();body.set('csrf_token',ANNY_SYNC_CSRF);
    fetch('/api/sync',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/x-www-form-urlencoded'},body})
      .then(r=>r.json()).then(d=>{
        text('anny-sync-trace',d.trace_id||'—');
        const msg=document.getElementById('anny-sync-message');if(msg)msg.textContent='SYNC requested; reading durable result…';
        annySyncPoll();
      })
      .catch(()=>render({sync_state:'FAILED',error_classification:'SYNC_REQUEST_FAILED'}))
      .finally(()=>setTimeout(annySyncPoll,250));
  };"""

new_js_funcs = old_sync_now + """
  window.annySyncStage=function(){
    const body=new URLSearchParams();body.set('csrf_token',ANNY_SYNC_CSRF);
    fetch('/api/sync/stage',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/x-www-form-urlencoded'},body})
      .then(r=>r.json()).then(d=>{
        const msg=document.getElementById('anny-sync-message');if(msg)msg.textContent='STAGE requested...';
        annySyncPoll();
      }).finally(()=>setTimeout(annySyncPoll,250));
  };
  window.annySyncActivate=function(){
    const body=new URLSearchParams();body.set('csrf_token',ANNY_SYNC_CSRF);
    fetch('/api/sync/activate',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/x-www-form-urlencoded'},body})
      .then(r=>r.json()).then(d=>{
        const msg=document.getElementById('anny-sync-message');if(msg)msg.textContent='ACTIVATE requested...';
        annySyncPoll();
      }).finally(()=>setTimeout(annySyncPoll,250));
  };
  window.annySyncRollback=function(){
    const body=new URLSearchParams();body.set('csrf_token',ANNY_SYNC_CSRF);
    fetch('/api/sync/rollback',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/x-www-form-urlencoded'},body})
      .then(r=>r.json()).then(d=>{
        const msg=document.getElementById('anny-sync-message');if(msg)msg.textContent='ROLLBACK requested...';
        annySyncPoll();
      }).finally(()=>setTimeout(annySyncPoll,250));
  };"""

code = code.replace(old_sync_now, new_js_funcs)

with open("/home/anny/.gemini/antigravity/scratch/ANNY-RUNTIME/runtime/admin/sync_ui.py", "w") as f:
    f.write(code)

print("Updated sync_ui.py successfully.")
