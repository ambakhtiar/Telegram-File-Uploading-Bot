import os
import asyncio
import logging
import sqlite3
import hashlib
import signal
import json
import time
from datetime import datetime
from telethon import TelegramClient, errors
from dotenv import load_dotenv

# ================= INITIALIZATION =================
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PROJECT_DIR, '.env'))

API_ID   = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH', '')
GROUP_ID = int(os.getenv('GROUP_ID', 0))

BASE_DIR = os.path.expanduser('~/storage/shared/DCIM')
DB_FILE = os.path.join(PROJECT_DIR, 'uploads.db')
SESSION_FILE = os.path.join(PROJECT_DIR, 'backup_session')
STATE_FILE = os.path.join(PROJECT_DIR, 'state.json')
CONFIG_FILE = os.path.join(PROJECT_DIR, 'config.json')
LOG_FILE = os.path.join(PROJECT_DIR, 'uploader.log')
PROGRESS_FILE = os.path.join(PROJECT_DIR, 'progress.json')
QUEUE_FILE = os.path.join(PROJECT_DIR, 'queue.json') # নতুন কিউ ট্র্যাকিং ফাইল

MAX_CONCURRENT_UPLOADS = 1 
DELAY_BETWEEN_UPLOADS  = 1.5
UPLOAD_RETRY_LIMIT     = 3
SCAN_INTERVAL          = 3 # ইন্সট্যান্ট ফিল দেওয়ার জন্য ৩ সেকেন্ড করা হলো

# ================= LOGGING SETUP =================
class SpacedFormatter(logging.Formatter):
    def format(self, record): return f"\n{super().format(record)}"

logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

# ================= CONFIG & STATE MANAGER =================
def get_config():
    try:
        with open(CONFIG_FILE, 'r') as f: return json.load(f)
    except: return {"auto_delete_after_upload": False, "folders": {}}

def get_current_state():
    if not os.path.exists(STATE_FILE): return "running"
    try:
        with open(STATE_FILE, 'r') as f: return json.load(f).get("status", "running")
    except: return "running"

def update_progress(data):
    try:
        with open(PROGRESS_FILE, 'w') as f: json.dump(data, f)
    except: pass

def update_queue_count(count):
    try:
        with open(QUEUE_FILE, 'w') as f: json.dump({"count": count}, f)
    except: pass

