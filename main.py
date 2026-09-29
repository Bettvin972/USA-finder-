import os
import re
import time
import threading
import requests
import cloudscraper
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "WhatsApp Link Scraper V14.2 - Active"

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

WA_REGEX = r"https?://chat\.whatsapp\.com/([A-Za-z0-9]{20,26})"
REDIRECT_REGEX = r'href=["\'](/join/[^"\']+|/group/[^"\']+|redirect\.php\?[^"\']+)["\']'

seen = set()
scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})

def send_telegram(text):
    if not TOKEN or not CHAT_ID: return
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=15)
    except: pass

def is_alive(link):
    try:
        r = requests.get(link, timeout=10, headers={"User-Agent":"Mozilla/5.0"})
        t = r.text.lower()
        if any(x in t for x in ["invalid invite link", "expired", "couldn't find", "revoked", "you can't join"]):
            return False
        return "join group" in t or "join chat" in t
    except:
        return False

def fetch_url(url):
    try:
        res = scraper.get(url, timeout=20, allow_redirects=True)
        if res.status_code == 200:
            return res.text, res.url
    except: pass
    return "", url

def resolve_redirect_link(base_url, path):
    if path.startswith("/"):
        domain = "/".join(base_url.split("/")[:3])
        target = f"{domain}{path}"
    else:
        target = path
    html, final_url = fetch_url(target)
    m = re.search(WA_REGEX, final_url)
    if m:
        return f"https://chat.whatsapp.com/{m.group(1)}"
    found = re.findall(WA_REGEX, html)
    if found:
        code = found[0] if isinstance(found[0], str) else found[0]
        # clean if full url returned
        if "chat.whatsapp.com" in code:
            return code
        return f"https://chat.whatsapp.com/{code}"
    return None

def scan_whatsapp_groups():
    SOURCES = [
        "https://whatsgrouplink.com/usa/",
        "https://groupsjoin.com/usa-whatsapp-group-links",
        "https://www.whatsappgroupslink.com/search/label/USA",
        "https://bgk.co.in/whatsapp-group-links-usa/"
    ]
    total_new = 0
    send_telegram("🔍 <b>V14.2 Scanning + LIVE check...</b>")
    for src in SOURCES:
        html, cur = fetch_url(src)
        if not html: continue
        for code in re.findall(WA_REGEX, html):
            full = f"https://chat.whatsapp.com/{code}" if "chat.whatsapp.com" not in code else code
            if full not in seen and is_alive(full):
                seen.add(full)
                total_new += 1
                send_telegram(f"🇺🇸 <b>LIVE Group #{total_new}</b>\n\n{full}")
                time.sleep(1.2)
        for path in set(re.findall(REDIRECT_REGEX, html)[:20]):
            wa = resolve_redirect_link(cur, path)
            if wa and wa not in seen and is_alive(wa):
                seen.add(wa)
                total_new += 1
                send_telegram(f"🇺🇸 <b>LIVE Group #{total_new} (redirect)</b>\n\n{wa}")
                time.sleep(1.2)
    if total_new == 0:
        send_telegram("⚠️ No NEW live links this run. Next in 10m")
    else:
        send_telegram(f"🏁 Done. {total_new} LIVE new. Total: {len(seen)}")

def telegram_polling():
    try: requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook", timeout=5)
    except: pass
    last_id = 0
    while True:
        try:
            res = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_id+1}&timeout=30", timeout=35).json()
            if res.get("ok"):
                for u in res.get("result", []):
                    last_id = u["update_id"]
                    txt = u.get("message", {}).get("text", "").lower()
                    if "/start" in txt:
                        send_telegram("👋 <b>V14.2 Active - LIVE check ON</b>\n/scan - manual\n/status - count")
                    elif "/scan" in txt:
                        threading.Thread(target=scan_whatsapp_groups, daemon=True).start()
                    elif "/status" in txt:
                        send_telegram(f"📊 LIVE cached: {len(seen)}")
        except: time.sleep(3)

def auto_loop():
    time.sleep(10)
    while True:
        scan_whatsapp_groups()
        time.sleep(600)

# FIX FOR GUNICORN - START THREADS ON IMPORT, NOT IN __main__
if TOKEN and CHAT_ID:
    threading.Thread(target=telegram_polling, daemon=True).start()
    threading.Thread(target=auto_loop, daemon=True).start()
    print("V14.2 Threads started for gunicorn")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

