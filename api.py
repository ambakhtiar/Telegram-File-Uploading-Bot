import os
import sqlite3
import json
from fastapi import FastAPI, APIRouter, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PROJECT_DIR, '.env'))

# .env থেকে পিন রিড করা হচ্ছে, না থাকলে ডিফল্ট 1234
DASHBOARD_PIN = os.getenv('DASHBOARD_PIN', '1234')

app = FastAPI(title="Telegram Uploader API")
api_router = APIRouter()

DB_FILE = os.path.join(PROJECT_DIR, 'uploads.db')
STATE_FILE = os.path.join(PROJECT_DIR, 'state.json')
PROGRESS_FILE = os.path.join(PROJECT_DIR, 'progress.json')
CONFIG_FILE = os.path.join(PROJECT_DIR, 'config.json')
QUEUE_FILE = os.path.join(PROJECT_DIR, 'queue.json')
LOG_FILE = os.path.join(PROJECT_DIR, 'uploader.log')

# ================= SECURITY DEPENDENCY =================
def verify_pin(x_pin: str = Header(None)):
    if x_pin != DASHBOARD_PIN:
        raise HTTPException(status_code=401, detail="Unauthorized API Key")

# ================= DATA MODELS =================
class FolderRule(BaseModel):
    name: str; file_type: str; topic_id: int
class SettingsItem(BaseModel):
    auto_delete: bool

# ================= HELPER FUNCTIONS =================
def get_state():
    if not os.path.exists(STATE_FILE): return "running"
    try:
        with open(STATE_FILE, 'r') as f: return json.load(f).get("status", "running")
    except: return "running"

def set_state(status):
    with open(STATE_FILE, 'w') as f: json.dump({"status": status}, f)

def read_config():
    if not os.path.exists(CONFIG_FILE): return {"auto_delete_after_upload": False, "folders": {}}
    try:
        with open(CONFIG_FILE, 'r') as f: return json.load(f)
    except: return {"auto_delete_after_upload": False, "folders": {}}

def write_config(data):
    with open(CONFIG_FILE, 'w') as f: json.dump(data, f, indent=4)

def get_db_stats():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM uploads")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT file_name, uploaded_at, message_link FROM uploads ORDER BY uploaded_at DESC LIMIT 5")
        recent = cursor.fetchall()
        conn.close()
        return total, [{"name": r[0], "time": r[1], "link": r[2] if len(r)>2 else None} for r in recent]
    except Exception: return 0, []

def get_progress():
    try:
        with open(PROGRESS_FILE, 'r') as f: return json.load(f)
    except: return {"status": "idle"}

def get_queue_count():
    try:
        with open(QUEUE_FILE, 'r') as f: return json.load(f).get("count", 0)
    except: return 0

# ================= SECURE API ENDPOINTS =================
@api_router.get("/stats")
def stats():
    total, recent = get_db_stats()
    return {"status": get_state(), "total_uploaded": total, "recent_uploads": recent, "progress": get_progress(), "queued_files": get_queue_count()}

@api_router.get("/history")
def get_history(query: str = "", limit: int = 20, offset: int = 0):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        if query: cursor.execute("SELECT file_name, uploaded_at, message_link FROM uploads WHERE file_name LIKE ? ORDER BY uploaded_at DESC LIMIT ? OFFSET ?", (f"%{query}%", limit, offset))
        else: cursor.execute("SELECT file_name, uploaded_at, message_link FROM uploads ORDER BY uploaded_at DESC LIMIT ? OFFSET ?", (limit, offset))
        records = cursor.fetchall()
        conn.close()
        return [{"name": r[0], "time": r[1], "link": r[2] if len(r)>2 else None} for r in records]
    except Exception: return []

@api_router.get("/logs")
def get_logs():
    if not os.path.exists(LOG_FILE): return {"logs": "Waiting for bot logs..."}
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f: return {"logs": "".join(f.readlines()[-50:])}
    except Exception as e: return {"logs": f"Error: {e}"}

@api_router.get("/action/{command}")
def control_bot(command: str):
    if command in ["pause", "resume"]:
        status = "paused" if command == "pause" else "running"
        set_state(status)
        return {"status": status}
    return {"error": "Invalid command"}

@api_router.get("/config")
def get_config_api(): return read_config()

@api_router.post("/settings")
def update_settings(item: SettingsItem):
    config = read_config()
    config["auto_delete_after_upload"] = item.auto_delete
    write_config(config)
    return {"status": "success"}

