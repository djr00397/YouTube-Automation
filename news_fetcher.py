import os, re, json, time, html, subprocess
import concurrent.futures as cf
from calendar import timegm
from collections import Counter
from datetime import datetime, timedelta
from urllib.parse import urlparse
import feedparser, requests
from bs4 import BeautifulSoup
import config

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
STOP = set("a an the of to in on for and or at by with from as is are was were be been this that it its after over new says say will us has have had not but his her their more than into out up about".split())
ENT_STOP = set("The This That These Those How Why What When Where Who Which After Before Over Under With Without From Into Amid Says Said New Big Top Here There Their".split())
BAD = ("subscribe", "sign up", "newsletter", "copyright", "all rights reserved", "click here", "read more",
       "advertisement", "follow us", "cookie", "privacy policy", "download the app")
WIKI = "https://en.wikipedia.org"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
BIZ = re.compile(r"\b(econom\w*|market\w*|stock\w*|shares?|shareholder\w*|bank\w*|inflation|interest rate\w*|rate cut\w*|rate hike\w*|fed|federal reserve|tariff\w*|trade|trading|invest\w*|earnings|profit\w*|revenue|compan\w*|business\w*|ceo|merger\w*|acqui\w*|oil|energy|prices?|dollar|currency|crypto\w*|bitcoin|debt|bond\w*|tax\w*|jobs?|unemployment|wages?|gdp|recession|billion|trillion|ipo|startup\w*|retail\w*|consumer\w*|supply chain|manufactur\w*|budget|deficit|financ\w*|loan\w*|mortgage\w*|housing|sales|spending|industry|workers|layoffs?)\b", re.I)
NOT_BIZ = re.compile(r"\b(nobel|football|soccer|cricket|nba|nfl|celebrity|movie|oscars?|grammys?|royal|murder|shooting|earthquake|hurricane|wildfire|obituary|dies|dead)\b", re.I)


class NoFreshTopic(Exception):
    pass


def is_business(e):
    return bool(BIZ.search(e["title"] + " " + e["summary"])) and not NOT_BIZ.search(e["title"])


def toks(t):
    return {w for w in re.findall(r"[a-z0-9]+", t.lower()) if w not in STOP and len(w) > 2}


def ents(t):
    return {w.lower() for w in re.findall(r"\b[A-Z][A-Za-z]{2,}\b", t) if w not in ENT_STOP}


def jacc(a, b):
    return len(a & b) / max(1, len(a | b))


def clean(t):
    t = html.unescape(t or "")
    if "<" in t:
        t = BeautifulSoup(t, "lxml").get_text(" ")
    return re.sub(r"\s+", " ", t).strip()


def fdate(epoch):
    return datetime.utcfromtimestamp(epoch).strftime("%b %d, %Y").replace(" 0", " ")


# ---------- topic memory: data/used/*.json (প্রতি রানে আলাদা ফাইল => merge conflict নেই) ----------
def _item(link, title, ts=None):
    return {"link": link, "title": title, "tokens": sorted(toks(title)), "ents": sorted(ents(title)), "ts": ts or int(time.time())}


