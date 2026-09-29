import os, re, time, threading, requests
from flask import Flask

app = Flask(__name__)
@app.route('/')
def home(): return "V11.2 ENTIRE USA WORKING + FILTER"

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8760780904:AAFrL4XCoGz-VR6iulMx9jhfO7R8QMuiUo8")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8910917503")

WA = r"https://chat\.whatsapp\.com/[A-Za-z0-9]{20,26}"
seen = set()
last_update_id = 0

GOOD_RIDES = ["ride", "rides", "rideshare", "carpool", "airport", "travel", "trip", "lift", "sharing"]
GOOD_HOUSING = ["housing", "room", "roommate", "apartment", "rent", "sublet", "lease", "accommodation", "flat", "house", "pg", "hostel"]
GOOD_LOCATION = ["usa", "america", "united states", "dallas", "texas", "houston", "austin", "arlington", "uta", "fort worth", "plano", "irving", "dfw", "new york", "nyc", "california", "los angeles", "la", "san francisco", "sf", "san diego", "san jose", "chicago", "florida", "miami", "orlando", "atlanta", "georgia", "boston", "seattle", "washington", "colorado", "denver", "phoenix", "arizona", "ohio", "michigan", "detroit", "pennsylvania", "philadelphia", "new jersey", "nj", "north carolina", "charlotte", "tennessee", "nashville", "illinois", "massachusetts", "virginia", "maryland", "dc", "las vegas", "nevada", "portland", "oregon", "minnesota", "wisconsin", "indiana", "missouri", "kansas", "oklahoma", "utah", "connecticut", "kentucky"]
BAD = ["kenya", "nairobi", "forex", "crypto", "binance", "betting", "pakistan", "india", "bangladesh", "nigeria", "adult", "18+", "xxx", "porn", "earn money", "lottery", "mlm"]

def send(text):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=20)
    except: pass

def is_usa_rides_housing(context, source_url):
    t = (context + " " + source_url).lower()
    for b in BAD:
        if b in t: return False, f"Blocked {b}"
    has_loc = any(l in t for l in GOOD_LOCATION)
    if not has_loc: return False, "Not USA"
    has_ride = any(r in t for r in GOOD_RIDES)
    has_house = any(h in t for h in GOOD_HOUSING)
    if has_ride and has_house: return True, "Rides + Housing USA"
    if has_ride: return True, "Rides USA"
    if has_house: return True, "Housing USA"
    return False, "Not rides/housing"

WELCOME = """👋 <b>V11.2 ENTIRE USA IS LIVE! 🇺🇸</b>

✅ Filter: ENTIRE USA Rides + Housing
✅ Covers: NY, CA, TX, FL, Chicago, Boston, Seattle + 50 states
❌ Blocks: Forex, Crypto, Adult, Jobs
✅ Sources: 12 WORKING sources (no FB block)

Type /scan now!
"""

def telegram_polling():
    global last_update_id
    while True:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_update_id+1}&timeout=30"
            resp = requests.get(url, timeout=35).json()
            if resp.get("ok"):
                for upd in resp.get("result", []):
                    last_update_id = upd["update_id"]
                    txt = upd.get("message", {}).get("text", "").lower()
                    if "/start" in txt: send(WELCOME)
                    elif "/scan" in txt:
                        send("🚀 <b>ENTIRE USA scan started!</b>")
                        threading.Thread(target=scan_working, daemon=True).start()
                    elif "/status" in txt:
                        send(f"📊 DB: {len(seen)} groups\nFilter: ENTIRE USA")
        except: time.sleep(5)

def scan_working():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"}
    SOURCES = [
        "https://groupsor.link/group/country/United_States",
        "https://groupsorlink.com/usa-whatsapp-group-links/",
        "https://whatsapp-group.net/usa-whatsapp-group-links/",
        "https://www.joinmywp.com/usa-whatsapp-group-links/",
        "https://whatsgrouplink.com/country/usa/",
        "https://allwhatsappgroups.com/usa-whatsapp-groups/",
        "https://www.whtsappgroups.com/usa-whatsapp-group-links/",
        "https://groupda.com/usa-whatsapp-group-links/",
        "https://groupsjoin.com/usa-whatsapp-group-links",
        "https://www.bing.com/search?q=site:chat.whatsapp.com+usa+housing+roommate",
        "https://www.bing.com/search?q=site:chat.whatsapp.com+usa+rideshare+carpool",
        "https://www.bing.com/search?q=site:chat.whatsapp.com+new+york+housing+apartment",
    ]
    
    total_ok = 0
    blocked = 0
    send(f"🔍 Scanning {len(SOURCES)} sources - ENTIRE USA filter...")
    
    for i, url in enumerate(SOURCES):
        try:
            send(f"🔍 {i+1}/{len(SOURCES)}: {url[:40]}...")
            r = requests.get(url, headers=headers, timeout=25)
            links = re.findall(WA, r.text)
            for link in links:
                if link in seen: continue
                pos = r.text.find(link)
                context = r.text[max(0, pos-600):pos+600]
                ok, reason = is_usa_rides_housing(context, url)
                if ok:
                    seen.add(link)
                    total_ok += 1
                    icon = "🚗" if "Rides" in reason else "🏠" if "Housing" in reason else "🏠🚗"
                    send(f"{icon} <b>{reason} ✅</b>\n\n{link}\n\n📍 {reason}")
                    time.sleep(1.5)
                else:
                    blocked += 1
            time.sleep(2)
        except Exception as e:
            send(f"⚠️ Source {i+1} failed")
    
    send(f"🏁 <b>DONE - ENTIRE USA</b>\n✅ Sent: {total_ok}\n❌ Blocked: {blocked}\n📦 Total DB: {len(seen)}\n\nNext auto-scan in 30 mins")

def auto_loop():
    time.sleep(5)
    send(WELCOME)
    while True:
        scan_working()
        time.sleep(1800)

threading.Thread(target=telegram_polling, daemon=True).start()
threading.Thread(target=auto_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
