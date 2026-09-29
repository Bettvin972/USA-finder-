
import os
import re
import json
import time
import html
import logging
import threading
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlparse

import requests
from flask import Flask, jsonify

# ============================================================
# V18 WHATSAPP PUBLIC GROUP DISCOVERY BOT
# ============================================================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

PORT = int(os.getenv("PORT", "10000"))
SCAN_INTERVAL = max(300, int(os.getenv("SCAN_INTERVAL", "1800")))
MAX_RESULTS = max(10, int(os.getenv("MAX_RESULTS_PER_SCAN", "100")))
TIMEOUT = max(5, int(os.getenv("REQUEST_TIMEOUT", "12")))
SEEN_FILE = os.getenv("SEEN_FILE", "seen_v18.json")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(threadName)s: %(message)s"
)

log = logging.getLogger("wa-v18")

app = Flask(__name__)

http = requests.Session()
http.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; PublicLinkDiscovery/18.0)"
})

# ============================================================
# SEARCH QUERIES
# ============================================================

TERMS = [
    '"chat.whatsapp.com" USA university students',
    '"chat.whatsapp.com" college students USA',
    '"chat.whatsapp.com" international students USA',
    '"chat.whatsapp.com" student housing USA',
    '"chat.whatsapp.com" student roommates USA',
    '"chat.whatsapp.com" student rideshare USA',
    '"chat.whatsapp.com" Indian students USA',
    '"chat.whatsapp.com" African students USA',
    'site:reddit.com "chat.whatsapp.com" students USA',
    'site:facebook.com "chat.whatsapp.com" university students',
    'site:x.com "chat.whatsapp.com" students',
    'site:tiktok.com "chat.whatsapp.com" students',
    'site:instagram.com "chat.whatsapp.com" students'
]

# Optional Google Programmable Search configuration
GOOGLE_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
GOOGLE_CX = os.getenv("GOOGLE_CX", "").strip()

INVITE_RE = re.compile(
    r'(?:https?://)?chat\.whatsapp\.com/[A-Za-z0-9_-]{10,}(?:\?[^\s"\'<>]*)?',
    re.IGNORECASE
)

# ============================================================
# THREADING AND STATE
# ============================================================

lock = threading.RLock()
scan_lock = threading.Lock()
stop = threading.Event()

state = {
    "started_at": datetime.now(timezone.utc).isoformat(),
    "last_scan_started": None,
    "last_scan_finished": None,
    "last_scan_status": "Not started",
    "last_scan_error": None,
    "last_scan_found": 0,
    "last_scan_sent": 0,
    "total_scans": 0,
    "total_links_found": 0,
    "total_links_sent": 0,
    "telegram_offset": 0
}

# ============================================================
# DUPLICATE DATABASE
# ============================================================

def load_seen():
    try:
        with open(SEEN_FILE, encoding="utf-8") as f:
            data = json.load(f)

        return data if isinstance(data, dict) else {}

    except FileNotFoundError:
        return {}

    except Exception:
        log.exception("Seen database could not be loaded")
        return {}


seen = load_seen()


def save_seen():
    temporary_file = SEEN_FILE + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)

    os.replace(temporary_file, SEEN_FILE)


# ============================================================
# WHATSAPP LINK CLEANING
# ============================================================

def clean_link(raw):
    raw = html.unescape(raw.strip().rstrip(".,);]}>"))

    if not raw.lower().startswith("http"):
        raw = "https://" + raw

    parsed = urlparse(raw)

    if parsed.netloc.lower() not in (
        "chat.whatsapp.com",
        "www.chat.whatsapp.com"
    ):
        return None

    token = parsed.path.strip("/").split("/")[0]

    if not re.fullmatch(r"[A-Za-z0-9_-]{10,}", token or ""):
        return None

    return "https://chat.whatsapp.com/" + token


# ============================================================
# TELEGRAM API
# ============================================================

def tg(method, payload=None, timeout=30):
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")

    response = http.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        json=payload or {},
        timeout=timeout
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(str(data))

    return data.get("result")


def send(message, chat=None):
    target = str(chat or CHAT_ID)

    if not target:
        return False

    try:
        tg(
            "sendMessage",
            {
                "chat_id": target,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
        )

        return True

    except Exception:
        log.exception("Telegram send failed")
        return False


# ============================================================
# SEARCH ENGINE
# ============================================================

def search(query):
    try:
        # Use Google if API credentials are configured.
        if GOOGLE_KEY and GOOGLE_CX:

            response = http.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": GOOGLE_KEY,
                    "cx": GOOGLE_CX,
                    "q": query,
                    "num": 10
                },
                timeout=TIMEOUT
            )

            response.raise_for_status()

            return json.dumps(
                response.json().get("items", []),
                ensure_ascii=False
            )

        # Otherwise use DuckDuckGo HTML search.
        response = http.get(
            "https://html.duckduckgo.com/html/?q=" + quote_plus(query),
            timeout=TIMEOUT
        )

        response.raise_for_status()

        return response.text

    except Exception as error:
        log.warning("Search failed (%s): %s", query, error)
        return ""


