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
    return "WhatsApp Link Scraper V14 - Active"

# Environment variables
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Broad pattern to match direct WhatsApp invite links
WA_REGEX = r"https?://chat\.whatsapp\.com/([A-Za-z0-9]{20,26})"
# Pattern to identify potential internal redirect links on directory sites
REDIRECT_REGEX = r'href=["\'](/join/[^"\']+|/group/[^"\']+|redirect\.php\?[^"\']+)["\']'

seen = set()
scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
)

def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception:
        pass

def fetch_url(url):
    """Attempts direct scraper fetch, falling back to follow redirects."""
    try:
        res = scraper.get(url, timeout=20, allow_redirects=True)
        if res.status_code == 200:
            return res.text, res.url
    except Exception:
        pass
    return "", url

def resolve_redirect_link(base_url, path):
    """Resolves relative redirect paths to find underlying WhatsApp links."""
    if path.startswith("/"):
        # Build absolute URL from domain root
        domain = "/".join(base_url.split("/")[:3])
        target = f"{domain}{path}"
    else:
        target = path

    html, final_url = fetch_url(target)
    # Check if final redirected URL itself is a WhatsApp link
    wa_match = re.search(WA_REGEX, final_url)
    if wa_match:
        return wa_match.group(0)

    # Check HTML content of the redirection landing page
    wa_in_html = re.findall(WA_REGEX, html)
    if wa_in_html:
        return wa_in_html[0]
    
    return None

def scan_whatsapp_groups():
    SOURCES = [
        "https://whatsgrouplink.com/usa/",
        "https://groupsjoin.com/usa-whatsapp-group-links",
        "https://www.whatsappgroupslink.com/search/label/USA",
        "https://bgk.co.in/whatsapp-group-links-usa/"
    ]

    total_new = 0
    send_telegram("🔍 <b>Scanning directory sources for WhatsApp invites...</b>")

    for source_url in SOURCES:
        html, current_url = fetch_url(source_url)
        if not html:
            continue

        # 1. Direct regex extraction from page source
        direct_links = re.findall(WA_REGEX, html)
        for link_code in direct_links:
            full_link = f"https://chat.whatsapp.com/{link_code}"
            if full_link not in seen:
                seen.add(full_link)
                total_new += 1
                send_telegram(f"🇺🇸 <b>Group Link #{total_new}</b>\n\n{full_link}")
                time.sleep(1.2)

        # 2. Extract relative redirects and resolve them
        redirect_paths = re.findall(REDIRECT_REGEX, html)
        for path in set(redirect_paths[:20]):  # Limit per page to stay within rate limits
            resolved_wa = resolve_redirect_link(current_url, path)
            if resolved_wa and resolved_wa not in seen:
                seen.add(resolved_wa)
                total_new += 1
                send_telegram(f"🇺🇸 <b>Group Link #{total_new}</b>\n\n{resolved_wa}")
                time.sleep(1.2)

    if total_new == 0:
        send_telegram("⚠️ <b>No new links found on this run.</b>")
    else:
        send_telegram(f"🏁 <b>Scan complete.</b> Found {total_new} new links. Total stored: {len(seen)}")

def telegram_polling():
    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook", timeout=5)
    except Exception:
        pass

    last_id = 0
    while True:
        try:
            res = requests.get(
                f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_id+1}&timeout=30", 
                timeout=35
            ).json()
            if res.get("ok"):
                for update in res.get("result", []):
                    last_id = update["update_id"]
                    msg_text = update.get("message", {}).get("text", "").lower()

                    if "/start" in msg_text:
                        send_telegram("👋 <b>Bot Active</b>\nCommands:\n/scan - Start manual scan\n/status - View unique link count")
                    elif "/scan" in msg_text:
                        threading.Thread(target=scan_whatsapp_groups, daemon=True).start()
                    elif "/status" in msg_text:
                        send_telegram(f"📊 Total unique group links cached: {len(seen)}")
        except Exception:
            time.sleep(3)

def auto_loop():
    time.sleep(5)
    while True:
        scan_whatsapp_groups()
        time.sleep(600)

if __name__ == "__main__":
    if TOKEN and CHAT_ID:
        threading.Thread(target=telegram_polling, daemon=True).start()
        threading.Thread(target=auto_loop, daemon=True).start()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

