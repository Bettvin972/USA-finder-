import os
import re
import time
import requests
from bs4 import BeautifulSoup

# ============ YOUR CONFIG ============
# Works with both Secrets / Env Vars and direct token
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8760780904:AAFrL4XCoGz-VR6iulMx9jhfO7R8QMuiUo8")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8910917503")

# Sources that list USA groups
TARGET_URLS = [
    "https://groupsor.link/group/country/United_States",
    "https://groupsor.link/group/category/Education",
    "https://groupsor.link/group/category/Travel",
    "https://groupsor.link/group/category/Housing",
    "https://wglfinder.com/america-whatsapp-group-link/",
    "https://wachannelsfinder.com/country/united-states-of-america/",
    "https://whatsgrouplink.com/usa-whatsapp-group-link/",
    "https://whatsappgroups.org/usa-whatsapp-group-links/",
    "https://groups1.com/country/united-states",
    "https://whatsgrouplinks.org/usa-whatsapp-group-links/",
]

WA_LINK_PATTERN = r"https://chat\.whatsapp\.com/[A-Za-z0-9]{20,24}"

# ALL USA KEYWORDS - Rides + Accommodation
US_KEYWORDS = [
    "usa","us","united states","america","american",
    "california","texas","florida","new york","pennsylvania","illinois","ohio","georgia","north carolina","michigan","new jersey","virginia","washington","arizona","massachusetts","tennessee","indiana","missouri","maryland","wisconsin","colorado","minnesota","alabama","louisiana","kentucky","oregon","oklahoma","connecticut","utah","iowa","nevada","arkansas","mississippi","kansas","new mexico","nebraska","west virginia","idaho","hawaii","new hampshire","maine","rhode island","montana","delaware","south dakota","north dakota","alaska","vermont","wyoming",
    "nyc","la","los angeles","chicago","houston","phoenix","philadelphia","san antonio","san diego","dallas","austin","san jose","seattle","miami","boston","atlanta","las vegas","denver","orlando","san francisco","dfw","bay area","dmv","new jersey",
    "university","college","campus","masters","ms in us","f1 students","h1b","opt","cpt","indian in usa","desi in usa","telugu in usa",
    "carpool","rideshare","ride share","ride","commute","shuttle","airport ride","rides","cab share","ride needed","need ride","airport pickup","airport drop","lift",
    "accommodation","roommate","housing","apartments","apartment","lease","sublease","sub lease","rooms available","room available","looking for room","flatmate","student housing","room rent","shared room","private room","room needed"
]

STRICT_EXCLUSIONS = [
    "kenya","nairobi","mombasa","nakuru","juja","jkuat","comrades","kisumu","eldoret","kenyan","kisii","machakos",
    "india","delhi","mumbai","bangalore","pune","hyderabad","chennai","kerala","kolkata",
    "nigeria","lagos","abuja","ghana","uk","london","canada","toronto","pakistan","bangladesh","south africa","ethiopia","uganda","zimbabwe","zambia","tanzania",
    "forex","crypto","bitcoin","betting","aviator","porn","xxx","adult","onlyfans","earn money","lottery","trading signals","casino","18+","sex"
]

FILE_DB = "us_student_groups.txt"
FILE_RIDES = "rides.txt"
FILE_ROOMS = "rooms.txt"

discovered_links = set()
if os.path.exists(FILE_DB):
    with open(FILE_DB, "r", encoding="utf-8") as f:
        for line in f:
