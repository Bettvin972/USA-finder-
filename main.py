
"""
V17.0 — Multi-platform public WhatsApp group discovery bot

Discovery sources:
- Existing public group-link directories
- DuckDuckGo HTML search for indexed public pages/posts on Facebook, X, TikTok,
  Reddit, and the wider web
- Optional Google Programmable Search JSON API

The bot does not log in to social platforms, bypass access controls, or access
private/member-only groups. Search-engine indexing is incomplete and results
are not guaranteed to be current.
"""

import os
import re
import json
import time
import html
import logging
import threading
from datetime import datetime, timezone
from urllib.parse import quote_plus, unquote

import requests
from flask import Flask, jsonify

VERSION = "V17.0"
app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
PORT = int(os.getenv("PORT", "10000"))
SCAN_INTERVAL = max(300, int(os.getenv("SCAN_INTERVAL", "1800")))
MAX_RESULTS_PER_SCAN = max(10, int(os.getenv("MAX_RESULTS_PER_SCAN", "150")))
DB_FILE = os.getenv("SEEN_FILE", "seen_v17.json")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
GOOGLE_CX = os.getenv("GOOGLE_CX", "").strip()

WA_REGEX = re.compile(
    r"https?://chat\.whatsapp\.com/[A-Za-z0-9]{20,26}",
    re.IGNORECASE,
)

SPAM_TERMS = (
    "earn money", "crypto", "bitcoin", "forex", "betting", "adult",
    "18+", "xxx", "porn", "onlyfans", "hot girls", "lottery",
    "giveaway money",
)

# Queries focus on publicly advertised student communities.
BASE_QUERIES = [
    '"WhatsApp" "USA students" group',
    '"WhatsApp group" "international students" USA',
    '"WhatsApp" university students USA group',
    '"WhatsApp" student housing USA',
    '"WhatsApp" student rideshare USA',
    '"WhatsApp" Indian students USA group',
    '"WhatsApp" African students USA group',
    '"WhatsApp" college students USA',
    '"WhatsApp" new students USA university',
]

PLATFORM_QUERIES = {
    "Facebook": [
        'site:facebook.com "WhatsApp" "students" USA group',
        'site:facebook.com "chat.whatsapp.com" university students',
    ],
    "X": [
        'site:x.com "chat.whatsapp.com" students USA',
        'site:twitter.com "WhatsApp group" university students',
    ],
    "TikTok": [
        'site:tiktok.com "chat.whatsapp.com" students',
        'site:tiktok.com "WhatsApp group" USA students',
    ],
    "Reddit": [
        'site:reddit.com "chat.whatsapp.com" students USA',
        'site:reddit.com "WhatsApp group" international students',
    ],
}

DIRECTORY_SOURCES = [
    "https://whatsgrouplink.com/usa/",
    "https://groupsjoin.com/usa-whatsapp-group-links",
    "https://www.whatsappgroupslink.com/search/label/USA",
    "https://whatsgrouplinks.org/usa-whatsapp-group-links/",
    "https://whatsappgroupslink.com/usa/",
    "https://www.invite-link.com/whatsapp-group-links/usa/",
    "https://whatsgrouplink.com/category/usa/",
    "https://groupslinky.com/usa-whatsapp-group-links/",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("pure-wa-v17")

http = requests.Session()
http.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; PublicGroupDiscovery/17.0)"
})

state_lock = threading.RLock()
scan_lock = threading.Lock()
seen = set()

stats = {
    "scans": 0,
    "last_scan": None,
    "last_status": "Starting",
    "last_candidates": 0,
    "new_links": 0,
    "errors": 0,
    "by_platform": {},
}


# ============================================================
# MEMORY
# ============================================================

def load_seen():
    global seen

    try:
        if os.path.isfile(DB_FILE):
            with open(DB_FILE, "r", encoding="utf-8") as f:
                value = json.load(f)

            if isinstance(value, list):
                with state_lock:
                    seen = set(value)

    except (OSError, ValueError) as exc:
        log.warning("Could not load seen-link database: %s", exc)


def save_seen():
    try:
        with state_lock:
            snapshot = sorted(seen)

        temp = DB_FILE + ".tmp"

        with open(temp, "w", encoding="utf-8") as f:
            json.dump(snapshot, f)

        os.replace(temp, DB_FILE)

    except OSError:
        log.exception("Could not persist seen-link database")


def remember(url):
    with state_lock:
        if url in seen:
            return False

        seen.add(url)

    save_seen()
    return True


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(message):
    if not TOKEN or not CHAT_ID:
        log.info("Telegram not configured; notification skipped")
        return False

    try:
        response = http.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )

        response.raise_for_status()
        return bool(response.json().get("ok"))

    except requests.RequestException:
        log.exception("Telegram send failed")
        return False


# ============================================================
# LINK VALIDATION
# ============================================================

def is_valid_wa(url):
    return bool(WA_REGEX.fullmatch(url.strip()))


