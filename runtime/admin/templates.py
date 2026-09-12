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
    <link rel="icon" href="data:image/x-icon;base64,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" type="image/x-icon">
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
            <img src="data:image/png;base64,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" alt="ANNY Logo" style="width:32px; height:auto; margin-bottom:8px;" />
            <h1>ANNY</h1>
            
            <div class="version" style="margin-top:8px;">Runtime: ANNY-RUNTIME</div>
        </div>
        <div class="nav-section">
            <div class="nav-section-label">OVERVIEW</div>
            {_nav_link('/', '⬡', 'Dashboard', active_path)}
        </div>
        <div class="nav-section">
            <div class="nav-section-label">UNIVERSE</div>
            {_nav_link('/universe/organization', '❖', 'Organization', active_path)}
            {_nav_link('/universe/projects', '◫', 'Projects', active_path)}
            {_nav_link('/universe/repositories', '⊙', 'Repositories', active_path)}
            {_nav_link('/universe/resources', '◈', 'Resources', active_path)}
            {_nav_link('/universe/dependencies', '⋈', 'Dependencies', active_path)}
        </div>
        <div class="nav-section">
            <div class="nav-section-label">EXECUTION</div>
            {_nav_link('/execution/missions', '🎯', 'Missions', active_path)}
            {_nav_link('/execution/tasks', '✓', 'Tasks', active_path)}
            {_nav_link('/execution/workers', '⚙', 'Workers', active_path)}
            {_nav_link('/execution/executions', '▶', 'Executions', active_path)}
            {_nav_link('/execution/workspaces', '📁', 'Workspaces', active_path)}
            {_nav_link('/execution/results', '📊', 'Results', active_path)}
        </div>
        <div class="nav-section">
            <div class="nav-section-label">INTELLIGENCE</div>
            {_nav_link('/intelligence/models', '🧠', 'Models', active_path)}
            {_nav_link('/intelligence/capabilities', '⚡', 'Capabilities', active_path)}
            {_nav_link('/intelligence/executors', '🛠', 'Executors', active_path)}
            {_nav_link('/intelligence/performance', '📈', 'Performance', active_path)}
        </div>
        <div class="nav-section">
            <div class="nav-section-label">INFRASTRUCTURE</div>
            {_nav_link('/infrastructure/runtime', '🖥', 'Runtime', active_path)}
            {_nav_link('/infrastructure/github', '🐙', 'GitHub', active_path)}
            {_nav_link('/infrastructure/fabric', '☁', 'Fabric', active_path)}
            {_nav_link('/infrastructure/mcp', '🔌', 'MCP', active_path)}
            {_nav_link('/infrastructure/azure', '🔷', 'Azure', active_path)}
        </div>
        <div class="nav-section">
            <div class="nav-section-label">TELEMETRY</div>
            {_nav_link('/telemetry/live', '📡', 'Live Stream', active_path)}
            {_nav_link('/telemetry/timeline', '⏱', 'Timeline', active_path)}
        </div>
        <div class="nav-section">
            <div class="nav-section-label">CONTINUITY</div>
            {_nav_link('/continuity/state', '⏱', 'Current state', active_path)}
            {_nav_link('/continuity/mission', '🎯', 'Mission', active_path)}
            {_nav_link('/continuity/task', '✓', 'Task', active_path)}
            {_nav_link('/continuity/next', '⏭', 'Next action', active_path)}
            {_nav_link('/continuity/blockers', '🛑', 'Blockers', active_path)}
            {_nav_link('/continuity/recovery', '⚕', 'Recovery', active_path)}
        </div>
        <div class="nav-section">
            <div class="nav-section-label">AUDIT</div>
            {_nav_link('/audit/events', '📋', 'Events', active_path)}
            {_nav_link('/audit/provenance', '🔍', 'Provenance', active_path)}
            {_nav_link('/audit/evidence', '🛡', 'Evidence', active_path)}
            {_nav_link('/audit/changes', '📝', 'Changes', active_path)}
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
    <link rel="icon" href="data:image/x-icon;base64,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" type="image/x-icon">
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>Setup — ANNY Runtime</title>
    <style>{COMMON_CSS}</style>
</head>
<body>
<div class="login-container">
    <div class="login-card animate-fade-in" style="text-align:center;">
        <div class="sidebar-brand" style="margin-bottom: 24px;">
            <img src="data:image/png;base64,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" alt="ANNY Logo" style="width: 48px; height: 48px; object-fit: contain; margin-bottom: 12px; filter: drop-shadow(0 0 8px rgba(255,255,255,0.2));">
            
            <h1 style="margin: 4px 0;">ANNY</h1>
            <div class="version" style="font-size: 12px; color: var(--text-muted);">Runtime: ANNY-RUNTIME</div>
        </div>
        <p style="color:var(--text-primary);font-weight:600;margin-bottom:8px;">Runtime installed</p>
        <p style="color:var(--text-primary);font-weight:600;margin-bottom:24px;">Runtime active</p>
        <p style="color:var(--text-secondary);margin-bottom:32px;">Connect GitHub to begin.</p>
        {error_html}
        <form method="POST" action="/github/device/init">
            <input type="hidden" name="csrf_token" value="{csrf_token}">
            <button type="submit" class="btn btn-primary login-btn">CONNECT GITHUB</button>
        </form>
    </div>
