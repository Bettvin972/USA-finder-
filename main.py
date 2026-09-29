import os, re, time, threading, requests
from bs4 import BeautifulSoup
from flask import Flask

app = Flask(__name__)
@app.route('/')
def home(): return "USA Finder Bot Running 24/7"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8760780904:AAFrL4XCoGz-VR6iulMx9jhfO7R8QMuiUo8")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8910917503")

TARGET_URLS = [
    "https://groupsor.link/group/country/United_States",
    "https://groupsor.link/group/category/Education",
    "https://groupsor.link/group/category/Travel",
    "https://groupsor.link/group/category/Housing",
    "https://wglfinder.com/america-whatsapp-group-link/",
    "https://wachannelsfinder.com/country/united-states-of-america/",
    "https://whatsgrouplink.com/usa-whatsapp-group-link/",
]
WA_LINK_PATTERN = r"https://chat\.whatsapp\.com/[A-Za-z0-9]{20,24}"
US_KEYWORDS = ["usa","texas","dallas","houston","austin","california","new york","florida","university","carpool","rideshare","ride","accommodation","roommate","housing","lease","sublease","room available","airport ride"]
STRICT_EXCLUSIONS = ["kenya","nairobi","india","nigeria","forex","crypto","betting","porn","xxx"]

FILE_DB = "us_student_groups.txt"
discovered_links = set()

def extract_links(url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        return list(set(re.findall(WA_LINK_PATTERN, r.text)))
    except: return []

def validate_group(invite_url):
    try:
        r = requests.get(invite_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        low = r.text.lower()
        if "invalid" in low or "revoked" in low: return {"valid": False}
        soup = BeautifulSoup(r.text, 'html.parser')
        title = soup.find("meta", property="og:title")
        name = title["content"] if title else ""
        l = name.lower()
        if any(b in l for b in STRICT_EXCLUSIONS): return {"valid": False}
        if not any(k in l for k in US_KEYWORDS): return {"valid": False}
        return {"valid": True, "name": name, "url": invite_url}
    except: return {"valid": False}

def send_telegram(name, url):
    try:
        api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        tag = "🏠 ROOM" if "room" in name.lower() or "housing" in name.lower() else "🚗 RIDE"
        requests.post(api, json={"chat_id": TELEGRAM_CHAT_ID, "text": f"{tag} 🇺🇸 {name}\n{url}"}, timeout=10)
    except: pass

def run_pipeline():
    while True:
        try:
            for target in TARGET_URLS:
                for link in extract_links(target):
                    if link in discovered_links: continue
                    discovered_links.add(link)
                    info = validate_group(link)
                    if info["valid"]:
                        send_telegram(info['name'], info['url'])
                        with open(FILE_DB, "a") as f: f.write(f"{info['name']} | {info['url']}\n")
                    time.sleep(2)
        except: pass
        time.sleep(1800)

# Start bot in background thread
threading.Thread(target=run_pipeline, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