def load_history():
    items, styles = [], []
    try:
        items += json.loads((config.DATA / "history.json").read_text()).get("items", [])
    except Exception:
        pass
    for f in sorted(config.USED.glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        items += d.get("items", [])
        if d.get("profile"):
            styles.append((d.get("ts", 0), d["profile"]))
    for it in items:
        it.setdefault("title", "")
        it.setdefault("tokens", sorted(toks(it["title"])))
        it.setdefault("ents", sorted(ents(it["title"])))
        it.setdefault("ts", 0)
    items.sort(key=lambda x: x["ts"])
    return {"items": items[-900:], "styles": [p for _, p in sorted(styles, key=lambda x: x[0])][-24:]}


def is_repeat(e, h):
    t, E, now = toks(e["title"]), ents(e["title"]), time.time()
    for it in h["items"]:
        if it.get("link") == e.get("link"):
            return True
        jt, ce = jacc(t, set(it["tokens"])), len(E & set(it["ents"]))
        age = (now - it["ts"]) / 86400.0 if it["ts"] else 999
        if age <= 10:
            if jt >= 0.30 or (ce >= 2 and jt >= 0.12) or (ce >= 1 and jt >= 0.22):
                return True
        elif jt >= 0.40:
            return True
    return False


def _git(*a):
    return subprocess.run(["git", *a], cwd=str(config.BASE), capture_output=True, text=True)


def push_used():
    if os.getenv("GITHUB_ACTIONS") != "true":
        return
    ref = os.getenv("GITHUB_REF_NAME", "main")
    _git("config", "user.name", "bot")
    _git("config", "user.email", "bot@users.noreply.github.com")
    _git("add", "data/used")
    _git("commit", "-m", "reserve topic")
    r = None
    for i in range(6):
        _git("pull", "--rebase", "--autostash", "origin", ref)
        r = _git("push", "origin", f"HEAD:{ref}")
        if r.returncode == 0:
            print("reservation pushed")
            return
        time.sleep(3 + i * 3)
    print("WARNING: could not push reservation:", (r.stderr or "")[-300:])


def reserve(topic, profile):
    ts = int(time.time())
    items = [_item(topic["link"], topic["headline"], ts)] + [_item(a["link"], a["title"], ts) for a in topic["articles"]]
    name = f"{ts}-{os.getenv('GITHUB_RUN_ID', 'local')}-{os.getenv('GITHUB_RUN_ATTEMPT', '0')}.json"
    (config.USED / name).write_text(json.dumps({"ts": ts, "items": items, "profile": profile}))
    push_used()


# ---------- RSS ----------
def feed_image(e):
    for k in ("media_content", "media_thumbnail"):
        for m in e.get(k) or []:
            if m.get("url"):
                return m["url"]
    for l in e.get("links") or []:
        if str(l.get("type", "")).startswith("image") and l.get("href"):
            return l["href"]
    for src in (e.get("summary", ""), (e.get("content") or [{}])[0].get("value", "")):
        m = re.search(r'<img[^>]+src=["\']([^"\']+)', src or "")
        if m:
            return m.group(1)
    return None


def fetch_feed(url):
    try:
        r = requests.get(url, headers=UA, timeout=20)
        d = feedparser.parse(r.content)
    except Exception:
        return []
    src = clean(d.feed.get("title", "")) or urlparse(url).netloc
    out = []
    for e in d.entries[:40]:
        link, title = e.get("link"), clean(e.get("title", ""))
        if not link or not title:
            continue
        ts = e.get("published_parsed") or e.get("updated_parsed")
        out.append({"title": title, "link": link, "summary": clean(e.get("summary", "")), "image": feed_image(e),
                    "epoch": timegm(ts) if ts else time.time(), "source": src[:40]})
    return out


def gather():
    entries = []
    with cf.ThreadPoolExecutor(12) as ex:
        for r in ex.map(fetch_feed, config.FEEDS):
            entries += r
    seen, out = set(), []
    for e in entries:
        if e["link"] in seen or e["epoch"] < time.time() - 172800 or not is_business(e):
            continue
        seen.add(e["link"])
        out.append(e)
    return out


def article_page(url):
    try:
        r = requests.get(url, headers=UA, timeout=20, allow_redirects=True)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            return "", None
        s = BeautifulSoup(r.text, "lxml")
        og = s.find("meta", property="og:image")
        img = og["content"] if og and og.get("content") else None
        for t in s(["script", "style", "nav", "footer", "aside", "form"]):
            t.decompose()
        ps = [clean(p.get_text(" ")) for p in s.find_all("p")]
        return " ".join(p for p in ps if len(p) > 50 and not any(b in p.lower() for b in BAD)), img
    except Exception:
        return "", None


def sentences(text, maxlen=260):
    out = []
    for s in re.split(r'(?<=[.!?])\s+(?=[A-Z"“‘])', text):
        s = s.strip()
        if 45 <= len(s) <= maxlen and not any(b in s.lower() for b in BAD):
            out.append(s)
    return out


# ---------- Wikipedia ----------
def wiki_text(href):
    url = href if href.startswith("http") else WIKI + href
    try:
        r = requests.get(url, headers=UA, timeout=25)
        if r.status_code != 200:
            return "", ""
        s = BeautifulSoup(r.text, "lxml")
        c = s.find("div", id="mw-content-text")
        if not c:
            return "", ""
        ps = [clean(p.get_text(" ")) for p in c.find_all("p")]
        text = re.sub(r"\[[^\]]*\]", "", " ".join(p for p in ps if len(p) > 60))
        h = s.find("h1")
        return text[:12000], (clean(h.get_text(" ")) if h else "")
    except Exception:
        return "", ""


def wiki_search(q):
    try:
        r = requests.get(WIKI + "/w/index.php", params={"search": q, "ns0": 1, "fulltext": 1}, headers=UA, timeout=25)
        if "Special:Search" not in r.url and "/wiki/" in r.url:
            return urlparse(r.url).path
        a = BeautifulSoup(r.text, "lxml").select_one(".mw-search-result-heading a")
        return a["href"] if a and a.get("href") else None
    except Exception:
        return None


def wiki_context(keywords):
    for q in (" ".join(keywords[:2]), keywords[0] if keywords else ""):
        if not q:
            continue
        href = wiki_search(q)
        if href:
            tx, title = wiki_text(href)
            ss = sentences(tx, 400)
            if len(ss) >= 5:
                return {"title": title, "url": WIKI + href, "sentences": ss[:30]}
    return None


def wiki_events():
    out, now = [], datetime.utcnow()
    for back in range(4):
        d = now - timedelta(days=back)
        url = config.WIKI_EVENTS.format(y=d.year, m=MONTHS[d.month - 1], d=d.day)
        try:
            r = requests.get(url, headers=UA, timeout=25)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        s = BeautifulSoup(r.text, "lxml")
        for p in (s.find("div", class_="current-events-content") or s).find_all("p"):
            if "business and economy" not in p.get_text(" ").lower():
                continue
            ul = p.find_next_sibling("ul")
            if not ul:
                continue
            for li in ul.find_all("li"):
                if li.find("li"):
                    continue
                txt = re.sub(r"\([^)]*\)\s*$", "", clean(li.get_text(" "))).strip()
                if len(txt) < 50:
                    continue
                links = [a["href"] for a in li.find_all("a", href=True) if a["href"].startswith("/wiki/") and ":" not in a["href"]]
                out.append({"title": txt[:140], "link": f"{url}#{len(out)}", "summary": txt, "epoch": time.time() - back * 86400,
                            "source": "Wikipedia Current events", "wiki_links": links[:3]})
        if len(out) >= 6:
            break
    return out


def wiki_topic(hist):
    for e in [e for e in wiki_events() if not is_repeat(e, hist)]:
        arts = [{"source": e["source"], "title": e["title"], "link": e["link"], "summary": e["summary"], "image": None,
                 "epoch": e["epoch"], "sentences": sentences(e["summary"] + " ", 500) or [e["summary"]]}]
        for href in e["wiki_links"]:
            tx, t = wiki_text(href)
            if tx:
                arts.append({"source": "Wikipedia", "title": t, "link": WIKI + href, "summary": "", "image": None,
                             "epoch": e["epoch"], "sentences": sentences(tx, 400)[:25]})
        if sum(len(a["sentences"]) for a in arts) < 6:
            continue
        kws = [w for w, _ in Counter(w for a in arts for w in toks(a["title"])).most_common(6)]
        print("TOPIC (Wikipedia fallback):", e["title"])
        return {"headline": e["title"], "link": e["link"], "articles": arts, "keywords": kws, "wiki": wiki_context(kws),
                "pool": [], "date": fdate(e["epoch"])}
    raise NoFreshTopic("no unused business topic from RSS or Wikipedia")


# ---------- topic selection ----------
def _rss_topic(hist):
    entries = gather()
    if len(entries) < 6:
        raise RuntimeError("RSS weak")
    tl = [toks(e["title"]) for e in entries]
    now, scored = time.time(), []
    for i, e in enumerate(entries):
        if is_repeat(e, hist):
            continue
        pop = sum(1 for j, o in enumerate(entries) if j != i and o["source"] != e["source"] and jacc(tl[i], tl[j]) >= 0.3)
        scored.append((pop * 3 + max(0, 24 - (now - e["epoch"]) / 3600) / 6 + min(len(e["summary"]), 300) / 150, i))
    if not scored:
        raise RuntimeError("all RSS candidates already used")
    scored.sort(reverse=True)
    best = None
    for _, i in scored[:8]:
        rel, seen = [], set()
        for sim, j in sorted(((jacc(tl[i], tl[j]), j) for j in range(len(entries))), reverse=True):
            if sim >= 0.22 and entries[j]["link"] not in seen and not (j != i and is_repeat(entries[j], hist)):
                rel.append(entries[j])
                seen.add(entries[j]["link"])
            if len(rel) >= 8:
                break
        with cf.ThreadPoolExecutor(8) as ex:
            pages = list(ex.map(lambda e: article_page(e["link"]), rel))
        arts = []
        for e, (tx, og) in zip(rel, pages):
            ss = sentences(tx) or sentences(e["summary"] + " ")
            if ss:
                arts.append({"source": e["source"], "title": e["title"], "link": e["link"], "summary": e["summary"],
                             "image": e.get("image") or og, "epoch": e["epoch"], "sentences": ss[:40]})
        total = sum(len(a["sentences"]) for a in arts)
        if arts and (best is None or total > best[0]):
            best = (total, {"headline": entries[i]["title"], "link": entries[i]["link"], "articles": arts})
        if total >= 25:
            break
    if not best or best[0] < 6:
        raise RuntimeError("not enough article text")
    topic = best[1]
    topic["keywords"] = [w for w, _ in Counter(w for a in topic["articles"] for w in toks(a["title"])).most_common(6)]
    topic["wiki"] = wiki_context(topic["keywords"])
    topic["date"] = fdate(topic["articles"][0]["epoch"])
    topic["pool"] = [{"title": e["title"], "link": e["link"], "source": e["source"], "image": e["image"],
                      "tokens": sorted(toks(e["title"] + " " + e["summary"][:200]))} for e in entries if e.get("image")][:500]
    print("TOPIC (RSS):", topic["headline"], "| articles:", len(topic["articles"]), "| image pool:", len(topic["pool"]))
    return topic


def pick_topic(extra_titles=()):
    hist = load_history()
    for t in extra_titles:
        hist["items"].append(_item("yt:" + t[:60], t))
    try:
        return _rss_topic(hist)
    except Exception as e:
        print("RSS path failed:", e, "-> Wikipedia fallback")
        return wiki_topic(hist)
