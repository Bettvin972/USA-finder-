import os, re, time, threading, requests
from flask import Flask

app = Flask(__name__)
@app.route('/')
def home(): return "V10 RIDES+Housing USA ONLY LIVE"

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8760780904:AAFrL4XCoGz-VR6iulMx9jhfO7R8QMuiUo8")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8910917503")

WA = r"https://chat\.whatsapp\.com/[A-Za-z0-9]{20,26}"
seen = set()
last_update_id = 0

# --- FINAL PERFECT FILTER: RIDES + ACCOMMODATION USA ---
GOOD_RIDES = ["ride", "rides", "rideshare", "carpool", "car pooling", "lift", "travel", "trip", "airport", "dfw airport", "going to dallas", "from dallas", "austin to dallas", "houston to dallas"]
GOOD_HOUSING = ["housing", "accommodation", "room", "roommate", "roommates", "roomie", "apartment", "flat", "rent", "sublet", "sublease", "lease", "pg", "hostel", "stay", "house for rent"]
GOOD_LOCATION = ["usa", "america", "dallas", "texas", "arlington", "uta", "ut arlington", "dfw", "fort worth", "plano", "irving", "denton", "richardson", "houston", "austin"]

BAD = ["kenya", "nairobi", "mombasa", "forex", "crypto", "binance", "trading", "betting", "bet", "earn money", "make money", "pakistan", "india", "nigeria", "bangladesh", "adult", "18+", "hot girls", "xxx", "lottery", "forex signals", "investment", "job", "jobs", "hiring"]

def send(text):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=20)
        print(text[:100])
    except: pass

def is_rides_or_housing_usa(context, source_url):
    t = (context + " " + source_url).lower()
    
    # 1. BLOCK bad
    for b in BAD:
        if b in t:
            return False, f"Blocked spam: {b}"
    
    # 2. MUST have location = USA region
    has_location = any(loc in t for loc in GOOD_LOCATION)
    if not has_location:
        return False, "Not USA/Dallas"
    
    # 3. MUST have rides OR housing keyword
    has_ride = any(r in t for r in GOOD_RIDES)
    has_housing = any(h in t for h in GOOD_HOUSING)
    
    if has_ride and has_housing:
        return True, "Rides + Housing USA"
    if has_ride:
        return True, "Rides USA"
    if has_housing:
        return True, "Housing USA"
    
    return False, "Not rides/housing"

WELCOME = """👋 <b>USA Rides & Housing Finder PRO 🇺🇸</b>

<b>Perfect Filter ON:</b>
✅ ONLY: Rides + Accommodation
✅ ONLY: USA Dallas/Texas/UTA/DFW
❌ BLOCK: Kenya, Forex, Jobs, Adult, Crypto

<b>You will get:</b>
🏠 Dallas housing WhatsApp groups
🚗 Dallas rideshare WhatsApp groups
💬 Found via FB + GroupMe + Telegram + Twitter + Reddit

<b>Live Updates:</b>
🔍 Searching...
💬 Found instantly!
🏁 Scan complete

Commands:
/start - Welcome
/status - Filter stats
/scan - Scan now
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
                    text = upd.get("message", {}).get("text", "").lower()
                    if "/start" in text:
                        send(WELCOME)
                    elif "/status" in text:
                        send(f"✅ <b>Rides + Housing Filter</b>\n✅ Rides keywords: {len(GOOD_RIDES)}\n✅ Housing keywords: {len(GOOD_HOUSING)}\n✅ USA locations: {len(GOOD_LOCATION)}\n❌ Blocked: {len(BAD)} spam types\n📦 Found: {len(seen)} groups")
                    elif "/scan" in text:
                        send("🚀 Scanning for USA Rides + Housing only...")
                        threading.Thread(target=scan_live, daemon=True).start()
        except:
            time.sleep(5)

def scan_live():
    headers = {"User-Agent": "Mozilla/5.0"}
    SOURCES = {
        "📘 Facebook - Dallas Housing": ["https://mbasic.facebook.com/groups/utarlingtonhousing/", "https://mbasic.facebook.com/groups/dallashousing/", "https://mbasic.facebook.com/groups/DallasFortWorthHousing/"],
        "📘 Facebook - Dallas Rides": ["https://mbasic.facebook.com/groups/UTArideshare/", "https://mbasic.facebook.com/groups/dallasrideshare/"],
        "👥 GroupMe": ["https://app.groupme.com/discover?query=dallas+housing", "https://app.groupme.com/discover?query=dallas+rideshare+uta"],
        "✈️ Telegram": ["https://t.me/s/USAWhatsAppGroups", "https://t.me/s/DallasHousingGroups", "https://t.me/s/DallasRideshare"],
        "🐦 Twitter/X": ["https://nitter.net/search?f=tweets&q=Dallas+housing+chat.whatsapp.com", "https://nitter.net/search?f=tweets&q=Dallas+rideshare+chat.whatsapp.com"],
        "💬 USA Directories": ["https://groupsorlink.com/usa-whatsapp-group-links/", "https://whatsapp-group.net/usa-whatsapp-group-links/", "https://www.whtsappgroups.com/usa-whatsapp-group-links/", "https://groupsor.link/group/country/United_States"]
    }
    
    total_ok = 0
    total_bad = 0
    
    for platform, urls in SOURCES.items():
        send(f"🔍 <b>Searching {platform} for Rides + Housing USA...</b>")
        time.sleep(1)
        
        for url in urls:
            try:
                r = requests.get(url, headers=headers, timeout=15)
                links = re.findall(WA, r.text)
                
                for link in links:
                    if link in seen: continue
                    pos = r.text.find(link)
                    context = r.text[max(0, pos-600):pos+600]
                    
                    ok, reason = is_rides_or_housing_usa(context, url)
                    
                    if ok:
                        seen.add(link)
                        total_ok += 1
                        # Different emoji for rides vs housing
                        icon = "🚗" if "ride" in reason.lower() else "🏠"
                        send(f"{icon} <b>PERFECT MATCH: {reason} ✅</b>\n\n{link}\n\n📍 Via: {platform}\n🎯 {reason}\n🔗 {url[:35]}\n\nJoin fast!")
                        time.sleep(2)
                    else:
                        total_bad += 1
            except Exception as e:
                print(f"Err {url}: {e}")
    
    send(f"🏁 <b>SCAN DONE - Rides + Housing Only</b>\n\n✅ Sent: {total_ok} USA Rides/Housing groups\n❌ Blocked: {total_bad} irrelevant groups\n📦 Total DB: {len(seen)}\n\nNext scan in 30 mins. Type /scan for instant!")

def auto_loop():
    time.sleep(5)
    send(WELCOME)
    while True:
        scan_live()
        send("💤 Sleeping 30 mins - Filter: Rides + Housing USA Only")
        time.sleep(1800)

threading.Thread(target=telegram_polling, daemon=True).start()
threading.Thread(target=auto_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
