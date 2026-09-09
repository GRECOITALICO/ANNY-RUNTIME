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

/* Device Flow (reserved for optional future auth method) */

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


def first_run_page(error=None, csrf_token=""):
    error_html = f'<div style="color:var(--accent-ruby); margin-bottom:16px; font-size:14px; padding:12px; background:rgba(235,87,87,0.1); border-radius:4px;">{error}</div>' if error else ''
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
        {error_html}
        <form method="POST" action="/github/token">
            <input type="hidden" name="csrf_token" value="{csrf_token}">
            <div style="margin-bottom: 24px; text-align: left;">
                <label for="github_token_input" style="display:block; margin-bottom:8px; color:var(--text-secondary); font-size:12px; font-weight:600; letter-spacing:1px;">GITHUB ACCESS TOKEN</label>
                <input type="password" name="github_token" id="github_token_input" style="width:100%; padding:12px; border:1px solid var(--border-color); border-radius:4px; background:var(--bg-secondary); color:var(--text-primary); font-family:var(--font-mono); font-size:14px;" required autocomplete="off" spellcheck="false">
            </div>
            <button type="submit" class="btn btn-primary login-btn">CONNECT</button>
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
        <p style="color:var(--text-primary);font-weight:600;margin-bottom:8px;">GitHub authorization expired</p>
        <p style="color:var(--text-secondary);margin-bottom:32px;">Please provide a new GitHub Access Token to reconnect.</p>
        <form method="POST" action="/github/token">
            <input type="hidden" name="csrf_token" value="{csrf_token}">
            <div style="margin-bottom: 24px; text-align: left;">
                <label for="github_token_input" style="display:block; margin-bottom:8px; color:var(--text-secondary); font-size:12px; font-weight:600; letter-spacing:1px;">GITHUB ACCESS TOKEN</label>
                <input type="password" name="github_token" id="github_token_input" style="width:100%; padding:12px; border:1px solid var(--border-color); border-radius:4px; background:var(--bg-secondary); color:var(--text-primary); font-family:var(--font-mono); font-size:14px;" required autocomplete="off" spellcheck="false">
            </div>
            <button type="submit" class="btn btn-primary login-btn">RECONNECT</button>
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
        <form method="POST" action="/github/token">
            <input type="hidden" name="csrf_token" value="{csrf_token}">
            <div style="margin-bottom: 24px; text-align: left;">
                <label for="github_token_input" style="display:block; margin-bottom:8px; color:var(--text-secondary); font-size:12px; font-weight:600; letter-spacing:1px;">GITHUB ACCESS TOKEN</label>
                <input type="password" name="github_token" id="github_token_input" style="width:100%; padding:12px; border:1px solid var(--border-color); border-radius:4px; background:var(--bg-secondary); color:var(--text-primary); font-family:var(--font-mono); font-size:14px;" required autocomplete="off" spellcheck="false">
            </div>
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
            <div class="detail-row"><span class="detail-label">GitHub</span><span class="detail-value">{gh.get('auth_status', 'CONNECTED')}</span></div>
            <div class="detail-row"><span class="detail-label">Principal</span><span class="detail-value">{gh.get('principal', '—')}</span></div>
            <div class="detail-row"><span class="detail-label">Organizations</span><span class="detail-value">{org_name}</span></div>
            <div class="detail-row"><span class="detail-label">Repositories</span><span class="detail-value">{repo_count} discovered</span></div>
            <div class="detail-row"><span class="detail-label">Operational State</span><span class="detail-value">{cont.get('canonical_source', 'CONNECTED')}</span></div>
            <div class="detail-row"><span class="detail-label">Current Mission</span><span class="detail-value" style="font-weight:600; color:var(--accent-emerald);">{mission}</span></div>
            <div class="detail-row"><span class="detail-label">Fabric</span><span class="detail-value" style="color:var(--text-muted);">NOT CONFIGURED</span></div>
        </div>

        <div class="card" style="text-align:center; padding:32px 24px;">
            <h2 style="color:var(--accent-emerald);margin-bottom:16px;font-weight:700;letter-spacing:1px;font-size:24px;">ANNY: INITIALIZING</h2>
            <p style="font-size:13px; color:var(--text-secondary); max-width:500px; margin:0 auto 24px;">ANNY Runtime Customer Zero bootstrap complete. Node is listening and ready for authorized mission work.</p>
            <form method="POST" action="/github/disconnect">
                <input type="hidden" name="csrf_token" value="{csrf_token}">
                <button type="submit" class="btn btn-ghost">Disconnect GitHub</button>
            </form>
        </div>
    """, "/", csrf_token)



def github_page(gh_status, error=None, csrf_token=""):
    """Render the GitHub status page."""
    badge_class = 'badge-success' if gh_status.get('connected') else 'badge-danger'
    status_text = gh_status.get('auth_status', 'UNKNOWN')
    scopes = ', '.join(gh_status.get('scopes', [])) or '—'

    error_html = f'<div style="color:var(--accent-ruby); margin-bottom:16px; font-size:14px; padding:12px; background:rgba(235,87,87,0.1); border-radius:4px; border: 1px solid rgba(235,87,87,0.3);">{error}</div>' if error else ''

    input_form_html = ""
    if not gh_status.get('connected'):
        input_form_html = f"""
        <div class="detail-panel" style="margin-bottom: 24px;">
            <h3 style="margin-top:0; margin-bottom:16px; font-size:14px; color:var(--text-primary);">Connect GitHub</h3>
            {error_html}
            <form method="POST" action="/github/token">
                <input type="hidden" name="csrf_token" value="{csrf_token}">
                <div style="margin-bottom: 16px;">
                    <label for="github_token_input" style="display:block; margin-bottom:8px; color:var(--text-secondary); font-size:12px; font-weight:600; letter-spacing:1px;">GITHUB ACCESS TOKEN</label>
                    <input type="password" name="github_token" id="github_token_input" style="width:100%; max-width:400px; padding:10px; border:1px solid var(--border-color); border-radius:4px; background:var(--bg-secondary); color:var(--text-primary); font-family:var(--font-mono); font-size:14px;" required autocomplete="off" spellcheck="false">
                </div>
                <button type="submit" class="btn btn-primary">Connect</button>
            </form>
        </div>
        """

    return base_layout("GitHub", f"""
        <div class="page-header">
            <h2>GitHub Connection</h2>
            <p>Manage the GitHub authorization for this ANNY Runtime instance.</p>
        </div>

        {input_form_html}

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