def is_spam(text):
    low = (text or "").lower()
    return any(term in low for term in SPAM_TERMS)


def extract_links(text):
    if not text:
        return set()

    candidates = set()

    for variant in (html.unescape(text), unquote(html.unescape(text))):
        for match in WA_REGEX.findall(variant):
            cleaned = match.rstrip(".,;:!?)\\]}'\"")

            if is_valid_wa(cleaned):
                candidates.add(cleaned)

    return candidates


# ============================================================
# WEB REQUESTS
# ============================================================

def get_page(url, timeout=15):
    try:
        response = http.get(url, timeout=timeout)

        if response.status_code == 200:
            return response.text

        log.info("HTTP %s from %s", response.status_code, url)

    except requests.RequestException as exc:
        log.warning("Fetch failed for %s: %s", url, exc)

    return ""


def duckduckgo_search(query):
    """Search public/indexed pages; not a direct social-platform API."""

    url = (
        "https://html.duckduckgo.com/html/?q="
        + quote_plus(query)
    )

    page = get_page(url)
    return extract_links(page)


def google_search(query):
    """Optional official Google Programmable Search API integration."""

    if not (GOOGLE_API_KEY and GOOGLE_CX):
        return set()

    try:
        response = http.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": GOOGLE_API_KEY,
                "cx": GOOGLE_CX,
                "q": query,
                "num": 10,
            },
            timeout=20,
        )

        response.raise_for_status()
        data = response.json()

        combined = "\n".join(
            str(item.get("link", ""))
            + "\n"
            + str(item.get("title", ""))
            + "\n"
            + str(item.get("snippet", ""))
            for item in data.get("items", [])
        )

        return extract_links(combined)

    except (requests.RequestException, ValueError) as exc:
        log.warning("Google search failed: %s", exc)
        return set()


def identify_platform(query):
    q = query.lower()

    if "site:facebook.com" in q:
        return "Facebook-indexed"

    if "site:x.com" in q or "site:twitter.com" in q:
        return "X-indexed"

    if "site:tiktok.com" in q:
        return "TikTok-indexed"

    if "site:reddit.com" in q:
        return "Reddit-indexed"

    return "Web search"


# ============================================================
# WHATSAPP INVITATION CHECK
# ============================================================

