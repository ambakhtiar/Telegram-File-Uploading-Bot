# 🚀 Telegram Smart Auto-Uploader

A powerful, fully automated, and secure background bot that syncs your local device files to Telegram Topics. It comes with a beautiful Web Dashboard for easy control and monitoring!

---

## ✨ Features

- **🌐 Web Control Panel:** Manage everything from a beautiful, responsive web dashboard.
- **🗂️ Smart Routing:** Automatically send Images to one topic and Videos to another topic from the same folder.
- **🗑️ Auto-Delete (Danger Zone):** Automatically delete files from local storage after a successful upload to save phone memory.
- **🖥️ Live Console:** Watch live terminal logs directly from your browser.
- **🔍 Full History & Search:** Infinite scroll history with instant search functionality.
- **🔒 Secure Access:** PIN-protected dashboard to ensure privacy on your network.

---

## ⚙️ How to Get Telegram API ID & Hash

Before starting, you need your API credentials from Telegram:
1. Go to [my.telegram.org](https://my.telegram.org) and log in with your phone number.
2. Click on **"API development tools"**.
3. Fill in the basic details (App title, short name) and click **"Create application"**.
4. Save your **App api_id** and **App api_hash** safely.

---

## 🛠️ Installation & Setup (Termux / Android)

### Step 1: Install Prerequisites
Open Termux and run the following commands:
```bash
pkg update && pkg upgrade -y
pkg install python git rust binutils clang make libffi openssl -y

```
### Step 2: Clone the Repository
```bash
git clone [https://github.com/ambakhtiar/Telegram-File-Uploading-Bot](https://github.com/ambakhtiar/Telegram-File-Uploading-Bot)
cd Telegram-File-Uploading-Bot

```
### Step 3: Install Required Python Packages
```bash
pip install telethon fastapi uvicorn pydantic python-dotenv
# To boost upload speed, install cryptg (Takes a few minutes):
pip install cryptg

```
### Step 4: Configure the Environment
Create a .env file and add your credentials:
```bash
nano .env 

```
**Paste the following and replace with your data:**
```env
API_ID=your_api_id_here
API_HASH=your_api_hash_here
GROUP_ID=-100xxxxxxxxxx
DASHBOARD_PIN=1234

```
*(Press CTRL + O, Enter to save, and CTRL + X to exit.)*
## 🚀 Running the Bot
You need to run two processes. You can do this by opening two separate sessions (tabs) in Termux.
### Session 1: Start the Background Engine
```bash
python bot.py 

```
*(The first time you run this, it will ask for your Telegram phone number and OTP to authenticate).*
### Session 2: Start the Web Dashboard
```bash
uvicorn api:app --host 0.0.0.0 --port 8000

```
## 🎮 How to Use
 1. Open your browser and go to http://localhost:8000 (or your phone's local IP, e.g., http://192.168.0.x:8000).
 2. Enter the **PIN** you set in the .env file.
 3. In the **"Smart Folders"** section:
   * Enter a folder path (e.g., /sdcard/DCIM/Camera).
   * Select the file type (e.g., Images Only).
   * Enter the **Telegram Topic ID**.
 4. Click **Add Rule** and watch the magic happen! The bot will instantly queue the files and start uploading.

## 📝 License
This project is for personal use and educational purposes. Use it responsibly. 