def executions_page(executions, csrf_token=""):
    """Render the executions control plane page."""
    rows = ""
    for e in executions:
        badge_cls = 'badge-muted'
        if e.status.value == 'SUCCEEDED': badge_cls = 'badge-success'
        elif e.status.value in ('FAILED', 'LIMIT_EXCEEDED', 'TIMED_OUT'): badge_cls = 'badge-danger'
        elif e.status.value == 'RUNNING': badge_cls = 'badge-info'
        
        rows += f"""<tr>
            <td class="mono">{e.execution_id[:16]}...</td>
            <td class="mono">{e.task_id[:16]}...</td>
            <td>{e.capability_id}</td>
            <td><span class="badge {badge_cls}">{e.status.value}</span></td>
            <td>{e.started_at.isoformat()[:19] if e.started_at else '—'}</td>
            <td>{e.completed_at.isoformat()[:19] if e.completed_at else '—'}</td>
            <td>{e.duration_ms if e.duration_ms is not None else '—'}</td>
        </tr>"""
    if not rows:
        rows = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:32px;">No executions</td></tr>'

    return base_layout("Executions", f"""
        <div class="page-header">
            <h2>Workspace Executions</h2>
            <p>Control Plane view of ephemeral workspace tasks and their states.</p>
        </div>
        <div class="detail-panel">
            <table class="data-table">
                <thead><tr><th>Execution ID</th><th>Task ID</th><th>Capability</th><th>Status</th><th>Started</th><th>Completed</th><th>Duration (ms)</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    """, "/executions", csrf_token)


def capabilities_page(capabilities, csrf_token=""):
    rows = ""
    for c in capabilities:
        badge_cls = 'badge-success' if c.enabled else 'badge-danger'
        inf_badge = 'badge-warning' if c.inference_required else 'badge-muted'
        rows += f"""<tr>
            <td class="mono">{c.capability_id}</td>
            <td>{c.name}</td>
            <td><span class="badge {inf_badge}">{"Yes" if c.inference_required else "No"}</span></td>
            <td>{c.preferred_executor.value if c.preferred_executor else '—'}</td>
            <td><span class="badge {badge_cls}">{"ENABLED" if c.enabled else "DISABLED"}</span></td>
            <td>{c.risk_level}</td>
        </tr>"""
    if not rows:
        rows = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:32px;">No capabilities registered</td></tr>'

    return base_layout("Capabilities", f"""
        <div class="page-header">
            <h2>Capability Registry</h2>
            <p>Formal definitions of operations authorized in this runtime.</p>
        </div>
        <div class="detail-panel">
            <table class="data-table">
                <thead><tr><th>ID</th><th>Name</th><th>Inference Req</th><th>Pref. Executor</th><th>Status</th><th>Risk</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    """, "/capabilities", csrf_token)


def executors_page(executors, csrf_token=""):
    return base_layout("Executors", f"""
        <div class="page-header">
            <h2>Execution Engines</h2>
            <p>Available executors and bound LLM models.</p>
        </div>
        <div class="detail-panel">
            <table class="data-table">
                <thead><tr><th>Executor ID</th><th>Type</th><th>Model Binding</th><th>Status</th></tr></thead>
                <tbody>
                    <tr>
                        <td class="mono">deterministic-v1</td>
                        <td>DETERMINISTIC</td>
                        <td><span class="badge badge-muted">NONE</span></td>
                        <td><span class="badge badge-success">READY</span></td>
                    </tr>
                </tbody>
            </table>
        </div>
    """, "/executors", csrf_token)