# ================= DATABASE MANAGER =================
class Database:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute('''CREATE TABLE IF NOT EXISTS uploads 
            (file_hash TEXT PRIMARY KEY, file_name TEXT, file_path TEXT, topic_id INTEGER, uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        self.conn.commit()

    def is_uploaded(self, file_hash):
        return bool(self.conn.execute("SELECT 1 FROM uploads WHERE file_hash=?", (file_hash,)).fetchone())

    def mark_uploaded(self, file_hash, file_name, file_path, topic_id):
        self.conn.execute("INSERT INTO uploads (file_hash, file_name, file_path, topic_id) VALUES (?,?,?,?)",
                          (file_hash, file_name, file_path, topic_id))
        self.conn.commit()

    def close(self): self.conn.close()

# ================= UTILITIES =================
def generate_file_hash(file_path):
    try:
        stats = os.stat(file_path)
        return hashlib.md5(f"{file_path}_{stats.st_size}_{stats.st_mtime}".encode()).hexdigest(), stats
    except: return None, None

def get_device_info(file_path):
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.webp']:
            from PIL import Image, ExifTags
            with Image.open(file_path) as img:
                exif = img.getexif()
                if not exif: return None
                make, model = "", ""
                for tag_id, value in exif.items():
                    tag = ExifTags.TAGS.get(tag_id, tag_id)
                    if tag == 'Make': make = str(value).strip()
                    elif tag == 'Model': model = str(value).strip()
                if make or model:
                    if make and make.lower() in model.lower(): return model
                    return f"{make} {model}".strip()
        return None
    except: return None

def format_metadata(file_name, file_path, stats):
    size_mb = round(stats.st_size / (1024 * 1024), 2)
    dt_modified = datetime.fromtimestamp(stats.st_mtime).strftime('%d %b %Y, %I:%M %p')
    ext = os.path.splitext(file_name)[1]
    hashtag = f"#{ext[1:].lower()}" if ext else "#unknown"
    
    caption = f"📄 **{file_name}**\n\n💾 **Size:** {size_mb} MB\n📅 **Date:** {dt_modified}"
    device = get_device_info(file_path)
    if device: caption += f"\n📱 **Device:** {device}"
    caption += f"\n\n🏷️ {hashtag}"
    return caption

# ================= SCANNER =================
def scan_and_sort_files(db):
    files_to_upload = []
    config = get_config()
    folder_map = config.get("folders", {})

    for folder_name, topic_id in folder_map.items():
        folder_path = os.path.join(BASE_DIR, folder_name)
        if not os.path.exists(folder_path): continue
            
        for root, _, files in os.walk(folder_path):
            for file in files:
                full_path = os.path.join(root, file)
                file_hash, stats = generate_file_hash(full_path)
                if file_hash and not db.is_uploaded(file_hash):
                    files_to_upload.append({
                        'folder_name': folder_name, # ফোল্ডারের নাম সেভ রাখা হলো
                        'path': full_path, 'name': file, 'hash': file_hash,
                        'mtime': stats.st_mtime, 'stats': stats, 'topic_id': topic_id
                    })
    files_to_upload.sort(key=lambda x: x['mtime'])
    return files_to_upload

# ================= UPLOADER CORE =================
async def upload_worker(name, client, db, queue, queued_hashes):
    while True:
        try:
            if get_current_state() == "paused":
                update_progress({"status": "idle"})
                await asyncio.sleep(2)
                continue 

            item = await queue.get()
            config = get_config()
            
            # --- Smart Drop Logic (Instant Delete) ---
            if item['folder_name'] not in config.get("folders", {}):
                queued_hashes.discard(item['hash'])
                queue.task_done()
                update_queue_count(len(queued_hashes))
                continue # ফোল্ডার কনফিগে না থাকলে ফাইল সাথে সাথে ড্রপ করে দেবে
            # ----------------------------------------

            if not os.path.exists(item['path']):
                logger.warning(f"[{name}] 👻 Skipped Ghost File: {item['name']}")
                queued_hashes.discard(item['hash'])
                queue.task_done()
                update_queue_count(len(queued_hashes))
                continue

            auto_delete = config.get("auto_delete_after_upload", False)
            caption = format_metadata(item['name'], item['path'], item['stats'])

            async def progress_callback(current, total):
                now = time.time()
                elapsed = now - start_time
                if elapsed == 0: elapsed = 0.1
                speed = current / elapsed  # Raw bytes per second
                percentage = (current / total) * 100
                eta = (total - current) / speed if speed > 0 else 0
                
                update_progress({
                    "status": "uploading", "file_name": item['name'],
                    "current": current, "total": total, "percentage": round(percentage, 1),
                    "speed": speed, "eta": round(eta) # Raw speed পাঠানো হচ্ছে
                })

            for attempt in range(1, UPLOAD_RETRY_LIMIT + 1):
                try:
                    logger.info(f"[{name}] 🚀 Uploading: {item['name']}")
                    start_time = time.time()
                    
                    await client.send_file(
                        GROUP_ID, item['path'], caption=caption,
                        reply_to=item['topic_id'], force_document=True,
                        progress_callback=progress_callback
                    )
                    
                    db.mark_uploaded(item['hash'], item['name'], item['path'], item['topic_id'])
                    logger.info(f"[{name}] ✅ Done: {item['name']}")
                    update_progress({"status": "idle"})

                    if auto_delete:
                        try: os.remove(item['path'])
                        except: pass

                    await asyncio.sleep(DELAY_BETWEEN_UPLOADS)
                    break 
                except errors.FloodWaitError as e:
                    logger.warning(f"[{name}] ⏳ FloodWait: Waiting {e.seconds}s")
                    update_progress({"status": "flood_wait", "seconds": e.seconds})
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logger.error(f"[{name}] ❌ Error on {item['name']}: {e}")
                    await asyncio.sleep(5)
                    
            queued_hashes.discard(item['hash'])
            queue.task_done()
            update_queue_count(len(queued_hashes)) # আপলোড শেষে কিউ আপডেট
            
        except asyncio.CancelledError:
            break

# ================= MAIN RUNNER =================
async def main():
    if not API_ID or not API_HASH or not GROUP_ID:
        logger.error("❌ Missing variables in .env file! Please check.")
        return

    update_progress({"status": "idle"})
    update_queue_count(0)
    
    logger.info("🌟 Starting Advanced Telegram Uploader...")
    db = Database(DB_FILE)
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)

    await client.start()
    logger.info("🤖 Bot Authenticated!")

    queue = asyncio.Queue()
    queued_hashes = set()

    # --- Background Rescanner Task ---
    async def rescanner_loop():
        while True:
            if get_current_state() == "running":
                new_files = await asyncio.to_thread(scan_and_sort_files, db)
                added_count = 0
                for item in new_files:
                    if item['hash'] not in queued_hashes:
                        queued_hashes.add(item['hash'])
                        queue.put_nowait(item)
                        added_count += 1
                if added_count > 0:
                    update_queue_count(len(queued_hashes))
                    logger.info(f"📥 Found & Queued {added_count} new files.")
            await asyncio.sleep(SCAN_INTERVAL)
            
    rescanner_task = asyncio.create_task(rescanner_loop())
    # ---------------------------------

    workers = [asyncio.create_task(upload_worker(f"Worker-{i+1}", client, db, queue, queued_hashes)) for i in range(MAX_CONCURRENT_UPLOADS)]
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM): 
        loop.add_signal_handler(sig, lambda: stop_event.set())

    await stop_event.wait()

    for w in workers: w.cancel()
    rescanner_task.cancel()
    db.close()
    await client.disconnect()
    logger.info("🛑 Bot offline safely.")

if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