def verify_invite(url):
    """
    Best-effort page check only.

    WhatsApp may change page markup, block automated requests,
    or show a preview without confirming joinability.
    """

    try:
        response = http.get(
            url,
            timeout=12,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return "Unverified"

        body = html.unescape(response.text).lower()

        dead_phrases = (
            "invalid invite",
            "invite link has expired",
            "invite link is no longer valid",
            "invite link was revoked",
            "couldn't find",
        )

        if any(phrase in body for phrase in dead_phrases):
            return "Appears expired/invalid"

        live_phrases = (
            "join group",
            "join chat",
            "group invite",
        )

        if any(phrase in body for phrase in live_phrases):
            return "Invitation page detected"

        return "Unverified"

    except requests.RequestException:
        return "Unverified"


# ============================================================
# SEARCH QUERY GENERATOR
# ============================================================

def all_searches():
    for query in BASE_QUERIES:
        yield query

    for queries in PLATFORM_QUERIES.values():
        for query in queries:
            yield query


# ============================================================
# SCAN ENGINE
# ============================================================

def run_scan():

    if not scan_lock.acquire(blocking=False):
        telegram_send("⏳ A scan is already running.")
        return

    try:
        with state_lock:
            stats["last_status"] = "Scanning"

        telegram_send(
            f"🔎 <b>{VERSION} MULTI-PLATFORM SCAN STARTED</b>\n"
            f"Directories: {len(DIRECTORY_SOURCES)}\n"
            "Search: public/indexed Facebook, X, TikTok, Reddit and web pages"
        )

        discovered = {}

        # Scan existing public directories.
        for source in DIRECTORY_SOURCES:
            page = get_page(source)

            for url in extract_links(page):
                discovered.setdefault(url, "Group-link directory")

            time.sleep(0.8)

        # Search public/indexed social media and web content.
        for query in all_searches():
            platform = identify_platform(query)

            try:
                links = duckduckgo_search(query)

                for url in links:
                    discovered.setdefault(url, platform)

                # Google is optional and requires API credentials.
                for url in google_search(query):
                    discovered.setdefault(url, "Google indexed search")

                time.sleep(1.2)

            except Exception:
                log.exception("Search query failed: %s", query)

        with state_lock:
            stats["last_candidates"] = len(discovered)

        sent = 0
        checked = 0
        platform_counts = {}

        for url, source in list(discovered.items())[:MAX_RESULTS_PER_SCAN]:

            if not is_valid_wa(url) or is_spam(url):
                continue

            if not remember(url):
                continue

            checked += 1
            status = verify_invite(url)

            platform_counts[source] = (
                platform_counts.get(source, 0) + 1
            )

            sent += 1

            safe_url = html.escape(url)
            safe_source = html.escape(source)
            safe_status = html.escape(status)

            telegram_send(
                f"🔗 <b>WhatsApp invitation discovered #{sent}</b>\n\n"
                f"Source: {safe_source}\n"
                f"Automated check: <b>{safe_status}</b>\n"
                f"<code>{safe_url}</code>\n\n"
                "<i>Check the invitation in WhatsApp before sharing.</i>"
            )

            time.sleep(0.7)

        with state_lock:
            stats["scans"] += 1
            stats["last_scan"] = datetime.now(
                timezone.utc
            ).isoformat()
            stats["last_status"] = "Completed"
            stats["new_links"] += sent
            stats["by_platform"] = platform_counts

        telegram_send(
            "🏁 <b>SCAN COMPLETE</b>\n\n"
            f"Unique candidates: {len(discovered)}\n"
            f"New invitations reported: {sent}\n"
            f"New links checked: {checked}\n"
            f"Remembered links: {len(seen)}"
        )

    except Exception:
        log.exception("Scan failed")

        with state_lock:
            stats["errors"] += 1
            stats["last_status"] = "Error"

        telegram_send(
            "❌ Scan encountered an unexpected error. "
            "Check server logs."
        )

    finally:
        scan_lock.release()


# ============================================================
# TELEGRAM COMMANDS
# ============================================================

def handle_command(text):

    command = text.strip().split()[0].split("@")[0].lower()

    if command == "/start":

        telegram_send(
            f"👋 <b>{VERSION} MULTI-PLATFORM DISCOVERY</b>\n\n"
            "Finds publicly indexed WhatsApp invitations from the web "
            "and social-platform search results.\n\n"
            "<b>Commands</b>\n"
            "/scan — start a scan\n"
            "/status — show status\n"
            "/clear — clear duplicate memory"
        )

    elif command == "/scan":

        threading.Thread(
            target=run_scan,
            daemon=True,
        ).start()

    elif command == "/status":

        with state_lock:
            current = dict(stats)
            memory_count = len(seen)

        telegram_send(
            "📊 <b>V17 STATUS</b>\n\n"
            f"Running: {scan_lock.locked()}\n"
            f"Completed scans: {current['scans']}\n"
            f"Last candidates: {current['last_candidates']}\n"
            f"New links reported: {current['new_links']}\n"
            f"Errors: {current['errors']}\n"
            f"Remembered: {memory_count}\n"
            f"Last scan: {current['last_scan'] or 'Never'}\n"
            f"Status: {current['last_status']}"
        )

    elif command == "/clear":

        if scan_lock.locked():
            telegram_send(
                "⚠️ Wait until the current scan finishes "
                "before clearing memory."
            )
            return

        with state_lock:
            seen.clear()

        save_seen()

        telegram_send("🗑️ Duplicate memory cleared.")


# ============================================================
# TELEGRAM LONG POLLING
# ============================================================

def telegram_polling():

    offset = 0

    try:
        http.post(
            f"https://api.telegram.org/bot{TOKEN}/deleteWebhook",
            timeout=10,
        )

    except requests.RequestException:
        log.exception("Could not delete webhook")

    while True:

        try:
            response = http.get(
                f"https://api.telegram.org/bot{TOKEN}/getUpdates",
                params={
                    "offset": offset,
                    "timeout": 30,
                    "allowed_updates": json.dumps(["message"]),
                },
                timeout=35,
            )

            response.raise_for_status()
            payload = response.json()

            for update in payload.get("result", []):

                offset = update["update_id"] + 1

                message = update.get("message", {})
                chat_id = str(
                    message.get("chat", {}).get("id", "")
                )

                # Only the configured chat may control the bot.
                if chat_id != CHAT_ID:
                    continue

                text = message.get("text", "")

                if text.startswith("/"):
                    handle_command(text)

        except requests.RequestException:
            log.exception("Telegram polling network error")
            time.sleep(5)

        except Exception:
            log.exception("Telegram polling error")
            time.sleep(3)


# ============================================================
# AUTOMATIC SCANNING
# ============================================================

def automatic_scanner():

    time.sleep(15)

    while True:
        run_scan()
        time.sleep(SCAN_INTERVAL)


# ============================================================
# FLASK HEALTH CHECK
# ============================================================

@app.get("/")
def home():

    return jsonify({
        "service": "PURE WA multi-platform discovery",
        "version": VERSION,
        "status": "online",
    })


@app.get("/health")
def health():

    return jsonify({
        "status": "healthy",
        "version": VERSION,
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
    })


# ============================================================
# STARTUP
# ============================================================

load_seen()

if TOKEN and CHAT_ID:

    threading.Thread(
        target=telegram_polling,
        daemon=True,
    ).start()

    threading.Thread(
        target=automatic_scanner,
        daemon=True,
    ).start()

    log.info(
        "%s started; remembered links=%d",
        VERSION,
        len(seen),
    )

else:

    log.warning(
        "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
        "to enable the bot."
    )


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=PORT,
)
