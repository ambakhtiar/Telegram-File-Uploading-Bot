import os
import sqlite3
import json
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="Telegram Uploader API")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(PROJECT_DIR, 'uploads.db')
STATE_FILE = os.path.join(PROJECT_DIR, 'state.json')
PROGRESS_FILE = os.path.join(PROJECT_DIR, 'progress.json')
CONFIG_FILE = os.path.join(PROJECT_DIR, 'config.json')
QUEUE_FILE = os.path.join(PROJECT_DIR, 'queue.json')
LOG_FILE = os.path.join(PROJECT_DIR, 'uploader.log')

# ================= DATA MODELS =================
class FolderRule(BaseModel):
    name: str
    file_type: str
    topic_id: int

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
    except Exception as e: 
        return 0, []

def get_progress():
    try:
        with open(PROGRESS_FILE, 'r') as f: return json.load(f)
    except: return {"status": "idle"}

def get_queue_count():
    try:
        with open(QUEUE_FILE, 'r') as f: return json.load(f).get("count", 0)
    except: return 0

# ================= API ENDPOINTS =================
@app.get("/api/stats")
def stats():
    total, recent = get_db_stats()
    return {
        "status": get_state(),
        "total_uploaded": total,
        "recent_uploads": recent,
        "progress": get_progress(),
        "queued_files": get_queue_count()
    }

@app.get("/api/logs")
def get_logs():
    if not os.path.exists(LOG_FILE):
        return {"logs": "Waiting for bot logs..."}
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            return {"logs": "".join(lines[-50:])}
    except Exception as e:
        return {"logs": f"Error: {e}"}

@app.get("/api/action/{command}")
def control_bot(command: str):
    if command in ["pause", "resume"]:
        status = "paused" if command == "pause" else "running"
        set_state(status)
        return {"status": status}
    return {"error": "Invalid command"}

@app.get("/api/config")
def get_config_api(): return read_config()

# --- Settings & Folders Endpoints ---
@app.post("/api/settings")
def update_settings(item: SettingsItem):
    config = read_config()
    config["auto_delete_after_upload"] = item.auto_delete
    write_config(config)
    return {"status": "success"}

@app.post("/api/folders")
def add_folder(item: FolderRule):
    config = read_config()
    folders = config.setdefault("folders", {})
    if item.name not in folders: folders[item.name] = {}
    folders[item.name][item.file_type] = item.topic_id
    write_config(config)
    return {"status": "success"}

@app.delete("/api/folders/{folder_name}")
def delete_folder(folder_name: str):
    config = read_config()
    if folder_name in config.get("folders", {}):
        del config["folders"][folder_name]
        write_config(config)
        return {"status": "success"}
    return {"error": "Not found"}