@api_router.post("/folders")
def add_folder(item: FolderRule):
    config = read_config()
    folders = config.setdefault("folders", {})
    if item.name not in folders: folders[item.name] = {}
    folders[item.name][item.file_type] = item.topic_id
    write_config(config)
    return {"status": "success"}

@api_router.delete("/folders/{folder_name}")
def delete_folder(folder_name: str):
    config = read_config()
    if folder_name in config.get("folders", {}):
        del config["folders"][folder_name]
        write_config(config)
        return {"status": "success"}
    return {"error": "Not found"}

app.include_router(api_router, prefix="/api", dependencies=[Depends(verify_pin)])

# ================= WEB DASHBOARD (Public Entry) =================
@app.get("/", response_class=HTMLResponse)
def dashboard():
    html_content = """
    <html>
        <head>
            <title>Secure Bot Panel</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 15px; background-color: #f0f2f5; color: #333; overflow-x: hidden; }
                .card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 8px 16px rgba(0,0,0,0.05); max-width: 500px; margin: auto; }
                h2, h3 { color: #1a73e8; }
                h2 { text-align: center; margin-top: 0; font-size: 22px; }
                h3 { font-size: 15px; border-bottom: 1px solid #eee; padding-bottom: 5px; margin-top: 25px; }
                
                .status { font-weight: bold; text-transform: uppercase; padding: 4px 8px; border-radius: 4px; font-size: 12px; }
                .running { background-color: #e6f4ea; color: #1e8e3e; }
                .paused { background-color: #fce8e6; color: #d93025; }
                
                .stats-container { display: flex; justify-content: space-between; background: #f8f9fa; padding: 10px 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e8eaed; }
                .stat-box { text-align: center; width: 48%; }
                .stat-value { font-size: 18px; font-weight: bold; }
                .stat-label { font-size: 11px; color: #5f6368; text-transform: uppercase; letter-spacing: 0.5px; }
                
                .btn { padding: 12px; border: none; border-radius: 6px; color: white; cursor: pointer; margin: 5px; font-weight: bold; width: 47%; transition: 0.2s; }
                .btn:active { opacity: 0.8; }
                .btn-pause { background-color: #d93025; }
                .btn-resume { background-color: #1e8e3e; }
                .btn-history { background-color: #5f6368; width: 100%; margin-top: 10px; }
                .btn-logout { background-color: #fff; border: 1px solid #d93025; color: #d93025; padding: 8px 15px; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 12px; }
                
                .form-wrapper { background: #f8f9fa; padding: 15px; border-radius: 8px; border: 1px solid #e8eaed; margin-bottom: 15px; }
                .form-input { padding: 12px; border: 1px solid #ccc; border-radius: 6px; font-size: 14px; width: 100%; box-sizing: border-box; }
                .row-group { display: flex; gap: 10px; margin-top: 10px; }
                .btn-add { background-color: #1a73e8; color: white; border: none; border-radius: 6px; padding: 12px; font-weight: bold; cursor: pointer; width: 100%; margin-top: 10px; font-size: 14px; }
                
                .progress-container { margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 8px; border: 1px solid #e8eaed; display: none; }
                .file-name { font-weight: bold; font-size: 14px; margin-bottom: 8px; word-break: break-all; color: #1a73e8; }
                .progress-bar-bg { background: #e0e0e0; height: 12px; border-radius: 6px; overflow: hidden; margin-bottom: 8px; }
                .progress-bar-fill { background: linear-gradient(90deg, #1a73e8, #4285f4); height: 100%; width: 0%; transition: width 0.3s ease; }
                .progress-stats { display: flex; justify-content: space-between; font-size: 12px; color: #5f6368; font-family: monospace; font-weight: bold; }
                
                .terminal-box { background-color: #1e1e1e; color: #ffffff; font-family: 'Courier New', Courier, monospace; font-size: 11px; padding: 15px; border-radius: 8px; height: 200px; overflow-y: auto; white-space: pre-wrap; margin-top: 10px; border: 1px solid #333; line-height: 1.4; }
                
                ul { list-style-type: none; padding: 0; margin-top: 10px; }
                li { background: #f8f9fa; border-bottom: 1px solid #e8eaed; padding: 10px; font-size: 13px; display: flex; justify-content: space-between; align-items: center; }
                li:last-child { border-bottom: none; }
                .time { font-size: 11px; color: #80868b; }
                .msg-link { color: #1a73e8; text-decoration: none; font-weight: bold; font-size: 12px; padding-left: 10px; }
                
                .danger-zone { margin-top: 30px; padding: 15px; border: 1px solid #fad2cf; border-radius: 8px; background-color: #fce8e6; }
                .danger-zone h3 { color: #d93025; margin-top: 0; border-bottom: 1px solid #fad2cf; }
                .settings-bar { display: flex; justify-content: space-between; align-items: center; margin-top: 10px; }
                .switch { position: relative; display: inline-block; width: 40px; height: 22px; }
                .switch input { opacity: 0; width: 0; height: 0; }
                .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #ccc; transition: .4s; border-radius: 22px; }
                .slider:before { position: absolute; content: ""; height: 16px; width: 16px; left: 3px; bottom: 3px; background-color: white; transition: .4s; border-radius: 50%; }
                input:checked + .slider { background-color: #d93025; }
                input:checked + .slider:before { transform: translateX(18px); }

                /* Full Screen Modals */
                .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 1000; justify-content: center; align-items: center; padding: 15px; box-sizing: border-box; backdrop-filter: blur(5px); }
                .modal-content { background: white; padding: 20px; border-radius: 12px; width: 100%; max-width: 500px; max-height: 85vh; display: flex; flex-direction: column; }
                .modal-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-bottom: 15px; }
                .search-box { width: 100%; padding: 12px; border: 1px solid #ccc; border-radius: 6px; font-size: 14px; margin-bottom: 15px; box-sizing: border-box; }
                .history-list { overflow-y: auto; flex-grow: 1; padding-right: 5px; }

                /* Login Modal Specific */
                .login-box { text-align: center; max-width: 320px; padding: 30px 20px; }
                .login-input { font-size: 24px; letter-spacing: 5px; text-align: center; margin: 20px 0; font-weight: bold; }
                
                .custom-confirm-box { text-align: center; }
                .btn-group { display: flex; gap: 10px; margin-top: 20px; }
                .btn-cancel { flex: 1; padding: 12px; border-radius: 6px; border: 1px solid #ccc; background: white; font-weight: bold; cursor: pointer; }
                .btn-confirm { flex: 1; padding: 12px; border-radius: 6px; border: none; color: white; font-weight: bold; cursor: pointer; }

                #toast { position: fixed; bottom: -100px; left: 50%; transform: translateX(-50%); color: white; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 13px; z-index: 9999; transition: bottom 0.4s ease-in-out; box-shadow: 0 4px 12px rgba(0,0,0,0.2); white-space: nowrap; }
                
                /* Main Dashboard Container */
                #main-dashboard { display: none; }
            </style>
        </head>
        <body>
            <div id="toast">Notification</div>

            <div id="login-modal" class="modal-overlay" style="display: flex;">
                <div class="modal-content login-box">
                    <h2 style="margin:0; color:#333;">🔒 Security Check</h2>
                    <p style="color:#666; font-size:14px;">Enter PIN to access Control Panel</p>
                    <input type="password" id="pin-input" class="form-input login-input" placeholder="****" maxlength="8">
                    <button onclick="attemptLogin()" class="btn-add" style="margin-top:0;">Login</button>
                    <p id="login-error" style="color:#d93025; font-size:12px; display:none; margin-top:10px;">Incorrect PIN. Try again.</p>
                </div>
            </div>

            <div id="main-dashboard" class="card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h2>⚙️ Control Panel</h2>
                    <button onclick="logout()" class="btn-logout">Logout</button>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <span style="font-size: 14px; font-weight: 500;">System Status:</span>
                    <span id="bot-status" class="status">Loading...</span>
                </div>
                
                <div class="stats-container">
                    <div class="stat-box">
                        <div id="total-count" class="stat-value" style="color: #1a73e8;">0</div>
                        <div class="stat-label">Uploaded</div>
                    </div>
                    <div style="border-left: 1px solid #ddd;"></div>
                    <div class="stat-box">
                        <div id="queue-count" class="stat-value" style="color: #f29900;">0</div>
                        <div class="stat-label">In Queue</div>
                    </div>
                </div>
                
                <div style="text-align: center; display: flex; justify-content: space-between;">
                    <button onclick="sendAction('pause')" class="btn btn-pause">⏸️ PAUSE</button>
                    <button onclick="sendAction('resume')" class="btn btn-resume">▶️ RESUME</button>
                </div>

                <div id="progress-box" class="progress-container">
                    <div class="file-name">⬆️ <span id="p-file">Uploading...</span></div>
                    <div class="progress-bar-bg"><div id="p-bar" class="progress-bar-fill"></div></div>
                    <div class="progress-stats">
                        <span id="p-percent">0%</span><span id="p-speed" style="color: #1e8e3e;">0 KB/s</span><span id="p-eta">0s left</span>
                    </div>
                </div>

                <h3>🖥️ Live Console</h3>
                <div id="log-viewer" class="terminal-box">Loading logs...</div>

                <h3>📂 Smart Folders</h3>
                <div class="form-wrapper">
                    <input type="text" id="f-name" class="form-input" placeholder="Folder Name (e.g. Camera)">
                    <div class="row-group">
                        <select id="f-type" class="form-input" style="flex: 1.2;">
                            <option value="all">All Files</option>
                            <option value="image">Images Only</option>
                            <option value="video">Videos Only</option>
                        </select>
                        <input type="number" id="f-topic" class="form-input" placeholder="Topic ID" style="flex: 0.8;">
                    </div>
                    <button onclick="addFolder()" class="btn-add">➕ Add Rule</button>
                </div>
                <ul id="folder-list"><li>Loading...</li></ul>

                <h3>🕒 Recent Uploads</h3>
                <ul id="recent-list"><li>Loading...</li></ul>
                <button onclick="openHistoryModal()" class="btn btn-history">🔍 View All History</button>

                <div class="danger-zone">
                    <h3>⚠️ Danger Zone</h3>
                    <div class="settings-bar">
                        <span style="font-size: 13px; font-weight: bold; color: #d93025;">🗑️ Auto-delete local files</span>
                        <div class="switch" onclick="handleToggleClick(event)">
                            <input type="checkbox" id="auto-del-toggle">
                            <span class="slider"></span>
                        </div>
                    </div>
                </div>
            </div>

            <div id="history-modal" class="modal-overlay">
                <div class="modal-content">
                    <div class="modal-header">
                        <h3 style="margin:0;">📜 Full Upload History</h3>
                        <button style="background:#f1f3f4; border:none; border-radius:50%; width:30px; height:30px; cursor:pointer;" onclick="closeHistoryModal()">X</button>
                    </div>
                    <input type="text" id="search-input" class="search-box" placeholder="Search files by name..." onkeyup="initSearch()">
                    <div class="history-list" id="history-scroll-box">
                        <ul id="full-history-list" style="margin-top: 0;"></ul>
                    </div>
                </div>
            </div>

            <div id="custom-confirm-modal" class="modal-overlay">
                <div class="modal-content" style="max-width: 320px;">
                    <div class="custom-confirm-box">
                        <h3 id="confirm-title" style="margin-top: 0;">⚠️ Danger Zone</h3>
                        <p id="confirm-desc" style="font-size: 14px; color: #555;">Are you sure?</p>
                        <div class="btn-group">
                            <button class="btn-cancel" onclick="closeConfirmModal()">Cancel</button>
                            <button id="confirm-btn" class="btn-confirm" onclick="applyToggle()">Yes</button>
                        </div>
                    </div>
                </div>
            </div>

            <script>
                // ================= AUTHENTICATION & API WRAPPER =================
                let userPin = localStorage.getItem('auth_pin') || null;
                let pollingIntervals = [];

                function startApp() {
                    document.getElementById('login-modal').style.display = 'none';
                    document.getElementById('main-dashboard').style.display = 'block';
                    fetchFoldersAndSettings();
                    fetchStats();
                    fetchLogs(); 
                    pollingIntervals.push(setInterval(fetchStats, 1000));
                    pollingIntervals.push(setInterval(fetchLogs, 2000));
                }

                function stopApp() {
                    document.getElementById('login-modal').style.display = 'flex';
                    document.getElementById('main-dashboard').style.display = 'none';
                    pollingIntervals.forEach(clearInterval);
                    pollingIntervals = [];
                }

                function apiFetch(url, options = {}) {
                    if (!options.headers) options.headers = {};
                    options.headers['x-pin'] = userPin || '';
                    
                    return fetch(url, options).then(res => {
                        if (res.status === 401) { 
                            localStorage.removeItem('auth_pin');
                            userPin = null;
                            stopApp();
                            document.getElementById('login-error').style.display = 'block';
                            throw new Error("Unauthorized");
                        }
                        return res.json();
                    });
                }

                function attemptLogin() {
                    let pin = document.getElementById('pin-input').value;
                    userPin = pin;
                    apiFetch('/api/stats').then(() => {
                        localStorage.setItem('auth_pin', pin);
                        document.getElementById('login-error').style.display = 'none';
                        startApp();
                    }).catch(err => {
                        console.log("Login failed");
                    });
                }

                function logout() {
                    localStorage.removeItem('auth_pin');
                    userPin = null;
                    document.getElementById('pin-input').value = '';
                    stopApp();
                }

                if (userPin) { startApp(); }

                // ================= UTILITIES =================
                function formatSpeed(bytesPerSec) {
                    if (bytesPerSec < 1024 * 1024) return (bytesPerSec / 1024).toFixed(1) + ' KB/s';
                    else return (bytesPerSec / (1024 * 1024)).toFixed(2) + ' MB/s';
                }

                function showToast(message, isDanger) {
                    let toast = document.getElementById('toast');
                    toast.innerText = message;
                    toast.style.backgroundColor = isDanger ? '#d93025' : '#1e8e3e';
                    toast.style.bottom = '20px';
                    setTimeout(() => { toast.style.bottom = '-100px'; }, 4000);
                }

                function sendAction(action) { apiFetch('/api/action/' + action).then(() => fetchStats()); }

                // ================= SETTINGS & FOLDERS =================
                let targetToggleState = false;
                function handleToggleClick(event) {
                    event.preventDefault();
                    let checkbox = document.getElementById('auto-del-toggle');
                    targetToggleState = !checkbox.checked;
                    let title = document.getElementById('confirm-title');
                    let desc = document.getElementById('confirm-desc');
                    let btn = document.getElementById('confirm-btn');

                    if (targetToggleState) {
                        title.innerText = '⚠️ Warning'; title.style.color = '#d93025';
                        desc.innerText = 'Files will be PERMANENTLY DELETED from your phone once uploaded! Are you sure?';
                        btn.style.backgroundColor = '#d93025'; btn.innerText = 'Yes, Enable';
                    } else {
                        title.innerText = 'Turn Off Auto-Delete?'; title.style.color = '#1e8e3e';
                        desc.innerText = 'Local files will no longer be deleted after upload.';
                        btn.style.backgroundColor = '#1e8e3e'; btn.innerText = 'Yes, Turn Off';
                    }
                    document.getElementById('custom-confirm-modal').style.display = 'flex';
                }

                function closeConfirmModal() { document.getElementById('custom-confirm-modal').style.display = 'none'; }
                function applyToggle() {
                    document.getElementById('auto-del-toggle').checked = targetToggleState;
                    closeConfirmModal();
                    apiFetch('/api/settings', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({auto_delete: targetToggleState}) });
                }

                function fetchFoldersAndSettings() {
                    apiFetch('/api/config').then(data => {
                        document.getElementById('auto-del-toggle').checked = data.auto_delete_after_upload || false;
                        let listHTML = ''; let count = 0;
                        let folders = data.folders || {};
                        for (const [name, rules] of Object.entries(folders)) {
                            let ruleText = Object.entries(rules).map(([t, id]) => `<span style="background:#e8eaed; padding:2px 5px; border-radius:4px; font-size:10px; color:#555;">${t}: ${id}</span>`).join(" ");
                            listHTML += `<li><div style="display:flex; flex-direction:column;"><span>📁 <b>${name}</b></span><div style="margin-top:4px;">${ruleText}</div></div><button onclick="deleteFolder('${name}')" style="background:none; border:none; font-size:16px; cursor:pointer;">🗑️</button></li>`;
                            count++;
                        }
                        document.getElementById('folder-list').innerHTML = count > 0 ? listHTML : "<li style='justify-content:center; color:#888;'>No rules added</li>";
                    });
                }

                function addFolder() {
                    let name = document.getElementById('f-name').value.trim();
                    let type = document.getElementById('f-type').value;
                    let topic = parseInt(document.getElementById('f-topic').value);
                    if(!name || isNaN(topic)) return;
                    apiFetch('/api/folders', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: name, file_type: type, topic_id: topic}) }).then(() => {
                        document.getElementById('f-name').value = ''; document.getElementById('f-topic').value = '';
                        fetchFoldersAndSettings(); 
                    });
                }

                function deleteFolder(name) {
                    if(!confirm(`Remove all rules for '${name}'?`)) return;
                    apiFetch('/api/folders/' + name, { method: 'DELETE' }).then(() => fetchFoldersAndSettings());
                }

                // ================= DATA FETCHING =================
                function fetchLogs() {
                    apiFetch('/api/logs').then(data => {
                        let logViewer = document.getElementById('log-viewer');
                        let isScrolledToBottom = logViewer.scrollHeight - logViewer.clientHeight <= logViewer.scrollTop + 10;
                        logViewer.innerText = data.logs;
                        if (isScrolledToBottom) logViewer.scrollTop = logViewer.scrollHeight;
                    });
                }

                let lastTotalUploaded = -1;
                function fetchStats() {
                    apiFetch('/api/stats').then(data => {
                        let statusEl = document.getElementById('bot-status');
                        statusEl.innerText = data.status; statusEl.className = 'status ' + data.status;
                        document.getElementById('total-count').innerText = data.total_uploaded;
                        document.getElementById('queue-count').innerText = data.queued_files;
                        
                        if (lastTotalUploaded !== -1 && data.total_uploaded > lastTotalUploaded) {
                            if (document.getElementById('auto-del-toggle').checked) showToast("✅ Uploaded & Deleted from Local Storage 🗑️", true);
                            else showToast("✅ File Uploaded Successfully", false);
                        }
                        lastTotalUploaded = data.total_uploaded;

                        let pBox = document.getElementById('progress-box');
                        if (data.status === 'running' && data.progress.status === 'uploading') {
                            pBox.style.display = 'block';
                            document.getElementById('p-file').innerText = data.progress.file_name;
                            document.getElementById('p-bar').style.width = data.progress.percentage + '%';
                            document.getElementById('p-percent').innerText = data.progress.percentage + '%';
                            document.getElementById('p-speed').innerText = formatSpeed(data.progress.speed);
                        } else { pBox.style.display = 'none'; }

                        let listHTML = '';
                        data.recent_uploads.forEach(file => {
                            let linkHtml = file.link ? `<a href="${file.link}" target="_blank" class="msg-link">🔗 Link</a>` : '';
                            listHTML += `<li><span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 55%;">📄 ${file.name}</span><div style="display:flex; align-items:center;"><span class="time">${file.time}</span>${linkHtml}</div></li>`;
                        });
                        document.getElementById('recent-list').innerHTML = listHTML || "<li style='justify-content:center; color:#888;'>No files yet</li>";
                    });
                }

                // ================= HISTORY PAGINATION =================
                let currentOffset = 0; let isFetching = false; let hasMore = true; let searchTimeout;

                function openHistoryModal() {
                    document.getElementById('history-modal').style.display = 'flex';
                    document.getElementById('search-input').value = '';
                    initSearch();
                }
                function closeHistoryModal() { document.getElementById('history-modal').style.display = 'none'; }

                function initSearch() {
                    clearTimeout(searchTimeout);
                    searchTimeout = setTimeout(() => {
                        currentOffset = 0; hasMore = true;
                        document.getElementById('full-history-list').innerHTML = '';
                        loadMoreHistory();
                    }, 300);
                }

                function loadMoreHistory() {
                    if (isFetching || !hasMore) return;
                    isFetching = true;
                    let query = document.getElementById('search-input').value.trim();
                    apiFetch(`/api/history?query=${encodeURIComponent(query)}&limit=20&offset=${currentOffset}`).then(data => {
                        if (data.length < 20) hasMore = false;
                        let listHTML = '';
                        data.forEach(file => {
                            let linkHtml = file.link ? `<a href="${file.link}" target="_blank" class="msg-link">🔗 Link</a>` : '';
                            listHTML += `<li><div style="display:flex; flex-direction:column; max-width: 70%;"><span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: bold;">📄 ${file.name}</span><span class="time" style="margin-top:4px;">${file.time}</span></div>${linkHtml}</li>`;
                        });
                        
                        let ul = document.getElementById('full-history-list');
                        if (currentOffset === 0 && data.length === 0) ul.innerHTML = "<li style='justify-content:center; color:#888; padding:20px;'>No matching files found.</li>";
                        else ul.insertAdjacentHTML('beforeend', listHTML);
                        
                        currentOffset += 20; isFetching = false;
                    });
                }

                document.getElementById('history-scroll-box').addEventListener('scroll', function() {
                    if (this.scrollTop + this.clientHeight >= this.scrollHeight - 10) loadMoreHistory();
                });
            </script>
        </body>
    </html>
    """
    return html_content