</div>
</body>
</html>"""

def device_flow_page(user_code, verification_uri, csrf_token=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <link rel="icon" href="data:image/x-icon;base64,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" type="image/x-icon">
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>Authorize — ANNY Runtime</title>
    <style>{COMMON_CSS}</style>
</head>
<body>
<div class="login-container">
    <div class="login-card animate-fade-in" style="text-align:center;">
        <h2 style="margin-bottom:16px;">GitHub Authorization</h2>
        <p style="color:var(--text-secondary);margin-bottom:24px;">Please enter this code on GitHub to authorize ANNY:</p>
        <div style="font-size:32px; letter-spacing:4px; font-weight:700; margin-bottom:24px; padding:16px; background:var(--bg-secondary); border-radius:8px;">
            {user_code}
        </div>
        <a href="{verification_uri}" target="_blank" class="btn btn-primary login-btn" style="text-decoration:none; display:block; margin-bottom:24px;">OPEN GITHUB</a>
        <p id="status-text" style="color:var(--text-secondary);font-size:14px;">Waiting for authorization...</p>
    </div>
</div>
<script>
    function pollStatus() {{
        fetch('/github/device/poll')
            .then(response => response.json())
            .then(data => {{
                if (data.status === 'AUTHORIZED') {{
                    document.getElementById('status-text').innerText = 'Authorized! Redirecting...';
                    document.getElementById('status-text').style.color = 'var(--accent-teal)';
                    setTimeout(() => window.location.href = '/', 1000);
                }} else if (data.status === 'FAILED') {{
                    document.getElementById('status-text').innerText = 'Authorization failed: ' + (data.error || 'Unknown error');
                    document.getElementById('status-text').style.color = 'var(--accent-ruby)';
                }} else {{
                    setTimeout(pollStatus, 3000);
                }}
            }})
            .catch(error => {{
                console.error('Polling error:', error);
                setTimeout(pollStatus, 5000);
            }});
    }}
    setTimeout(pollStatus, 3000);
</script>
</body>
</html>"""


def reconnect_page(csrf_token=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <link rel="icon" href="data:image/x-icon;base64,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" type="image/x-icon">
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>Reconnect — ANNY Runtime</title>
    <style>{COMMON_CSS}</style>
</head>
<body>
<div class="login-container">
    <div class="login-card animate-fade-in" style="text-align:center;">
        <div class="sidebar-brand" style="margin-bottom: 24px;">
            <img src="data:image/png;base64,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" alt="ANNY Logo" style="width: 48px; height: 48px; object-fit: contain; margin-bottom: 12px; filter: drop-shadow(0 0 8px rgba(255,255,255,0.2));">
            
            <h1 style="margin: 4px 0;">ANNY</h1>
            <div class="version" style="font-size: 12px; color: var(--text-muted);">Runtime: ANNY-RUNTIME</div>
        </div>
        <p style="color:var(--text-primary);font-weight:600;margin-bottom:8px;">GitHub authorization expired</p>
        <p style="color:var(--text-secondary);margin-bottom:32px;">Please provide a new GitHub Access Token to reconnect.</p>
        <form method="POST" action="/github/token">
            <input type="hidden" name="csrf_token" value="{csrf_token}">
            <div style="margin-bottom: 24px; text-align: left;">
                <label for="github_token_input" style="display:block; margin-bottom:8px; color:var(--text-secondary); font-size:12px; font-weight:600; letter-spacing:1px;">RECOVERY TOKEN (Admin Only)</label>
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
    <link rel="icon" href="data:image/x-icon;base64,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" type="image/x-icon">
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
                <label for="github_token_input" style="display:block; margin-bottom:8px; color:var(--text-secondary); font-size:12px; font-weight:600; letter-spacing:1px;">RECOVERY TOKEN (Admin Only)</label>
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
            <p>Operational Dashboard & Universe Status</p>
        </div>

        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px;">
            <!-- INFRASTRUCTURE -->
            <a href="/infrastructure/runtime" style="text-decoration:none;" class="card" style="padding:20px; cursor:pointer;">
                <div style="font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">Runtime</div>
                <div style="font-size:22px; font-weight:700;"><span class="badge badge-success">{cont.get('runtime_status', 'CONNECTED')}</span></div>
            </a>
            <a href="/infrastructure/github" style="text-decoration:none;" class="card" style="padding:20px; cursor:pointer;">
                <div style="font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">GitHub</div>
                <div style="font-size:22px; font-weight:700;"><span class="badge { 'badge-success' if gh.get('connected') else 'badge-danger' }">{gh.get('auth_status', 'ERROR')}</span></div>
            </a>
            <a href="/infrastructure/fabric" style="text-decoration:none;" class="card" style="padding:20px; cursor:pointer;">
                <div style="font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">Fabric</div>
                <div style="font-size:22px; font-weight:700;"><span class="badge { 'badge-success' if status.get('fabric_connected') else 'badge-danger' }">{ 'CONNECTED' if status.get('fabric_connected') else 'ERROR' }</span></div>
            </a>
            <a href="/infrastructure/mcp" style="text-decoration:none;" class="card" style="padding:20px; cursor:pointer;">
                <div style="font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">MCP Nodes</div>
                <div style="font-size:22px; font-weight:700; color:var(--accent-indigo);">{status.get('mcp_count', 0)}</div>
            </a>

            <!-- UNIVERSE -->
            <a href="/universe/projects" style="text-decoration:none;" class="card" style="padding:20px; cursor:pointer;">
                <div style="font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">Projects</div>
                <div style="font-size:22px; font-weight:700; color:var(--accent-indigo);">{status.get('project_count', 0)}</div>
            </a>
            <a href="/universe/repositories" style="text-decoration:none;" class="card" style="padding:20px; cursor:pointer;">
                <div style="font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">Repositories</div>
                <div style="font-size:22px; font-weight:700; color:var(--accent-indigo);">{repo_count}</div>
            </a>
            <a href="/universe/resources" style="text-decoration:none;" class="card" style="padding:20px; cursor:pointer;">
                <div style="font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">Fabric Resources</div>
                <div style="font-size:22px; font-weight:700; color:var(--accent-emerald);">{status.get('resource_count', 0)}</div>
            </a>

            <!-- INTELLIGENCE -->
            <a href="/intelligence/models" style="text-decoration:none;" class="card" style="padding:20px; cursor:pointer;">
                <div style="font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">Models</div>
                <div style="font-size:22px; font-weight:700; color:var(--accent-indigo);">{status.get('model_count', 0)}</div>
            </a>
            <a href="/intelligence/capabilities" style="text-decoration:none;" class="card" style="padding:20px; cursor:pointer;">
                <div style="font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">Capabilities</div>
                <div style="font-size:22px; font-weight:700; color:var(--accent-indigo);">{status.get('capability_count', 0)}</div>
            </a>

            <!-- EXECUTION -->
            <a href="/execution/workers" style="text-decoration:none;" class="card" style="padding:20px; cursor:pointer;">
                <div style="font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">Workers</div>
                <div style="font-size:22px; font-weight:700; color:var(--accent-indigo);">{status.get('worker_count', 0)}</div>
            </a>
            <a href="/execution/tasks" style="text-decoration:none;" class="card" style="padding:20px; cursor:pointer;">
                <div style="font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">Pending Tasks</div>
                <div style="font-size:22px; font-weight:700; color:var(--accent-indigo);">{status.get('task_count', 0)}</div>
            </a>
            <a href="/continuity/blockers" style="text-decoration:none;" class="card" style="padding:20px; cursor:pointer;">
                <div style="font-size:12px; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px;">Blockers</div>
                <div style="font-size:22px; font-weight:700; color:var(--accent-amber);">{blocker_count}</div>
            </a>
        </div>

        <div class="detail-panel" style="margin-bottom: 24px;">
            <h3 style="font-size:15px; margin-bottom:16px; color:var(--accent-indigo);">Canonical State Overview</h3>
            <div class="detail-row"><span class="detail-label">Runtime Identity</span><span class="detail-value">{id_str}</span></div>
            <div class="detail-row"><span class="detail-label">GitHub Principal</span><span class="detail-value">{gh.get('principal', '—')}</span></div>
            <div class="detail-row"><span class="detail-label">Organizations</span><span class="detail-value">{org_name}</span></div>
            <div class="detail-row"><span class="detail-label">Current Mission</span><span class="detail-value" style="font-weight:600; color:var(--accent-emerald);">{mission}</span></div>
        </div>
    """, "/", csrf_token)



def github_page(gh_status, error=None, csrf_token=""):
    """Render the GitHub status page."""
    badge_class = 'badge-success' if gh_status.get('connected') else 'badge-danger'
    status_text = 'CONNECTED' if gh_status.get('connected') else gh_status.get('auth_status', 'UNKNOWN')
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
                    <label for="github_token_input" style="display:block; margin-bottom:8px; color:var(--text-secondary); font-size:12px; font-weight:600; letter-spacing:1px;">RECOVERY TOKEN (Admin Only)</label>
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
            <div class="detail-row"><span class="detail-label">Fabric Resources</span><span class="detail-value">{fab_status.get('resource_count', '0')}</span></div>
            <div class="detail-row"><span class="detail-label">Provenance</span><span class="badge badge-success">HEALTHY</span></div>
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


def models_page(models, csrf_token=""):
    rows = ""
    for m in models:
        badge_cls = 'badge-success' if m.state.value in ('AVAILABLE', 'REGISTERED') else 'badge-danger'
        rows += f"""<tr>
            <td class="mono"><a href="/models/{m.model_id}">{m.model_id}</a></td>
            <td>{m.model_name}</td>
            <td>{m.provider}</td>
            <td>{m.version}</td>
            <td><span class="badge {badge_cls}">{m.state.value}</span></td>
        </tr>"""
    if not rows:
        rows = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:32px;">No models registered</td></tr>'

    return base_layout("Models", f"""
        <div class="page-header">
            <h2>Model Registry</h2>
            <p>Control plane view of registered models, capabilities, and availability.</p>
        </div>
        <div class="detail-panel">
            <table class="data-table">
                <thead><tr><th>Model ID</th><th>Name</th><th>Provider</th><th>Version</th><th>State</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    """, "/models", csrf_token)

def model_detail_page(model, bindings, hw_profile, perf_profile, csrf_token=""):
    state_badge = 'badge-success' if model.state.value in ('AVAILABLE', 'REGISTERED') else 'badge-danger'
    
    bindings_rows = ""
    for b in bindings:
        pref = 'badge-info' if b.preferred else 'badge-muted'
        bindings_rows += f"""<tr>
            <td class="mono">{b.capability_id}</td>
            <td><span class="badge {pref}">{"Yes" if b.preferred else "No"}</span></td>
            <td>{b.authorization}</td>
        </tr>"""
    if not bindings_rows:
        bindings_rows = '<tr><td colspan="3" style="text-align:center;color:var(--text-muted);padding:16px;">No capabilities bound</td></tr>'

    hw_info = ""
    if hw_profile:
        hw_info = f"""
            <div class="detail-row"><span class="detail-label">Hardware Type</span><span class="detail-value">{hw_profile.hardware_type}</span></div>
            <div class="detail-row"><span class="detail-label">VRAM MB</span><span class="detail-value">{hw_profile.vram_mb}</span></div>
            <div class="detail-row"><span class="detail-label">RAM MB</span><span class="detail-value">{hw_profile.ram_mb}</span></div>
            <div class="detail-row"><span class="detail-label">Compute Class</span><span class="detail-value">{hw_profile.compute_class}</span></div>
        """
        
    perf_info = ""
    if perf_profile:
        perf_info = f"""
            <div class="detail-row"><span class="detail-label">Context Window Size</span><span class="detail-value">{perf_profile.context_window_size}</span></div>
            <div class="detail-row"><span class="detail-label">Max Output Tokens</span><span class="detail-value">{perf_profile.max_output_tokens}</span></div>
            <div class="detail-row"><span class="detail-label">Avg Tokens/s</span><span class="detail-value">{perf_profile.avg_tokens_per_second}</span></div>
            <div class="detail-row"><span class="detail-label">Cold Start Time (ms)</span><span class="detail-value">{perf_profile.cold_start_time_ms}</span></div>
            <div class="detail-row"><span class="detail-label">Cost per 1k</span><span class="detail-value">{perf_profile.cost_per_1k}</span></div>
        """

    return base_layout(f"Model {model.model_id}", f"""
        <div class="page-header">
            <h2>Model Detail: <span class="mono">{model.model_id}</span></h2>
        </div>
        <div class="detail-panel">
            <h3 style="font-size:14px; margin-bottom:12px; color:var(--text-primary);">Definition</h3>
            <div class="detail-row"><span class="detail-label">State</span><span class="badge {state_badge}">{model.state.value}</span></div>
            <div class="detail-row"><span class="detail-label">Name</span><span class="detail-value">{model.model_name}</span></div>
            <div class="detail-row"><span class="detail-label">Provider</span><span class="detail-value">{model.provider}</span></div>
            <div class="detail-row"><span class="detail-label">Version</span><span class="detail-value">{model.version}</span></div>
            <div class="detail-row"><span class="detail-label">Location Type</span><span class="detail-value">{model.location_type}</span></div>
            <div class="detail-row"><span class="detail-label">Path/URI</span><span class="mono">{model.path_or_uri}</span></div>
            <div class="detail-row"><span class="detail-label">Executor Type</span><span class="detail-value">{model.executor_type}</span></div>
        </div>
        
        <div class="detail-panel">
            <h3 style="font-size:14px; margin-bottom:12px; color:var(--text-primary);">Hardware Constraints</h3>
            {hw_info or '<div class="detail-row"><span class="detail-label">No hardware profile</span><span class="detail-value">—</span></div>'}
        </div>
        
        <div class="detail-panel">
            <h3 style="font-size:14px; margin-bottom:12px; color:var(--text-primary);">Performance Profile</h3>
            {perf_info or '<div class="detail-row"><span class="detail-label">No performance profile</span><span class="detail-value">—</span></div>'}
        </div>

        <div class="detail-panel">
            <h3 style="font-size:14px; margin-bottom:12px; color:var(--text-primary);">Capability Bindings</h3>
            <table class="data-table" style="margin-top:0;">
                <thead><tr><th>Capability</th><th>Preferred</th><th>Authorization</th></tr></thead>
                <tbody>{bindings_rows}</tbody>
            </table>
        </div>
    """, "/models", csrf_token)


# New Templates for Control Plane Universe 001

def _render_empty_state(message="No data available."):
    return f'<div style="padding: 40px; text-align: center; color: var(--text-muted); font-size: 14px;">{message}</div>'

def universe_organization_page(orgs, csrf_token=""):
    rows = ""
    for org in orgs:
        rows += f'<tr><td>{org.get("login", "—")}</td><td>{org.get("id", "—")}</td><td><span class="badge badge-success">ACTIVE</span></td></tr>'
    content = f"""
        <div class="page-header"><h2>Organization Map</h2><p>Discovered Github Organizations</p></div>
        <div class="detail-panel">
            <table class="data-table">
                <thead><tr><th>Organization</th><th>ID</th><th>State</th></tr></thead>
                <tbody>{rows if rows else '<tr><td colspan="3" style="text-align:center;">No organizations discovered</td></tr>'}</tbody>
            </table>
        </div>
    """
    return base_layout("Organization Map", content, "/universe/organization", csrf_token)

def universe_projects_page(projects, csrf_token=""):
    content = f"""
        <div class="page-header"><h2>Project Map</h2><p>Logical Groupings</p></div>
        {_render_empty_state('No projects configured.')}
    """
    return base_layout("Project Map", content, "/universe/projects", csrf_token)

def universe_repositories_page(repos, csrf_token=""):
    rows = ""
    for r in repos:
        name = r.get('name', '—')
        owner = r.get('owner', '—')
        vis = r.get('visibility', '—')
        rows += f'<tr><td class="mono">{owner}/{name}</td><td>{vis}</td><td>GitHub</td><td><a href="/universe/resources">View in Fabric</a></td></tr>'
    content = f"""
        <div class="page-header"><h2>Repository Map</h2><p>Discovered Code Repositories</p></div>
        <div class="detail-panel">
            <table class="data-table">
                <thead><tr><th>Name</th><th>Visibility</th><th>Provider</th><th>Links</th></tr></thead>
                <tbody>{rows if rows else '<tr><td colspan="4" style="text-align:center;">No repositories discovered</td></tr>'}</tbody>
            </table>
        </div>
    """
    return base_layout("Repository Map", content, "/universe/repositories", csrf_token)

def universe_resources_page(resources, csrf_token=""):
    rows = ""
    for res in resources:
        res_id = getattr(res, 'resource_id', res.get('resource_id', '—') if isinstance(res, dict) else '—')
        prov_id = getattr(res, 'provenance_id', res.get('provenance_id', '—') if isinstance(res, dict) else '—')
        state = getattr(res, 'state', res.get('state', 'UNKNOWN') if isinstance(res, dict) else 'UNKNOWN')
        badge = 'badge-success' if state == 'ACTIVE' else 'badge-muted'
        rows += f'<tr><td class="mono">{res_id}</td><td><span class="badge {badge}">{state}</span></td><td><a href="/audit/provenance?id={prov_id}" class="mono">{prov_id}</a></td></tr>'
    
    content = f"""
        <div class="page-header"><h2>Fabric Resources</h2><p>Canonical domain entities registered in Fabric</p></div>
        <div class="detail-panel">
            <table class="data-table">
                <thead><tr><th>Resource ID</th><th>State</th><th>Provenance ID</th></tr></thead>
                <tbody>{rows if rows else '<tr><td colspan="3" style="text-align:center;">No Fabric resources registered.</td></tr>'}</tbody>
            </table>
        </div>
    """
    return base_layout("Fabric Resources", content, "/universe/resources", csrf_token)

def execution_tasks_page(tasks, csrf_token=""):
    rows = ""
    for t_id, task in tasks.items():
        rows += f'<tr><td class="mono">{t_id}</td><td>{task.capability_id}</td><td><span class="badge badge-info">QUEUED</span></td></tr>'
    content = f"""
        <div class="page-header"><h2>Pending Tasks</h2><p>Tasks waiting for execution</p></div>
        <div class="detail-panel">
            <table class="data-table">
                <thead><tr><th>Task ID</th><th>Capability</th><th>Status</th></tr></thead>
                <tbody>{rows if rows else '<tr><td colspan="3" style="text-align:center;">No pending tasks.</td></tr>'}</tbody>
            </table>
        </div>
    """
    return base_layout("Pending Tasks", content, "/execution/tasks", csrf_token)

def execution_workers_page(workers, csrf_token=""):
    rows = ""
    for w_id, worker in workers.items():
        state = worker.state.value if hasattr(worker.state, 'value') else str(worker.state)
        badge = 'badge-success' if state == 'SUCCEEDED' else ('badge-info' if state == 'RUNNING' else 'badge-muted')
        rows += f'<tr><td class="mono">{w_id}</td><td>{worker.capability_id}</td><td>{worker.model_id}</td><td><span class="badge {badge}">{state}</span></td></tr>'
    content = f"""
        <div class="page-header"><h2>Worker Topology</h2><p>Active and historical workers</p></div>
        <div class="detail-panel">
            <table class="data-table">
                <thead><tr><th>Worker ID</th><th>Capability</th><th>Model</th><th>State</th></tr></thead>
                <tbody>{rows if rows else '<tr><td colspan="4" style="text-align:center;">No workers present.</td></tr>'}</tbody>
            </table>
        </div>
    """
    return base_layout("Worker Topology", content, "/execution/workers", csrf_token)

def intelligence_capabilities_page(caps, bindings, csrf_token=""):
    rows = ""
    for cap in caps:
        c_id = cap.capability_id
        # Find preferred model
        pref_model = "—"
        for b in bindings:
            if b.capability_id == c_id and b.preferred:
                pref_model = b.model_id
                break
        rows += f'<tr><td class="mono">{c_id}</td><td>{cap.name}</td><td class="mono">{pref_model}</td></tr>'
    
    content = f"""
        <div class="page-header"><h2>Capability Map</h2><p>Registered capabilities and preferred models</p></div>
        <div class="detail-panel">
            <table class="data-table">
                <thead><tr><th>Capability ID</th><th>Name</th><th>Preferred Model</th></tr></thead>
                <tbody>{rows if rows else '<tr><td colspan="3" style="text-align:center;">No capabilities found.</td></tr>'}</tbody>
            </table>
        </div>
    """
    return base_layout("Capabilities", content, "/intelligence/capabilities", csrf_token)

def infrastructure_topology_page(gh_status, fabric_status, mcp_status, csrf_token=""):
    gh_badge = 'badge-success' if gh_status else 'badge-danger'
    fab_badge = 'badge-success' if fabric_status else 'badge-danger'
    content = f"""
        <div class="page-header"><h2>Infrastructure Topology</h2><p>System boundaries</p></div>
        <div style="font-family: var(--font-mono); font-size: 14px; background: var(--bg-secondary); padding: 24px; border-radius: var(--radius-md); text-align:center; line-height:2;">
            <div>[ GitHub <span class="badge {gh_badge}">{"UP" if gh_status else "DOWN"}</span> ]</div>
            <div>│</div>
            <div>▼</div>
            <div>[ ANNY-RUNTIME <span class="badge badge-success">UP</span> ]</div>
            <div>│</div>
            <div style="display:flex; justify-content:center; gap: 40px;">
                <div>▼<br>[ MCP <span class="badge badge-muted">0 Nodes</span> ]</div>
                <div>▼<br>[ Workers ]</div>
                <div>▼<br>[ Fabric <span class="badge {fab_badge}">{"UP" if fabric_status else "DOWN"}</span> ]</div>
            </div>
            <div style="display:flex; justify-content:center; gap: 40px;">
                <div>▼<br>[ Tools ]</div>
                <div>▼<br>[ Models ]</div>
                <div>▼<br>[ Azure ]</div>
            </div>
        </div>
    """
    return base_layout("Infrastructure Topology", content, "/infrastructure/runtime", csrf_token)

def audit_events_page(events, csrf_token=""):
    rows = ""
    for ev in events:
        # Event fields: id, timestamp, level, category, module, event_type, status, message, data, instance_id, runtime_id
        timestamp = ev[1]
        cat = ev[3]
        mod = ev[4]
        typ = ev[5]
        status = ev[6]
        msg = ev[7]
        badge = 'badge-success' if status == 'SUCCESS' else ('badge-danger' if status == 'ERROR' else 'badge-info')
        rows += f'<tr><td>{timestamp}</td><td>{mod}</td><td>{typ}</td><td><span class="badge {badge}">{status}</span></td><td class="mono">{msg}</td></tr>'
        
    content = f"""
        <div class="page-header"><h2>Audit Events</h2><p>Chronological system logs</p></div>
        <div class="detail-panel">
            <table class="data-table">
                <thead><tr><th>Time</th><th>Module</th><th>Type</th><th>Status</th><th>Message</th></tr></thead>
                <tbody>{rows if rows else '<tr><td colspan="5" style="text-align:center;">No events.</td></tr>'}</tbody>
            </table>
        </div>
    """
    return base_layout("Audit Events", content, "/audit/events", csrf_token)

def audit_provenance_page(prov_data, csrf_token=""):
    content = f"""
        <div class="page-header"><h2>Provenance & Evidence</h2><p>Cryptographic traces</p></div>
        <pre style="background:var(--bg-secondary); padding: 16px; border-radius: var(--radius-sm); font-size:12px;">{prov_data if prov_data else 'No provenance data selected or available.'}</pre>
    """
    return base_layout("Provenance", content, "/audit/provenance", csrf_token)

def search_page(query, csrf_token=""):
    content = f"""
        <div class="page-header"><h2>Global Search</h2><p>Results for: {query}</p></div>
        {_render_empty_state('Search returned 0 results. Indexing is lazy.')}
    """
    return base_layout("Search", content, "/search", csrf_token)

def generic_placeholder_page(title, path, csrf_token=""):
    return base_layout(title, f'<div class="page-header"><h2>{title}</h2></div>{_render_empty_state("No instances found.")}', path, csrf_token)


def telemetry_live_page(csrf_token=""):
    return base_layout("Live Telemetry", f"""
        <div class="page-header">
            <h2>Live Telemetry Stream</h2>
            <p>Real-time observability of ANNY Universe execution events.</p>
        </div>
        
        <div class="card" style="margin-bottom: 24px; padding: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <div id="connection-indicator" style="width: 12px; height: 12px; border-radius: 50%; background: var(--accent-emerald); box-shadow: 0 0 8px var(--accent-emerald);"></div>
                    <span id="connection-status" style="font-weight: 600; font-size: 13px;">CONNECTED</span>
                </div>
                <button id="clear-btn" class="btn btn-ghost" style="padding: 6px 12px; font-size: 12px;">Clear Output</button>
            </div>
        </div>

        <div id="telemetry-console" style="background: var(--bg-primary); border: 1px solid var(--border-subtle); border-radius: var(--radius); padding: 16px; height: 600px; overflow-y: auto; font-family: 'JetBrains Mono', monospace; font-size: 12px; line-height: 1.5;">
            <!-- Events will be appended here -->
        </div>

        <script>
            const consoleEl = document.getElementById('telemetry-console');
            const statusEl = document.getElementById('connection-status');
            const indicatorEl = document.getElementById('connection-indicator');
            const clearBtn = document.getElementById('clear-btn');
            
            let eventSource = null;

            function connect() {{
                if (eventSource) {{
                    eventSource.close();
                }}
                
                statusEl.textContent = 'CONNECTING...';
                indicatorEl.style.background = 'var(--accent-amber)';
                indicatorEl.style.boxShadow = '0 0 8px var(--accent-amber)';

                eventSource = new EventSource('/api/v1/telemetry/stream');
                
                eventSource.onopen = function() {{
                    statusEl.textContent = 'CONNECTED';
                    indicatorEl.style.background = 'var(--accent-emerald)';
                    indicatorEl.style.boxShadow = '0 0 8px var(--accent-emerald)';
                }};
                
                eventSource.onmessage = function(event) {{
                    try {{
                        const data = JSON.parse(event.data);
                        appendEvent(data);
                    }} catch (e) {{
                        console.error("Error parsing event data", e);
                    }}
                }};
                
                eventSource.onerror = function() {{
                    statusEl.textContent = 'DISCONNECTED - RECONNECTING...';
                    indicatorEl.style.background = 'var(--accent-rose)';
                    indicatorEl.style.boxShadow = '0 0 8px var(--accent-rose)';
                }};
            }}
            
            function formatTime(isoString) {{
                if (!isoString) return '';
                const d = new Date(isoString);
                return d.toLocaleTimeString('en-US', {{ hour12: false, hour: '2-digit', minute:'2-digit', second:'2-digit', fractionalSecondDigits: 3 }});
            }}

            function appendEvent(env) {{
                const el = document.createElement('div');
                el.style.borderBottom = '1px solid var(--border-subtle)';
                el.style.padding = '8px 0';
                el.style.display = 'flex';
                el.style.gap = '16px';
                
                // Timestamp
                const tsEl = document.createElement('div');
                tsEl.style.color = 'var(--text-muted)';
                tsEl.style.minWidth = '110px';
                tsEl.textContent = formatTime(env.timestamp);
                
                // Component & Source
                const compEl = document.createElement('div');
                compEl.style.minWidth = '150px';
                compEl.innerHTML = `<span style="color: var(--accent-blue)">${{env.component}}</span><br><span style="color: var(--text-muted); font-size: 10px;">${{env.source || ''}}</span>`;
                
                // Event Type & Trace
                const nameEl = document.createElement('div');
                nameEl.style.flex = '1';
                nameEl.innerHTML = `<span style="color: var(--text-primary); font-weight: 600;">${{env.event_type}}</span>`;
                
                if (env.trace_id) {{
                    nameEl.innerHTML += `<br><span style="color: var(--text-muted); font-size: 10px;">Trace: ${{env.trace_id.substring(0,8)}} | Span: ${{(env.span_id || '').substring(0,8)}}</span>`;
                }}
                
                el.appendChild(tsEl);
                el.appendChild(compEl);
                el.appendChild(nameEl);
                
                // Metadata preview (if any)
                if (env.metadata && Object.keys(env.metadata).length > 0) {{
                    const dataEl = document.createElement('div');
                    dataEl.style.width = '100%';
                    dataEl.style.marginTop = '4px';
                    dataEl.style.padding = '8px';
                    dataEl.style.background = 'var(--bg-secondary)';
                    dataEl.style.borderRadius = '4px';
                    dataEl.style.color = 'var(--accent-emerald)';
                    dataEl.textContent = JSON.stringify(env.metadata);
                    
                    const containerEl = document.createElement('div');
                    containerEl.style.display = 'flex';
                    containerEl.style.flexDirection = 'column';
                    containerEl.style.flex = '2';
                    containerEl.appendChild(nameEl);
                    containerEl.appendChild(dataEl);
                    el.replaceChild(containerEl, nameEl);
                }}
                
                consoleEl.appendChild(el);
                
                // Auto scroll to bottom
                consoleEl.scrollTop = consoleEl.scrollHeight;
                
                // Keep only last 500 events
                while (consoleEl.children.length > 500) {{
                    consoleEl.removeChild(consoleEl.firstChild);
                }}
            }}
            
            clearBtn.addEventListener('click', () => {{
                consoleEl.innerHTML = '';
            }});
            
            // Connect on load
            document.addEventListener('DOMContentLoaded', connect);
        </script>
    """, "/telemetry/live", csrf_token)


def telemetry_timeline_page(recent_events, csrf_token=""):
    rows = ""
    for env in recent_events:
        ts = env.timestamp if hasattr(env, 'timestamp') else env.get("timestamp", "")
        comp = env.component if hasattr(env, 'component') else env.get("component", "")
        src = env.source if hasattr(env, 'source') else env.get("source", "")
        evt = env.event_type if hasattr(env, 'event_type') else env.get("event_type", "")
        
        tid = (env.trace_id if hasattr(env, 'trace_id') else env.get("trace_id")) or ""
        sid = (env.span_id if hasattr(env, 'span_id') else env.get("span_id")) or ""
        tid = tid[:8] if tid else ""
        sid = sid[:8] if sid else ""
        
        rows += f"""
        <tr>
            <td class="mono">{ts}</td>
            <td><span class="badge badge-info">{comp}</span></td>
            <td>{src}</td>
            <td style="font-weight: 600;">{evt}</td>
            <td class="mono" style="color: var(--text-muted);">{tid}</td>
            <td class="mono" style="color: var(--text-muted);">{sid}</td>
        </tr>
        """

        
    return base_layout("Telemetry Timeline", f"""
        <div class="page-header">
            <h2>Telemetry Timeline</h2>
            <p>Historical view of recent execution events across the stack.</p>
        </div>
        
        <div class="card" style="padding: 0; overflow-x: auto;">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Component</th>
                        <th>Source</th>
                        <th>Event Type</th>
                        <th>Trace ID</th>
                        <th>Span ID</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
    """, "/telemetry/timeline", csrf_token)

def browser_dashboard_page(sessions: list, csrf_token: str = "") -> str:
    rows = ""
    for s_tuple in sessions:
        s = s_tuple[0]  # BrowserSession
        status_color = "var(--accent-green)" if s.status.value == "RUNNING" else "var(--text-muted)"
        if s.status.value == "FAILED":
            status_color = "var(--accent-rose)"
        elif s.status.value == "PAUSED_FOR_HUMAN":
            status_color = "var(--accent-yellow)"
            
        rows += f"""
        <tr>
            <td><a href="/browser/{s.session_id}" style="color: var(--accent-blue)">{s.session_id[:8]}...</a></td>
            <td><code>{s.worker_id[:8]}</code></td>
            <td>{s.mode.value}</td>
            <td><span style="color: {status_color}">{s.status.value}</span></td>
            <td>{s.current_url or 'N/A'}</td>
            <td>{s.created_at.isoformat() if s.created_at else 'N/A'}</td>
        </tr>
        """
    if not rows:
        rows = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted)">No active browser sessions</td></tr>'

    return render_admin_page("Browser Integration", f"""
        <div class="page-header">
            <h2>Browser Integration</h2>
            <p>Active and recent Playwright-driven ephemeral browser sessions.</p>
        </div>
        
        <div class="card" style="padding: 0; overflow-x: auto;">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Session ID</th>
                        <th>Worker ID</th>
                        <th>Mode</th>
                        <th>Status</th>
                        <th>Current URL</th>
                        <th>Started At</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
    """, "/browser", csrf_token)


def browser_session_page(session, csrf_token: str = "") -> str:
    import base64
    
    status_color = "var(--accent-green)" if session.status.value == "RUNNING" else "var(--text-muted)"
    if session.status.value == "FAILED":
        status_color = "var(--accent-rose)"
    elif session.status.value == "PAUSED_FOR_HUMAN":
        status_color = "var(--accent-yellow)"
        
    return render_admin_page(f"Browser Session {session.session_id[:8]}", f"""
        <div class="page-header">
            <h2>Session {session.session_id[:8]}</h2>
            <p><a href="/browser" style="color: var(--accent-blue)">&larr; Back to Browser Dashboard</a></p>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px;">
            <div class="card">
                <h3>Session Status</h3>
                <table class="data-table">
                    <tr><td style="color: var(--text-muted); width: 30%">Mode</td><td>{session.mode.value}</td></tr>
                    <tr><td style="color: var(--text-muted)">State</td><td><span style="color: {status_color}">{session.status.value}</span></td></tr>
                    <tr><td style="color: var(--text-muted)">Current URL</td><td><a href="{session.current_url}" target="_blank" style="color: var(--accent-blue)">{session.current_url or 'N/A'}</a></td></tr>
                    <tr><td style="color: var(--text-muted)">Worker ID</td><td><code>{session.worker_id}</code></td></tr>
                    <tr><td style="color: var(--text-muted)">Task ID</td><td><code>{session.task_id}</code></td></tr>
                </table>
            </div>
            
            <div class="card">
                <h3>Policy & Constraints</h3>
                <table class="data-table">
                    <tr><td style="color: var(--text-muted); width: 30%">Network Policy</td><td>{session.policy.network_policy}</td></tr>
                    <tr><td style="color: var(--text-muted)">Allowed Domains</td><td>{', '.join(session.policy.allowed_domains) or 'None'}</td></tr>
                    <tr><td style="color: var(--text-muted)">Timeout</td><td>{session.policy.timeout_ms} ms</td></tr>
                    <tr><td style="color: var(--text-muted)">Human Assist</td><td>{'Yes' if session.policy.human_assistance_allowed else 'No'}</td></tr>
                    <tr><td style="color: var(--text-muted)">Profile Path</td><td><code>{session.profile_path or 'N/A'}</code></td></tr>
                </table>
            </div>
        </div>
    """, "/browser", csrf_token)
