def control_center_page(csrf_token: str) -> str:
    """Renders the ANNY Control Center dashboard page."""
    _html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ANNY CONTROL CENTER</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --panel-bg: #111827;
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --accent: #3b82f6;
            --accent-hover: #2563eb;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --border: #1f2937;
            --verifying: #8b5cf6;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0; padding: 0;
            background-color: var(--bg-color);
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
            display: flex; flex-direction: column; min-height: 100vh;
        }
        header {
            background-color: var(--panel-bg);
            border-bottom: 1px solid var(--border);
            padding: 1rem 2rem;
            display: flex; justify-content: space-between; align-items: center;
            position: sticky; top: 0; z-index: 100;
            box-shadow: 0 4px 12px rgba(0,0,0,.3);
        }
        .header-left h1 {
            font-size: 1.3rem; font-weight: 700; letter-spacing: .08em; margin: 0;
            background: linear-gradient(90deg, #60a5fa, #a78bfa);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .header-left .sub { font-size: .75rem; color: var(--text-secondary); margin-top: .2rem; }
        .header-actions { display: flex; align-items: center; gap: 1rem; }
        #last-verified { font-size: .75rem; color: var(--text-secondary); }
        #verify-btn {
            background: linear-gradient(135deg, #3b82f6, #6366f1);
            color: #fff; border: none; padding: .45rem 1.1rem;
            border-radius: 6px; font-weight: 600; font-size: .85rem;
            cursor: pointer; transition: opacity .2s;
        }
        #verify-btn:hover { opacity: .85; }
        #verify-btn:disabled { opacity: .4; cursor: not-allowed; }
        main {
            padding: 1.5rem;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
            gap: 1.25rem;
        }
        .panel {
            background-color: var(--panel-bg);
            border: 1px solid var(--border);
            border-radius: 10px; padding: 1.25rem;
            box-shadow: 0 4px 6px rgba(0,0,0,.15);
        }
        .panel.full { grid-column: 1 / -1; }
        .panel h2 {
            font-size: .75rem; text-transform: uppercase; letter-spacing: .08em;
            color: var(--text-secondary); margin: 0 0 1rem;
            border-bottom: 1px solid var(--border); padding-bottom: .5rem;
        }
        .kv-grid {
            display: grid; grid-template-columns: 1fr 1fr; gap: .75rem;
        }
        .kv { display: flex; flex-direction: column; }
        .kv .lbl { font-size: .65rem; color: var(--text-secondary); text-transform: uppercase; margin-bottom: .2rem; }
        .kv .val { font-family: 'JetBrains Mono', monospace; font-size: .85rem; font-weight: 600; }
        .badge {
            display: inline-block; padding: .15rem .45rem; border-radius: 4px;
            font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
        }
        .pass, .ready, .ok, .connected, .admitted, .coherent, .authorized { background: rgba(16,185,129,.15); color: #10b981; }
        .fail, .blocked, .error { background: rgba(239,68,68,.15); color: #ef4444; }
        .verifying, .starting { background: rgba(139,92,246,.15); color: #8b5cf6; }
        .stale, .pending, .not_configured, .unavailable, .unauthorized { background: rgba(245,158,11,.15); color: #f59e0b; }
        .unknown { background: rgba(156,163,175,.12); color: #9ca3af; }
        table { width: 100%; border-collapse: collapse; font-size: .82rem; }
        th, td { padding: .45rem .5rem; text-align: left; border-bottom: 1px solid var(--border); }
        th { color: var(--text-secondary); font-weight: 600; text-transform: uppercase; font-size: .68rem; }
        .mono { font-family: 'JetBrains Mono', monospace; }
        .dot { width:8px; height:8px; border-radius:50%; background:var(--border); display:inline-block; }
        .dot.on { background:#10b981; }
        .dot.off { background:#1f2937; }
        .pulse { animation: pulse 2s infinite; }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }
        @media(max-width:640px){ main{grid-template-columns:1fr} }
    </style>
</head>
<body>
<header>
    <div class="header-left">
        <h1>⬡ ANNY CONTROL CENTER</h1>
        <div class="sub">
            State: <span id="rt-state-badge" class="badge unknown pulse">LOADING</span>
            &nbsp;|&nbsp; Ready: <span id="rt-ready-badge" class="badge unknown">--</span>
        </div>
    </div>
    <div class="header-actions">
        <span id="last-verified">LAST POLLED: —</span>
        <button id="verify-btn" onclick="triggerVerify()">⟳ VERIFY NOW</button>
    </div>
</header>
<main>

<!-- Top-Level State -->
<div class="panel" data-projection-id="control.top_level_state">
    <h2>Top-Level State</h2>
    <div class="kv-grid">
        <div class="kv"><span class="lbl">ANNY STATUS</span><span class="val" id="st-anny">--</span></div>
        <div class="kv"><span class="lbl">RUNTIME HEALTH</span><span class="val" id="st-health">--</span></div>
        <div class="kv"><span class="lbl">GITHUB STATUS</span><span class="val" id="st-github">--</span></div>
        <div class="kv"><span class="lbl">FABRIC STATUS</span><span class="val" id="st-fabric">--</span></div>
        <div class="kv"><span class="lbl">ADMISSION STATUS</span><span class="val" id="st-admission">--</span></div>
        <div class="kv"><span class="lbl">RECONCILIATION</span><span class="val" id="st-recon">--</span></div>
    </div>
</div>

<!-- Operational Snapshot -->
<div class="panel" data-projection-id="control.operational_snapshot">
    <h2>Operational Snapshot</h2>
    <div class="kv-grid">
        <div class="kv"><span class="lbl">RUNTIME ID</span><span class="val mono" id="snap-id">--</span></div>
        <div class="kv"><span class="lbl">VERSION</span><span class="val mono" id="snap-ver">--</span></div>
        <div class="kv"><span class="lbl">FABRIC ORG</span><span class="val mono" id="snap-fab-org">--</span></div>
        <div class="kv"><span class="lbl">FABRIC REPO</span><span class="val mono" id="snap-fab-repo">--</span></div>
        <div class="kv"><span class="lbl">FABRIC NODE</span><span class="val mono" id="snap-fab-node">--</span></div>
        <div class="kv"><span class="lbl">TENANT</span><span class="val mono" id="snap-tenant">--</span></div>
        <div class="kv"><span class="lbl">POLICY REV</span><span class="val mono" id="snap-pol-rev">--</span></div>
        <div class="kv"><span class="lbl">CONTRACT REV</span><span class="val mono" id="snap-con-rev">--</span></div>
    </div>
</div>

<!-- Bootstrap Verification -->
<div class="panel full" data-projection-id="control.bootstrap_verification">
    <h2>Bootstrap Verification</h2>
    <div style="overflow-x:auto">
        <table>
            <thead><tr><th>Phase</th><th>Gate</th><th>Result</th><th>Detail</th><th>Evidence</th></tr></thead>
            <tbody id="gates-tbody"><tr><td colspan="5" style="color:var(--text-secondary)">Loading...</td></tr></tbody>
        </table>
    </div>
</div>

<!-- Runtime Health -->
<div class="panel" data-projection-id="control.runtime_health">
    <h2>Runtime Health</h2>
    <table><thead><tr><th>Subsystem</th><th>Status</th></tr></thead>
    <tbody id="health-tbody"></tbody></table>
</div>

<!-- Repository Fabric -->
<div class="panel" data-projection-id="control.repository_fabric">
    <h2>Repository Fabric</h2>
    <table><thead><tr><th>Component</th><th>Status</th></tr></thead>
    <tbody id="fabric-tbody"></tbody></table>
</div>

<!-- Access Verification -->
<div class="panel" data-projection-id="control.access_verification">
    <h2>Access Verification</h2>
    <table><thead><tr><th>Capability</th><th>Expected</th><th>Result</th></tr></thead>
    <tbody id="access-tbody"></tbody></table>
</div>

<!-- Current Contract -->
<div class="panel" data-projection-id="control.current_contract">
    <h2>Current Contract</h2>
    <div id="contract-div"></div>
</div>

<!-- Capability Inventory -->
<div class="panel full" data-projection-id="control.capability_inventory">
    <h2>Capability Inventory</h2>
    <div style="overflow-x:auto">
        <table>
            <thead><tr>
                <th>Capability ID</th>
                <th title="DECLARED">DEC</th><th title="CONFIGURED">CFG</th>
                <th title="ENABLED">ENA</th><th title="AUTHORIZED">AUT</th>
                <th title="AVAILABLE">AVL</th><th title="FUNCTIONAL">FNC</th>
                <th title="TESTED">TST</th><th title="VERIFIED">VRF</th>
            </tr></thead>
            <tbody id="cap-tbody"></tbody>
        </table>
    </div>
</div>

<!-- Tools -->
<div class="panel" data-projection-id="control.tools">
    <h2>Tools</h2>
    <table><thead><tr><th>Tool</th><th>Status</th></tr></thead>
    <tbody id="tools-tbody"></tbody></table>
</div>

<!-- Models -->
<div class="panel" data-projection-id="control.models">
    <h2>Models</h2>
    <table><thead><tr><th>Model</th><th>Status</th></tr></thead>
    <tbody id="models-tbody"></tbody></table>
</div>

<!-- Workers -->
<div class="panel" data-projection-id="control.workers">
    <h2>Workers</h2>
    <table><thead><tr><th>Worker Profile</th><th>Status</th></tr></thead>
    <tbody id="workers-tbody"></tbody></table>
</div>

<!-- Connectors -->
<div class="panel" data-projection-id="control.connectors">
    <h2>Connectors</h2>
    <table><thead><tr><th>Connector</th><th>Status</th></tr></thead>
    <tbody id="connectors-tbody"></tbody></table>
</div>

<!-- Processing Matrix -->
<div class="panel full" data-projection-id="control.processing_matrix">
    <h2>Processing Matrix</h2>
    <div style="overflow-x:auto">
        <table>
            <thead><tr>
                <th>Department</th>
                <th title="Total Tasks">Total</th>
                <th title="Deterministic Plane">DET</th>
                <th title="Local Model Plane">LOC</th>
                <th title="Frontier Model Plane">FRN</th>
                <th title="Unknown Plane">UNK</th>
                <th title="Succeeded">SUC</th>
                <th title="Failed">FAL</th>
                <th title="Timed Out">TMO</th>
                <th title="Blocked">BLK</th>
                <th title="Average Duration (ms)">Avg(ms)</th>
            </tr></thead>
            <tbody id="matrix-tbody"><tr><td colspan="11" style="color:var(--text-secondary)">Loading...</td></tr></tbody>
        </table>
    </div>
</div>

<!-- Projection Registry -->
<div class="panel full">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:.75rem;flex-wrap:wrap">
        <div>
            <h2 style="margin-bottom:.35rem">Projection Registry</h2>
            <div id="projection-registry-meta" style="font-size:.7rem;color:var(--text-secondary)">
                Loading registry...
            </div>
        </div>
        <label style="font-size:.7rem;color:var(--text-secondary)">
            PRIORITY
            <select id="projection-priority-filter" style="margin-left:.35rem;background:#111827;color:#f3f4f6;border:1px solid var(--border);border-radius:5px;padding:.3rem .45rem">
                <option value="">ALL</option>
                <option value="P0">P0</option>
                <option value="P1">P1</option>
                <option value="P2">P2</option>
                <option value="P3">P3</option>
            </select>
        </label>
    </div>
    <div style="overflow-x:auto;margin-top:.9rem">
        <table>
            <thead><tr>
                <th>ID</th><th>Title</th><th>Section</th><th>Priority</th>
                <th>Implementation</th><th>Truth</th><th>Freshness</th><th>Source</th>
            </tr></thead>
            <tbody id="projection-registry-tbody">
                <tr><td colspan="8" style="color:var(--text-secondary)">Loading...</td></tr>
            </tbody>
        </table>
    </div>
</div>

<!-- Continuity -->
<div class="panel full" data-projection-id="control.continuity">
    <h2>Continuity</h2>
    <div class="kv-grid">
        <div class="kv"><span class="lbl">CURRENT MISSION</span><span class="val mono" id="cont-mission">--</span></div>
        <div class="kv"><span class="lbl">CURRENT TASK</span><span class="val mono" id="cont-task">--</span></div>
        <div class="kv"><span class="lbl">CURRENT STEP</span><span class="val mono" id="cont-step">--</span></div>
        <div class="kv"><span class="lbl">NEXT ACTION</span><span class="val mono" id="cont-action">--</span></div>
        <div class="kv"><span class="lbl">BLOCKERS</span><span class="val mono" id="cont-blockers">--</span></div>
        <div class="kv"><span class="lbl">STATUS</span><span class="val" id="cont-status">--</span></div>
    </div>
</div>

</main>
<script>
const CSRF_TOKEN = "__CSRF__";

function badge(text) {
    if (!text) return '<span class="badge unknown">UNKNOWN</span>';
    const u = String(text).toUpperCase().split(' ').join('_');
    const cls = (['PASS','READY','OK','CONNECTED','ADMITTED','COHERENT','AUTHORIZED'].includes(u) ? 'pass' :
                 ['FAIL','BLOCKED','ERROR','DENIED'].includes(u) ? 'fail' :
                 ['VERIFYING','STARTING'].includes(u) ? 'verifying' :
                 ['STALE','PENDING','NOT_CONFIGURED','UNAVAILABLE','UNAUTHORIZED'].includes(u) ? 'stale' : 'unknown');
    return '<span class="badge ' + cls + '">' + u + '</span>';
}

function dot(v) { return '<span class="dot ' + (v ? 'on' : 'off') + '"></span>'; }

function setInner(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
}
function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text || '--';
}

function populateTable(tbodyId, arr, cols) {
    if (!arr || !arr.length) {
        setInner(tbodyId, '<tr><td colspan="' + cols + '" style="color:var(--text-secondary)">None</td></tr>');
        return;
    }
    setInner(tbodyId, arr.map(function(i) {
        return '<tr><td class="mono">' + (i.name || i.id || '--') + '</td><td>' + badge(i.status) + '</td></tr>';
    }).join(''));
}

function updateUI(d) {
    // Header badges
    const stateBadge = document.getElementById('rt-state-badge');
    if (stateBadge) {
        stateBadge.innerHTML = (d.runtime_state || 'UNKNOWN');
        stateBadge.className = 'badge ' + (d.runtime_state || 'unknown').toLowerCase().replace(/_/g,'-');
        const isActive = ['STARTING','VERIFYING'].includes((d.runtime_state||'').toUpperCase());
        if (isActive) stateBadge.classList.add('pulse'); else stateBadge.classList.remove('pulse');
    }
    setInner('rt-ready-badge', badge(d.anny_ready ? 'PASS' : (d.runtime_state === 'STARTING' ? 'VERIFYING' : 'BLOCKED')));

    // Top-level state
    setInner('st-anny', badge(d.anny_ready ? 'READY' : 'BLOCKED'));
    setInner('st-health', badge(d.runtime_health));
    setInner('st-github', badge(d.github_status));
    setInner('st-fabric', badge(d.fabric_status));
    setInner('st-admission', badge(d.admission_status));
    setInner('st-recon', badge(d.reconciliation_status));

    // Timestamp
    if (d.timestamp) setText('last-verified', 'LAST POLLED: ' + d.timestamp);

    // Snapshot
    setText('snap-id', d.runtime_id);
    setText('snap-ver', d.runtime_version);
    setText('snap-fab-org', d.fabric_org);
    setText('snap-fab-repo', d.fabric_repo);
    setText('snap-fab-node', d.fabric_node);
    setText('snap-tenant', d.tenant);
    setText('snap-pol-rev', d.policy_revision);
    setText('snap-con-rev', d.contract_revision);

    // Gates
    if (d.gates && d.gates.length) {
        setInner('gates-tbody', d.gates.map(function(g) {
            return '<tr><td>' + (g.phase||'') + '</td><td class="mono">' + (g.gate||'') + '</td><td>' +
                   badge(g.status) + '</td><td>' + (g.detail||'') + '</td><td class="mono" style="font-size:.7rem">' +
                   (g.evidence||'') + '</td></tr>';
        }).join(''));
    } else if (d.runtime_state === 'STARTING') {
        setInner('gates-tbody', '<tr><td colspan="5" style="color:var(--verifying)">Bootstrap running...</td></tr>');
    }

    // Health
    if (d.health && Object.keys(d.health).length) {
        setInner('health-tbody', Object.entries(d.health).map(function(kv) {
            return '<tr><td class="mono">' + kv[0] + '</td><td>' + badge(kv[1]) + '</td></tr>';
        }).join(''));
    }

    // Fabric details
    if (d.fabric_details && Object.keys(d.fabric_details).length) {
        setInner('fabric-tbody', Object.entries(d.fabric_details).map(function(kv) {
            return '<tr><td class="mono">' + kv[0] + '</td><td>' + badge(kv[1]) + '</td></tr>';
        }).join(''));
    } else {
        setInner('fabric-tbody', '<tr><td class="mono">fabric</td><td>' + badge(d.fabric_status) + '</td></tr>');
    }

    // Access
    if (d.access && d.access.length) {
        setInner('access-tbody', d.access.map(function(a) {
            return '<tr><td class="mono">' + a.capability + '</td><td class="mono">' + a.expected + '</td><td>' + badge(a.result) + '</td></tr>';
        }).join(''));
    } else {
        setInner('access-tbody', '<tr><td colspan="3" style="color:var(--text-secondary)">None</td></tr>');
    }

    // Contract
    if (d.contract) {
        setInner('contract-div',
            '<div style="margin-bottom:.4rem"><strong>ALLOWED:</strong> <span class="mono">' + (d.contract.allowed||'NONE') + '</span></div>' +
            '<div style="margin-bottom:.4rem"><strong>DENIED:</strong> <span class="mono">' + (d.contract.denied||'NONE') + '</span></div>' +
            '<div style="margin-bottom:.4rem"><strong>NETWORK:</strong> <span class="mono">' + (d.contract.network||'UNKNOWN') + '</span></div>' +
            '<div><strong>WORKER LIMITS:</strong> <span class="mono">' + (d.contract.worker_limits||'UNKNOWN') + '</span></div>'
        );
    }

    // Capabilities
    if (d.capabilities && d.capabilities.length) {
        setInner('cap-tbody', d.capabilities.map(function(c) {
            var s = c.states || {};
            return '<tr><td class="mono">' + c.id + '</td>' +
                   ['DECLARED','CONFIGURED','ENABLED','AUTHORIZED','AVAILABLE','FUNCTIONAL','TESTED','VERIFIED'].map(function(k) {
                       return '<td>' + dot(s[k]) + '</td>';
                   }).join('') + '</tr>';
        }).join(''));
    } else {
        setInner('cap-tbody', '<tr><td colspan="9" style="color:var(--text-secondary)">No capabilities declared</td></tr>');
    }

    // Inventories
    populateTable('tools-tbody', d.tools, 2);
    populateTable('models-tbody', d.models, 2);
    populateTable('workers-tbody', d.workers, 2);
    populateTable('connectors-tbody', d.connectors, 2);

    // Continuity
    if (d.continuity) {
        setText('cont-mission', d.continuity.mission);
        setText('cont-task', d.continuity.task);
        setText('cont-step', d.continuity.step);
        setText('cont-action', d.continuity.action);
        setText('cont-blockers', d.continuity.blockers);
        setInner('cont-status', badge(d.continuity.status));
    }
}

async function fetchStatus() {
    try {
        const r = await fetch('/api/status');
        if (!r.ok) return;
        const d = await r.json();
        updateUI(d);
        const now = new Date().toISOString().replace('T',' ').substring(0,19);
        setText('last-verified', 'LAST POLLED: ' + now + ' UTC');
    } catch(e) {
        console.error('Status fetch failed:', e);
    }
}

async function fetchProcessingMatrix() {
    try {
        const r = await fetch('/api/processing/matrix');
        if (!r.ok) return;
        const d = await r.json();
        
        let html = '';
        if (d.global) {
            html += '<tr><td class="mono" style="font-weight:bold">ALL</td>' +
                   '<td>' + (d.global.total||0) + '</td>' +
                   '<td>' + (d.global.deterministic||0) + '</td>' +
                   '<td>' + (d.global.local_model||0) + '</td>' +
                   '<td>' + (d.global.frontier_model||0) + '</td>' +
                   '<td>' + (d.global.unknown||0) + '</td>' +
                   '<td>' + (d.global.success||0) + '</td>' +
                   '<td>' + (d.global.failed||0) + '</td>' +
                   '<td>' + (d.global.timeout||0) + '</td>' +
                   '<td>' + (d.global.blocked||0) + '</td>' +
                   '<td>' + Math.round(d.global.average_duration||0) + '</td></tr>';
        }
        if (d.departments && Object.keys(d.departments).length > 0) {
            for (const [dept, stats] of Object.entries(d.departments)) {
                html += '<tr><td class="mono">' + (dept||'UNKNOWN') + '</td>' +
                       '<td>' + (stats.total||0) + '</td>' +
                       '<td>' + (stats.deterministic||0) + '</td>' +
                       '<td>' + (stats.local_model||0) + '</td>' +
                       '<td>' + (stats.frontier_model||0) + '</td>' +
                       '<td>' + (stats.unknown||0) + '</td>' +
                       '<td>' + (stats.success||0) + '</td>' +
                       '<td>' + (stats.failed||0) + '</td>' +
                       '<td>' + (stats.timeout||0) + '</td>' +
                       '<td>' + (stats.blocked||0) + '</td>' +
                       '<td>' + Math.round(stats.average_duration||0) + '</td></tr>';
            }
        }
        if (!html) {
            html = '<tr><td colspan="11" style="color:var(--text-secondary)">No telemetry data</td></tr>';
        }
        setInner('matrix-tbody', html);
    } catch(e) {
        console.error('Matrix fetch failed:', e);
    }
}

async function triggerVerify() {
    const btn = document.getElementById('verify-btn');
    btn.disabled = true; btn.textContent = '⟳ VERIFYING...';
    try {
        await fetch('/api/bootstrap/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: 'csrf_token=' + encodeURIComponent(CSRF_TOKEN)
        });
        setTimeout(fetchStatus, 500);
    } catch(e) { console.error(e); }
    finally { btn.disabled = false; btn.textContent = '⟳ VERIFY NOW'; }
}

async function fetchProjectionRegistry() {
    try {
        const filter = document.getElementById('projection-priority-filter');
        const priority = filter ? filter.value : '';
        const url = priority
            ? '/api/control-center/projections?priority=' + encodeURIComponent(priority)
            : '/api/control-center/projections';
        const r = await fetch(url);
        if (!r.ok) return;
        const d = await r.json();

        const meta = document.getElementById('projection-registry-meta');
        if (meta) {
            const s = d.summary || {};
            const byPriority = s.by_priority || {};
            meta.textContent =
                'MASTER=' + (d.master_inventory_boundary || 'UNKNOWN') +
                ' · P0 VIEWPORT TARGET=' + String(d.initial_p0_viewport_target || '—') +
                ' · REGISTERED=' + String(s.total_definitions || 0) +
                ' · P0=' + String(byPriority.P0 || 0) +
                ' · P1=' + String(byPriority.P1 || 0) +
                ' · P2=' + String(byPriority.P2 || 0) +
                ' · P3=' + String(byPriority.P3 || 0) +
                ' · INVENTORY LIMIT=' + String(d.inventory_limit);
        }

        const tbody = document.getElementById('projection-registry-tbody');
        if (!tbody) return;
        while (tbody.firstChild) tbody.removeChild(tbody.firstChild);

        const projections = Array.isArray(d.projections) ? d.projections : [];
        if (!projections.length) {
            const row = document.createElement('tr');
            const cell = document.createElement('td');
            cell.colSpan = 8;
            cell.textContent = 'No projections registered for this filter.';
            cell.style.color = 'var(--text-secondary)';
            row.appendChild(cell);
            tbody.appendChild(row);
            return;
        }

        for (const item of projections) {
            const row = document.createElement('tr');
            const cells = [
                item.projection_id, item.title, item.section, item.priority,
                item.implementation_status, item.truth_class, item.freshness,
                item.source_authority
            ];
            for (const value of cells) {
                const cell = document.createElement('td');
                cell.className = 'mono';
                cell.textContent = value === null || value === undefined || value === ''
                    ? '—'
                    : String(value);
                row.appendChild(cell);
            }
            tbody.appendChild(row);
        }
    } catch(e) {
        console.error('Projection registry fetch failed:', e);
    }
}

fetchStatus();
fetchProcessingMatrix();
fetchProjectionRegistry();
setInterval(function() {
    fetchStatus();
    fetchProcessingMatrix();
    fetchProjectionRegistry();
}, 2000);

const projectionFilter = document.getElementById('projection-priority-filter');
if (projectionFilter) {
    projectionFilter.addEventListener('change', fetchProjectionRegistry);
}
</script>
</body>
</html>"""
    return _html.replace("__CSRF__", csrf_token)