# ============================================================
# DISCOVERY ENGINE
# ============================================================

def discover():
    results = {}

    # Rotate search order between scans.
    rotation = int(time.time() // SCAN_INTERVAL) % len(TERMS)

    queries = TERMS[rotation:] + TERMS[:rotation]

    for query in queries:

        if stop.is_set():
            break

        page = search(query)

        for raw in INVITE_RE.findall(page):

            link = clean_link(raw)

            if link:
                results.setdefault(link, query)

        if len(results) >= MAX_RESULTS:
            break

        # Moderate request pacing.
        time.sleep(1)

    return dict(list(results.items())[:MAX_RESULTS])


# ============================================================
# INVITATION VALIDATION
# ============================================================

def validate(link):
    """
    Best-effort check of a public invitation page.

    A loaded page does not guarantee that a person can join.
    """

    try:
        response = http.get(
            link,
            timeout=TIMEOUT,
            allow_redirects=True
        )

        body = (response.text or "").lower()

        title_match = re.search(
            r"<title[^>]*>(.*?)</title>",
            body,
            re.IGNORECASE | re.DOTALL
        )

        title = ""

        if title_match:
            title = re.sub(
                r"\s+",
                " ",
                title_match.group(1)
            ).strip()

        if response.status_code in (404, 410):
            return "Appears unavailable", f"HTTP {response.status_code}"

        invalid_messages = [
            "invite link was reset",
            "invite link has been reset",
            "this invite link is no longer valid",
            "invalid invite link",
            "link has been revoked"
        ]

        if any(message in body for message in invalid_messages):
            return (
                "Appears invalid/reset",
                title or "WhatsApp indicates an invalid invitation"
            )

        if response.status_code == 200 and (
            "whatsapp" in title.lower()
            or "join" in body
            or "group" in body
        ):
            return (
                "Invitation page detected (joinability unconfirmed)",
                title or "Page loaded"
            )

        return (
            "Unverified",
            f"HTTP {response.status_code}; automated check inconclusive"
        )

    except requests.RequestException as error:
        return (
            "Unverified",
            f"Check blocked/failed: {type(error).__name__}"
        )


# ============================================================
# TELEGRAM MESSAGE FORMAT
# ============================================================

def esc(value):
    return html.escape(str(value), quote=False)


def format_message(link, source, status, detail):
    return (
        "🔎 <b>Public WhatsApp group link discovered</b>\n\n"
        f"🔗 {esc(link)}\n"
        f"🧪 <b>Check:</b> {esc(status)}\n"
        f"ℹ️ <b>Details:</b> {esc(detail[:220])}\n"
        f"🌐 <b>Search:</b> {esc(source[:160])}\n\n"
        "<i>Automated checks cannot guarantee that a group accepts new members.</i>"
    )


# ============================================================
# SCAN ENGINE
# ============================================================

def run_scan():

    if not scan_lock.acquire(blocking=False):
        log.info("Scan already running; skipping")
        return {"status": "already_running"}

    with lock:
        state["last_scan_started"] = datetime.now(timezone.utc).isoformat()
        state["last_scan_status"] = "Running"
        state["last_scan_error"] = None
        state["total_scans"] += 1

    found = 0
    sent = 0

    try:
        links = discover()
        found = len(links)

        for link, source in links.items():

            if stop.is_set():
                break

            with lock:
                already_seen = link in seen

            if already_seen:
                continue

            status, detail = validate(link)

            # Record processed links to prevent repeated notifications.
            with lock:
                seen[link] = {
                    "first_seen": datetime.now(timezone.utc).isoformat(),
                    "status": status,
                    "source": source
                }

                save_seen()

            # Skip links that clearly appear unavailable or revoked.
            if status in (
                "Appears unavailable",
                "Appears invalid/reset"
            ):
                log.info(
                    "Filtered stale invitation %s (%s)",
                    link,
                    status
                )
                continue

            if send(format_message(link, source, status, detail)):
                sent += 1

            time.sleep(0.4)

        with lock:
            state.update(
                last_scan_status="Completed",
                last_scan_finished=datetime.now(timezone.utc).isoformat(),
                last_scan_found=found,
                last_scan_sent=sent,
                total_links_found=state["total_links_found"] + found,
                total_links_sent=state["total_links_sent"] + sent
            )

        log.info(
            "Scan complete found=%d sent=%d",
            found,
            sent
        )

        return {
            "status": "completed",
            "found": found,
            "sent": sent
        }

    except Exception as error:

        log.exception("Scan failed")

        with lock:
            state["last_scan_status"] = "Failed; scheduled retry"
            state["last_scan_error"] = (
                f"{type(error).__name__}: {error}"
            )[:400]

            state["last_scan_finished"] = (
                datetime.now(timezone.utc).isoformat()
            )

        send(
            "⚠️ <b>V18 scan error.</b>\n"
            + esc(f"{type(error).__name__}: {error}")[:300]
            + "\nThe scheduler will retry at the next interval."
        )

        return {"status": "failed"}

    finally:
        scan_lock.release()


# ============================================================
# STATUS COMMAND
# ============================================================

def status_text():

    with lock:
        snapshot = dict(state)

    return (
        "🤖 <b>WhatsApp Discovery Bot V18</b>\n\n"
        f"Status: <b>{esc(snapshot['last_scan_status'])}</b>\n"
        f"Last started: {esc(snapshot['last_scan_started'] or 'Never')}\n"
        f"Last finished: {esc(snapshot['last_scan_finished'] or 'Never')}\n"
        f"Found last scan: {snapshot['last_scan_found']} | "
        f"Sent: {snapshot['last_scan_sent']}\n"
        f"Total scans: {snapshot['total_scans']}\n"
        f"Total links found: {snapshot['total_links_found']}\n"
        f"Total links sent: {snapshot['total_links_sent']}\n"
        f"Interval: {SCAN_INTERVAL // 60} minutes\n"
        f"Last error: {esc(snapshot['last_scan_error'] or 'None')}"
    )


# ============================================================
# TELEGRAM COMMAND HANDLER
# ============================================================

def allowed(chat):
    return bool(CHAT_ID) and str(chat) == str(CHAT_ID)


def telegram_loop():

    if not BOT_TOKEN:
        log.error("Telegram disabled: token not configured")
        return

    delay = 2

    log.info("Telegram polling started")

    while not stop.is_set():

        try:
            updates = tg(
                "getUpdates",
                {
                    "offset": state["telegram_offset"],
                    "timeout": 20,
                    "allowed_updates": ["message"]
                },
                timeout=30
            )

            delay = 2

            for update in updates or []:

                state["telegram_offset"] = max(
                    state["telegram_offset"],
                    int(update.get("update_id", 0)) + 1
                )

                message = update.get("message") or {}

                chat = (message.get("chat") or {}).get("id")
                text = (message.get("text") or "").strip()

                if not allowed(chat):
                    log.warning(
                        "Ignored unauthorized chat %s",
                        chat
                    )
                    continue

                command = (
                    text.split()[0].split("@")[0].lower()
                    if text else ""
                )

                if command in ("/start", "/help"):

                    send(
                        "Welcome to <b>WhatsApp Discovery Bot V18</b>.\n\n"
                        "/scan — scan now\n"
                        "/status — bot status\n"
                        "/help — commands",
                        chat
                    )

                elif command == "/status":

                    send(status_text(), chat)

                elif command == "/scan":

                    if scan_lock.locked():

                        send(
                            "A scan is already running. Check /status.",
                            chat
                        )

                    else:

                        send(
                            "🔍 Scan started; results will arrive as they are processed.",
                            chat
                        )

                        threading.Thread(
                            target=run_scan,
                            name="manual-scan",
                            daemon=True
                        ).start()

                else:

                    send("Unknown command. Use /help.", chat)

        except Exception:

            log.exception(
                "Telegram polling failed; reconnecting in %ds",
                delay
            )

            stop.wait(delay)
            delay = min(delay * 2, 60)


# ============================================================
# AUTOMATIC SCANNER
# ============================================================

def scheduler():

    log.info("Scheduler active; first scan in 15 seconds")

    if stop.wait(15):
        return

    while not stop.is_set():

        try:
            run_scan()

        except Exception:
            log.exception(
                "Scheduler recovered from unexpected error"
            )

        stop.wait(SCAN_INTERVAL)


# ============================================================
# FLASK HEALTH ENDPOINTS
# ============================================================

@app.get("/")
def home():

    return (
        "<h2>WhatsApp Discovery Bot V18</h2>"
        "<p>Service is running.</p>"
        "<p><a href='/health'>Health</a></p>"
    )


@app.get("/health")
def health():

    with lock:
        snapshot = dict(state)

    return jsonify(
        ok=True,
        service="whatsapp-discovery-v18",
        telegram_configured=bool(BOT_TOKEN and CHAT_ID),
        scan_status=snapshot["last_scan_status"],
        last_scan_finished=snapshot["last_scan_finished"],
        last_error=snapshot["last_scan_error"]
    )


# ============================================================
# START BACKGROUND THREADS
# ============================================================

def start_threads():

    if getattr(start_threads, "started", False):
        return

    start_threads.started = True

    threading.Thread(
        target=telegram_loop,
        name="telegram-polling",
        daemon=True
    ).start()

    threading.Thread(
        target=scheduler,
        name="scan-scheduler",
        daemon=True
    ).start()


start_threads()


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=PORT,
        threaded=True
  )
