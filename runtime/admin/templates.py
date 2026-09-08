"""Premium HTML templates for the ANNY Runtime admin panel.

Dark-mode, responsive, glassmorphism design. No external dependencies.
All CSS is embedded. No CDN, no framework, no external JS.
"""

COMMON_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
    --bg-primary: #0a0e17;
    --bg-secondary: #111827;
    --bg-card: rgba(17, 24, 39, 0.7);
    --bg-glass: rgba(255, 255, 255, 0.03);
    --border-subtle: rgba(255, 255, 255, 0.06);
    --border-glow: rgba(99, 102, 241, 0.3);
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent-indigo: #818cf8;
    --accent-blue: #60a5fa;
    --accent-emerald: #34d399;
    --accent-amber: #fbbf24;
    --accent-rose: #fb7185;
    --accent-cyan: #22d3ee;
    --gradient-primary: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    --gradient-success: linear-gradient(135deg, #34d399 0%, #059669 100%);
    --gradient-danger: linear-gradient(135deg, #fb7185 0%, #e11d48 100%);
    --gradient-warning: linear-gradient(135deg, #fbbf24 0%, #d97706 100%);
    --shadow-glow: 0 0 30px rgba(99, 102, 241, 0.1);
    --shadow-card: 0 4px 24px rgba(0, 0, 0, 0.3);
    --radius: 12px;
    --radius-sm: 8px;
    --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    min-height: 100vh;
    line-height: 1.6;
}

.app-shell {
    display: flex;
    min-height: 100vh;
}

/* Sidebar Navigation */
.sidebar {
    width: 260px;
    background: var(--bg-secondary);
    border-right: 1px solid var(--border-subtle);
    padding: 24px 0;
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 100;
    display: flex;
    flex-direction: column;
    backdrop-filter: blur(20px);
}

.sidebar-brand {
    padding: 0 24px 24px;
    border-bottom: 1px solid var(--border-subtle);
    margin-bottom: 16px;
}

.sidebar-brand h1 {
    font-size: 18px;
    font-weight: 700;
    background: var(--gradient-primary);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: -0.5px;
}

.sidebar-brand .version {
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 4px;
    font-weight: 500;
}

.nav-section {
    padding: 8px 12px;
    margin-top: 8px;
}

.nav-section-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: var(--text-muted);
    padding: 0 12px;
    margin-bottom: 8px;
}

.nav-link {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 16px;
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    text-decoration: none;
    font-size: 13px;
    font-weight: 500;
    transition: var(--transition);
    margin: 2px 0;
}

.nav-link:hover {
    background: var(--bg-glass);
    color: var(--text-primary);
}

.nav-link.active {
    background: rgba(99, 102, 241, 0.12);
    color: var(--accent-indigo);
    border-left: 3px solid var(--accent-indigo);
}

.nav-icon { font-size: 16px; width: 20px; text-align: center; }

.sidebar-footer {
    margin-top: auto;
    padding: 16px 24px;
    border-top: 1px solid var(--border-subtle);
}

/* Main Content */
.main-content {
    margin-left: 260px;
    flex: 1;
    padding: 32px 40px;
    min-height: 100vh;
}

.page-header {
    margin-bottom: 32px;
}

.page-header h2 {
    font-size: 24px;
    font-weight: 700;
    letter-spacing: -0.5px;
    margin-bottom: 8px;
}

.page-header p {
    color: var(--text-secondary);
    font-size: 14px;
}

/* Cards */
.card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 20px;
    margin-bottom: 32px;
}

.card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius);
    padding: 24px;
    backdrop-filter: blur(10px);
    transition: var(--transition);
    box-shadow: var(--shadow-card);
}

.card:hover {
    border-color: var(--border-glow);
    box-shadow: var(--shadow-glow);
    transform: translateY(-2px);
}

.card-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-muted);
    margin-bottom: 8px;
}