# ================= WEB DASHBOARD =================
@app.get("/", response_class=HTMLResponse)
def dashboard():
    html_content = """
    <html>
        <head>
            <title>Bot Control Panel</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 15px; background-color: #f0f2f5; color: #333; }
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
                
                /* Settings Toggle */
                .settings-bar { display: flex; justify-content: space-between; align-items: center; padding: 10px 15px; background: #fff8e1; border: 1px solid #ffecb3; border-radius: 8px; margin-bottom: 20px; }
                .settings-text { font-size: 13px; font-weight: bold; color: #b08d00; }
                .switch { position: relative; display: inline-block; width: 40px; height: 22px; }
                .switch input { opacity: 0; width: 0; height: 0; }
                .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #ccc; transition: .4s; border-radius: 22px; }
                .slider:before { position: absolute; content: ""; height: 16px; width: 16px; left: 3px; bottom: 3px; background-color: white; transition: .4s; border-radius: 50%; }
                input:checked + .slider { background-color: #1a73e8; }
                input:checked + .slider:before { transform: translateX(18px); }

                .btn { padding: 12px; border: none; border-radius: 6px; color: white; cursor: pointer; margin: 5px; font-weight: bold; width: 47%; transition: 0.2s; }
                .btn:active { opacity: 0.8; }
                .btn-pause { background-color: #d93025; }
                .btn-resume { background-color: #1e8e3e; }
                
                /* Modern Stacked Input Form for Mobile */
                .form-wrapper { background: #f8f9fa; padding: 15px; border-radius: 8px; border: 1px solid #e8eaed; margin-bottom: 15px; }
                .form-input { padding: 12px; border: 1px solid #ccc; border-radius: 6px; font-size: 14px; width: 100%; box-sizing: border-box; }
                .row-group { display: flex; gap: 10px; margin-top: 10px; }
                .btn-add { background-color: #1a73e8; color: white; border: none; border-radius: 6px; padding: 12px; font-weight: bold; cursor: pointer; width: 100%; margin-top: 10px; font-size: 14px; }
                
                .progress-container { margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 8px; border: 1px solid #e8eaed; display: none; }
                .file-name { font-weight: bold; font-size: 14px; margin-bottom: 8px; word-break: break-all; color: #1a73e8; }
                .progress-bar-bg { background: #e0e0e0; height: 12px; border-radius: 6px; overflow: hidden; margin-bottom: 8px; }
                .progress-bar-fill { background: linear-gradient(90deg, #1a73e8, #4285f4); height: 100%; width: 0%; transition: width 0.3s ease; }
                .progress-stats { display: flex; justify-content: space-between; font-size: 12px; color: #5f6368; font-family: monospace; font-weight: bold; }
                .progress-size { text-align: center; font-size: 11px; color: #80868b; margin-top: 8px; font-family: monospace; }
                
                /* Terminal Box with WHITE text */
                .terminal-box { background-color: #1e1e1e; color: #ffffff; font-family: 'Courier New', Courier, monospace; font-size: 11px; padding: 15px; border-radius: 8px; height: 200px; overflow-y: auto; white-space: pre-wrap; margin-top: 10px; border: 1px solid #333; line-height: 1.4; }
                .terminal-box::-webkit-scrollbar { width: 8px; }
                .terminal-box::-webkit-scrollbar-thumb { background: #555; border-radius: 4px; }
                
                ul { list-style-type: none; padding: 0; margin-top: 10px; }
                li { background: #f8f9fa; border-bottom: 1px solid #e8eaed; padding: 10px; font-size: 13px; display: flex; justify-content: space-between; align-items: center; }
                li:last-child { border-bottom: none; }
                .time { font-size: 11px; color: #80868b; }
                .msg-link { color: #1a73e8; text-decoration: none; font-weight: bold; font-size: 12px; padding-left: 10px; }
            </style>
        </head>
        <body>
            <div class="card">
                <h2>⚙️ Control Panel</h2>
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

                <div class="settings-bar">
                    <span class="settings-text">🗑️ Auto-delete files after upload</span>
                    <label class="switch">
                        <input type="checkbox" id="auto-del-toggle" onchange="toggleAutoDelete()">
                        <span class="slider"></span>
                    </label>
                </div>
                
                <div style="text-align: center; display: flex; justify-content: space-between;">
                    <button onclick="sendAction('pause')" class="btn btn-pause">⏸️ PAUSE</button>
                    <button onclick="sendAction('resume')" class="btn btn-resume">▶️ RESUME</button>
                </div>

                <div id="progress-box" class="progress-container">
                    <div class="file-name">⬆️ <span id="p-file">Uploading...</span></div>
                    <div class="progress-bar-bg"><div id="p-bar" class="progress-bar-fill"></div></div>
                    <div class="progress-stats">
                        <span id="p-percent">0%</span>
                        <span id="p-speed" style="color: #1e8e3e;">0 KB/s</span>
                        <span id="p-eta">0s left</span>
                    </div>
                    <div id="p-size" class="progress-size">0 KB / 0 KB</div>
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
            </div>

            <script>
                function sendAction(action) { fetch('/api/action/' + action).then(res => fetchStats()); }

                function formatBytes(bytes) {
                    if (bytes === 0) return '0 Bytes';
                    const k = 1024;
                    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
                    const i = Math.floor(Math.log(bytes) / Math.log(k));
                    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
                }

                function formatSpeed(bytesPerSec) {
                    if (bytesPerSec < 1024 * 1024) return (bytesPerSec / 1024).toFixed(1) + ' KB/s';
                    else return (bytesPerSec / (1024 * 1024)).toFixed(2) + ' MB/s';
                }

                function toggleAutoDelete() {
                    let isChecked = document.getElementById('auto-del-toggle').checked;
                    fetch('/api/settings', {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({auto_delete: isChecked})
                    });
                }

                function fetchFoldersAndSettings() {
                    fetch('/api/config').then(res => res.json()).then(data => {
                        // Update toggle switch
                        document.getElementById('auto-del-toggle').checked = data.auto_delete_after_upload || false;
                        
                        // Update folder list
                        let listHTML = ''; let count = 0;
                        let folders = data.folders || {};
                        for (const [name, rules] of Object.entries(folders)) {
                            let ruleText = Object.entries(rules).map(([t, id]) => `<span style="background:#e8eaed; padding:2px 5px; border-radius:4px; font-size:10px; color:#555;">${t}: ${id}</span>`).join(" ");
                            listHTML += `<li>
                                <div style="display:flex; flex-direction:column;">
                                    <span>📁 <b>${name}</b></span>
                                    <div style="margin-top:4px;">${ruleText}</div>
                                </div>
                                <button onclick="deleteFolder('${name}')" style="background:none; border:none; font-size:16px; cursor:pointer;">🗑️</button>
                            </li>`;
                            count++;
                        }
                        document.getElementById('folder-list').innerHTML = count > 0 ? listHTML : "<li style='justify-content:center; color:#888;'>No rules added</li>";
                    });
                }

                function addFolder() {
                    let name = document.getElementById('f-name').value.trim();
                    let type = document.getElementById('f-type').value;
                    let topic = parseInt(document.getElementById('f-topic').value);
                    if(!name || isNaN(topic)) { alert("Invalid input!"); return; }
                    
                    fetch('/api/folders', {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({name: name, file_type: type, topic_id: topic})
                    }).then(() => {
                        document.getElementById('f-name').value = '';
                        document.getElementById('f-topic').value = '';
                        fetchFoldersAndSettings(); 
                    });
                }

                function deleteFolder(name) {
                    if(!confirm(`Remove all rules for '${name}'?`)) return;
                    fetch('/api/folders/' + name, { method: 'DELETE' }).then(() => fetchFoldersAndSettings());
                }

                function fetchLogs() {
                    fetch('/api/logs').then(res => res.json()).then(data => {
                        let logViewer = document.getElementById('log-viewer');
                        let isScrolledToBottom = logViewer.scrollHeight - logViewer.clientHeight <= logViewer.scrollTop + 10;
                        logViewer.innerText = data.logs;
                        if (isScrolledToBottom) logViewer.scrollTop = logViewer.scrollHeight;
                    });
                }

                function fetchStats() {
                    fetch('/api/stats').then(res => res.json()).then(data => {
                        let statusEl = document.getElementById('bot-status');
                        statusEl.innerText = data.status;
                        statusEl.className = 'status ' + data.status;
                        
                        document.getElementById('total-count').innerText = data.total_uploaded;
                        document.getElementById('queue-count').innerText = data.queued_files;
                        
                        let pBox = document.getElementById('progress-box');
                        if (data.status === 'running' && data.progress.status === 'uploading') {
                            pBox.style.display = 'block';
                            document.getElementById('p-file').innerText = data.progress.file_name;
                            document.getElementById('p-bar').style.width = data.progress.percentage + '%';
                            document.getElementById('p-percent').innerText = data.progress.percentage + '%';
                            
                            document.getElementById('p-speed').innerText = formatSpeed(data.progress.speed);
                            document.getElementById('p-eta').innerText = data.progress.eta + 's left';
                            document.getElementById('p-size').innerText = formatBytes(data.progress.current) + ' / ' + formatBytes(data.progress.total);
                        } else { pBox.style.display = 'none'; }

                        let listHTML = '';
                        data.recent_uploads.forEach(file => {
                            let linkHtml = file.link ? `<a href="${file.link}" target="_blank" class="msg-link">🔗 Link</a>` : '';
                            listHTML += `<li>
                                <span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 55%;">📄 ${file.name}</span>
                                <div style="display:flex; align-items:center;">
                                    <span class="time">${file.time}</span>
                                    ${linkHtml}
                                </div>
                            </li>`;
                        });
                        document.getElementById('recent-list').innerHTML = listHTML || "<li style='justify-content:center; color:#888;'>No files yet</li>";
                    });
                }

                fetchFoldersAndSettings();
                fetchStats();
                fetchLogs(); 
                
                setInterval(fetchStats, 1000); 
                setInterval(fetchLogs, 2000); 
            </script>
        </body>
    </html>
    """
    return html_content