def policies_page(policy, csrf_token=""):
    allow_llm = policy.allow_llm if policy else False
    isolation = policy.enforce_strict_isolation if policy else True
    return base_layout("Policies", f"""
        <div class="page-header">
            <h2>Runtime Execution Policies</h2>
            <p>Rules governing execution contexts and executor selection.</p>
        </div>
        <div class="detail-panel">
            <div class="detail-row"><span class="detail-label">LLM Executors Allowed</span><span class="badge {'badge-success' if allow_llm else 'badge-danger'}">{'YES' if allow_llm else 'NO'}</span></div>
            <div class="detail-row"><span class="detail-label">Strict Isolation Enforced</span><span class="badge {'badge-success' if isolation else 'badge-danger'}">{'YES' if isolation else 'NO'}</span></div>
            <div class="detail-row"><span class="detail-label">Active Policy Version</span><span class="detail-value">{policy.version if policy else 'UNKNOWN'}</span></div>
        </div>
    """, "/policies", csrf_token)


def workers_page(workers, csrf_token=""):
    rows = ""
    for w in workers:
        state_badge = 'badge-success' if w.state.value == 'SUCCEEDED' else 'badge-danger' if w.state.value in ('FAILED', 'TIMED_OUT', 'LIMIT_EXCEEDED') else 'badge-warning'
        rows += f"""<tr>
            <td class="mono"><a href="/workers/{w.worker_id}">{w.worker_id}</a></td>
            <td class="mono">{w.execution_id}</td>
            <td class="mono">{w.capability_id}</td>
            <td>{w.executor_type}</td>
            <td><span class="badge {state_badge}">{w.state.value}</span></td>
            <td>{w.created_at.isoformat()}</td>
        </tr>"""
    if not rows:
        rows = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:32px;">No active workers</td></tr>'

    return base_layout("Workers", f"""
        <div class="page-header">
            <h2>Ephemeral Workers</h2>
            <p>Execution units running capabilities.</p>
        </div>
        <div class="detail-panel">
            <table class="data-table">
                <thead><tr><th>Worker ID</th><th>Execution ID</th><th>Capability</th><th>Executor</th><th>State</th><th>Created</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    """, "/workers", csrf_token)

def worker_detail_page(w, csrf_token=""):
    state_badge = 'badge-success' if w.state.value == 'SUCCEEDED' else 'badge-danger' if w.state.value in ('FAILED', 'TIMED_OUT', 'LIMIT_EXCEEDED') else 'badge-warning'
    
    duration = "—"
    if w.started_at and w.finished_at:
        duration = f"{int((w.finished_at - w.started_at).total_seconds() * 1000)} ms"

    return base_layout(f"Worker {w.worker_id}", f"""
        <div class="page-header">
            <h2>Worker Detail: <span class="mono">{w.worker_id}</span></h2>
        </div>
        <div class="detail-panel">
            <div class="detail-row"><span class="detail-label">State</span><span class="badge {state_badge}">{w.state.value}</span></div>
            <div class="detail-row"><span class="detail-label">Execution ID</span><span class="mono">{w.execution_id}</span></div>
            <div class="detail-row"><span class="detail-label">Task ID</span><span class="mono">{w.task_id}</span></div>
            <div class="detail-row"><span class="detail-label">Capability</span><span class="mono">{w.capability_id}</span></div>
            <div class="detail-row"><span class="detail-label">Executor Type</span><span class="detail-value">{w.executor_type}</span></div>
            <div class="detail-row"><span class="detail-label">Executor ID</span><span class="detail-value">{w.executor_id}</span></div>
            <div class="detail-row"><span class="detail-label">Model ID</span><span class="detail-value">{w.model_id or '—'}</span></div>
            <div class="detail-row"><span class="detail-label">Created At</span><span class="detail-value">{w.created_at.isoformat()}</span></div>
            <div class="detail-row"><span class="detail-label">Started At</span><span class="detail-value">{w.started_at.isoformat() if w.started_at else '—'}</span></div>
            <div class="detail-row"><span class="detail-label">Finished At</span><span class="detail-value">{w.finished_at.isoformat() if w.finished_at else '—'}</span></div>
            <div class="detail-row"><span class="detail-label">Duration</span><span class="detail-value">{duration}</span></div>
            <div class="detail-row"><span class="detail-label">Workspace ID</span><span class="mono">{w.workspace_id}</span></div>
            <div class="detail-row"><span class="detail-label">Network Policy</span><span class="detail-value">{w.network_policy}</span></div>
            <div class="detail-row"><span class="detail-label">Filesystem Policy</span><span class="detail-value">{w.filesystem_policy}</span></div>
            <div class="detail-row"><span class="detail-label">Resource Limits</span><span class="detail-value">{w.resource_limits}</span></div>
        </div>
    """, "/workers", csrf_token)