.card-value {
    font-size: 28px;
    font-weight: 700;
    letter-spacing: -1px;
}

.card-sub {
    font-size: 12px;
    color: var(--text-secondary);
    margin-top: 4px;
}

/* Status Badges */
.badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 100px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.3px;
}

.badge-success { background: rgba(52, 211, 153, 0.15); color: var(--accent-emerald); }
.badge-warning { background: rgba(251, 191, 36, 0.15); color: var(--accent-amber); }
.badge-danger  { background: rgba(251, 113, 133, 0.15); color: var(--accent-rose); }
.badge-info    { background: rgba(96, 165, 250, 0.15); color: var(--accent-blue); }
.badge-muted   { background: rgba(148, 163, 184, 0.1); color: var(--text-muted); }

.badge::before {
    content: '';
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
}

/* Data Tables */
.data-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    margin-top: 16px;
}

.data-table thead th {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-muted);
    padding: 12px 16px;
    text-align: left;
    border-bottom: 1px solid var(--border-subtle);
    position: sticky;
    top: 0;
    background: var(--bg-secondary);
}

.data-table tbody td {
    padding: 14px 16px;
    font-size: 13px;
    border-bottom: 1px solid var(--border-subtle);
    color: var(--text-secondary);
}

.data-table tbody tr:hover td {
    background: var(--bg-glass);
    color: var(--text-primary);
}

.data-table .mono {
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px;
}

/* Detail Panels */
.detail-panel {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius);
    padding: 28px;
    margin-bottom: 24px;
    backdrop-filter: blur(10px);
}

.detail-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 0;
    border-bottom: 1px solid var(--border-subtle);
}

.detail-row:last-child { border-bottom: none; }

.detail-label {
    font-size: 13px;
    color: var(--text-muted);
    font-weight: 500;
}

.detail-value {
    font-size: 13px;
    color: var(--text-primary);
    font-weight: 500;
    font-family: 'JetBrains Mono', monospace;
}

/* Buttons */
.btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 10px 20px;
    border-radius: var(--radius-sm);
    font-size: 13px;
    font-weight: 600;
    border: none;
    cursor: pointer;
    transition: var(--transition);
    text-decoration: none;
    font-family: inherit;
}

.btn-primary {
    background: var(--gradient-primary);
    color: white;
    box-shadow: 0 2px 12px rgba(99, 102, 241, 0.3);
}
.btn-primary:hover { transform: translateY(-1px); box-shadow: 0 4px 20px rgba(99, 102, 241, 0.4); }

.btn-success {
    background: var(--gradient-success);
    color: white;
}

.btn-danger {
    background: var(--gradient-danger);
    color: white;
}

.btn-ghost {
    background: transparent;
    color: var(--text-secondary);
    border: 1px solid var(--border-subtle);
}
.btn-ghost:hover { border-color: var(--border-glow); color: var(--text-primary); }

.btn-group { display: flex; gap: 12px; margin-top: 20px; }

/* Login Page */
.login-container {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    background: var(--bg-primary);
}

.login-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: 16px;
    padding: 48px;
    width: 420px;
    backdrop-filter: blur(20px);
    box-shadow: var(--shadow-glow);
}

.login-card h1 {
    font-size: 24px;
    font-weight: 700;
    background: var(--gradient-primary);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 8px;
    text-align: center;
}

.login-card p {
    color: var(--text-muted);
    font-size: 14px;
    text-align: center;
    margin-bottom: 32px;
}

.input-group {
    margin-bottom: 20px;
}

.input-group label {
    display: block;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.input-group input {
    width: 100%;
    padding: 12px 16px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 14px;
    font-family: 'JetBrains Mono', monospace;
    transition: var(--transition);
    outline: none;
}

.input-group input:focus {
    border-color: var(--accent-indigo);
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}

.login-btn {
    width: 100%;
    padding: 14px;
    margin-top: 8px;
}

.error-msg {
    background: rgba(251, 113, 133, 0.1);
    color: var(--accent-rose);
    padding: 12px 16px;
    border-radius: var(--radius-sm);
    font-size: 13px;
    margin-bottom: 16px;
    border: 1px solid rgba(251, 113, 133, 0.2);
}

/* Device Flow */
.device-flow-panel {
    background: var(--bg-card);
    border: 1px solid var(--border-glow);
    border-radius: var(--radius);
    padding: 32px;
    text-align: center;
    margin: 24px 0;
}

.device-code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 32px;
    font-weight: 700;
    letter-spacing: 4px;
    color: var(--accent-indigo);
    margin: 16px 0;
    padding: 16px;
    background: rgba(99, 102, 241, 0.08);
    border-radius: var(--radius-sm);
    display: inline-block;
}

/* Animations */
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.animate-pulse { animation: pulse 2s ease-in-out infinite; }
.animate-fade-in { animation: fadeIn 0.4s ease-out; }

/* Responsive */
@media (max-width: 768px) {
    .sidebar { width: 60px; padding: 16px 0; }
    .sidebar-brand h1, .nav-link span, .nav-section-label, .sidebar-footer { display: none; }
    .nav-link { justify-content: center; padding: 12px; }
    .main-content { margin-left: 60px; padding: 20px; }
    .card-grid { grid-template-columns: 1fr; }
}
"""


def _nav_link(path, icon, label, active_path):
    active = ' active' if path == active_path else ''
    return f'<a href="{path}" class="nav-link{active}"><span class="nav-icon">{icon}</span><span>{label}</span></a>'


def base_layout(title, content, active_path="/", csrf_token=""):
    """Wrap content in the full admin shell layout."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>{title} — ANNY Runtime</title>
    <style>{COMMON_CSS}</style>
</head>
<body>
<div class="app-shell">
    <nav class="sidebar">
        <div class="sidebar-brand">
            <h1>ANNY Runtime</h1>
            <div class="version">Administration Panel</div>
        </div>
        <div class="nav-section">
            <div class="nav-section-label">Overview</div>
            {_nav_link('/', '⬡', 'Dashboard', active_path)}
        </div>
        <div class="nav-section">
            <div class="nav-section-label">Integrations</div>
            {_nav_link('/github', '⊙', 'GitHub', active_path)}
            {_nav_link('/fabric', '◈', 'Fabric', active_path)}
        </div>
        <div class="nav-section">
            <div class="nav-section-label">Runtime</div>
            {_nav_link('/sessions', '◉', 'Sessions', active_path)}
            {_nav_link('/operations', '▶', 'Operations', active_path)}
            {_nav_link('/receipts', '☰', 'Receipts', active_path)}
            {_nav_link('/doctor', '✚', 'Diagnostics', active_path)}
        </div>
        <div class="sidebar-footer">
            <form method="POST" action="/logout" style="display:inline;">
                <input type="hidden" name="csrf_token" value="{csrf_token}">
                <button type="submit" class="btn btn-ghost" style="width:100%;">⏻ Logout</button>
            </form>
        </div>
    </nav>
    <main class="main-content animate-fade-in">
        {content}
    </main>
</div>
</body>
</html>"""


def first_run_page(csrf_token=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>Setup — ANNY Runtime</title>
    <style>{COMMON_CSS}</style>
</head>
<body>
<div class="login-container">
    <div class="login-card animate-fade-in" style="text-align:center;">
        <h1>ANNY</h1>
        <p style="color:var(--text-primary);font-weight:600;margin-bottom:8px;">Runtime installed</p>
        <p style="color:var(--text-primary);font-weight:600;margin-bottom:24px;">Runtime active</p>
        <p style="color:var(--text-secondary);margin-bottom:32px;">Connect GitHub to begin.</p>
        <form method="POST" action="/github/connect">
            <input type="hidden" name="csrf_token" value="{csrf_token}">
            <button type="submit" class="btn btn-primary login-btn">CONNECT GITHUB</button>
        </form>
    </div>
</div>
</body>
</html>"""


def reconnect_page(csrf_token=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>Reconnect — ANNY Runtime</title>
    <style>{COMMON_CSS}</style>
</head>
<body>
<div class="login-container">
    <div class="login-card animate-fade-in" style="text-align:center;">
        <h1>ANNY</h1>
        <p style="color:var(--text-primary);font-weight:600;margin-bottom:32px;">GitHub authorization expired</p>
        <form method="POST" action="/github/connect">
            <input type="hidden" name="csrf_token" value="{csrf_token}">
            <button type="submit" class="btn btn-primary login-btn">RECONNECT GITHUB</button>
        </form>
    </div>
</div>
</body>
</html>"""


def failure_page(reason, csrf_token=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>Failure — ANNY Runtime</title>
    <style>{COMMON_CSS}</style>
</head>
<body>
<div class="login-container">
    <div class="login-card animate-fade-in" style="text-align:center;">
        <h1>ANNY</h1>
        <p style="color:var(--text-primary);font-weight:600;margin-bottom:16px;">GitHub connection failed.</p>
        <p style="color:var(--text-secondary);margin-bottom:32px;">Reason:<br>{reason}</p>
        <form method="POST" action="/github/connect">
            <input type="hidden" name="csrf_token" value="{csrf_token}">
            <button type="submit" class="btn btn-primary login-btn">RETRY</button>
        </form>
    </div>
</div>
</body>
</html>"""


def ready_page(status, csrf_token=""):
    cont = status.get('continuity', {}) if isinstance(status, dict) else {}
    gh = status.get('github', {}) if isinstance(status, dict) else {}
    runtime_st = status.get('runtime', {}) if isinstance(status, dict) else {}
    
    continuity_status = cont.get('status', 'UNKNOWN')
    badge_class = 'badge-success' if continuity_status in ('CONSISTENT', 'READY') else ('badge-warning' if continuity_status == 'DEGRADED' else 'badge-danger')
    
    mission = cont.get('current_mission', '—')
    task = cont.get('current_task', '—')
    next_action = cont.get('next_action', '—')
    blocker_count = cont.get('blocker_count', 0)
    
    orgs = cont.get('organizations', [])
    org_name = orgs[0].get('login') if orgs and isinstance(orgs[0], dict) else gh.get('principal', '—')
    
    repos = cont.get('repositories', [])
    repo_count = len(repos)
    
    l2_info = cont.get('l2_worker_summary') or {}
    l2_count = l2_info.get('count', 0) if isinstance(l2_info, dict) else 0

    identity = status.get('identity', {}) if isinstance(status, dict) else {}
    id_str = f"{identity.get('key_type', 'UNKNOWN')} / {identity.get('status', 'UNKNOWN')}"

    return base_layout("Dashboard", f"""
        <div class="page-header">
            <h2>ANNY Control Plane</h2>
            <p>Operational Dashboard & Continuity Status</p>
        </div>

        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px;">
            <div class="card" style="padding:20px;">
                <div style="font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">Continuity</div>
                <div style="font-size:22px; font-weight:700;"><span class="badge {badge_class}">{continuity_status}</span></div>
                <div style="font-size:12px; color:var(--text-secondary); margin-top:8px;">Source: {cont.get('canonical_source', '—')}</div>
            </div>
            <div class="card" style="padding:20px;">
                <div style="font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">Repository Fabric</div>
                <div style="font-size:20px; font-weight:700; color:var(--text-muted);"><span class="badge badge-muted">NOT CONFIGURED</span></div>
                <div style="font-size:12px; color:var(--text-muted); margin-top:8px;">Fabric endpoint unavailable</div>
            </div>
            <div class="card" style="padding:20px;">
                <div style="font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">GitHub Principal & Org</div>
                <div style="font-size:18px; font-weight:600; color:var(--accent-indigo);">{gh.get('principal', '—')} / {org_name}</div>
                <div style="font-size:12px; color:var(--text-secondary); margin-top:8px;">Repos Discovered: {repo_count}</div>
            </div>
            <div class="card" style="padding:20px;">
                <div style="font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">Blockers & Workers</div>
                <div style="font-size:18px; font-weight:600; color:var(--accent-amber);">Blockers: {blocker_count} | L2 Workers: {l2_count}</div>
                <div style="font-size:12px; color:var(--text-secondary); margin-top:8px;">Runtime: {cont.get('runtime_status', 'UNKNOWN')}</div>
            </div>
        </div>

        <div class="detail-panel" style="margin-bottom: 24px;">
            <h3 style="font-size:15px; margin-bottom:16px; color:var(--accent-indigo);">Canonical State Overview</h3>
            <div class="detail-row"><span class="detail-label">Runtime Identity</span><span class="detail-value">{id_str}</span></div>
            <div class="detail-row"><span class="detail-label">GitHub Connection</span><span class="detail-value">{gh.get('auth_status', 'CONNECTED')}</span></div>
            <div class="detail-row"><span class="detail-label">Operational State</span><span class="detail-value">{cont.get('canonical_source', 'CONNECTED')}</span></div>
            <div class="detail-row"><span class="detail-label">Current Mission</span><span class="detail-value" style="font-weight:600; color:var(--accent-emerald);">{mission}</span></div>
            <div class="detail-row"><span class="detail-label">Current Task</span><span class="detail-value">{task}</span></div>
            <div class="detail-row"><span class="detail-label">Next Action</span><span class="detail-value" style="color:var(--accent-cyan);">{next_action}</span></div>
            <div class="detail-row"><span class="detail-label">Repository Fabric</span><span class="detail-value" style="color:var(--text-muted);">NOT CONFIGURED</span></div>
        </div>

        <div class="card" style="text-align:center; padding:32px 24px;">
            <h2 style="color:var(--accent-emerald);margin-bottom:16px;font-weight:700;letter-spacing:1px;font-size:24px;">ANNY READY FOR WORK</h2>
            <p style="font-size:13px; color:var(--text-secondary); max-width:500px; margin:0 auto 24px;">ANNY Runtime Customer Zero bootstrap complete. Node is listening and ready for authorized mission work.</p>
            <form method="POST" action="/github/disconnect">
                <input type="hidden" name="csrf_token" value="{csrf_token}">
                <button type="submit" class="btn btn-ghost">Disconnect GitHub</button>
            </form>
        </div>
    """, "/", csrf_token)



def github_page(gh_status, csrf_token="", device_flow=None):
    """Render the GitHub status page."""
    badge_class = 'badge-success' if gh_status.get('connected') else 'badge-danger'
    status_text = gh_status.get('auth_status', 'UNKNOWN')
    scopes = ', '.join(gh_status.get('scopes', [])) or '—'

    device_flow_html = ""
    if device_flow:
        device_flow_html = f"""
        <div class="device-flow-panel">
            <p style="color:var(--text-secondary);margin-bottom:8px;">Enter this code at GitHub:</p>
            <div class="device-code">{device_flow.get('user_code', '')}</div>
            <p style="margin-top:12px;"><a href="{device_flow.get('verification_uri', '')}" target="_blank" class="btn btn-primary">Open GitHub →</a></p>
            <p style="color:var(--text-muted);font-size:12px;margin-top:12px;">Code expires in {device_flow.get('expires_in', '?')} seconds</p>
        </div>
        """

    return base_layout("GitHub", f"""
        <div class="page-header">
            <h2>GitHub Connection</h2>
            <p>Manage the GitHub authorization for this ANNY Runtime instance.</p>
        </div>

        {device_flow_html}

        <div class="detail-panel">
            <div class="detail-row"><span class="detail-label">Status</span><span class="badge {badge_class}">{status_text}</span></div>
            <div class="detail-row"><span class="detail-label">Principal</span><span class="detail-value">{gh_status.get('principal', '—')}</span></div>
            <div class="detail-row"><span class="detail-label">Token Status</span><span class="detail-value">{gh_status.get('token_status', '—')}</span></div>
            <div class="detail-row"><span class="detail-label">Token Expiry</span><span class="detail-value">{gh_status.get('token_expiry', '—')}</span></div>
            <div class="detail-row"><span class="detail-label">Scopes</span><span class="detail-value">{scopes}</span></div>
            <div class="detail-row"><span class="detail-label">Last Validation</span><span class="detail-value">{gh_status.get('last_validation', '—')}</span></div>
            <div class="detail-row"><span class="detail-label">Last Failure</span><span class="detail-value">{gh_status.get('last_failure', '—')}</span></div>
            <div class="detail-row"><span class="detail-label">Failure Reason</span><span class="detail-value">{gh_status.get('last_failure_reason', '—')}</span></div>
        </div>

        <div class="btn-group">
            <form method="POST" action="/github/connect"><input type="hidden" name="csrf_token" value="{csrf_token}"><button class="btn btn-primary" type="submit">⊙ Connect GitHub</button></form>
            <form method="POST" action="/github/validate"><input type="hidden" name="csrf_token" value="{csrf_token}"><button class="btn btn-ghost" type="submit">✓ Validate</button></form>
            <form method="POST" action="/github/disconnect"><input type="hidden" name="csrf_token" value="{csrf_token}"><button class="btn btn-danger" type="submit">✕ Disconnect</button></form>
        </div>
    """, "/github", csrf_token)


def fabric_page(fab_status, csrf_token=""):
    """Render the Fabric status page."""
    badge = 'badge-success' if fab_status.get('connected') else 'badge-muted'
    return base_layout("Fabric", f"""
        <div class="page-header">
            <h2>Repository Fabric</h2>
            <p>Durable state synchronization and tenant binding status.</p>
        </div>
        <div class="detail-panel">
            <div class="detail-row"><span class="detail-label">Connection</span><span class="badge {badge}">{'CONNECTED' if fab_status.get('connected') else 'DISCONNECTED'}</span></div>
            <div class="detail-row"><span class="detail-label">Tenant</span><span class="detail-value">{fab_status.get('tenant', '—')}</span></div>
            <div class="detail-row"><span class="detail-label">ANNY Instance</span><span class="detail-value">{fab_status.get('anny_instance', '—')}</span></div>
            <div class="detail-row"><span class="detail-label">Runtime Registration</span><span class="detail-value">{fab_status.get('runtime_registration', '—')}</span></div>
            <div class="detail-row"><span class="detail-label">Last Heartbeat</span><span class="detail-value">{fab_status.get('last_heartbeat', '—')}</span></div>
            <div class="detail-row"><span class="detail-label">Last Reconciliation</span><span class="detail-value">{fab_status.get('last_reconciliation', '—')}</span></div>
        </div>
    """, "/fabric", csrf_token)


def sessions_page(sessions, csrf_token=""):
    """Render the sessions list page."""
    rows = ""
    for s in sessions:
        badge = 'badge-success' if s.get('status') == 'ACTIVE' else 'badge-muted'
        rows += f"""<tr>
            <td class="mono">{s.get('session_id', '—')[:16]}...</td>
            <td>{s.get('provider', '—')}</td>
            <td>{s.get('principal', '—')}</td>
            <td>{s.get('tenant', '—')}</td>
            <td>{s.get('created_at', '—')[:19]}</td>
            <td>{s.get('expires_at', '—')[:19]}</td>
            <td><span class="badge {badge}">{s.get('status', '—')}</span></td>
        </tr>"""
    if not rows:
        rows = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:32px;">No active sessions</td></tr>'

    return base_layout("Sessions", f"""
        <div class="page-header">
            <h2>Sessions</h2>
            <p>Active ANNY sessions connected to this Runtime. No credentials shown.</p>
        </div>
        <div class="detail-panel">
            <table class="data-table">
                <thead><tr><th>Session ID</th><th>Provider</th><th>Principal</th><th>Tenant</th><th>Created</th><th>Expires</th><th>Status</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    """, "/sessions", csrf_token)


def operations_page(operations, csrf_token=""):
    """Render the operations list page."""
    rows = ""
    for op in operations:
        rows += f"""<tr>
            <td class="mono">{op.get('operation_id', '—')}</td>
            <td>{op.get('actor', '—')}</td>
            <td>{op.get('tenant', '—')}</td>
            <td class="mono">{op.get('workspace', '—')[:20]}</td>
            <td><span class="badge badge-info">{op.get('state', '—')}</span></td>
            <td>{op.get('started_at', '—')[:19]}</td>
            <td>{op.get('runtime_generation', '—')}</td>
        </tr>"""
    if not rows:
        rows = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:32px;">No operations</td></tr>'

    return base_layout("Operations", f"""
        <div class="page-header">
            <h2>Operations</h2>
            <p>Current and recent Runtime operations.</p>
        </div>
        <div class="detail-panel">
            <table class="data-table">
                <thead><tr><th>Operation</th><th>Actor</th><th>Tenant</th><th>Workspace</th><th>State</th><th>Started</th><th>Gen</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    """, "/operations", csrf_token)


def receipts_page(receipts, csrf_token=""):
    """Render the receipts list page."""
    rows = ""
    for r in receipts:
        badge = 'badge-success' if r.get('status') == 'SUCCESS' else 'badge-danger'
        rows += f"""<tr>
            <td class="mono">{r.get('receipt_id', '—')[:16]}</td>
            <td class="mono">{r.get('operation', '—')}</td>
            <td>{r.get('tool', '—')}</td>
            <td><span class="badge {badge}">{r.get('status', '—')}</span></td>
            <td>{r.get('timestamp', '—')[:19]}</td>
            <td>{r.get('duration_ms', '—')}ms</td>
        </tr>"""
    if not rows:
        rows = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:32px;">No receipts</td></tr>'

    return base_layout("Receipts", f"""
        <div class="page-header">
            <h2>Execution Receipts</h2>
            <p>Audit trail of all tool executions. No secrets included.</p>
        </div>
        <div class="detail-panel">
            <table class="data-table">
                <thead><tr><th>Receipt</th><th>Operation</th><th>Tool</th><th>Status</th><th>Timestamp</th><th>Duration</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    """, "/receipts", csrf_token)


def doctor_page(diagnostics, csrf_token=""):
    """Render the diagnostics page."""
    checks_html = ""
    for check in diagnostics.get('checks', []):
        badge = 'badge-success' if check.get('status') == 'OK' else 'badge-danger'
        checks_html += f"""
        <div class="detail-row">
            <span class="detail-label">{check.get('name', '—')}</span>
            <span class="badge {badge}">{check.get('status', '—')}</span>
        </div>"""
    if not checks_html:
        checks_html = '<div class="detail-row"><span class="detail-label">No diagnostics available</span><span class="badge badge-muted">—</span></div>'

    return base_layout("Diagnostics", f"""
        <div class="page-header">
            <h2>Runtime Diagnostics</h2>
            <p>Health checks and system verification — equivalent to <code>anny-runtime doctor</code>.</p>
        </div>
        <div class="detail-panel">{checks_html}</div>
        <div class="btn-group">
            <form method="POST" action="/admin/diagnostics"><input type="hidden" name="csrf_token" value="{csrf_token}"><button class="btn btn-primary" type="submit">✚ Run Diagnostics</button></form>
        </div>
    """, "/doctor", csrf_token)
