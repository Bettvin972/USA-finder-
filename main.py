import os, re, time, threading, requests, cloudscraper
from flask import Flask

app = Flask(__name__)
@app.route('/')
def home(): return "V13.1 ONLY REAL WA LINKS - FIXED"

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8760780904:AAFrL4XCoGz-VR6iulMx9jhfO7R8QMuiUo8")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8910917503")

WA = r"https://chat\.whatsapp\.com/[A-Za-z0-9]{20,26}"
seen = set()
scraper = cloudscraper.create_scraper()

def send(text):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=20)
    except: pass

def get_bypass(url):
    try:
        r = scraper.get(url, timeout=25)
        if r.status_code == 200 and "chat.whatsapp.com" in r.text:
            return r.text
    except: pass
    try:
        r = requests.get(f"https://api.allorigins.win/raw?url={url}", timeout=25)
        if "chat.whatsapp.com" in r.text:
            return r.text
    except: pass
    try:
        r = requests.get(f"https://api.codetabs.com/v1/proxy?quest={url}", timeout=25)
        if "chat.whatsapp.com" in r.text:
            return r.text
    except: pass
    return ""

def scan_v13():
    SOURCES = [
        "https://groupsor.link/group/country/United_States",
        "https://whatsgrouplink.com/usa/",
        "https://groupsjoin.com/usa-whatsapp-group-links",
        "https://www.whatsappgroupslink.com/search/label/USA",
    ]
    
    total = 0
    send(f"🔍 <b>Scanning for REAL WhatsApp invites...</b>\nOnly chat.whatsapp.com links will be sent")
    
    for url in SOURCES:
        html = get_bypass(url)
        if not html:
            continue
        
        links = list(set(re.findall(WA, html)))
        for link in links:
            if link not in seen:
                seen.add(link)
                total += 1
                # ONLY REAL WA LINK - NO SOURCE URL
                send(f"🇺🇸 <b>ENTIRE USA GROUP #{total}</b>\n\n{link}\n\n📍 USA Housing / Rides - Tap to join 👆")
                time.sleep(1.5)
    
    if total == 0:
        send(f"⚠️ <b>Found 0 real invites</b>\nRender IP blocked. Try manual scan later.")
    else:
        send(f"🏁 <b>DONE - ENTIRE USA</b>\n✅ Sent: {total} REAL WhatsApp links\n📦 Total DB: {len(seen)}\nNext auto-scan in 10 mins")

def telegram_polling():
    try: requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook", timeout=5)
    except: pass
    last_id = 0
    while True:
        try:
            resp = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_id+1}&timeout=30", timeout=35).json()
            if resp.get("ok"):
                for u in resp.get("result", []):
                    last_id = u["update_id"]
                    txt = u.get("message", {}).get("text","").lower()
                    if "/start" in txt:
                        send("👋 <b>V13.1 LIVE! 🇺🇸</b>\n\n✅ Only sends REAL WhatsApp links\n✅ chat.whatsapp.com/xxxxx\n✅ Entire USA Housing + Rides\n\nCommands:\n/scan - scan now\n/status - count")
                    elif "/scan" in txt:
                        threading.Thread(target=scan_v13, daemon=True).start()
                    elif "/status" in txt:
                        send(f"📊 Total real groups found: {len(seen)}")
        except: time.sleep(3)

def auto_loop():
    time.sleep(4)
    send("👋 <b>V13.1 STARTED - ONLY REAL WA LINKS</b>\nAuto-scan entire USA every 10 mins")
    while True:
        scan_v13()
        time.sleep(600)

threading.Thread(target=telegram_polling, daemon=True).start()
threading.Thread(target=auto_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
