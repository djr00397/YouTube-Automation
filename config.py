import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
WORK, DATA, VOICES, MODELS, OUT, BUILD = (BASE / n for n in ("work", "data", "voices", "models", "output", "build"))
USED = DATA / "used"
for _p in (WORK, DATA, USED, VOICES, MODELS, OUT, BUILD):
    _p.mkdir(parents=True, exist_ok=True)

DRY = os.getenv("DRY_RUN", "0") == "1"
MODE = os.getenv("VIDEO_TYPE", "short").strip().lower()
if MODE not in ("long", "short"):
    MODE = "short"
IS_SHORT = MODE == "short"

# ডিজাইন লজিক্যাল 1280x720 (বা 720x1280) ইউনিটে; Cairo ৩ গুণ স্কেলে সরাসরি 4K ভেক্টর আঁকে
LW, LH, S = (720, 1280, 3) if IS_SHORT else (1280, 720, 3)
W, H = LW * S, LH * S           # long 3840x2160, short 2160x3840
FPS = 24
SR = 44100

if IS_SHORT:
    MIN_SEC, TARGET_SEC, MAX_SEC = 25, 52, 175
else:
    MIN_SEC, TARGET_SEC, MAX_SEC = 20 * 60, 22 * 60 + 30, 24 * 60 + 40

SLOT_HOURS_LOCAL = [18, 6] if IS_SHORT else [12, 0]
LOCAL_UTC_OFFSET = float(os.getenv("LOCAL_UTC_OFFSET", "6"))
JOB_BUDGET_SEC = 335 * 60

FRAMES_PER_SHARD = 1800
MAX_SHARDS = 18

RSS_IMAGES = os.getenv("RSS_IMAGES", "1") == "1"
IMG_MAX = 10 if IS_SHORT else 44
IMG_MIN = 3 if IS_SHORT else 12
WIKI_CONTACT = os.getenv("WIKI_CONTACT", "https://github.com/")
GEO_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson"

VOICE_MODELS = ["en_US-ryan-high", "en_US-joe-medium", "en_US-lessac-medium"]
LLM_PATH = Path(os.getenv("LLM_PATH", str(MODELS / "qwen2.5-3b-instruct-q4_k_m.gguf")))
LLM_THREADS = int(os.getenv("LLM_THREADS", str(os.cpu_count() or 4)))

FEEDS = [
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://feeds.npr.org/1006/rss.xml",
    "https://www.cnbc.com/id/10001147/device/rss/rss.html",
    "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "https://www.theguardian.com/uk/business/rss",
    "https://www.theguardian.com/business/economics/rss",
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml",
    "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "https://finance.yahoo.com/news/rssindex",
    "https://www.forbes.com/business/feed/",
    "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
    "https://www.business-standard.com/rss/home_page_top_stories.rss",
    "https://www.thehindubusinessline.com/feeder/default.rss",
]
WIKI_EVENTS = "https://en.wikipedia.org/wiki/Portal:Current_events/{y}_{m}_{d}"
